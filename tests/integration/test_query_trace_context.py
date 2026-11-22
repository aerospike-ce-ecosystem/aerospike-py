"""Check where the public query entry points capture the Python trace context."""

import asyncio
import contextvars
import os
import subprocess
import sys
import types
import uuid

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG


@pytest.mark.integration
def test_query_uses_the_executing_callers_trace_context():
    # The native tracer caches the Python propagator for the life of the process.
    run = subprocess.run(
        [sys.executable, "-m", __name__],
        env={
            **os.environ,
            "OTEL_SDK_DISABLED": "false",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_TRACES_SAMPLER": "always_off",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr


def check_context_capture():
    parent = contextvars.ContextVar("parent", default="create")
    seen = []

    def inject(carrier):
        seen.append(parent.get())
        # A valid, unsampled remote parent needs no collector.
        carrier["traceparent"] = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-00"

    package = types.ModuleType("opentelemetry")
    propagate = types.ModuleType("opentelemetry.propagate")
    propagate.inject = inject
    package.propagate = propagate
    sys.modules.update({"opentelemetry": package, "opentelemetry.propagate": propagate})
    set_name = f"querytrace_{uuid.uuid4().hex[:8]}"

    async def run_async():
        client = await aerospike_py.AsyncClient(AEROSPIKE_CONFIG).connect()
        try:
            parent.set("create")
            query = client.query("test", set_name)
            stream = query.stream()
            results, foreach = query.results(), query.foreach(lambda _: None)
            parent.set("async results")
            await results
            parent.set("async foreach")
            await foreach
            parent.set("first consumer")
            assert [row async for row in stream] == []
            parent.set("later consumer")
            assert [row async for row in stream] == []
        finally:
            await client.close()

    aerospike_py.init_tracing()
    try:
        client = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        try:
            query = client.query("test", set_name)
            parent.set("sync results")
            query.results()
            parent.set("sync foreach")
            query.foreach(lambda _: None)
        finally:
            client.close()
        asyncio.run(run_async())
        assert seen == ["sync results", "sync foreach", "async results", "async foreach", "first consumer"], seen
    finally:
        aerospike_py.shutdown_tracing()


if __name__ == "__main__":
    check_context_capture()
