import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import aerospike_py
from aerospike_py import AsyncClient
from app.config import settings
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

    # Tracing (reads OTEL_EXPORTER_OTLP_ENDPOINT env var)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_endpoint)
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)
    aerospike_py.init_tracing()
    app.state.tracing_enabled = True

    # Aerospike client
    client = AsyncClient(
        {
            "hosts": [(settings.aerospike_host, settings.aerospike_port)],
            "policies": {"key": aerospike_py.POLICY_KEY_SEND},
        }
    )
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
    return {"status": "ok"}
