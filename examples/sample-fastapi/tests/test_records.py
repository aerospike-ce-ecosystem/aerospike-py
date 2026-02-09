from __future__ import annotations


def _key_body(key: str, set_name: str = "demo"):
    return {"namespace": "test", "set_name": set_name, "key": key}


def test_select(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-select-1")
    aerospike_client.put(key, {"name": "Alice", "age": 30})
    cleanup.append(key)

    resp = client.post(
        "/records/select",
        json={"key": _key_body("rec-select-1"), "bins": ["name"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["bins"]["name"] == "Alice"
    assert "age" not in data["bins"]


def test_exists_found(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-exists-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post("/records/exists", json={"key": _key_body("rec-exists-1")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["meta"]["gen"] >= 1


def test_exists_not_found(client):
    resp = client.post("/records/exists", json={"key": _key_body("rec-notexist-xyz")})

    assert resp.status_code == 200
    assert resp.json()["exists"] is False


def test_touch(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-touch-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post("/records/touch", json={"key": _key_body("rec-touch-1"), "val": 300})

    assert resp.status_code == 200
    assert resp.json()["message"] == "Record touched"


def test_append(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-append-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/records/append",
        json={"key": _key_body("rec-append-1"), "bin": "name", "val": "_suffix"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "Value appended"
    # Verify side effect
    _, _, bins = aerospike_client.get(key)
    assert bins["name"] == "Alice_suffix"


def test_prepend(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-prepend-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/records/prepend",
        json={"key": _key_body("rec-prepend-1"), "bin": "name", "val": "prefix_"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "Value prepended"
    # Verify side effect
    _, _, bins = aerospike_client.get(key)
    assert bins["name"] == "prefix_Alice"


def test_increment(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-incr-1")
    aerospike_client.put(key, {"counter": 10})
    cleanup.append(key)

    resp = client.post(
        "/records/increment",
        json={"key": _key_body("rec-incr-1"), "bin": "counter", "offset": 5},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "Value incremented"
    # Verify side effect
    _, _, bins = aerospike_client.get(key)
    assert bins["counter"] == 15


def test_remove_bin(client, aerospike_client, cleanup):
    key = ("test", "demo", "rec-rmbin-1")
    aerospike_client.put(key, {"name": "Alice", "tmp": "removeme"})
    cleanup.append(key)

    resp = client.post(
        "/records/remove-bin",
        json={"key": _key_body("rec-rmbin-1"), "bin_names": ["tmp"]},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "Bins removed"
    # Verify side effect
    _, _, bins = aerospike_client.get(key)
    assert "tmp" not in bins
    assert bins["name"] == "Alice"
