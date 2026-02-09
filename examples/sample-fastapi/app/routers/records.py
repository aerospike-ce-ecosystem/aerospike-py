from __future__ import annotations

from fastapi import APIRouter, Depends

from aerospike_py import AsyncClient
from app.dependencies import get_client
from app.models import (
    AppendPrependRequest,
    ExistsResponse,
    IncrementRequest,
    KeyRequest,
    MessageResponse,
    RecordResponse,
    RemoveBinRequest,
    SelectRequest,
    TouchRequest,
)

router = APIRouter(prefix="/records", tags=["records"])


@router.post("/select", response_model=RecordResponse)
async def select(body: SelectRequest, client: AsyncClient = Depends(get_client)):
    """Read specific bins from a record."""
    key, meta, bins = await client.select(body.key.to_tuple(), body.bins)
    return RecordResponse(key=key, meta=meta, bins=bins)


@router.post("/exists", response_model=ExistsResponse)
async def exists(body: KeyRequest, client: AsyncClient = Depends(get_client)):
    """Check if a record exists."""
    key, meta = await client.exists(body.key.to_tuple())
    return ExistsResponse(key=key, meta=meta, exists=meta is not None)


@router.post("/touch", response_model=MessageResponse)
async def touch(body: TouchRequest, client: AsyncClient = Depends(get_client)):
    """Touch a record (update TTL without changing bins)."""
    await client.touch(body.key.to_tuple(), val=body.val)
    return MessageResponse(message="Record touched")


@router.post("/append", response_model=MessageResponse)
async def append(body: AppendPrependRequest, client: AsyncClient = Depends(get_client)):
    """Append a string to a bin value."""
    await client.append(body.key.to_tuple(), body.bin, body.val)
    return MessageResponse(message="Value appended")


@router.post("/prepend", response_model=MessageResponse)
async def prepend(body: AppendPrependRequest, client: AsyncClient = Depends(get_client)):
    """Prepend a string to a bin value."""
    await client.prepend(body.key.to_tuple(), body.bin, body.val)
    return MessageResponse(message="Value prepended")


@router.post("/increment", response_model=MessageResponse)
async def increment(body: IncrementRequest, client: AsyncClient = Depends(get_client)):
    """Increment a numeric bin value."""
    await client.increment(body.key.to_tuple(), body.bin, body.offset)
    return MessageResponse(message="Value incremented")


@router.post("/remove-bin", response_model=MessageResponse)
async def remove_bin(body: RemoveBinRequest, client: AsyncClient = Depends(get_client)):
    """Remove specific bins from a record."""
    await client.remove_bin(body.key.to_tuple(), body.bin_names)
    return MessageResponse(message="Bins removed")
