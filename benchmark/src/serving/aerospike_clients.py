"""Dual Aerospike client management — official C client + aerospike-py.

Provides three batch_read execution modes:
- gather: asyncio.gather(N x batch_read) — default, max concurrency
- sequential: for-loop await — one set at a time
- single: merge all keys → one batch_read → demux results
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import aerospike
from opentelemetry import trace

import aerospike_py
from serving.config import AEROSPIKE_HOSTS, MAX_CONCURRENT_OPS, THREAD_POOL_SIZE
from serving.observability.metrics import (
    aerospike_batch_read_io_duration_seconds,
    aerospike_batch_read_set_duration_seconds,
    aerospike_dict_conversion_duration_seconds,
)

logger = logging.getLogger("serving")
tracer = trace.get_tracer("serving.aerospike_clients")

_executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------


async def create_official_client() -> AsyncOfficialClient:
    """Create and connect the official Aerospike C client (async wrapper)."""
    config = {"hosts": AEROSPIKE_HOSTS}
    client = aerospike.client(config).connect()
    return AsyncOfficialClient(client)


async def create_py_async_client(
    max_concurrent_ops: int = MAX_CONCURRENT_OPS,
) -> aerospike_py.AsyncClient:
    """Create and connect the aerospike-py native async client."""
    client = aerospike_py.AsyncClient(
        {"hosts": AEROSPIKE_HOSTS, "max_concurrent_operations": max_concurrent_ops},
    )
    await client.connect()
    return client


# ---------------------------------------------------------------------------
# AsyncOfficialClient — wraps sync C client with run_in_executor
# ---------------------------------------------------------------------------


class AsyncOfficialClient:
    """Async wrapper around the official Aerospike C client."""

    def __init__(self, client: aerospike.Client) -> None:
        self._client = client

    async def batch_read(self, keys: list[tuple]) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, partial(self._client.batch_read, keys))

    async def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Multi-set batch_read orchestration
# ---------------------------------------------------------------------------


async def batch_read_all_sets_official(
    client: AsyncOfficialClient,
    keys_by_set: dict[str, list[tuple]],
    mode: str = "gather",
) -> dict[str, list[dict]]:
    """Batch-read across all sets using the official client."""
    if mode == "single":
        return await _batch_read_single_official(client, keys_by_set)
    if mode == "sequential":
        return await _batch_read_sequential_official(client, keys_by_set)
    return await _batch_read_gather_official(client, keys_by_set)


async def batch_read_all_sets_py(
    client: aerospike_py.AsyncClient,
    keys_by_set: dict[str, list[tuple]],
    mode: str = "gather",
) -> dict[str, list[dict]]:
    """Batch-read across all sets using aerospike-py."""
    if mode == "single":
        return await _batch_read_single_py(client, keys_by_set)
    if mode == "sequential":
        return await _batch_read_sequential_py(client, keys_by_set)
    return await _batch_read_gather_py(client, keys_by_set)


# ---------------------------------------------------------------------------
# Official client modes
# ---------------------------------------------------------------------------


async def _batch_read_gather_official(
    client: AsyncOfficialClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    tasks = {set_name: _read_set_official(client, set_name, keys) for set_name, keys in keys_by_set.items()}
    results_list = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results_list, strict=True))


async def _batch_read_sequential_official(
    client: AsyncOfficialClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for set_name, keys in keys_by_set.items():
        results[set_name] = await _read_set_official(client, set_name, keys)
    return results


async def _batch_read_single_official(
    client: AsyncOfficialClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    all_keys: list[tuple] = []
    set_ranges: dict[str, tuple[int, int]] = {}
    for set_name, keys in keys_by_set.items():
        start = len(all_keys)
        all_keys.extend(keys)
        set_ranges[set_name] = (start, len(all_keys))

    batch_result = await client.batch_read(all_keys)

    results: dict[str, list[dict]] = {}
    for set_name, (start, end) in set_ranges.items():
        bins_list: list[dict] = []
        for rec in batch_result.batch_records[start:end]:
            if rec.record and rec.record[2] is not None:
                bins_list.append(rec.record[2])
            else:
                bins_list.append({})
        results[set_name] = bins_list
    return results


async def _read_set_official(
    client: AsyncOfficialClient,
    set_name: str,
    keys: list[tuple],
) -> list[dict]:
    with tracer.start_as_current_span(
        f"aerospike.official.batch_read.{set_name}",
        attributes={"aerospike.set": set_name, "aerospike.batch_size": len(keys)},
    ):
        t0 = time.perf_counter()
        batch_result = await client.batch_read(keys)
        elapsed = time.perf_counter() - t0
        aerospike_batch_read_set_duration_seconds.labels(
            client_type="official",
            set_name=set_name,
        ).observe(elapsed)

    bins_list: list[dict] = []
    found = 0
    for rec in batch_result.batch_records:
        if rec.record and rec.record[2] is not None:
            bins_list.append(rec.record[2])
            found += 1
        else:
            bins_list.append({})

    logger.info(
        "batch_read completed",
        extra={
            "operation": "batch_read_set",
            "client_type": "official",
            "set_name": set_name,
            "latency_ms": round(elapsed * 1000, 2),
            "batch_size": len(keys),
            "found_count": found,
        },
    )
    return bins_list


# ---------------------------------------------------------------------------
# aerospike-py client modes
# ---------------------------------------------------------------------------


async def _batch_read_gather_py(
    client: aerospike_py.AsyncClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    tasks = {set_name: _read_set_py(client, set_name, keys) for set_name, keys in keys_by_set.items()}
    results_list = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results_list, strict=True))


async def _batch_read_sequential_py(
    client: aerospike_py.AsyncClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for set_name, keys in keys_by_set.items():
        results[set_name] = await _read_set_py(client, set_name, keys)
    return results


async def _batch_read_single_py(
    client: aerospike_py.AsyncClient,
    keys_by_set: dict[str, list[tuple]],
) -> dict[str, list[dict]]:
    all_keys: list[tuple] = []
    key_to_set: list[tuple[str, int]] = []  # (set_name, local_index)
    set_counts: dict[str, int] = {}
    for set_name, keys in keys_by_set.items():
        set_counts[set_name] = len(keys)
        for i, k in enumerate(keys):
            all_keys.append(k)
            key_to_set.append((set_name, i))

    # batch_read returns dict[UserKey, bins_dict]
    batch_result = await client.batch_read(all_keys)

    # Initialize result with empty dicts
    results: dict[str, list[dict]] = {sn: [{} for _ in range(cnt)] for sn, cnt in set_counts.items()}
    # Fill in found records by matching user keys back
    for key_tuple, (sn, idx) in zip(all_keys, key_to_set, strict=True):
        user_key = key_tuple[2]  # (ns, set, user_key)
        if user_key in batch_result:
            results[sn][idx] = batch_result[user_key]
    return results


async def _read_set_py(
    client: aerospike_py.AsyncClient,
    set_name: str,
    keys: list[tuple],
) -> list[dict]:
    with tracer.start_as_current_span(
        f"aerospike.py_async.batch_read.{set_name}",
        attributes={"aerospike.set": set_name, "aerospike.batch_size": len(keys)},
    ):
        # Phase 1: Rust I/O — await returns PyBatchReadHandle (GIL <0.01ms)
        t0 = time.perf_counter()
        handle = await client._inner.batch_read(keys, None, None, None)
        t_io = time.perf_counter()

        # Phase 2: Dict conversion — handle.as_dict() (GIL held, 3-8ms)
        batch_result = handle.as_dict()
        t_conv = time.perf_counter()

        io_elapsed = t_io - t0
        conv_elapsed = t_conv - t_io
        total_elapsed = t_conv - t0

        aerospike_batch_read_set_duration_seconds.labels(
            client_type="py-async",
            set_name=set_name,
        ).observe(total_elapsed)
        aerospike_batch_read_io_duration_seconds.labels(
            client_type="py-async",
            set_name=set_name,
        ).observe(io_elapsed)
        aerospike_dict_conversion_duration_seconds.labels(
            client_type="py-async",
            set_name=set_name,
        ).observe(conv_elapsed)

    # batch_result is dict[UserKey, bins_dict]
    bins_list: list[dict] = []
    found = 0
    for key_tuple in keys:
        user_key = key_tuple[2]
        bins = batch_result.get(user_key, {})
        bins_list.append(bins)
        if bins:
            found += 1

    logger.info(
        "batch_read completed",
        extra={
            "operation": "batch_read_set",
            "client_type": "py-async",
            "set_name": set_name,
            "io_ms": round(io_elapsed * 1000, 2),
            "conv_ms": round(conv_elapsed * 1000, 2),
            "total_ms": round(total_elapsed * 1000, 2),
            "batch_size": len(keys),
            "found_count": found,
        },
    )
    return bins_list
