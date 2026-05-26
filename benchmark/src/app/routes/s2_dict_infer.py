"""S2 — batch_read → dict iteration → torch tensor → DLRM forward.

Common pattern for FastAPI ML serving when the upstream call returns a dict
of dicts. Both clients pay a per-record Python dict access cost. The point
of comparison vs S3 is the materialisation path, not inference speed.
"""

from __future__ import annotations

import torch
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import key_for
from app.model import FEATURE_NAMES, infer

router = APIRouter(prefix="/s2", tags=["s2"])


class PredictRequest(BaseModel):
    offset: int = 0
    batch_size: int = 50


class PredictResponse(BaseModel):
    found: int
    pred_sum: float


@router.post("/predict", response_model=PredictResponse)
async def s2_predict(req: PredictRequest, request: Request) -> PredictResponse:
    keys = [key_for(req.offset + i) for i in range(req.batch_size)]
    client_name = request.app.state.client_name
    result = await request.app.state.client.batch_read(keys)

    rows: list[list[float]] = []
    found = 0
    if client_name == "aerospike-py":
        bins_by_key = result.to_dict()
        for k in keys:
            bins = bins_by_key.get(k[2])
            if bins is None:
                rows.append([0.0] * len(FEATURE_NAMES))
            else:
                found += 1
                rows.append([bins[name] for name in FEATURE_NAMES])
    else:
        # Official client (aerospike >= 19): batch_records is returned in
        # request order — verified against the live server, matches the
        # aerospike-py path positionally.
        for br in result.batch_records:
            if br.result == 0:
                found += 1
                bins = br.record[2]
                rows.append([bins[name] for name in FEATURE_NAMES])
            else:
                rows.append([0.0] * len(FEATURE_NAMES))

    matrix = torch.tensor(rows, dtype=torch.float32)
    preds = infer(matrix)
    return PredictResponse(found=found, pred_sum=float(preds.sum()))
