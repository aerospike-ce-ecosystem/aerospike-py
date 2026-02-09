from __future__ import annotations

from fastapi import APIRouter, Depends

from aerospike_py import AsyncClient
from app.dependencies import get_client
from app.models import (
    BatchOperateRequest,
    BatchReadRequest,
    BatchRecordResponse,
    BatchRecordsResponse,
    BatchRemoveRequest,
    MessageResponse,
    RecordResponse,
)

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/read", response_model=BatchRecordsResponse)
async def batch_read(body: BatchReadRequest, client: AsyncClient = Depends(get_client)):
    """Read multiple records in a single batch call."""
    keys = [k.to_tuple() for k in body.keys]
    result = await client.batch_read(keys, bins=body.bins)
    records = []
    for br in result.batch_records:
        rec = None
        if br.record is not None:
            k, m, b = br.record
            rec = RecordResponse(key=k, meta=m, bins=b)
        records.append(BatchRecordResponse(key=br.key, result=br.result, record=rec))
    return BatchRecordsResponse(batch_records=records)


@router.post("/operate", response_model=list[RecordResponse])
async def batch_operate(body: BatchOperateRequest, client: AsyncClient = Depends(get_client)):
    """Execute operations on multiple records in a single batch call."""
    keys = [k.to_tuple() for k in body.keys]
    ops = [{"op": op.op, "bin": op.bin, "val": op.val} for op in body.ops]
    results = await client.batch_operate(keys, ops)
    return [RecordResponse(key=k, meta=m, bins=b) for k, m, b in results]


@router.post("/remove", response_model=MessageResponse)
async def batch_remove(body: BatchRemoveRequest, client: AsyncClient = Depends(get_client)):
    """Remove multiple records in a single batch call."""
    keys = [k.to_tuple() for k in body.keys]
    await client.batch_remove(keys)
    return MessageResponse(message=f"{len(keys)} records removed")
