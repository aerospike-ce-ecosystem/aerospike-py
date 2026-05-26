"""S1 — read-only batch_read endpoint.

Body: { "offset": int, "batch_size": int }
Returns:  { "found": int }

Why not echo back the records? — Two reasons:
  1) The two clients return different shapes (LazyBatchRecords vs list of
     (key, meta, bins)). Serialising the full payload would measure JSON
     encoding noise on top of batch_read.
  2) We want this endpoint to isolate the *DB round trip*, not response
     marshalling. Returning a count lets oha latency reflect read latency.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import key_for

router = APIRouter(prefix="/s1", tags=["s1"])


class ReadRequest(BaseModel):
    offset: int = 0
    batch_size: int = 50


class ReadResponse(BaseModel):
    found: int


def _materialise(result, client_name: str, batch_size: int) -> int:
    """Return how many records were found WITHOUT materialising bins.

    S1 is the "pure round trip" baseline — calling LazyBatchRecords.to_dict()
    here would trigger the full PyDict build that S2 measures. Use the
    pure-Rust filter+count on the aerospike-py side, and the per-record
    result_code check on the official side. Both count result_code == 0.
    """
    if client_name == "aerospike-py":
        return result.found_count()
    return sum(1 for br in result.batch_records if br.result == 0)


@router.post("/read", response_model=ReadResponse)
async def s1_read(req: ReadRequest, request: Request) -> ReadResponse:
    keys = [key_for(req.offset + i) for i in range(req.batch_size)]
    result = await request.app.state.client.batch_read(keys)
    found = _materialise(result, request.app.state.client_name, req.batch_size)
    return ReadResponse(found=found)
