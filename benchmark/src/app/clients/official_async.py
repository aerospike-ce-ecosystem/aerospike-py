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

    def __init__(self, host: str, port: int, cluster_name: str = "docker") -> None:
        self._host = host
        self._port = port
        self._cluster_name = cluster_name
        self._client: aerospike.Client | None = None

    async def connect(self) -> None:
        # Offload the blocking C-extension connect off the event loop so
        # startup mirrors PyAsyncBench's shape and a slow cluster handshake
        # doesn't stall the asyncio runtime.
        def _do_connect() -> aerospike.Client:
            return aerospike.client({"hosts": [(self._host, self._port)], "cluster_name": self._cluster_name}).connect()

        self._client = await asyncio.to_thread(_do_connect)

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> Any:
        assert self._client is not None, "call connect() before batch_read()"
        return await asyncio.to_thread(self._client.batch_read, keys)

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
