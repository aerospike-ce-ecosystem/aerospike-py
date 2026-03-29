"""Integration tests for ping() health check (requires Aerospike server)."""

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG


class TestPing:
    def test_ping_returns_true_when_connected(self, client):
        """ping() returns True on a connected client."""
        assert client.ping() is True

    def test_ping_returns_false_when_not_connected(self):
        """ping() returns False on an unconnected client (no exception)."""
        c = aerospike_py.client(AEROSPIKE_CONFIG)
        assert c.ping() is False

    def test_ping_returns_false_after_close(self):
        """ping() returns False after client.close()."""
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        assert c.ping() is True
        c.close()
        assert c.ping() is False


class TestAsyncPing:
    @pytest.mark.asyncio
    async def test_async_ping_returns_true_when_connected(self, async_client):
        """Async ping() returns True on a connected client."""
        assert await async_client.ping() is True

    @pytest.mark.asyncio
    async def test_async_ping_returns_false_when_not_connected(self):
        """Async ping() returns False on an unconnected client."""
        c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        assert await c.ping() is False

    @pytest.mark.asyncio
    async def test_async_ping_returns_false_after_close(self):
        """Async ping() returns False after client.close()."""
        c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await c.connect()
        assert await c.ping() is True
        await c.close()
        assert await c.ping() is False
