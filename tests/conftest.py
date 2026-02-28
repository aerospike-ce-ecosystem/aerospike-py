"""Shared fixtures for all test suites."""

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.helpers import invoke


@pytest.fixture(scope="module")
def client():
    """Create and connect a sync client for the test module."""
    try:
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture
async def async_client():
    """Create and connect an AsyncClient, skip if server is unavailable."""
    try:
        c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await c.connect()
    except Exception as e:
        pytest.skip(f"Aerospike server not available: {e}")
    yield c
    await c.close()


@pytest.fixture(params=["sync", "async"], ids=["sync", "async"])
async def any_client(request, client, async_client):
    """Yield either the sync or async client, parametrized.

    Each test using this fixture runs twice: once with the sync client
    and once with the async client. Use ``invoke()`` from ``tests.helpers``
    to call methods transparently.
    """
    if request.param == "sync":
        yield client
    else:
        yield async_client


@pytest.fixture
async def any_cleanup(any_client):
    """Clean up test keys after each test, works with any_client."""
    keys = []
    yield keys
    for key in keys:
        try:
            await invoke(any_client, "remove", key)
        except Exception:
            pass


@pytest.fixture
def cleanup(client):
    """Clean up test keys after each test.

    Not autouse — integration/concurrency conftest layers add autouse wrappers.
    """
    keys = []
    yield keys
    for key in keys:
        try:
            client.remove(key)
        except Exception:
            pass


@pytest.fixture
async def async_cleanup(async_client):
    """Collect keys to clean up after an async test.

    Depends on async_client explicitly so pytest tears this fixture down
    *before* closing the client connection.

    Usage:
        async def test_something(async_client, async_cleanup):
            key = ("test", "demo", "k1")
            async_cleanup.append(key)
            ...
    """
    keys = []
    yield keys
    for key in keys:
        try:
            await async_client.remove(key)
        except Exception:
            pass
