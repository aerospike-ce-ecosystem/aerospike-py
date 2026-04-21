"""Regression tests for the close / __aexit__ unification (issue #293).

Verifies that:

- Both exits (`close()` and `__aexit__`) share the same state-machine semantics.
- Calling `close()` on a never-connected or already-closed client is a no-op.
- Calling `__aexit__` on a never-entered / already-closed client is a no-op.
- Both exits raise `ClientError` when state is `CONNECTING` (previously
  `__aexit__` silently returned `False`, leaving a half-initialized client).

The CONNECTING-race test uses a non-routable host (TEST-NET-1, RFC 5737) so
the underlying `AsClient::new()` blocks long enough to observe the transient
CONNECTING state from a second coroutine. It is inherently timing-sensitive
but tolerant of schedules: if the connect() somehow resolves first, the test
is skipped rather than flaking.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG


class TestCloseIdempotent:
    """Shared idempotent paths between close() and __aexit__."""

    async def test_close_on_never_connected_is_noop(self):
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        # Never called connect().
        await client.close()
        assert client.is_connected() is False
        # Calling again also a no-op.
        await client.close()

    async def test_close_twice_is_noop(self):
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await client.connect()
        await client.close()
        # Second call must not raise and must not re-run close().
        await client.close()
        assert client.is_connected() is False

    async def test_aexit_without_enter_is_noop(self):
        """__aexit__ on an AsyncClient that was never entered returns False."""
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        suppressed = await client.__aexit__(None, None, None)
        assert suppressed is False
        assert client.is_connected() is False

    async def test_aexit_after_close_is_noop(self):
        client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await client.connect()
        await client.close()
        suppressed = await client.__aexit__(None, None, None)
        assert suppressed is False

    async def test_async_with_exits_cleanly(self):
        async with aerospike_py.AsyncClient(AEROSPIKE_CONFIG) as client:
            await client.connect()
            assert client.is_connected() is True
        # Out of `async with`, client should be disconnected.
        assert client.is_connected() is False


class TestConnectingStateRace:
    """close() and __aexit__ both raise ClientError while CONNECTING.

    Prior to the unification, `__aexit__` silently no-op'd on CONNECTING,
    leaving a client that the connect future still held alive. Both exits
    must now raise so callers can't accidentally leak a half-initialized
    client by exiting the `async with` block during an in-flight connect.
    """

    # Non-routable TEST-NET-1 address (RFC 5737). Guaranteed to make the
    # aerospike_core TCP connect hang until its default timeout.
    UNREACHABLE_CONFIG: ClassVar[dict] = {
        "hosts": [("192.0.2.1", 3000)],
        "cluster_name": "unreachable-test",
    }

    async def _start_connecting(self, client: aerospike_py.AsyncClient) -> asyncio.Task:
        """Kick off connect() as a background task and yield long enough
        for the Rust state machine to transition to CONNECTING."""
        task = asyncio.create_task(client.connect())
        # A few event-loop turns give the Rust code time to CAS into CONNECTING.
        for _ in range(20):
            await asyncio.sleep(0)
        return task

    async def test_close_during_connecting_raises(self):
        client = aerospike_py.AsyncClient(self.UNREACHABLE_CONFIG)
        task = await self._start_connecting(client)

        if task.done():
            pytest.skip("connect() resolved before we could observe CONNECTING state")

        with pytest.raises(aerospike_py.ClientError, match="currently connecting"):
            await client.close()

        # Clean up the outstanding connect task so the test doesn't leak it.
        task.cancel()
        try:
            await task
        except BaseException:  # connect errors or CancelledError
            pass

    async def test_aexit_during_connecting_raises(self):
        """Regression for #293 — previously this silently returned False."""
        client = aerospike_py.AsyncClient(self.UNREACHABLE_CONFIG)
        task = await self._start_connecting(client)

        if task.done():
            pytest.skip("connect() resolved before we could observe CONNECTING state")

        with pytest.raises(aerospike_py.ClientError, match="currently connecting"):
            await client.__aexit__(None, None, None)

        task.cancel()
        try:
            await task
        except BaseException:
            pass
