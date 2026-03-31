"""Concurrency tests for connect() race condition prevention.

Verifies that concurrent connect() calls on the same AsyncClient instance
are properly guarded by the lifecycle state machine — only one succeeds,
others get a clear ClientError.

Requires a running Aerospike server.
"""

import asyncio

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG


class TestAsyncConnectRace:
    """Concurrent connect() on the same AsyncClient."""

    async def test_concurrent_connect_only_one_succeeds(self):
        """When multiple coroutines call connect() concurrently, only one should succeed."""
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)

        results = await asyncio.gather(
            client.connect(),
            client.connect(),
            client.connect(),
            return_exceptions=True,
        )

        # connect() returns self on success (not None), so check for non-Exception results.
        successes = [r for r in results if not isinstance(r, Exception)]
        guard_errors = [r for r in results if isinstance(r, aerospike_py.ClientError)]

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
        assert len(guard_errors) == 2, f"Expected 2 ClientError, got {len(guard_errors)}: {results}"

        # Verify the error message mentions the state.
        for err in guard_errors:
            assert "already" in str(err).lower()

        assert client.is_connected() is True
        await client.close()

    async def test_connect_after_close_succeeds(self):
        """After close(), a new connect() should succeed (reconnect cycle)."""
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)

        await client.connect()
        assert client.is_connected() is True

        await client.close()
        assert client.is_connected() is False

        # Reconnect should work.
        await client.connect()
        assert client.is_connected() is True

        await client.close()

    async def test_double_close_is_idempotent(self):
        """Calling close() twice should not raise."""
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await client.connect()

        await client.close()
        await client.close()  # should not raise

        assert client.is_connected() is False

    async def test_connect_close_reconnect_cycle(self):
        """Multiple connect→close→reconnect cycles should work cleanly."""
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)

        for _ in range(3):
            await client.connect()
            assert client.is_connected() is True
            await client.close()
            assert client.is_connected() is False


class TestSyncConnectLifecycle:
    """Sync Client connect/close lifecycle (requires server)."""

    def test_connect_close_reconnect(self):
        """Sync client: connect → close → reconnect cycle."""
        client = aerospike_py.client(AEROSPIKE_CONFIG)

        client.connect()
        assert client.is_connected() is True

        client.close()
        assert client.is_connected() is False

        client.connect()
        assert client.is_connected() is True

        client.close()

    def test_double_connect_raises(self):
        """Calling connect() on an already-connected sync client should raise."""
        client = aerospike_py.client(AEROSPIKE_CONFIG)
        client.connect()

        with pytest.raises(aerospike_py.ClientError, match="already connected"):
            client.connect()

        client.close()

    def test_double_close_is_idempotent(self):
        """Calling close() twice on sync client should not raise."""
        client = aerospike_py.client(AEROSPIKE_CONFIG)
        client.connect()
        client.close()
        client.close()  # should not raise
