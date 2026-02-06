"""Shared fixtures for concurrency tests (requires Aerospike server)."""

import pytest

import aerospike_py

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}


@pytest.fixture(scope="module")
def client():
    """Create and connect a sync client for the test module."""
    try:
        c = aerospike_py.client(CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture
async def async_client():
    """Create and connect an AsyncClient, skip if server is unavailable."""
    try:
        c = aerospike_py.AsyncClient(CONFIG)
        await c.connect()
    except Exception as e:
        if "connect" in str(e).lower() or "cluster" in str(e).lower():
            pytest.skip(f"Aerospike server not available: {e}")
        raise
    yield c
    await c.close()
