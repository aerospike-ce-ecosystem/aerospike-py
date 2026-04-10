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
    """Read multiple records in a single batch call.

    Since v0.4.0, ``AsyncClient.batch_read()`` returns
    ``dict[UserKey, AerospikeRecord]`` — only successful reads are included.
    We reconstruct per-key results by checking dict membership.
    """
    keys = [k.to_tuple() for k in body.keys]
    result = await client.batch_read(keys, bins=body.bins)
    records = []
    for key_tuple in keys:
        user_key = key_tuple[2]
        if user_key in result:
            bins_dict = result[user_key]
            rec = RecordResponse(key=list(key_tuple), meta=None, bins=bins_dict)
            records.append(BatchRecordResponse(key=list(key_tuple), result=0, record=rec))
        else:
            records.append(BatchRecordResponse(key=list(key_tuple), result=2, record=None))
    return BatchRecordsResponse(batch_records=records)


@router.post("/operate", response_model=list[BatchRecordResponse])
async def batch_operate(body: BatchOperateRequest, client: AsyncClient = Depends(get_client)):
    """Execute operations on multiple records in a single batch call."""
    keys = [k.to_tuple() for k in body.keys]
    ops = [{"op": op.op, "bin": op.bin, "val": op.val} for op in body.ops]
    results = await client.batch_operate(keys, ops)
    records = []
    for br in results.batch_records:
        rec = None
        if br.record is not None:
            rec = RecordResponse(key=br.record.key, meta=br.record.meta, bins=br.record.bins)
        records.append(BatchRecordResponse(key=br.key, result=br.result, record=rec))
    return records


@router.post("/remove", response_model=MessageResponse)
async def batch_remove(body: BatchRemoveRequest, client: AsyncClient = Depends(get_client)):
    """Remove multiple records in a single batch call."""
    keys = [k.to_tuple() for k in body.keys]
    await client.batch_remove(keys)
    return MessageResponse(message=f"{len(keys)} records removed")
