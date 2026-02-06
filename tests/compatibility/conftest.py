"""Shared fixtures for official Aerospike client compatibility tests."""

import pytest

import aerospike_py

# Skip entire module if official client is not installed
aerospike = pytest.importorskip("aerospike")

RUST_CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
OFFICIAL_CONFIG = {"hosts": [("127.0.0.1", 3000)]}


@pytest.fixture(scope="module")
def rust_client():
    try:
        c = aerospike_py.client(RUST_CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(scope="module")
def official_client():
    try:
        c = aerospike.client(OFFICIAL_CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def cleanup(rust_client):
    """Clean up test keys after each test."""
    keys = []
    yield keys
    for key in keys:
        try:
            rust_client.remove(key)
        except Exception:
            pass
