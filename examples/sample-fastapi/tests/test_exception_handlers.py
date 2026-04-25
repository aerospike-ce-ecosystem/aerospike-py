"""Global Aerospike exception handler integration tests."""

from __future__ import annotations

from app.exception_handlers import _STATUS_MAP

import aerospike_py

NS, SET = "test", "exc_test"


def test_rust_panic_error_mapped_to_422():
    """Issue #280: a native Rust panic (e.g. legacy PYTHON_BLOB) surfaces
    as HTTP 422 so callers can distinguish it from a generic client
    error (502)."""
    assert aerospike_py.RustPanicError in _STATUS_MAP
    assert _STATUS_MAP[aerospike_py.RustPanicError] == 422


def test_get_nonexistent_user_returns_404(client):
    """RecordNotFound should be mapped to 404 by the global handler."""
    resp = client.get("/users/nonexistent_user_12345")
    assert resp.status_code == 404
    assert "KeyNotFoundError" in resp.json()["detail"] or "not found" in resp.json()["detail"].lower()


def test_delete_nonexistent_user_returns_404(client):
    """Remove on a missing record should also be 404 via global handler."""
    resp = client.delete("/users/nonexistent_user_12345")
    assert resp.status_code == 404


def test_get_nonexistent_record_returns_404(client):
    """A direct record get on a missing key should return 404."""
    resp = client.post(
        "/records/select",
        json={
            "key": {"namespace": NS, "set_name": SET, "key": "does_not_exist"},
            "bins": ["foo"],
        },
    )
    assert resp.status_code == 404
