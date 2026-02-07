from __future__ import annotations

from pathlib import Path


# Path to the test UDF file
UDF_PATH = str(Path(__file__).parent / "fixtures" / "test_udf.lua")


def test_udf_put(client):
    resp = client.post(
        "/udf/modules",
        json={"filename": UDF_PATH, "udf_type": 0},
    )

    assert resp.status_code == 200
    assert "test_udf.lua" in resp.json()["message"]
    # Cleanup
    client.delete("/udf/modules/test_udf")


def test_udf_remove(client):
    # Register first
    client.post(
        "/udf/modules",
        json={"filename": UDF_PATH, "udf_type": 0},
    )

    resp = client.delete("/udf/modules/test_udf")

    assert resp.status_code == 200
    assert "test_udf" in resp.json()["message"]


def test_apply_echo(client, aerospike_client, cleanup):
    # Register UDF
    client.post(
        "/udf/modules",
        json={"filename": UDF_PATH, "udf_type": 0},
    )

    key = ("test", "demo", "udf-echo-1")
    aerospike_client.put(key, {"name": "Alice"})
    cleanup.append(key)

    resp = client.post(
        "/udf/apply",
        json={
            "key": {"namespace": "test", "set_name": "demo", "key": "udf-echo-1"},
            "module": "test_udf",
            "function": "echo",
            "args": [42],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["result"] == 42
    # Cleanup UDF
    client.delete("/udf/modules/test_udf")


def test_apply_get_bin(client, aerospike_client, cleanup):
    # Register UDF
    client.post(
        "/udf/modules",
        json={"filename": UDF_PATH, "udf_type": 0},
    )

    key = ("test", "demo", "udf-getbin-1")
    aerospike_client.put(key, {"name": "Bob", "age": 25})
    cleanup.append(key)

    resp = client.post(
        "/udf/apply",
        json={
            "key": {"namespace": "test", "set_name": "demo", "key": "udf-getbin-1"},
            "module": "test_udf",
            "function": "get_bin",
            "args": ["name"],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["result"] == "Bob"
    # Cleanup UDF
    client.delete("/udf/modules/test_udf")
