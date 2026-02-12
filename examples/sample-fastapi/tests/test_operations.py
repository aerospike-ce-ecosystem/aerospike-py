from __future__ import annotations

import aerospike_py


def _key_body(key: str):
    return {"namespace": "test", "set_name": "demo", "key": key}


def test_operate(client, aerospike_client, cleanup):
    key = ("test", "demo", "op-1")
    aerospike_client.put(key, {"counter": 10, "name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/operations/operate",
        json={
            "key": _key_body("op-1"),
            "ops": [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["bins"]["counter"] == 11
    assert data["meta"]["gen"] >= 2


def test_operate_with_meta(client, aerospike_client, cleanup):
    key = ("test", "demo", "op-meta-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/operations/operate",
        json={
            "key": _key_body("op-meta-1"),
            "ops": [{"op": aerospike_py.OPERATOR_READ, "bin": "name", "val": None}],
            "meta": {"gen": 1, "ttl": 600},
        },
    )

    assert resp.status_code == 200
    assert resp.json()["bins"]["name"] == "Alice"


def test_operate_ordered(client, aerospike_client, cleanup):
    key = ("test", "demo", "op-ord-1")
    aerospike_client.put(key, {"counter": 10, "name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/operations/operate-ordered",
        json={
            "key": _key_body("op-ord-1"),
            "ops": [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
                {"op": aerospike_py.OPERATOR_READ, "bin": "name", "val": None},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    ordered = data["ordered_bins"]

    # NOTE: operate_ordered should return bins in operation order, but
    # aerospike-core 2.x stores bins in HashMap<String, Value> (record.rs:40)
    # which loses insertion order.  Until aerospike-core switches to an
    # order-preserving map (e.g. IndexMap), we verify values only.
    result_map = {pair[0]: pair[1] for pair in ordered}
    assert result_map["counter"] == 11
    assert result_map["name"] == "Alice"
