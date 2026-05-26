"""FastAPI lifespan: pick client by CLIENT env, connect once, attach to state."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.official_async import OfficialAsyncBench
from app.clients.py_async import PyAsyncBench
from app.config import (
    AEROSPIKE_CLUSTER_NAME,
    AEROSPIKE_HOST,
    AEROSPIKE_MAX_CONCURRENT_OPS,
    AEROSPIKE_PORT,
    CLIENT_KIND,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CLIENT_KIND == "py":
        client = PyAsyncBench(
            AEROSPIKE_HOST,
            AEROSPIKE_PORT,
            cluster_name=AEROSPIKE_CLUSTER_NAME,
            max_concurrent_operations=AEROSPIKE_MAX_CONCURRENT_OPS,
        )
    elif CLIENT_KIND == "official":
        client = OfficialAsyncBench(
            AEROSPIKE_HOST,
            AEROSPIKE_PORT,
            cluster_name=AEROSPIKE_CLUSTER_NAME,
        )
    else:
        raise RuntimeError(f"Unknown CLIENT={CLIENT_KIND!r}; expected 'py' or 'official'")

    await client.connect()
    app.state.client = client
    app.state.client_name = client.name
    try:
        yield
    finally:
        await client.close()
