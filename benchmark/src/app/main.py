"""FastAPI app factory.

Run with one of:
    CLIENT=py        uv run uvicorn app.main:app --workers 1
    CLIENT=official  uv run uvicorn app.main:app --workers 1
"""

from __future__ import annotations

from fastapi import FastAPI

from app.lifespan import lifespan
from app.routes import (
    s1_read_only,
    s2_dict_infer,
    s3_numpy_infer,
    s4_gather_vs_single,
    s5_lazy_subset,
)


def create_app() -> FastAPI:
    app = FastAPI(title="aerospike-py-benchmark", lifespan=lifespan)
    app.include_router(s1_read_only.router)
    app.include_router(s2_dict_infer.router)
    app.include_router(s3_numpy_infer.router)
    app.include_router(s4_gather_vs_single.router)
    app.include_router(s5_lazy_subset.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "client": app.state.client_name}

    return app


app = create_app()
