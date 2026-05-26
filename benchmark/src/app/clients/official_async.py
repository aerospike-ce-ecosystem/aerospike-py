"""Official aerospike C client wrapped with asyncio.to_thread.

This matches how the official client is typically used inside ASGI apps:
the sync API is offloaded to a thread so it doesn't block the event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aerospike


class OfficialAsyncBench:
    name = "official"

    def __init__(self, host: str, port: int) -> None:
        self._client = aerospike.client({"hosts": [(host, port)]}).connect()

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> Any:
        return await asyncio.to_thread(self._client.batch_read, keys)

    async def close(self) -> None:
        self._client.close()
