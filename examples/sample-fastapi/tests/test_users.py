from __future__ import annotations


def test_create_user(client, cleanup):
    resp = client.post("/users", json={"name": "Alice", "email": "alice@example.com", "age": 30})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert data["age"] == 30
    assert data["generation"] == 1
    # Clean up via API
    user_id = data["user_id"]
    client.delete(f"/users/{user_id}")


def test_get_user(client, aerospike_client, cleanup):
    key = ("test", "users", "get-u1")
    aerospike_client.put(key, {"name": "Bob", "email": "bob@example.com", "age": 25})
    cleanup.append(key)

    resp = client.get("/users/get-u1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "get-u1"
    assert data["name"] == "Bob"
    assert data["generation"] == 1


def test_get_user_not_found(client):
    resp = client.get("/users/nonexistent-user-xyz")

    assert resp.status_code == 404


def test_update_user(client, aerospike_client, cleanup):
    key = ("test", "users", "upd-u1")
    aerospike_client.put(key, {"name": "Old", "email": "a@b.com", "age": 20})
    cleanup.append(key)

    resp = client.put("/users/upd-u1", json={"name": "New"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_update_user_no_fields(client, aerospike_client, cleanup):
    key = ("test", "users", "upd-empty")
    aerospike_client.put(key, {"name": "X", "email": "x@x.com", "age": 1})
    cleanup.append(key)

    resp = client.put("/users/upd-empty", json={})

    assert resp.status_code == 422
    assert "No fields to update" in resp.json()["detail"]


def test_update_user_not_found(client):
    resp = client.put("/users/nonexistent-upd-xyz", json={"name": "New"})

    assert resp.status_code == 404


def test_delete_user(client, aerospike_client, cleanup):
    key = ("test", "users", "del-u1")
    aerospike_client.put(key, {"name": "ToDelete", "email": "d@b.com", "age": 30})
    # No cleanup needed — we're deleting via API

    resp = client.delete("/users/del-u1")

    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"]


def test_delete_user_not_found(client):
    # aerospike-py remove() raises RecordNotFound for non-existent keys,
    # so the router returns 404.
    resp = client.delete("/users/nonexistent-del-xyz")

    assert resp.status_code == 404


def test_list_users(client, cleanup):
    # Create via API so user_id is stored in bins for scan identification.
    r1 = client.post("/users", json={"name": "Alice", "email": "a@b.com", "age": 30})
    r2 = client.post("/users", json={"name": "Bob", "email": "b@b.com", "age": 25})
    assert r1.status_code == 201
    assert r2.status_code == 201
    cleanup.extend(
        [
            ("test", "users", r1.json()["user_id"]),
            ("test", "users", r2.json()["user_id"]),
        ]
    )

    resp = client.get("/users")

    assert resp.status_code == 200
    data = resp.json()
    names = [u["name"] for u in data]
    assert "Alice" in names
    assert "Bob" in names
