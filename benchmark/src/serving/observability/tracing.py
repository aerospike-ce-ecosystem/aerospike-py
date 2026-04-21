"""OpenTelemetry distributed tracing — exports to Tempo via OTLP/gRPC.

Initialization order matters:
1. Python TracerProvider + OTLPSpanExporter (gRPC)
2. W3C TraceContext propagator
3. aerospike_py.init_tracing() — Rust-side provider (same OTEL_* env vars)
4. FastAPIInstrumentor
5. AerospikeInstrumentor (official C client)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import aerospike_py

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("serving.observability")

_provider: TracerProvider | None = None


def _is_otel_disabled() -> bool:
    return os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true"


def configure_tracing(app: FastAPI, service_name: str = "aerospike-benchmark") -> None:
    """Initialize all tracing components. Call once during FastAPI lifespan."""
    global _provider

    if _is_otel_disabled():
        logger.info("OTEL_SDK_DISABLED=true — skipping tracing initialization")
        return

    # -- 1. Python TracerProvider ------------------------------------------
    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", service_name),
            "service.namespace": os.environ.get("OTEL_SERVICE_NAMESPACE", "mona-adagent"),
            "service.version": "0.2.0",
        }
    )
    _provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT env var
    _provider.add_span_processor(BatchSpanProcessor(exporter))
    trace_api.set_tracer_provider(_provider)

    # -- 2. W3C propagator -------------------------------------------------
    set_global_textmap(TraceContextTextMapPropagator())

    # -- 3. Rust-side tracing (aerospike_py) --------------------------------
    aerospike_py.init_tracing()

    # -- 4. FastAPI auto-instrumentation -----------------------------------
    FastAPIInstrumentor.instrument_app(app)

    # -- 5. Official Aerospike C client instrumentation --------------------
    try:
        from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor

        AerospikeInstrumentor().instrument()
    except ImportError:
        logger.info("opentelemetry-instrumentation-aerospike not installed — skipping official client instrumentation")

    logger.info("Tracing initialized (OTLP/gRPC → Tempo)")


async def shutdown_tracing() -> None:
    """Flush and shut down all tracing providers."""
    if _is_otel_disabled():
        return

    # Rust spans first — they may reference Python parent spans
    try:
        aerospike_py.shutdown_tracing()
    except Exception:
        logger.warning("Failed to shut down Rust tracing", exc_info=True)

    if _provider is not None:
        _provider.shutdown()

    logger.info("Tracing shut down")
