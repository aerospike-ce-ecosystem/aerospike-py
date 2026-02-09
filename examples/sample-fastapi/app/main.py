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
    operations,
    records,
    truncate,
    udf,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage AsyncClient lifecycle — connect on startup, close on shutdown."""
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


@app.get("/health")
async def health():
    return {"status": "ok"}
