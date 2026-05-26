"""FastAPI lifespan: pick client by CLIENT env, connect once, attach to state."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.official_async import OfficialAsyncBench
from app.clients.py_async import PyAsyncBench
from app.config import AEROSPIKE_HOST, AEROSPIKE_PORT, CLIENT_KIND


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CLIENT_KIND == "py":
        client = PyAsyncBench(AEROSPIKE_HOST, AEROSPIKE_PORT)
        await client.connect()
    elif CLIENT_KIND == "official":
        client = OfficialAsyncBench(AEROSPIKE_HOST, AEROSPIKE_PORT)
    else:
        raise RuntimeError(f"Unknown CLIENT={CLIENT_KIND!r}; expected 'py' or 'official'")

    app.state.client = client
    app.state.client_name = client.name
    try:
        yield
    finally:
        await client.close()
