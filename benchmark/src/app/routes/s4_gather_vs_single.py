"""S4 — fan-out gather vs collapsed single batch_read.

Two endpoints share the same effective key count (n_groups × per_group)
but split it differently:

* ``POST /s4/gather`` — N parallel batch_reads via ``asyncio.gather``.
  Each batch_read is its own DB round trip.
* ``POST /s4/single`` — the same keys concatenated into ONE batch_read call.

Same total work for the DB; the per-request fixed cost (serialise, socket
write, ack) is paid N× in gather and 1× in single. The point: aerospike-py
is native async so concurrent batch_reads truly overlap; the official
client serialises through ``asyncio.to_thread`` which makes gather more
expensive.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import key_for

router = APIRouter(prefix="/s4", tags=["s4"])


class FanoutRequest(BaseModel):
    offset: int = 0
    n_groups: int = 4
    per_group: int = 50


class FanoutResponse(BaseModel):
    found: int


def _count(result, client_name: str) -> int:
    if client_name == "aerospike-py":
        return result.found_count()
    return sum(1 for br in result.batch_records if br.result == 0)


@router.post("/gather", response_model=FanoutResponse)
async def s4_gather(req: FanoutRequest, request: Request) -> FanoutResponse:
    client = request.app.state.client
    client_name = request.app.state.client_name

    groups: list[list[tuple[str, str, str]]] = []
    for g in range(req.n_groups):
        start = req.offset + g * req.per_group
        groups.append([key_for(start + i) for i in range(req.per_group)])

    results = await asyncio.gather(*[client.batch_read(ks) for ks in groups])
    return FanoutResponse(found=sum(_count(r, client_name) for r in results))


@router.post("/single", response_model=FanoutResponse)
async def s4_single(req: FanoutRequest, request: Request) -> FanoutResponse:
    client = request.app.state.client
    client_name = request.app.state.client_name

    total = req.n_groups * req.per_group
    keys = [key_for(req.offset + i) for i in range(total)]
    result = await client.batch_read(keys)
    return FanoutResponse(found=_count(result, client_name))
