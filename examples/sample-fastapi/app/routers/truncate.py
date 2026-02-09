from __future__ import annotations

from fastapi import APIRouter, Depends

from aerospike_py import AsyncClient
from app.dependencies import get_client
from app.models import MessageResponse, TruncateRequest

router = APIRouter(prefix="/truncate", tags=["truncate"])


@router.post("", response_model=MessageResponse)
async def truncate(body: TruncateRequest, client: AsyncClient = Depends(get_client)):
    """Truncate all records in a namespace/set."""
    await client.truncate(body.namespace, body.set_name, nanos=body.nanos)
    return MessageResponse(message=f"Truncated {body.namespace}/{body.set_name}")
