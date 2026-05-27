"""FastAPI lifespan: pick client by CLIENT env, connect once, attach to state."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # CLIENT_KIND is also validated at import time in config.py — this branch
    # is just the dispatch.
    if CLIENT_KIND == "py":
        client = PyAsyncBench(
            AEROSPIKE_HOST,
            AEROSPIKE_PORT,
            cluster_name=AEROSPIKE_CLUSTER_NAME,
            max_concurrent_operations=AEROSPIKE_MAX_CONCURRENT_OPS,
        )
    else:  # "official"
        client = OfficialAsyncBench(
            AEROSPIKE_HOST,
            AEROSPIKE_PORT,
            cluster_name=AEROSPIKE_CLUSTER_NAME,
        )

    # On connect failure log the env we tried, then best-effort close so a
    # partial connect (TCP open + cluster-info hang) doesn't leak the Tokio
    # runtime / C tend thread before the asyncio loop unwinds.
    try:
        await client.connect()
    except BaseException:
        logger.exception(
            "lifespan startup connect failed: CLIENT=%s host=%s:%s cluster=%s",
            CLIENT_KIND,
            AEROSPIKE_HOST,
            AEROSPIKE_PORT,
            AEROSPIKE_CLUSTER_NAME,
        )
        try:
            await client.close()
        except Exception:
            logger.exception("close() during failed-startup cleanup raised")
        raise

    app.state.client = client
    app.state.client_name = client.name
    try:
        yield
    finally:
        await client.close()
