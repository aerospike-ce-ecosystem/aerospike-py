"""aerospike-py native async client wrapper."""

from __future__ import annotations

from typing import Any

import aerospike_py


class PyAsyncBench:
    name = "aerospike-py"

    def __init__(
        self,
        host: str,
        port: int,
        cluster_name: str = "docker",
        max_concurrent_operations: int | None = None,
    ) -> None:
        cfg: dict[str, Any] = {
            "hosts": [(host, port)],
            "cluster_name": cluster_name,
        }
        if max_concurrent_operations is not None:
            cfg["max_concurrent_operations"] = max_concurrent_operations
        self._client = aerospike_py.AsyncClient(cfg)

    async def connect(self) -> None:
        await self._client.connect()

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> Any:
        # Returns LazyBatchRecords (0.11.0+); .to_dict() materialises bins.
        return await self._client.batch_read(keys)

    async def close(self) -> None:
        # aerospike-py AsyncClient currently closes on drop; explicit close
        # is optional. Forward to client.close() if/when the underlying API
        # exposes it, so graceful uvicorn shutdown gets a structured close
        # instead of relying on garbage collection.
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result
