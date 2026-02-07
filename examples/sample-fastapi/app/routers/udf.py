from __future__ import annotations

from typing import Any

from aerospike_py import AsyncClient
from fastapi import APIRouter, Depends

from app.dependencies import get_client
from app.models import ApplyRequest, MessageResponse, UdfPutRequest

router = APIRouter(prefix="/udf", tags=["udf"])


@router.post("/modules", response_model=MessageResponse)
async def udf_put(body: UdfPutRequest, client: AsyncClient = Depends(get_client)):
    """Register a UDF module on the server."""
    await client.udf_put(body.filename, udf_type=body.udf_type)
    return MessageResponse(message=f"UDF module '{body.filename}' registered")


@router.delete("/modules/{module_name}", response_model=MessageResponse)
async def udf_remove(module_name: str, client: AsyncClient = Depends(get_client)):
    """Remove a UDF module from the server."""
    await client.udf_remove(module_name)
    return MessageResponse(message=f"UDF module '{module_name}' removed")


@router.post("/apply")
async def apply_udf(
    body: ApplyRequest, client: AsyncClient = Depends(get_client)
) -> Any:
    """Apply a UDF function to a record."""
    result = await client.apply(
        body.key.to_tuple(), body.module, body.function, args=body.args
    )
    return {"result": result}
