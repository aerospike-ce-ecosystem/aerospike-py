from __future__ import annotations

from fastapi import APIRouter, Depends

from aerospike_py import AsyncClient
from app.dependencies import get_client

router = APIRouter(prefix="/cluster", tags=["cluster"])


@router.get("/connected")
async def is_connected(client: AsyncClient = Depends(get_client)):
    """Check if the client is connected to the Aerospike cluster."""
    return {"connected": client.is_connected()}


@router.get("/nodes")
async def get_node_names(client: AsyncClient = Depends(get_client)):
    """Get the list of cluster node names."""
    nodes = await client.get_node_names()
    return {"nodes": nodes}
