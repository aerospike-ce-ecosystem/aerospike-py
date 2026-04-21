"""Observability — unified entry point for Tracing, Metrics, and Logging."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from serving.observability.metrics import configure_metrics
from serving.observability.nelo_logging import configure_logging, shutdown_logging
from serving.observability.tracing import configure_tracing, shutdown_tracing

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("serving.observability")


def configure_observability(app: FastAPI, service_name: str = "aerospike-benchmark") -> None:
    """Initialize all three observability pillars. Call once during lifespan."""
    configure_tracing(app, service_name)
    configure_metrics()
    configure_logging(service_name)
    logger.info("Observability stack initialized (tracing + metrics + logging)")


async def shutdown_observability() -> None:
    """Flush and shut down all observability components."""
    await shutdown_logging()
    await shutdown_tracing()
    logger.info("Observability stack shut down")
