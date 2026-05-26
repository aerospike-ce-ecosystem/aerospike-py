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
    """Force materialisation and return how many records were found.

    Same work for both clients so the count step doesn't bias either side.
    """
    if client_name == "aerospike-py":
        # LazyBatchRecords → dict of {user_key_str: bins or None}
        return sum(1 for v in result.to_dict().values() if v is not None)
    # Official client (>= 19): BatchRecords.batch_records is list[BatchRecord].
    # br.result == 0 means OK; non-zero (e.g. 2 = KEY_NOT_FOUND) means missing.
    return sum(1 for br in result.batch_records if br.result == 0)


@router.post("/read", response_model=ReadResponse)
async def s1_read(req: ReadRequest, request: Request) -> ReadResponse:
    keys = [key_for(req.offset + i) for i in range(req.batch_size)]
    result = await request.app.state.client.batch_read(keys)
    found = _materialise(result, request.app.state.client_name, req.batch_size)
    return ReadResponse(found=found)
