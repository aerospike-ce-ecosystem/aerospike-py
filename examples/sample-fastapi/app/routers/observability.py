from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

import aerospike_py
from app.models import LogLevelRequest

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Return Aerospike client metrics in Prometheus text format."""
    return PlainTextResponse(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.post("/log-level")
async def set_log_level(body: LogLevelRequest):
    """Change the aerospike-py log level at runtime."""
    aerospike_py.set_log_level(body.level)
    level_names = {-1: "OFF", 0: "ERROR", 1: "WARN", 2: "INFO", 3: "DEBUG", 4: "TRACE"}
    return {"message": f"Log level set to {level_names.get(body.level, str(body.level))}"}


@router.get("/tracing-status")
async def tracing_status(request: Request):
    """Return the current tracing initialization status."""
    enabled = getattr(request.app.state, "tracing_enabled", False)
    return {"tracing_enabled": enabled}
