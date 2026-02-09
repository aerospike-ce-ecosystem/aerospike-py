from __future__ import annotations

from fastapi import Request

from aerospike_py import AsyncClient


def get_client(request: Request) -> AsyncClient:
    """Shared dependency to retrieve the AsyncClient from app state."""
    return request.app.state.aerospike
