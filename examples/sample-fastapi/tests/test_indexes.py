from __future__ import annotations

import time


def test_index_integer_create(client):
    idx_name = "idx_int_test_1"
    resp = client.post(
        "/indexes/integer",
        json={
            "namespace": "test",
            "set_name": "idx_demo",
            "bin_name": "age",
            "index_name": idx_name,
        },
    )

    assert resp.status_code == 200
    assert idx_name in resp.json()["message"]
    # Cleanup
    time.sleep(0.5)
    client.delete(f"/indexes/test/{idx_name}")


def test_index_string_create(client):
    idx_name = "idx_str_test_1"
    resp = client.post(
        "/indexes/string",
        json={
            "namespace": "test",
            "set_name": "idx_demo",
            "bin_name": "name",
            "index_name": idx_name,
        },
    )

    assert resp.status_code == 200
    assert idx_name in resp.json()["message"]
    # Cleanup
    time.sleep(0.5)
    client.delete(f"/indexes/test/{idx_name}")


def test_index_geo2dsphere_create(client):
    idx_name = "idx_geo_test_1"
    resp = client.post(
        "/indexes/geo2dsphere",
        json={
            "namespace": "test",
            "set_name": "idx_demo",
            "bin_name": "location",
            "index_name": idx_name,
        },
    )

    assert resp.status_code == 200
    assert idx_name in resp.json()["message"]
    # Cleanup
    time.sleep(0.5)
    client.delete(f"/indexes/test/{idx_name}")


def test_index_remove(client):
    idx_name = "idx_rm_test_1"
    # Create first
    client.post(
        "/indexes/integer",
        json={
            "namespace": "test",
            "set_name": "idx_demo",
            "bin_name": "score",
            "index_name": idx_name,
        },
    )
    time.sleep(0.5)

    resp = client.delete(f"/indexes/test/{idx_name}")

    assert resp.status_code == 200
    assert idx_name in resp.json()["message"]
