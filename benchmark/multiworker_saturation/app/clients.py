"""Thin client abstraction over aerospike-py and aerospike-client-python.

Both expose the same ``async batch_read(keys) -> int`` (count of found records),
so the FastAPI endpoint stays branchless after startup. Implementations are
intentionally minimal — heavy lifting belongs in the client libraries we are
measuring, not in this wrapper.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from typing import Any, Protocol

from . import config


class AsyncBatchReadClient(Protocol):
    async def batch_read(self, keys: list[tuple[str, str, str]]) -> int: ...

    async def close(self) -> None: ...


class AerospikePyClient:
    """Native async client via aerospike-py (Rust/PyO3)."""

    def __init__(self) -> None:
        self._client: Any = None

    async def connect(self) -> None:
        from aerospike_py import AsyncClient

        self._client = AsyncClient({"hosts": [(config.AEROSPIKE_HOST, config.AEROSPIKE_PORT)]})
        await self._client.connect()

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> int:
        # AsyncClient.batch_read returns ``dict[UserKey, AerospikeRecord]``
        # directly — the Python wrapper at ``aerospike_py/_async_client.py``
        # already calls the underlying handle's ``as_dict()`` for us, which
        # is the documented fastest path (single GIL bulk conversion).
        result = await self._client.batch_read(keys)
        return len(result)

    async def close(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()


class LegacyAsyncWrapper:
    """aerospike-client-python (C ext) — awaitable via run_in_executor.

    The C extension is sync; concurrent ``await`` calls are serialized inside
    the default ThreadPoolExecutor. This matches the comparison setup in
    issue #347.
    """

    def __init__(self) -> None:
        self._client: Any = None

    async def connect(self) -> None:
        import aerospike

        loop = asyncio.get_running_loop()
        self._client = aerospike.client({"hosts": [(config.AEROSPIKE_HOST, config.AEROSPIKE_PORT)]})
        await loop.run_in_executor(None, self._client.connect)

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> int:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(self._client.batch_read, keys),
        )
        return sum(
            1 for rec in result.batch_records if rec.record and rec.record[2] is not None
        )

    async def close(self) -> None:
        if self._client is not None:
            loop = asyncio.get_running_loop()
            with contextlib.suppress(Exception):
                await loop.run_in_executor(None, self._client.close)


async def create_client() -> AsyncBatchReadClient:
    """Factory — selects implementation from ``config.CLIENT_KIND``."""
    if config.CLIENT_KIND == "aerospike-py":
        client = AerospikePyClient()
    elif config.CLIENT_KIND == "legacy":
        client = LegacyAsyncWrapper()
    else:
        raise ValueError(
            f"Unknown CLIENT_KIND={config.CLIENT_KIND!r}; expected 'aerospike-py' or 'legacy'"
        )
    await client.connect()
    return client
