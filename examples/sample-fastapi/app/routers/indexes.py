from __future__ import annotations

from aerospike_py import AsyncClient
from fastapi import APIRouter, Depends

from app.dependencies import get_client
from app.models import IndexCreateRequest, MessageResponse

router = APIRouter(prefix="/indexes", tags=["indexes"])


@router.post("/integer", response_model=MessageResponse)
async def index_integer_create(
    body: IndexCreateRequest, client: AsyncClient = Depends(get_client)
):
    """Create a secondary index on an integer bin."""
    await client.index_integer_create(
        body.namespace, body.set_name, body.bin_name, body.index_name
    )
    return MessageResponse(message=f"Integer index '{body.index_name}' created")


@router.post("/string", response_model=MessageResponse)
async def index_string_create(
    body: IndexCreateRequest, client: AsyncClient = Depends(get_client)
):
    """Create a secondary index on a string bin."""
    await client.index_string_create(
        body.namespace, body.set_name, body.bin_name, body.index_name
    )
    return MessageResponse(message=f"String index '{body.index_name}' created")


@router.post("/geo2dsphere", response_model=MessageResponse)
async def index_geo2dsphere_create(
    body: IndexCreateRequest, client: AsyncClient = Depends(get_client)
):
    """Create a secondary index on a GeoJSON bin."""
    await client.index_geo2dsphere_create(
        body.namespace, body.set_name, body.bin_name, body.index_name
    )
    return MessageResponse(message=f"Geo2DSphere index '{body.index_name}' created")


@router.delete("/{namespace}/{index_name}", response_model=MessageResponse)
async def index_remove(
    namespace: str, index_name: str, client: AsyncClient = Depends(get_client)
):
    """Remove a secondary index."""
    await client.index_remove(namespace, index_name)
    return MessageResponse(message=f"Index '{index_name}' removed")
