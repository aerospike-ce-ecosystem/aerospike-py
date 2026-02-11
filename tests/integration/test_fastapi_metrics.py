"""FastAPI integration test: combine aerospike-py Rust metrics with Python prometheus_client."""

import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("prometheus_client")

from fastapi import FastAPI, Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest  # noqa: E402

import aerospike_py  # noqa: E402

app = FastAPI()

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "path"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["path"])
ACTIVE_CONNECTIONS = Gauge("active_connections", "Number of active connections")


@app.get("/metrics")
def metrics():
    python_metrics = generate_latest(REGISTRY).decode("utf-8")
    aerospike_metrics = aerospike_py.get_metrics()
    combined = python_metrics + "\n" + aerospike_metrics
    return Response(combined, media_type="text/plain; version=0.0.4")


@app.get("/users/{user_id}")
def get_user(user_id: int):
    REQUEST_COUNT.labels(method="GET", path="/users").inc()
    return {"user_id": user_id}


@app.post("/users")
def create_user():
    REQUEST_COUNT.labels(method="POST", path="/users").inc()
    return {"created": True}


# --- Basic Tests ---


def test_combined_metrics():
    client = TestClient(app)
    client.get("/users/1")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Python app metrics
    assert "http_requests_total" in body
    # Aerospike metrics header (present even without operations)
    assert "db_client_operation_duration" in body


def test_get_metrics_returns_string():
    text = aerospike_py.get_metrics()
    assert isinstance(text, str)
    assert "db_client_operation_duration" in text


# --- Prometheus Format Validation ---


def test_metrics_content_type():
    """Response Content-Type should be Prometheus text format."""
    client = TestClient(app)
    resp = client.get("/metrics")
    ct = resp.headers.get("content-type", "")
    assert "text/plain" in ct


def test_aerospike_metrics_has_help_and_type():
    """Aerospike metrics portion should contain HELP and TYPE headers."""
    text = aerospike_py.get_metrics()
    assert "# HELP db_client_operation_duration_seconds" in text
    assert "# TYPE db_client_operation_duration_seconds" in text


def test_aerospike_metrics_ends_with_eof():
    """OpenMetrics format requires # EOF at the end."""
    text = aerospike_py.get_metrics()
    assert text.strip().endswith("# EOF")


def test_combined_output_contains_both_help_sections():
    """Combined output should have HELP lines from both Python and Aerospike."""
    client = TestClient(app)
    client.get("/users/1")
    resp = client.get("/metrics")
    body = resp.text
    # Python prometheus_client HELP
    assert "# HELP http_requests_total" in body
    # Aerospike HELP
    assert "# HELP db_client_operation_duration_seconds" in body


# --- Multiple Scrapes ---


def test_multiple_scrapes_consistent():
    """Multiple /metrics requests should return consistent structure."""
    client = TestClient(app)
    resp1 = client.get("/metrics")
    resp2 = client.get("/metrics")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Both contain the same metric families
    for keyword in ["http_requests_total", "db_client_operation_duration_seconds"]:
        assert keyword in resp1.text
        assert keyword in resp2.text


def test_python_counter_increments_across_scrapes():
    """Python counter should reflect new requests between scrapes."""
    client = TestClient(app)
    # First scrape
    client.get("/users/1")
    resp1 = client.get("/metrics")
    # More requests
    client.get("/users/2")
    client.get("/users/3")
    resp2 = client.get("/metrics")

    # Extract counter values
    def extract_counter(body, label_method="GET"):
        for line in body.splitlines():
            if line.startswith("http_requests_total") and f'method="{label_method}"' in line:
                return float(line.split()[-1])
        return None

    v1 = extract_counter(resp1.text)
    v2 = extract_counter(resp2.text)
    assert v1 is not None
    assert v2 is not None
    assert v2 > v1


# --- Label Validation ---


def test_multiple_method_labels():
    """Different HTTP methods produce distinct counter label combinations."""
    client = TestClient(app)
    client.get("/users/1")
    client.post("/users")
    resp = client.get("/metrics")
    body = resp.text
    assert 'method="GET"' in body
    assert 'method="POST"' in body


# --- Aerospike Metric Structure ---


def test_aerospike_metric_valid_lines():
    """Each non-empty line in aerospike metrics should be a comment or metric sample."""
    text = aerospike_py.get_metrics()
    for line in text.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        assert stripped.startswith("#") or re.match(r"^[a-zA-Z_]", stripped), f"Invalid Prometheus line: {stripped!r}"


def test_aerospike_metric_name_convention():
    """Metric name should follow OTel DB client semantic convention."""
    text = aerospike_py.get_metrics()
    # Should use underscore-separated, lowercase naming
    assert "db_client_operation_duration_seconds" in text
    # Should NOT use dots (Prometheus convention)
    assert "db.client.operation.duration" not in text


# --- Edge Cases ---


def test_empty_metrics_endpoint_no_crash():
    """Metrics endpoint should work even if no app metrics were ever recorded."""
    # Create a fresh app with no recorded metrics (just the endpoint)
    fresh_app = FastAPI()

    @fresh_app.get("/metrics")
    def fresh_metrics():
        aerospike_text = aerospike_py.get_metrics()
        return Response(aerospike_text, media_type="text/plain; version=0.0.4")

    client = TestClient(fresh_app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "db_client_operation_duration_seconds" in resp.text


def test_get_metrics_no_side_effects():
    """Calling get_metrics() should not alter the metrics themselves."""
    before = aerospike_py.get_metrics()
    # Call many times
    for _ in range(100):
        aerospike_py.get_metrics()
    after = aerospike_py.get_metrics()
    # HELP/TYPE lines should be identical
    before_headers = [line for line in before.splitlines() if line.startswith("#")]
    after_headers = [line for line in after.splitlines() if line.startswith("#")]
    assert before_headers == after_headers
