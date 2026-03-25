from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

import aerospike_py
from app.dependencies import get_client
from app.models import LogLevelRequest

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Return Aerospike client metrics in Prometheus text format."""
    return PlainTextResponse(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics/status")
async def metrics_status():
    """Return whether metrics collection is currently enabled."""
    return {"metrics_enabled": aerospike_py.is_metrics_enabled()}


@router.post("/metrics/toggle")
async def toggle_metrics(enabled: bool = True):
    """Enable or disable metrics collection at runtime."""
    aerospike_py.set_metrics_enabled(enabled)
    return {"metrics_enabled": enabled}


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


@router.get("/ready")
async def readiness(client=Depends(get_client)):
    """Readiness probe — checks if the Aerospike client is connected."""
    connected = client.is_connected()
    if not connected:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"ready": False, "reason": "Aerospike client not connected"})
    return {"ready": True}
