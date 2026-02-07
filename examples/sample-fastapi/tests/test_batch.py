from __future__ import annotations

import aerospike_py


def _key_body(key: str):
    return {"namespace": "test", "set_name": "demo", "key": key}


def test_batch_read(client, aerospike_client, cleanup):
    k1 = ("test", "demo", "batch-r1")
    k2 = ("test", "demo", "batch-r2")
    aerospike_client.put(k1, {"name": "Alice"})
    aerospike_client.put(k2, {"name": "Bob"})
    cleanup.extend([k1, k2])

    resp = client.post(
        "/batch/read",
        json={"keys": [_key_body("batch-r1"), _key_body("batch-r2")]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["batch_records"]) == 2
    records = data["batch_records"]
    names = {r["record"]["bins"]["name"] for r in records if r["record"]}
    assert names == {"Alice", "Bob"}


def test_batch_read_with_bins(client, aerospike_client, cleanup):
    k1 = ("test", "demo", "batch-rb1")
    aerospike_client.put(k1, {"name": "Alice", "age": 30})
    cleanup.append(k1)

    resp = client.post(
        "/batch/read",
        json={"keys": [_key_body("batch-rb1")], "bins": ["name"]},
    )

    assert resp.status_code == 200
    record = resp.json()["batch_records"][0]["record"]
    assert record["bins"]["name"] == "Alice"


def test_batch_read_partial_not_found(client, aerospike_client, cleanup):
    k1 = ("test", "demo", "batch-pnf1")
    aerospike_client.put(k1, {"name": "Alice"})
    cleanup.append(k1)

    resp = client.post(
        "/batch/read",
        json={"keys": [_key_body("batch-pnf1"), _key_body("batch-notexist-xyz")]},
    )

    assert resp.status_code == 200
    data = resp.json()
    records = data["batch_records"]
    assert records[0]["record"] is not None
    assert records[1]["record"] is None
    assert records[1]["result"] == 2  # KEY_NOT_FOUND


def test_batch_operate(client, aerospike_client, cleanup):
    k1 = ("test", "demo", "batch-op1")
    k2 = ("test", "demo", "batch-op2")
    aerospike_client.put(k1, {"counter": 10})
    aerospike_client.put(k2, {"counter": 20})
    cleanup.extend([k1, k2])

    resp = client.post(
        "/batch/operate",
        json={
            "keys": [_key_body("batch-op1"), _key_body("batch-op2")],
            "ops": [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1}],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_batch_remove(client, aerospike_client, cleanup):
    k1 = ("test", "demo", "batch-rm1")
    k2 = ("test", "demo", "batch-rm2")
    aerospike_client.put(k1, {"name": "Alice"})
    aerospike_client.put(k2, {"name": "Bob"})
    # No cleanup needed — removing via API

    resp = client.post(
        "/batch/remove",
        json={"keys": [_key_body("batch-rm1"), _key_body("batch-rm2")]},
    )

    assert resp.status_code == 200
    assert "2 records removed" in resp.json()["message"]
    # Verify records are actually deleted
    _, meta1 = aerospike_client.exists(k1)
    _, meta2 = aerospike_client.exists(k2)
    assert meta1 is None
    assert meta2 is None


def test_batch_remove_verify_deletion(client, aerospike_client, cleanup):
    """Verify batch remove actually deletes records from Aerospike."""
    k1 = ("test", "demo", "batch-rmv1")
    aerospike_client.put(k1, {"name": "ToDelete"})

    resp = client.post(
        "/batch/remove",
        json={"keys": [_key_body("batch-rmv1")]},
    )

    assert resp.status_code == 200
    _, meta = aerospike_client.exists(k1)
    assert meta is None
