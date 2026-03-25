import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import aerospike_py
from aerospike_py import AsyncClient
from app.config import settings
from app.exception_handlers import register_exception_handlers
from app.routers import (
    admin_roles,
    admin_users,
    batch,
    cluster,
    indexes,
    numpy_batch,
    observability,
    operations,
    records,
    truncate,
    udf,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage AsyncClient lifecycle and observability — connect on startup, close on shutdown."""
    # Logging
    aerospike_py.set_log_level(settings.log_level)

    # Metrics
    aerospike_py.set_metrics_enabled(settings.metrics_enabled)

    # Tracing (reads OTEL_EXPORTER_OTLP_ENDPOINT env var)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_endpoint)
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)
    aerospike_py.init_tracing()
    app.state.tracing_enabled = True

    # Aerospike client with backpressure config
    config: dict = {
        "hosts": [(settings.aerospike_host, settings.aerospike_port)],
        "policies": {"key": aerospike_py.POLICY_KEY_SEND},
    }
    if settings.max_concurrent_ops > 0:
        config["max_concurrent_operations"] = settings.max_concurrent_ops
        config["backpressure_timeout_ms"] = settings.backpressure_timeout_ms

    client = AsyncClient(config)
    await client.connect()
    app.state.aerospike = client

    yield

    await client.close()
    aerospike_py.shutdown_tracing()
    app.state.tracing_enabled = False


app = FastAPI(
    title="aerospike-py FastAPI Example",
    description="Sample CRUD API backed by Aerospike using the async client",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(users.router)
app.include_router(records.router)
app.include_router(operations.router)
app.include_router(batch.router)
app.include_router(numpy_batch.router)
app.include_router(indexes.router)
app.include_router(truncate.router)
app.include_router(udf.router)
app.include_router(admin_users.router)
app.include_router(admin_roles.router)
app.include_router(cluster.router)
app.include_router(observability.router)


@app.get("/health")
async def health():
    """Liveness probe — always returns ok."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness():
    """Readiness probe — verifies Aerospike cluster connectivity."""
    client: AsyncClient | None = getattr(app.state, "aerospike", None)
    if client is None or not client.is_connected():
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "aerospike client not connected"},
        )
    try:
        nodes = client.get_node_names()
        return {"status": "ready", "nodes": len(nodes)}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": str(e)},
        )
