"""aerospike-py native async client wrapper."""

from __future__ import annotations

from typing import Any

import aerospike_py


class PyAsyncBench:
    name = "aerospike-py"

    def __init__(self, host: str, port: int) -> None:
        self._client = aerospike_py.AsyncClient({"hosts": [(host, port)]})

    async def connect(self) -> None:
        await self._client.connect()

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> Any:
        # Returns LazyBatchRecords (0.11.0+); .to_dict() materialises bins.
        return await self._client.batch_read(keys)

    async def close(self) -> None:
        # aerospike-py AsyncClient closes on drop; explicit close is optional.
        pass
