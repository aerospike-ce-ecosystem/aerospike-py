"""Concurrency tests for connect() race condition prevention.

Verifies that concurrent connect() calls on the same AsyncClient instance
are properly guarded by the lifecycle state machine — only one succeeds,
others get a clear ClientError.

Requires a running Aerospike server.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

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

    @pytest.mark.parametrize("context_exit", [False, True], ids=["close", "context_exit"])
    async def test_cancelled_close_finishes_before_reconnect(self, context_exit):
        client = await aerospike_py.AsyncClient(AEROSPIKE_CONFIG).connect()
        try:
            close = client.__aexit__(None, None, None) if context_exit else client.close()
            first = asyncio.create_task(close)
            await asyncio.sleep(0)  # let it hand the connection to native shutdown
            assert not client.is_connected()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            # Either closer may run while the original native shutdown is still
            # in progress. Both must finish before connect can reopen the client.
            await asyncio.wait_for(asyncio.gather(client.close(), client.close()), timeout=10)
            await client.connect()
            assert await client.ping()
        finally:
            await client.close()

    async def test_close_from_different_event_loop_threads(self):
        client = await aerospike_py.AsyncClient(AEROSPIKE_CONFIG).connect()
        workers = 8
        ready = threading.Barrier(workers, timeout=15)

        async def close_together():
            # Exercise both the live transition and overlapping idempotent closes.
            for _ in range(3):
                ready.wait()
                await client.close()

        def run_loop():
            asyncio.run(close_together())

        try:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(workers) as pool:
                await asyncio.gather(*(loop.run_in_executor(pool, run_loop) for _ in range(workers)))
            await client.connect()
            assert await client.ping()
        finally:
            await client.close()

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
