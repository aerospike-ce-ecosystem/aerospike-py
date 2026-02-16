"""Shared fixtures for official Aerospike client compatibility tests."""

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG

# Skip entire module if official client is not installed
aerospike = pytest.importorskip("aerospike")

OFFICIAL_CONFIG = {"hosts": [("127.0.0.1", 3000)]}


@pytest.fixture(scope="module")
def rust_client():
    try:
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
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


@pytest.fixture()
def both_clients(rust_client, official_client):
    """Convenience fixture returning (rust_client, official_client) tuple."""
    return rust_client, official_client


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
