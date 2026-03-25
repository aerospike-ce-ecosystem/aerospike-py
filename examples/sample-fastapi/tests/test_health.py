from __future__ import annotations

from unittest.mock import patch


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["aerospike_connected"] is True


def test_health_degraded_when_disconnected(client):
    """Health endpoint returns 503 when Aerospike client is not connected."""
    with patch.object(
        client.app.state.aerospike,
        "is_connected",
        return_value=False,
    ):
        resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["aerospike_connected"] is False


def test_readiness(client):
    """Readiness probe should report connected with at least one node."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["nodes"] >= 1
