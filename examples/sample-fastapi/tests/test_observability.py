"""Tests for observability endpoints (metrics, logging, tracing)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from contextlib import asynccontextmanager

import aerospike_py

# ── Metrics tests ─────────────────────────────────────────────


def test_metrics_endpoint(client):
    """GET /observability/metrics returns Prometheus text format."""
    resp = client.get("/observability/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# EOF" in body
    assert "db_client_operation_duration_seconds" in body


def test_metrics_after_operations(client, aerospike_client, cleanup):
    """Metrics reflect actual Aerospike operations."""
    key = ("test", "users", "metrics_test_key")
    cleanup.append(key)

    # Perform a put via the API
    client.post(
        "/users",
        json={"name": "MetricsUser", "email": "m@test.com", "age": 25},
    )

    resp = client.get("/observability/metrics")
    assert resp.status_code == 200
    body = resp.text
    # The put operation should have been recorded in the histogram
    assert "db_client_operation_duration_seconds" in body


# ── Log level tests ───────────────────────────────────────────


def test_log_level_change(client):
    """POST /observability/log-level changes log level."""
    resp = client.post("/observability/log-level", json={"level": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Log level set to DEBUG"


def test_log_level_all_levels(client):
    """All valid log levels (-1 to 4) are accepted."""
    level_names = {-1: "OFF", 0: "ERROR", 1: "WARN", 2: "INFO", 3: "DEBUG", 4: "TRACE"}
    for level, name in level_names.items():
        resp = client.post("/observability/log-level", json={"level": level})
        assert resp.status_code == 200
        assert resp.json()["message"] == f"Log level set to {name}"


def test_log_level_invalid(client):
    """Invalid log level values are rejected with 422."""
    resp = client.post("/observability/log-level", json={"level": 99})
    assert resp.status_code == 422

    resp = client.post("/observability/log-level", json={"level": -2})
    assert resp.status_code == 422


# ── Tracing status tests ─────────────────────────────────────


def test_tracing_status(client):
    """GET /observability/tracing-status returns current status."""
    resp = client.get("/observability/tracing-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "tracing_enabled" in data
    assert isinstance(data["tracing_enabled"], bool)


# ── Jaeger integration tests ─────────────────────────────────


def test_tracing_spans_sent_to_jaeger(aerospike_container, jaeger_container, aerospike_client, tmp_path):
    """Verify that Aerospike operations produce spans visible in Jaeger."""
    from app.main import app
    from fastapi.testclient import TestClient

    _, as_port = aerospike_container
    _, jaeger_otlp_port, jaeger_ui_port = jaeger_container

    service_name = "sample-fastapi-test"

    @asynccontextmanager
    async def _jaeger_lifespan(a):
        # Configure tracing to send to the test Jaeger instance
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"http://127.0.0.1:{jaeger_otlp_port}"
        os.environ["OTEL_SERVICE_NAME"] = service_name
        os.environ.pop("OTEL_SDK_DISABLED", None)

        aerospike_py.init_tracing()
        a.state.tracing_enabled = True

        ac = aerospike_py.AsyncClient(
            {
                "hosts": [("127.0.0.1", as_port)],
                "cluster_name": "docker",
                "policies": {"key": aerospike_py.POLICY_KEY_SEND},
            }
        )
        await ac.connect()
        a.state.aerospike = ac
        yield
        await ac.close()
        aerospike_py.shutdown_tracing()
        a.state.tracing_enabled = False

    original_lifespan = app.router.lifespan_context
    original_aerospike = getattr(app.state, "aerospike", None)
    original_tracing = getattr(app.state, "tracing_enabled", False)
    app.router.lifespan_context = _jaeger_lifespan

    try:
        with TestClient(app) as tc:
            # Perform operations that generate spans
            resp = tc.post(
                "/users",
                json={"name": "TracingUser", "email": "trace@test.com", "age": 30},
            )
            assert resp.status_code == 201
            user_id = resp.json()["user_id"]

            tc.get(f"/users/{user_id}")
            tc.delete(f"/users/{user_id}")

        # shutdown_tracing flushes spans; give Jaeger a moment to index
        time.sleep(3)

        # Query Jaeger API for our service's traces
        url = f"http://127.0.0.1:{jaeger_ui_port}/api/traces?service={service_name}&limit=10"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())

        assert "data" in data, f"Unexpected Jaeger response: {data}"
        traces = data["data"]
        assert len(traces) > 0, "No traces found in Jaeger for the test service"

        # Verify span attributes
        all_spans = []
        for trace in traces:
            all_spans.extend(trace.get("spans", []))

        assert len(all_spans) > 0, "No spans found in Jaeger traces"

        # Check that at least one span has the aerospike db.system.name tag
        found_aerospike_tag = False
        for span in all_spans:
            for tag in span.get("tags", []):
                if tag.get("key") == "db.system.name" and tag.get("value") == "aerospike":
                    found_aerospike_tag = True
                    break
            if found_aerospike_tag:
                break
        assert found_aerospike_tag, "No span with db.system.name=aerospike found"

    finally:
        app.router.lifespan_context = original_lifespan
        # Restore original app state so the session-scoped client fixture is not affected
        if original_aerospike is not None:
            app.state.aerospike = original_aerospike
        app.state.tracing_enabled = original_tracing
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        os.environ.pop("OTEL_SERVICE_NAME", None)
        # Re-initialize tracing with SDK disabled for remaining tests
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
