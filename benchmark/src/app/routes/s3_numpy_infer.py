"""S3 — batch_read → numpy structured array → torch.from_numpy → DLRM.

For aerospike-py: ``LazyBatchRecords.to_numpy(dtype)`` fills a contiguous
structured array with the GIL released (``py.detach``). We view that as
``(batch, N)`` float32 — zero-copy — and pass it to torch.from_numpy.

For the official client: there is no equivalent. We allocate the matrix
upfront and copy each bin from per-record dicts. This isolates the
materialisation-path cost (S2 vs S3) for both clients on the same DB shape.
"""

from __future__ import annotations

import numpy as np
import torch
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import key_for
from app.model import FEATURE_NAMES, N_FEATURES, infer

router = APIRouter(prefix="/s3", tags=["s3"])

_DTYPE = np.dtype([(name, "<f4") for name in FEATURE_NAMES])


class PredictRequest(BaseModel):
    offset: int = 0
    batch_size: int = 50


class PredictResponse(BaseModel):
    found: int
    pred_sum: float


@router.post("/predict", response_model=PredictResponse)
async def s3_predict(req: PredictRequest, request: Request) -> PredictResponse:
    keys = [key_for(req.offset + i) for i in range(req.batch_size)]
    client_name = request.app.state.client_name
    result = await request.app.state.client.batch_read(keys)

    if client_name == "aerospike-py":
        np_batch = result.to_numpy(_DTYPE)
        matrix_np = np_batch.batch_records.view(np.float32).reshape(-1, N_FEATURES)
        found = int((np_batch.result_codes == 0).sum())
    else:
        matrix_np = np.zeros((req.batch_size, N_FEATURES), dtype=np.float32)
        found = 0
        for i, br in enumerate(result.batch_records):
            if br.result == 0:
                found += 1
                bins = br.record[2]
                for j, name in enumerate(FEATURE_NAMES):
                    matrix_np[i, j] = bins[name]

    tensor = torch.from_numpy(matrix_np)
    preds = infer(tensor)
    return PredictResponse(found=found, pred_sum=float(preds.sum()))
