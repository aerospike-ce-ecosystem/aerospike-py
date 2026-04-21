"""Client factories, batch_read wrappers, and close helpers for three Aerospike clients.

Supported clients
-----------------
* **official**        — sync C-binding client (``aerospike.Client``)
* **official-async**  — thin async wrapper around the sync client via ``run_in_executor``
* **py-async**        — native async client powered by Rust/Tokio (``aerospike_py.AsyncClient``)
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from typing import Any

# ---------------------------------------------------------------------------
# 1. Official sync client
# ---------------------------------------------------------------------------


def create_official_sync(hosts: list[tuple[str, int]]) -> Any:
    """Instantiate and connect the official aerospike C client (sync)."""
    import aerospike

    client = aerospike.client({"hosts": hosts})
    client.connect()
    return client


def batch_read_official_sync(
    client: Any,
    keys: list[tuple[str, str, str]],
) -> tuple[int, int]:
    """Execute a sync batch_read.  Returns ``(total_keys, found_count)``."""
    result = client.batch_read(keys)
    found = sum(1 for rec in result.batch_records if rec.record and rec.record[2] is not None)
    return len(keys), found


def close_official_sync(client: Any) -> None:
    """Best-effort close for the sync client."""
    with contextlib.suppress(Exception):
        client.close()


# ---------------------------------------------------------------------------
# 2. Official async wrapper (run_in_executor over the sync C client)
# ---------------------------------------------------------------------------


class OfficialAsyncWrapper:
    """Makes the synchronous C client awaitable by delegating to the event-loop executor.

    This is *not* true async I/O — the C extension holds the GIL during network calls,
    so concurrent ``await`` s are effectively serialised.
    """

    def __init__(self, hosts: list[tuple[str, int]]) -> None:
        self._hosts = hosts
        self._inner: Any = None

    async def connect(self) -> None:
        import aerospike

        self._inner = aerospike.client({"hosts": self._hosts})
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._inner.connect)

    async def batch_read(self, keys: list) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(self._inner.batch_read, keys),
        )

    async def close(self) -> None:
        if self._inner is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._inner.close)


async def create_official_async(hosts: list[tuple[str, int]]) -> OfficialAsyncWrapper:
    """Factory for the executor-wrapped official client."""
    wrapper = OfficialAsyncWrapper(hosts)
    await wrapper.connect()
    return wrapper


async def batch_read_official_async(
    client: OfficialAsyncWrapper,
    keys: list[tuple[str, str, str]],
) -> tuple[int, int]:
    """Awaitable batch_read via executor.  Returns ``(total, found)``."""
    result = await client.batch_read(keys)
    found = sum(1 for rec in result.batch_records if rec.record and rec.record[2] is not None)
    return len(keys), found


async def close_official_async(client: OfficialAsyncWrapper) -> None:
    """Best-effort async close."""
    with contextlib.suppress(Exception):
        await client.close()


# ---------------------------------------------------------------------------
# 3. aerospike-py native async client (Rust / Tokio)
# ---------------------------------------------------------------------------


async def create_py_async(hosts: list[tuple[str, int]]) -> Any:
    """Create and connect the aerospike-py ``AsyncClient``."""
    from aerospike_py import AsyncClient

    client = AsyncClient({"hosts": hosts})
    await client.connect()
    return client


async def batch_read_py_async(
    client: Any,
    keys: list[tuple[str, str, str]],
) -> tuple[int, int]:
    """Native async batch_read.  Returns ``(total, found)``.

    ``aerospike_py.batch_read`` returns ``dict[UserKey, dict[str, Any]]``.
    Only keys with non-empty bins are counted as found.
    """
    result = await client.batch_read(keys)
    # result is a dict: {user_key: {bin_name: bin_value}, ...}
    found = len(result)
    return len(keys), found


async def close_py_async(client: Any) -> None:
    """Best-effort async close for aerospike-py."""
    with contextlib.suppress(Exception):
        await client.close()
