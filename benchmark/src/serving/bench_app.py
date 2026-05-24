"""Standalone FastAPI app for the GIL-detach load test.

A minimal sibling of `serving.app` that brings up *only* the aerospike-py
AsyncClient plus a tiny linear "model" — no official C client, no DLRM,
no OTel pipeline. The point is to measure the dict-vs-numpy
materialisation difference under a real ASGI worker pool when an HTTP
load tester (``oha``) drives concurrent requests, without unrelated
fixtures dominating the timing.

Run:
    AEROSPIKE_HOSTS=127.0.0.1:18710 \\
    PYTHONPATH=src \\
    uv run uvicorn serving.bench_app:app --host 0.0.0.0 --port 8000

Seed first:
    AEROSPIKE_PORT=18710 uv run python -m serving.bench_seed
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import aerospike_py
from serving.endpoints import bench

logger = logging.getLogger("serving.bench_app")


def _parse_hosts() -> list[tuple[str, int]]:
    raw = os.environ.get("AEROSPIKE_HOSTS", "127.0.0.1:18710")
    out: list[tuple[str, int]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        host, _, port = entry.partition(":")
        out.append((host, int(port) if port else 3000))
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    hosts = _parse_hosts()
    logger.info("Connecting aerospike-py AsyncClient to %s", hosts)
    # Use library defaults — explicit `max_concurrent_operations` caused
    # the local single-node cluster to refuse validation under load.
    client = aerospike_py.AsyncClient(
        {
            "hosts": hosts,
            "cluster_name": os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker"),
        },
    )
    await client.connect()
    app.state.py_client = client
    logger.info("Connected.")
    try:
        yield
    finally:
        await client.close()


app = FastAPI(title="aerospike-py GIL-detach bench", lifespan=lifespan)
app.include_router(bench.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
