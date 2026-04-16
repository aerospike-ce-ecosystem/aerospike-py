"""FastAPI application with dual Aerospike client lifespan + DLRM model."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from serving.aerospike_clients import create_official_client, create_py_async_client
from serving.config import MAX_CONCURRENT_OPS
from serving.endpoints import health, predict
from serving.model import create_model
from serving.observability import configure_observability, shutdown_observability

logger = logging.getLogger("serving")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DLRM model
    logger.info("Loading DLRM model...")
    model = create_model()
    app.state.model = model
    logger.info("DLRM model loaded and warmed up.")

    # 2. Official aerospike C client (async wrapper)
    logger.info("Connecting official Aerospike C client...")
    app.state.official_client = await create_official_client()
    logger.info("Official client connected.")

    # 3. aerospike-py AsyncClient (native async)
    logger.info("Connecting aerospike-py AsyncClient...")
    app.state.py_client = await create_py_async_client(
        max_concurrent_ops=MAX_CONCURRENT_OPS,
    )
    logger.info("aerospike-py client connected.")

    # 4. Observability (tracing + metrics + logging)
    configure_observability(app)

    yield

    # Shutdown
    logger.info("Shutting down...")
    await shutdown_observability()
    await app.state.py_client.close()
    await app.state.official_client.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Aerospike Benchmark API",
    description="Compare aerospike-py vs official C client with DLRM inference",
    lifespan=lifespan,
)

app.include_router(predict.router)
app.include_router(health.router)
