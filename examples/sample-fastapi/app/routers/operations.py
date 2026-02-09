from __future__ import annotations

from fastapi import APIRouter, Depends

from aerospike_py import AsyncClient
from app.dependencies import get_client
from app.models import OperateOrderedResponse, OperateRequest, RecordResponse

router = APIRouter(prefix="/operations", tags=["operations"])


def _build_ops(ops_input):
    """Convert OperationInput list to Aerospike operation dicts."""
    return [{"op": op.op, "bin": op.bin, "val": op.val} for op in ops_input]


def _build_meta(meta_input):
    """Convert MetadataInput to dict if provided."""
    if meta_input is None:
        return None
    m = {}
    if meta_input.gen is not None:
        m["gen"] = meta_input.gen
    if meta_input.ttl is not None:
        m["ttl"] = meta_input.ttl
    return m or None


@router.post("/operate", response_model=RecordResponse)
async def operate(body: OperateRequest, client: AsyncClient = Depends(get_client)):
    """Execute multiple operations on a single record."""
    ops = _build_ops(body.ops)
    meta = _build_meta(body.meta)
    key, result_meta, bins = await client.operate(body.key.to_tuple(), ops, meta=meta)
    return RecordResponse(key=key, meta=result_meta, bins=bins)


@router.post("/operate-ordered", response_model=OperateOrderedResponse)
async def operate_ordered(body: OperateRequest, client: AsyncClient = Depends(get_client)):
    """Execute multiple operations on a single record, returning results in operation order."""
    ops = _build_ops(body.ops)
    meta = _build_meta(body.meta)
    _, result_meta, ordered_bins = await client.operate_ordered(body.key.to_tuple(), ops, meta=meta)
    return OperateOrderedResponse(
        meta=result_meta,
        ordered_bins=[[b, v] for b, v in ordered_bins],
    )
