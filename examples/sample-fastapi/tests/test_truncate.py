from __future__ import annotations


def test_truncate(client, aerospike_client):
    # Seed data in a dedicated set to avoid interfering with other tests
    key = ("test", "trunc_demo", "trunc-1")
    aerospike_client.put(key, {"name": "Alice"})

    resp = client.post(
        "/truncate",
        json={"namespace": "test", "set_name": "trunc_demo", "nanos": 0},
    )

    assert resp.status_code == 200
    assert "test/trunc_demo" in resp.json()["message"]


def test_truncate_with_nanos(client, aerospike_client):
    key = ("test", "trunc_demo2", "trunc-2")
    aerospike_client.put(key, {"name": "Bob"})
    nanos = 1700000000000000000

    resp = client.post(
        "/truncate",
        json={"namespace": "test", "set_name": "trunc_demo2", "nanos": nanos},
    )

    assert resp.status_code == 200
