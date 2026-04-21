"""Health, readiness, and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response

from serving.observability.metrics import get_metrics_text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus scrape endpoint — combines Python + Rust metrics."""
    body = get_metrics_text()
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
