"""Minimal async client protocol — both implementations expose the same surface."""

from __future__ import annotations

from typing import Any, Protocol


class BenchClient(Protocol):
    name: str

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> Any: ...
    async def close(self) -> None: ...
