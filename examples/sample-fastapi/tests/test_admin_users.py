from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Aerospike CE does not support security features")


def test_admin_create_user(client):
    resp = client.post(
        "/admin/users",
        json={"username": "newuser", "password": "secret", "roles": ["read-write"]},
    )
    assert resp.status_code == 201


def test_admin_drop_user(client):
    resp = client.delete("/admin/users/olduser")
    assert resp.status_code == 200


def test_admin_change_password(client):
    resp = client.put(
        "/admin/users/testuser/password",
        json={"password": "newpass"},
    )
    assert resp.status_code == 200


def test_admin_grant_roles(client):
    resp = client.post(
        "/admin/users/testuser/grant-roles",
        json={"roles": ["sys-admin", "read-write"]},
    )
    assert resp.status_code == 200


def test_admin_revoke_roles(client):
    resp = client.post(
        "/admin/users/testuser/revoke-roles",
        json={"roles": ["sys-admin"]},
    )
    assert resp.status_code == 200


def test_admin_query_user_info(client):
    resp = client.get("/admin/users/testuser")
    assert resp.status_code == 200


def test_admin_query_users_info(client):
    resp = client.get("/admin/users")
    assert resp.status_code == 200
