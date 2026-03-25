"""Global Aerospike exception handler integration tests."""

from __future__ import annotations

NS, SET = "test", "exc_test"


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
