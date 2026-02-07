from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Aerospike CE does not support security features")


def test_admin_create_role(client):
    resp = client.post(
        "/admin/roles",
        json={
            "role": "custom-role",
            "privileges": [{"code": 10, "ns": "test", "set": ""}],
        },
    )
    assert resp.status_code == 201


def test_admin_create_role_minimal(client):
    resp = client.post(
        "/admin/roles",
        json={
            "role": "min-role",
            "privileges": [{"code": 10, "ns": "test", "set": ""}],
        },
    )
    assert resp.status_code == 201


def test_admin_drop_role(client):
    resp = client.delete("/admin/roles/custom-role")
    assert resp.status_code == 200


def test_admin_grant_privileges(client):
    resp = client.post(
        "/admin/roles/custom-role/grant-privileges",
        json={"privileges": [{"code": 10, "ns": "test", "set": ""}]},
    )
    assert resp.status_code == 200


def test_admin_revoke_privileges(client):
    resp = client.post(
        "/admin/roles/custom-role/revoke-privileges",
        json={"privileges": [{"code": 10, "ns": "test", "set": ""}]},
    )
    assert resp.status_code == 200


def test_admin_query_role(client):
    resp = client.get("/admin/roles/custom-role")
    assert resp.status_code == 200


def test_admin_query_roles(client):
    resp = client.get("/admin/roles")
    assert resp.status_code == 200


def test_admin_set_whitelist(client):
    resp = client.put(
        "/admin/roles/custom-role/whitelist",
        json={"whitelist": ["10.0.0.0/8"]},
    )
    assert resp.status_code == 200


def test_admin_set_quotas(client):
    resp = client.put(
        "/admin/roles/custom-role/quotas",
        json={"read_quota": 2000, "write_quota": 1000},
    )
    assert resp.status_code == 200
