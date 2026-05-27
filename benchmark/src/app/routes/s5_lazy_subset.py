"""S5 — partial materialisation downstream of batch_read.

Both clients receive the full bin set on the wire (no bin projection at
the request level — that's a separate, server-side optimisation we don't
want to conflate here). The difference is what the *client library*
forces you to materialise on the Python side before you can read any
field:

* **aerospike-py**: ``LazyBatchRecords`` defers conversion entirely. We
  ask ``.to_numpy(subset_dtype)`` for only 8 of the 64 fields — the Rust
  side fills exactly those columns with the GIL released. The remaining
  56 fields are never materialised into Python.
* **Official client**: ``BatchRecord.record[2]`` is a fully-materialised
  Python dict containing every bin. Reading 8 fields still pays the cost
  of building the dict for all 64.

Hence S5 measures the value of the "lazy" in LazyBatchRecords when
downstream code only consumes a subset of bins.
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import key_for

router = APIRouter(prefix="/s5", tags=["s5"])

_SUBSET_FIELDS = [f"f{i}" for i in range(8)]
_SUBSET_DTYPE = np.dtype([(name, "<f4") for name in _SUBSET_FIELDS])


class SubsetRequest(BaseModel):
    offset: int = 0
    batch_size: int = 50


class SubsetResponse(BaseModel):
    found: int
    subset_sum: float


@router.post("/subset", response_model=SubsetResponse)
async def s5_subset(req: SubsetRequest, request: Request) -> SubsetResponse:
    client = request.app.state.client
    client_name = request.app.state.client_name

    keys = [key_for(req.offset + i) for i in range(req.batch_size)]
    result = await client.batch_read(keys)

    if client_name == "aerospike-py":
        np_batch = result.to_numpy(_SUBSET_DTYPE)
        matrix = np_batch.batch_records.view(np.float32).reshape(-1, len(_SUBSET_FIELDS))
        found = int((np_batch.result_codes == 0).sum())
        subset_sum = float(matrix.sum())
    else:
        found = 0
        total = 0.0
        for br in result.batch_records:
            if br.result == 0:
                found += 1
                bins = br.record[2]
                for name in _SUBSET_FIELDS:
                    total += bins[name]
        subset_sum = total

    return SubsetResponse(found=found, subset_sum=subset_sum)
