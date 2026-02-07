from __future__ import annotations

from aerospike_py import AsyncClient
from fastapi import Request


def get_client(request: Request) -> AsyncClient:
    """Shared dependency to retrieve the AsyncClient from app state."""
    return request.app.state.aerospike
