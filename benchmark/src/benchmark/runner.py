"""Benchmark execution engine — sequential and concurrent runners for sync and async clients."""

from __future__ import annotations

import asyncio
import gc
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Stores timing data and statistics for a single benchmark combination."""

    client_name: str
    set_name: str
    batch_size: int
    iterations: int
    concurrency: int = 1
    latencies_ms: list[float] = field(default_factory=list)
    wall_times_ms: list[float] = field(default_factory=list)
    found_total: int = 0
    keys_total: int = 0

    # -- Latency statistics --------------------------------------------------

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def stddev_ms(self) -> float:
        return statistics.stdev(self.latencies_ms) if len(self.latencies_ms) >= 2 else 0.0

    @property
    def cv(self) -> float:
        """Coefficient of variation — lower means more stable measurements."""
        return (self.stddev_ms / self.mean_ms) if self.mean_ms > 0 else 0.0

    @property
    def p50_ms(self) -> float:
        return _pct(self.latencies_ms, 50)

    @property
    def p90_ms(self) -> float:
        return _pct(self.latencies_ms, 90)

    @property
    def p95_ms(self) -> float:
        return _pct(self.latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return _pct(self.latencies_ms, 99)

    @property
    def min_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    # -- Throughput / hit-rate -----------------------------------------------

    @property
    def tps(self) -> float:
        """Transactions per second derived from average wall time."""
        if not self.wall_times_ms:
            return 0.0
        avg_wall_s = statistics.mean(self.wall_times_ms) / 1_000
        return self.concurrency / avg_wall_s if avg_wall_s > 0 else 0.0

    @property
    def found_ratio(self) -> float:
        return self.found_total / self.keys_total if self.keys_total else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(data: list[float], percentile: float) -> float:
    """Linear-interpolation percentile on *data*."""
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * percentile / 100.0
    lo = int(idx)
    hi = lo + 1
    if hi >= len(s):
        return s[lo]
    frac = idx - lo
    return s[lo] + frac * (s[hi] - s[lo])


def _shuffled_copy(keys: list, enabled: bool) -> list:
    """Return a shuffled copy when *enabled*, otherwise return the original list."""
    if not enabled:
        return keys
    out = keys.copy()
    random.shuffle(out)
    return out


# ---------------------------------------------------------------------------
# Sequential runners
# ---------------------------------------------------------------------------


def run_single_benchmark(
    client_name: str,
    set_name: str,
    batch_size: int,
    keys: list[tuple[str, str, str]],
    batch_read_fn: Callable[[Any, list[tuple[str, str, str]]], tuple[int, int]],
    client: Any,
    iterations: int,
    warmup: int,
    shuffle_keys: bool = False,
) -> BenchmarkResult:
    """Sequentially call a **sync** ``batch_read`` and collect latencies."""
    # Warm-up phase — results discarded
    for _ in range(warmup):
        batch_read_fn(client, keys)

    res = BenchmarkResult(
        client_name=client_name,
        set_name=set_name,
        batch_size=batch_size,
        iterations=iterations,
        concurrency=1,
    )

    gc.disable()
    try:
        for _ in range(iterations):
            k = _shuffled_copy(keys, shuffle_keys)
            t0 = time.perf_counter()
            total, found = batch_read_fn(client, k)
            elapsed = (time.perf_counter() - t0) * 1_000
            res.latencies_ms.append(elapsed)
            res.wall_times_ms.append(elapsed)
            res.keys_total += total
            res.found_total += found
    finally:
        gc.enable()

    return res


async def run_single_async_benchmark(
    client_name: str,
    set_name: str,
    batch_size: int,
    keys: list[tuple[str, str, str]],
    batch_read_fn: Callable,
    client: Any,
    iterations: int,
    warmup: int,
    shuffle_keys: bool = False,
) -> BenchmarkResult:
    """Sequentially call an **async** ``batch_read`` and collect latencies."""
    for _ in range(warmup):
        await batch_read_fn(client, keys)

    res = BenchmarkResult(
        client_name=client_name,
        set_name=set_name,
        batch_size=batch_size,
        iterations=iterations,
        concurrency=1,
    )

    gc.disable()
    try:
        for _ in range(iterations):
            k = _shuffled_copy(keys, shuffle_keys)
            t0 = time.perf_counter()
            total, found = await batch_read_fn(client, k)
            elapsed = (time.perf_counter() - t0) * 1_000
            res.latencies_ms.append(elapsed)
            res.wall_times_ms.append(elapsed)
            res.keys_total += total
            res.found_total += found
    finally:
        gc.enable()

    return res


# ---------------------------------------------------------------------------
# Concurrent runners
# ---------------------------------------------------------------------------


async def _threaded_call(fn: Callable, client: Any, keys: list) -> tuple[float, int, int]:
    """Offload a sync ``batch_read`` to a thread and return ``(ms, total, found)``."""
    t0 = time.perf_counter()
    total, found = await asyncio.to_thread(fn, client, keys)
    return (time.perf_counter() - t0) * 1_000, total, found


async def _async_call(fn: Callable, client: Any, keys: list) -> tuple[float, int, int]:
    """Directly await an async ``batch_read`` and return ``(ms, total, found)``."""
    t0 = time.perf_counter()
    total, found = await fn(client, keys)
    return (time.perf_counter() - t0) * 1_000, total, found


async def run_concurrent_benchmark(
    client_name: str,
    set_name: str,
    batch_size: int,
    keys: list[tuple[str, str, str]],
    batch_read_fn: Callable[[Any, list[tuple[str, str, str]]], tuple[int, int]],
    client: Any,
    iterations: int,
    warmup: int,
    concurrency: int,
    shuffle_keys: bool = False,
) -> BenchmarkResult:
    """Fire *concurrency* **sync** batch_reads in parallel via ``asyncio.to_thread``."""
    # Warm-up with full concurrency
    for _ in range(warmup):
        await asyncio.gather(*[_threaded_call(batch_read_fn, client, keys) for _ in range(concurrency)])

    res = BenchmarkResult(
        client_name=client_name,
        set_name=set_name,
        batch_size=batch_size,
        iterations=iterations,
        concurrency=concurrency,
    )

    gc.disable()
    try:
        for _ in range(iterations):
            k = _shuffled_copy(keys, shuffle_keys)
            wall_t0 = time.perf_counter()
            outcomes = await asyncio.gather(*[_threaded_call(batch_read_fn, client, k) for _ in range(concurrency)])
            wall_ms = (time.perf_counter() - wall_t0) * 1_000
            res.wall_times_ms.append(wall_ms)
            for lat, total, found in outcomes:
                res.latencies_ms.append(lat)
                res.keys_total += total
                res.found_total += found
    finally:
        gc.enable()

    return res


async def run_concurrent_async_benchmark(
    client_name: str,
    set_name: str,
    batch_size: int,
    keys: list[tuple[str, str, str]],
    batch_read_fn: Callable,
    client: Any,
    iterations: int,
    warmup: int,
    concurrency: int,
    shuffle_keys: bool = False,
) -> BenchmarkResult:
    """Fire *concurrency* **async** batch_reads concurrently via ``asyncio.gather``."""
    for _ in range(warmup):
        await asyncio.gather(*[_async_call(batch_read_fn, client, keys) for _ in range(concurrency)])

    res = BenchmarkResult(
        client_name=client_name,
        set_name=set_name,
        batch_size=batch_size,
        iterations=iterations,
        concurrency=concurrency,
    )

    gc.disable()
    try:
        for _ in range(iterations):
            k = _shuffled_copy(keys, shuffle_keys)
            wall_t0 = time.perf_counter()
            outcomes = await asyncio.gather(*[_async_call(batch_read_fn, client, k) for _ in range(concurrency)])
            wall_ms = (time.perf_counter() - wall_t0) * 1_000
            res.wall_times_ms.append(wall_ms)
            for lat, total, found in outcomes:
                res.latencies_ms.append(lat)
                res.keys_total += total
                res.found_total += found
    finally:
        gc.enable()

    return res
