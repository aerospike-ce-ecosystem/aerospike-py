"""Unified benchmark: aerospike-py vs official aerospike C client.

Methodology for consistent results:
  1. Warmup phase (discarded) to stabilize connections & server cache
  2. Multiple rounds per operation, report median of round medians
  3. Data is pre-seeded before read benchmarks
  4. GC disabled during measurement
  5. Each client uses isolated key prefixes

Usage:
    python benchmark/bench_compare.py [--count N] [--rounds R] [--warmup W]
                                      [--concurrency C] [--batch-groups G]
                                      [--scenario basic|data_size|concurrency|memory|mixed|all]
                                      [--host HOST] [--port PORT]
                                      [--report] [--report-dir DIR]
                                      [--no-color]

Requirements:
    pip install aerospike   # official C client (comparison target)
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import math
import os
import platform
import random
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime

from _helpers import _fmt_ms, _lpad

NAMESPACE = "test"
SET_NAME = "bench_cmp"
WARMUP_COUNT = 500
SETTLE_SECS = 0.5  # pause between phases to let I/O settle
CLIENT_TIMEOUT_MS = 10_000  # generous client-level timeout (10s) to avoid flaky benchmark failures

_NULL_METRICS: dict = {"avg_ms": None, "p50_ms": None, "p99_ms": None, "ops_per_sec": None}

try:
    import numpy as np

    _NUMPY_READ_DTYPE = np.dtype(
        [
            ("bin_str", "S32"),
            ("bin_int", "i8"),
            ("bin_float", "f8"),
            ("bin_bytes", "S32"),
            ("bin_bool", "i8"),
            ("bin_str2", "S32"),
        ]
    )
except ImportError:
    _NUMPY_READ_DTYPE = None


# ── color helpers ────────────────────────────────────────────


class Color:
    GREEN = "\033[32m"
    RED = "\033[31m"
    BOLD_CYAN = "\033[1m\033[36m"
    DIM = "\033[2m"
    RESET = "\033[0m"


_use_color = True


def _c(code: str, text: str) -> str:
    """Wrap text with ANSI color code if color is enabled."""
    if not _use_color:
        return text
    return f"{code}{text}{Color.RESET}"


# ── BenchmarkResults dataclass ───────────────────────────────


@dataclass
class BenchmarkResults:
    aerospike_py_sync: dict = field(default_factory=dict)
    official_sync: dict | None = None
    aerospike_py_async: dict = field(default_factory=dict)
    official_async: dict | None = None
    count: int = 0
    rounds: int = 0
    warmup: int = 0
    concurrency: int = 0
    batch_groups: int = 0
    # Advanced scenario results
    data_size: dict | None = None
    concurrency_scaling: dict | None = None
    memory_profiling: dict | None = None
    mixed_workload: dict | None = None
    # NumPy batch benchmark results
    numpy_record_scaling: dict | None = None
    numpy_bin_scaling: dict | None = None
    numpy_post_processing: dict | None = None
    numpy_memory: dict | None = None
    numpy_rounds: int = 0
    numpy_warmup: int = 0
    numpy_concurrency: int = 0
    numpy_batch_groups: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    python_version: str = field(default_factory=platform.python_version)
    platform_info: str = field(default_factory=lambda: f"{platform.system()} {platform.machine()}")


# ── timing helpers ───────────────────────────────────────────


def _measure_loop(fn, count: int) -> list[float]:
    """Call fn(i) for i in range(count), return wall_times in seconds."""
    wall_times = []
    for i in range(count):
        w0 = time.perf_counter()
        fn(i)
        w1 = time.perf_counter()
        wall_times.append(w1 - w0)
    return wall_times


def _measure_bulk(fn) -> float:
    """Call fn() once, return total elapsed seconds."""
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def _trim_iqr(values: list[float]) -> list[float]:
    """Remove outliers outside 1.5x IQR. Returns original if too few samples."""
    if len(values) < 5:
        return values
    s = sorted(values)
    q1 = s[len(s) // 4]
    q3 = s[3 * len(s) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    trimmed = [v for v in values if lo <= v <= hi]
    return trimmed if len(trimmed) >= 3 else values


def _compute_percentile(sorted_vals: list[float], p: float) -> float | None:
    """Compute the p-th percentile from sorted values (nearest-rank method)."""
    n = len(sorted_vals)
    if n == 0:
        return None
    idx = max(0, math.ceil(n * p / 100) - 1)
    return sorted_vals[idx]


def _median_of_medians(
    rounds: list[list[float]],
) -> dict:
    """Given multiple rounds of per-op times, return stable metrics."""
    round_medians = _trim_iqr([statistics.median(r) * 1000 for r in rounds])
    round_means = _trim_iqr([statistics.mean(r) * 1000 for r in rounds])
    round_throughputs = _trim_iqr([len(r) / sum(r) for r in rounds if sum(r) > 0])

    # Combine all times for full percentile distribution
    all_ms = sorted(t * 1000 for r in rounds for t in r)
    n = len(all_ms)

    return {
        "avg_ms": statistics.median(round_means),
        "p50_ms": statistics.median(round_medians),
        "p99_ms": _compute_percentile(all_ms, 99) if n >= 100 else all_ms[-1] if all_ms else None,
        "ops_per_sec": statistics.median(round_throughputs) if round_throughputs else 0,
    }


def _bulk_median(
    round_times: list[float],
    count: int,
) -> dict:
    """Given multiple round elapsed times for a bulk op, return metrics."""
    avg_ms = _trim_iqr([(t / count) * 1000 for t in round_times])
    ops_per_sec = _trim_iqr([count / t for t in round_times if t > 0])
    return {
        "avg_ms": statistics.median(avg_ms),
        "p50_ms": None,
        "p99_ms": None,
        "ops_per_sec": statistics.median(ops_per_sec) if ops_per_sec else 0,
    }


def _log(msg: str):
    ts = _c(Color.DIM, f"[{time.strftime('%H:%M:%S')}]")
    print(f"      {ts} {msg}")


def _group_range(g: int, count: int, batch_groups: int) -> range:
    """Return the index range for group g, with the last group absorbing remainder."""
    size = count // batch_groups
    start = g * size
    end = count if g == batch_groups - 1 else (g + 1) * size
    return range(start, end)


def _settle():
    """GC collect + short sleep to stabilize between phases."""
    _log(f"gc.collect() + sleep {SETTLE_SECS}s ...")
    gc.collect()
    time.sleep(SETTLE_SECS)


def _warmup_sync(client, warmup: int, prefix: str = "_warm_") -> None:
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"{prefix}{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass


async def _warmup_async(client, warmup: int, concurrency: int, prefix: str = "_warm_a_") -> None:
    _log(f"warmup {warmup} ops (concurrent, concurrency={concurrency}) ...")
    sem = asyncio.Semaphore(concurrency)

    async def _warm(i):
        async with sem:
            key = (NAMESPACE, SET_NAME, f"{prefix}{i}")
            try:
                await client.put(key, {"w": i})
                await client.get(key)
                await client.remove(key)
            except Exception:
                pass

    await asyncio.gather(*[_warm(i) for i in range(warmup)])


_BATCH_REMOVE_CHUNK = 5000


async def _chunked_batch_remove(client, keys: list[tuple]) -> None:
    """batch_remove in chunks to avoid timeout on large key sets."""
    for i in range(0, len(keys), _BATCH_REMOVE_CHUNK):
        try:
            await client.batch_remove(keys[i : i + _BATCH_REMOVE_CHUNK])
        except Exception:
            # cleanup failures should not abort the benchmark
            pass


# ── record helpers ────────────────────────────────────────────


def _make_record(i: int) -> dict:
    return {
        "bin_str": f"user_{i:08d}",
        "bin_int": i,
        "bin_float": i * 1.1,
        "bin_bytes": f"d{i:04d}".encode(),
        "bin_list": [i, i + 1, i + 2],
        "bin_map": {"k": i, "v": f"v{i}"},
        "bin_bool": i % 2,
        "bin_str2": f"idx_{i:06d}",
    }


# ── seed / cleanup ───────────────────────────────────────────


def _seed_sync(put_fn, prefix: str, count: int, make_record=_make_record):
    for i in range(count):
        put_fn((NAMESPACE, SET_NAME, f"{prefix}{i}"), make_record(i))


def _cleanup_sync(remove_fn, prefix: str, count: int):
    for i in range(count):
        try:
            remove_fn((NAMESPACE, SET_NAME, f"{prefix}{i}"))
        except Exception:
            pass


async def _seed_async(client, prefix: str, count: int, concurrency: int, make_record=_make_record):
    sem = asyncio.Semaphore(concurrency)

    async def _p(i):
        async with sem:
            await client.put(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                make_record(i),
            )

    await asyncio.gather(*[_p(i) for i in range(count)])


# ── sync/async measurement helpers ────────────────────────────


def _bench_sync_op(
    op_name: str,
    fn,
    count: int,
    rounds: int,
    results: dict,
) -> None:
    """Run fn(i) for count iterations across rounds, collecting wall times."""
    wall_rounds = []
    for _ in range(rounds):
        gc.disable()
        wall_times = _measure_loop(fn, count)
        gc.enable()
        wall_rounds.append(wall_times)
    results[op_name] = _median_of_medians(wall_rounds)
    _settle()


async def _bench_async_per_op(
    sem: asyncio.Semaphore,
    coro_fn,
    count: int,
    rounds: int,
) -> tuple[list[float], list[list[float]]]:
    """Measure an async per-op benchmark across rounds.

    Returns (bulk_rounds, per_op_rounds).
    """
    bulk_rounds: list[float] = []
    per_op_rounds: list[list[float]] = []
    for rnd in range(rounds):
        per_op_times: list[float] = []

        async def _worker(i, _rnd=rnd, _pot=per_op_times):
            async with sem:
                t0 = time.perf_counter()
                await coro_fn(i, _rnd)
                _pot.append(time.perf_counter() - t0)

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_worker(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        bulk_rounds.append(elapsed)
        per_op_rounds.append(per_op_times)
    return bulk_rounds, per_op_rounds


def _finalize_async_per_op(
    bulk_rounds: list[float],
    per_op_rounds: list[list[float]],
    count: int,
) -> dict:
    """Convert raw async per-op rounds into a metrics dict."""
    result = _bulk_median(bulk_rounds, count)
    result["per_op"] = _median_of_medians(per_op_rounds) if per_op_rounds else None
    return result


async def _bench_async_bulk(
    bulk_fn,
    count: int,
    rounds: int,
) -> dict:
    """Measure an async bulk operation (batch_read, batch_write, query) across rounds.

    *bulk_fn* is an async callable that performs the full operation.
    Returns a metrics dict via _bulk_median.
    """
    bulk_rounds: list[float] = []
    for _ in range(rounds):
        gc.disable()
        t0 = time.perf_counter()
        await bulk_fn()
        elapsed = time.perf_counter() - t0
        gc.enable()
        bulk_rounds.append(elapsed)
    return _bulk_median(bulk_rounds, count)


# ── 1) aerospike-py sync ─────────────────────────────────────


def bench_aerospike_py_sync(host: str, port: int, count: int, rounds: int, warmup: int, batch_groups: int) -> dict:
    import aerospike_py

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS}
    ).connect()

    prefix = "rs_"
    results = {}

    # --- warmup (discarded) ---
    _warmup_sync(client, warmup, "_warm_rs_")

    # --- PUT ---
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled)")
    put_rounds = []
    for r in range(rounds):
        gc.disable()
        wall_times = _measure_loop(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                _make_record(i),
            ),
            count,
        )
        gc.enable()
        put_rounds.append(wall_times)
        for i in range(count):
            client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
    results["put"] = _median_of_medians(put_rounds)
    _settle()

    # --- seed data for GET/BATCH/QUERY ---
    _log(f"seeding {count} records ...")
    _seed_sync(client.put, prefix, count)
    _settle()

    # --- GET ---
    _log(f"GET  {count} ops x {rounds} rounds  (gc disabled)")
    _bench_sync_op("get", lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")), count, rounds, results)

    # --- OPERATE (read + increment in single call) ---
    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled)")
    _bench_sync_op(
        "operate",
        lambda i: client.operate(
            (NAMESPACE, SET_NAME, f"{prefix}{i}"),
            [
                {"op": aerospike_py.OPERATOR_READ, "bin": "bin_str"},
                {"op": aerospike_py.OPERATOR_INCR, "bin": "bin_int", "val": 1},
            ],
        ),
        count,
        rounds,
        results,
    )

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled)")
    remove_rounds = []
    for r in range(rounds):
        # seed fresh keys for removal
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        wall_times = _measure_loop(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(wall_times)
    results["remove"] = _median_of_medians(remove_rounds)
    _settle()

    # --- BATCH READ MULTI (sequential) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
        gc.enable()
        multi_batch_rounds.append(elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count)
    _settle()

    # --- BATCH READ NUMPY (sequential) ---
    try:
        import numpy as np

        numpy_dtype = _NUMPY_READ_DTYPE
        _log(f"BATCH_READ_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_batch_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(lambda: [client.batch_read(g, _dtype=numpy_dtype) for g in groups])
            gc.enable()
            numpy_batch_rounds.append(elapsed)
        results["batch_read_numpy"] = _bulk_median(numpy_batch_rounds, count)
    except ImportError:
        _log("numpy not installed, skipping BATCH_READ_NUMPY")
        results["batch_read_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- BATCH WRITE (batch_operate with OPERATOR_WRITE) ---
    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    write_ops = [
        {"op": aerospike_py.OPERATOR_WRITE, "bin": "bin_str", "val": "batch_val"},
        {"op": aerospike_py.OPERATOR_WRITE, "bin": "bin_int", "val": 999},
    ]
    bw_keys = [(NAMESPACE, SET_NAME, f"{prefix}bw_{i}") for i in range(count)]
    bw_groups = [bw_keys[i::batch_groups] for i in range(batch_groups)]
    batch_write_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: [client.batch_operate(g, write_ops) for g in bw_groups])
        gc.enable()
        batch_write_rounds.append(elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count)
    # cleanup batch_write keys
    for k in bw_keys:
        try:
            client.remove(k)
        except Exception:
            pass
    _settle()

    # --- BATCH WRITE NUMPY ---
    try:
        import numpy as np

        numpy_write_dtype = np.dtype(
            [
                ("_key", "i4"),
                ("bin_str", "S32"),
                ("bin_int", "i8"),
                ("bin_float", "f8"),
                ("bin_bytes", "S32"),
                ("bin_bool", "i8"),
                ("bin_str2", "S32"),
            ]
        )
        _log(f"BATCH_WRITE_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_write_data = [
            np.array(
                [
                    (
                        i,
                        f"nw_{i}".encode(),
                        i * 10,
                        float(i) * 0.1,
                        f"d{i:04d}".encode(),
                        i % 2,
                        f"idx_{i:06d}".encode(),
                    )
                    for i in _group_range(g, count, batch_groups)
                ],
                dtype=numpy_write_dtype,
            )
            for g in range(batch_groups)
        ]
        numpy_write_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(
                lambda: [client.batch_write_numpy(d, NAMESPACE, SET_NAME, numpy_write_dtype) for d in numpy_write_data]
            )
            gc.enable()
            numpy_write_rounds.append(elapsed)
        results["batch_write_numpy"] = _bulk_median(numpy_write_rounds, count)
        # cleanup numpy write keys
        nw_keys = [(NAMESPACE, SET_NAME, i) for g in range(batch_groups) for i in _group_range(g, count, batch_groups)]
        for k in nw_keys:
            try:
                client.remove(k)
            except Exception:
                pass
    except ImportError:
        _log("numpy not installed, skipping BATCH_WRITE_NUMPY")
        results["batch_write_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    query_rounds = []
    for _ in range(rounds):
        q = client.query(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda q=q: q.results())
        gc.enable()
        query_rounds.append(elapsed)
    results["query"] = _bulk_median(query_rounds, count)

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(client.remove, prefix, count)
    client.close()

    return results


# ── 2) official aerospike sync (C client) ────────────────────


def bench_official_sync(host: str, port: int, count: int, rounds: int, warmup: int, batch_groups: int) -> dict | None:
    try:
        import aerospike as aerospike_c  # noqa: F811
    except ImportError:
        return None

    client = aerospike_c.client({"hosts": [(host, port)], "policies": {"timeout": CLIENT_TIMEOUT_MS}}).connect()

    prefix = "cc_"
    results = {}

    # --- warmup (discarded) ---
    _warmup_sync(client, warmup, "_warm_cc_")

    # --- PUT ---
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled)")
    put_rounds = []
    for r in range(rounds):
        gc.disable()
        wall_times = _measure_loop(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                _make_record(i),
            ),
            count,
        )
        gc.enable()
        put_rounds.append(wall_times)
        for i in range(count):
            client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
    results["put"] = _median_of_medians(put_rounds)
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    _seed_sync(client.put, prefix, count)
    _settle()

    # --- GET ---
    _log(f"GET  {count} ops x {rounds} rounds  (gc disabled)")
    _bench_sync_op("get", lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")), count, rounds, results)

    # --- OPERATE (read + increment in single call) ---
    from aerospike_helpers.operations import operations as as_ops_single

    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled)")
    _bench_sync_op(
        "operate",
        lambda i: client.operate(
            (NAMESPACE, SET_NAME, f"{prefix}{i}"),
            [as_ops_single.read("bin_str"), as_ops_single.increment("bin_int", 1)],
        ),
        count,
        rounds,
        results,
    )

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled)")
    remove_rounds = []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        wall_times = _measure_loop(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(wall_times)
    results["remove"] = _median_of_medians(remove_rounds)
    _settle()

    # --- BATCH READ MULTI (sequential) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
        gc.enable()
        multi_batch_rounds.append(elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count)
    # C client does not support NumpyBatchRecords
    results["batch_read_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- BATCH WRITE (batch_operate with write ops) ---
    from aerospike_helpers.operations import operations as as_ops

    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    c_write_ops = [
        as_ops.write("bin_str", "batch_val"),
        as_ops.write("bin_int", 999),
    ]
    bw_keys = [(NAMESPACE, SET_NAME, f"{prefix}bw_{i}") for i in range(count)]
    bw_groups = [bw_keys[i::batch_groups] for i in range(batch_groups)]
    batch_write_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: [client.batch_operate(g, c_write_ops) for g in bw_groups])
        gc.enable()
        batch_write_rounds.append(elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count)
    # cleanup batch_write keys
    for k in bw_keys:
        try:
            client.remove(k)
        except Exception:
            pass
    # C client does not support batch_write_numpy
    results["batch_write_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    query_rounds = []
    for _ in range(rounds):
        q = client.query(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda q=q: q.results())
        gc.enable()
        query_rounds.append(elapsed)
    results["query"] = _bulk_median(query_rounds, count)

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(client.remove, prefix, count)
    client.close()

    return results


# ── 3) aerospike-py async ────────────────────────────────────


async def bench_aerospike_py_async(
    host: str,
    port: int,
    count: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict:
    from aerospike_py import AsyncClient

    client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS})
    await client.connect()

    prefix = "ra_"
    results = {}
    sem = asyncio.Semaphore(concurrency)

    # --- warmup (discarded, concurrent to warm up connection pool + Tokio threads) ---
    await _warmup_async(client, warmup, concurrency, "_warm_ra_")

    # --- PUT (concurrent, per-op latency tracked) ---
    _log(f"PUT  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    put_rounds = []
    put_per_op_rounds = []
    for r in range(rounds):
        per_op_times = []

        async def _put(i, _r=r):
            async with sem:
                t0 = time.perf_counter()
                await client.put(
                    (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                    _make_record(i),
                )
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_put(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        put_rounds.append(elapsed)
        put_per_op_rounds.append(per_op_times)

        # cleanup
        await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}") for i in range(count)])
    results["put"] = _bulk_median(put_rounds, count)
    results["put"]["per_op"] = _median_of_medians(put_per_op_rounds) if put_per_op_rounds else None
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    await _seed_async(client, prefix, count, concurrency)
    _settle()

    # --- GET (concurrent, per-op latency tracked) ---
    _log(f"GET  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    gr, gpo = await _bench_async_per_op(
        sem, lambda i, _r: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")), count, rounds
    )
    results["get"] = _finalize_async_per_op(gr, gpo, count)
    _settle()

    # --- OPERATE (concurrent: read + increment, per-op latency tracked) ---
    from aerospike_py import OPERATOR_READ, OPERATOR_INCR

    _log(f"OPERATE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    operate_ops = [
        {"op": OPERATOR_READ, "bin": "bin_str"},
        {"op": OPERATOR_INCR, "bin": "bin_int", "val": 1},
    ]
    opr, oppo = await _bench_async_per_op(
        sem,
        lambda i, _r: client.operate((NAMESPACE, SET_NAME, f"{prefix}{i}"), operate_ops),
        count,
        rounds,
    )
    results["operate"] = _finalize_async_per_op(opr, oppo, count)
    _settle()

    # --- REMOVE (concurrent, per-op latency tracked) ---
    _log(f"REMOVE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    rmr, rmpo = [], []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        await _seed_async(client, rm_prefix, count, concurrency)
        r_br, r_po = await _bench_async_per_op(
            sem, lambda i, _r, _p=rm_prefix: client.remove((NAMESPACE, SET_NAME, f"{_p}{i}")), count, 1
        )
        rmr.extend(r_br)
        rmpo.extend(r_po)
    results["remove"] = _finalize_async_per_op(rmr, rmpo, count)
    _settle()

    # --- BATCH READ MULTI (concurrent) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    results["batch_read"] = await _bench_async_bulk(
        lambda: asyncio.gather(*[client.batch_read(g) for g in groups]), count, rounds
    )
    _settle()

    # --- BATCH READ NUMPY (concurrent) ---
    try:
        import numpy as np  # noqa: F811

        numpy_dtype = _NUMPY_READ_DTYPE
        _log(f"BATCH_READ_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        results["batch_read_numpy"] = await _bench_async_bulk(
            lambda: asyncio.gather(*[client.batch_read(g, _dtype=numpy_dtype) for g in groups]), count, rounds
        )
    except ImportError:
        _log("numpy not installed, skipping BATCH_READ_NUMPY")
        results["batch_read_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- BATCH WRITE (batch_operate with OPERATOR_WRITE, concurrent) ---
    from aerospike_py import OPERATOR_WRITE as ASYNC_OP_WRITE

    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    write_ops = [
        {"op": ASYNC_OP_WRITE, "bin": "bin_str", "val": "batch_val"},
        {"op": ASYNC_OP_WRITE, "bin": "bin_int", "val": 999},
    ]
    bw_keys = [(NAMESPACE, SET_NAME, f"{prefix}bw_{i}") for i in range(count)]
    bw_groups = [bw_keys[i::batch_groups] for i in range(batch_groups)]
    results["batch_write"] = await _bench_async_bulk(
        lambda: asyncio.gather(*[client.batch_operate(g, write_ops) for g in bw_groups]), count, rounds
    )
    # cleanup batch_write keys
    await _chunked_batch_remove(client, bw_keys)
    _settle()

    # --- BATCH WRITE NUMPY (concurrent) ---
    try:
        import numpy as np

        numpy_write_dtype = np.dtype(
            [
                ("_key", "i4"),
                ("bin_str", "S32"),
                ("bin_int", "i8"),
                ("bin_float", "f8"),
                ("bin_bytes", "S32"),
                ("bin_bool", "i8"),
                ("bin_str2", "S32"),
            ]
        )
        _log(f"BATCH_WRITE_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_write_data = [
            np.array(
                [
                    (
                        i,
                        f"nw_{i}".encode(),
                        i * 10,
                        float(i) * 0.1,
                        f"d{i:04d}".encode(),
                        i % 2,
                        f"idx_{i:06d}".encode(),
                    )
                    for i in _group_range(g, count, batch_groups)
                ],
                dtype=numpy_write_dtype,
            )
            for g in range(batch_groups)
        ]
        results["batch_write_numpy"] = await _bench_async_bulk(
            lambda: asyncio.gather(
                *[client.batch_write_numpy(d, NAMESPACE, SET_NAME, numpy_write_dtype) for d in numpy_write_data]
            ),
            count,
            rounds,
        )
        # cleanup numpy write keys
        nw_keys = [(NAMESPACE, SET_NAME, i) for g in range(batch_groups) for i in _group_range(g, count, batch_groups)]
        await _chunked_batch_remove(client, nw_keys)
    except ImportError:
        _log("numpy not installed, skipping BATCH_WRITE_NUMPY")
        results["batch_write_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")

    async def _query_fn():
        async_q = client.query(NAMESPACE, SET_NAME)
        await async_q.results()

    results["query"] = await _bench_async_bulk(_query_fn, count, rounds)

    # cleanup
    _log("cleanup ...")
    await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)])
    await client.close()

    return results


# ── 4) official aerospike async (C client via run_in_executor) ──


async def bench_official_async(
    host: str,
    port: int,
    count: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict | None:
    try:
        import aerospike as aerospike_c  # noqa: F811
    except ImportError:
        return None

    import concurrent.futures
    from functools import partial

    sync_client = aerospike_c.client({"hosts": [(host, port)], "policies": {"timeout": CLIENT_TIMEOUT_MS}}).connect()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    loop = asyncio.get_event_loop()

    prefix = "oa_"
    results = {}
    sem = asyncio.Semaphore(concurrency)

    # --- warmup (discarded, concurrent to warm up connection pool) ---
    _log(f"warmup {warmup} ops (concurrent, concurrency={concurrency}) ...")
    warm_sem = asyncio.Semaphore(concurrency)

    async def _warm(i):
        async with warm_sem:
            key = (NAMESPACE, SET_NAME, f"_warm_oa_{i}")
            try:
                await loop.run_in_executor(executor, partial(sync_client.put, key, {"w": i}))
                await loop.run_in_executor(executor, partial(sync_client.get, key))
                await loop.run_in_executor(executor, partial(sync_client.remove, key))
            except Exception:
                pass

    await asyncio.gather(*[_warm(i) for i in range(warmup)])

    # --- PUT (concurrent, per-op latency tracked) ---
    _log(f"PUT  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    put_rounds = []
    put_per_op_rounds = []
    for r in range(rounds):
        per_op_times = []

        async def _put(i, _r=r):
            async with sem:
                t0 = time.perf_counter()
                await loop.run_in_executor(
                    executor,
                    partial(sync_client.put, (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"), _make_record(i)),
                )
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_put(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        put_rounds.append(elapsed)
        put_per_op_rounds.append(per_op_times)

        # cleanup
        for i in range(count):
            try:
                sync_client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
            except Exception:
                pass
    results["put"] = _bulk_median(put_rounds, count)
    results["put"]["per_op"] = _median_of_medians(put_per_op_rounds) if put_per_op_rounds else None
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")

    async def _seed_oa(i):
        async with sem:
            await loop.run_in_executor(
                executor,
                partial(sync_client.put, (NAMESPACE, SET_NAME, f"{prefix}{i}"), _make_record(i)),
            )

    await asyncio.gather(*[_seed_oa(i) for i in range(count)])
    _settle()

    # --- GET (concurrent, per-op latency tracked) ---
    _log(f"GET  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    gr, gpo = await _bench_async_per_op(
        sem,
        lambda i, _r: loop.run_in_executor(executor, partial(sync_client.get, (NAMESPACE, SET_NAME, f"{prefix}{i}"))),
        count,
        rounds,
    )
    results["get"] = _finalize_async_per_op(gr, gpo, count)
    _settle()

    # --- OPERATE (concurrent: read + increment, per-op latency tracked) ---
    from aerospike_helpers.operations import operations as oa_ops

    _log(f"OPERATE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    oa_operate_ops = [oa_ops.read("bin_str"), oa_ops.increment("bin_int", 1)]
    opr, oppo = await _bench_async_per_op(
        sem,
        lambda i, _r: loop.run_in_executor(
            executor, partial(sync_client.operate, (NAMESPACE, SET_NAME, f"{prefix}{i}"), oa_operate_ops)
        ),
        count,
        rounds,
    )
    results["operate"] = _finalize_async_per_op(opr, oppo, count)
    _settle()

    # --- REMOVE (concurrent, per-op latency tracked) ---
    _log(f"REMOVE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    rmr, rmpo = [], []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"

        async def _seed_rm(i, _p=rm_prefix):
            async with sem:
                await loop.run_in_executor(
                    executor,
                    partial(sync_client.put, (NAMESPACE, SET_NAME, f"{_p}{i}"), _make_record(i)),
                )

        await asyncio.gather(*[_seed_rm(i) for i in range(count)])
        r_br, r_po = await _bench_async_per_op(
            sem,
            lambda i, _r, _p=rm_prefix: loop.run_in_executor(
                executor, partial(sync_client.remove, (NAMESPACE, SET_NAME, f"{_p}{i}"))
            ),
            count,
            1,
        )
        rmr.extend(r_br)
        rmpo.extend(r_po)
    results["remove"] = _finalize_async_per_op(rmr, rmpo, count)
    _settle()

    # --- BATCH READ MULTI (concurrent) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    results["batch_read"] = await _bench_async_bulk(
        lambda: asyncio.gather(*[loop.run_in_executor(executor, partial(sync_client.batch_read, g)) for g in groups]),
        count,
        rounds,
    )
    # C client does not support NumpyBatchRecords
    results["batch_read_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- BATCH WRITE (batch_operate with write ops, concurrent) ---
    from aerospike_helpers.operations import operations as oa_batch_ops

    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    oa_write_ops = [
        oa_batch_ops.write("bin_str", "batch_val"),
        oa_batch_ops.write("bin_int", 999),
    ]
    bw_keys = [(NAMESPACE, SET_NAME, f"{prefix}bw_{i}") for i in range(count)]
    bw_groups = [bw_keys[i::batch_groups] for i in range(batch_groups)]
    results["batch_write"] = await _bench_async_bulk(
        lambda: asyncio.gather(
            *[loop.run_in_executor(executor, partial(sync_client.batch_operate, g, oa_write_ops)) for g in bw_groups]
        ),
        count,
        rounds,
    )
    # cleanup batch_write keys
    for k in bw_keys:
        try:
            sync_client.remove(k)
        except Exception:
            pass
    # C client does not support batch_write_numpy
    results["batch_write_numpy"] = dict(_NULL_METRICS)
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    results["query"] = await _bench_async_bulk(
        lambda: loop.run_in_executor(executor, lambda: sync_client.query(NAMESPACE, SET_NAME).results()),
        count,
        rounds,
    )

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(sync_client.remove, prefix, count)
    sync_client.close()
    executor.shutdown(wait=False)

    return results


# ── comparison output ────────────────────────────────────────

COL_OP = 18
COL_VAL = 27
COL_SP = 18


def _speedup_latency(target: float, baseline: float, color: bool = True) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    pct = (baseline - target) / baseline * 100
    if pct >= 0:
        text = f"+{pct:.2f}%"
        return _c(Color.GREEN, text) if color else text
    text = f"{pct:.2f}%"
    return _c(Color.RED, text) if color else text


def _speedup_throughput(target: float, baseline: float, color: bool = True) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    pct = (target - baseline) / baseline * 100
    if pct >= 0:
        text = f"+{pct:.2f}%"
        return _c(Color.GREEN, text) if color else text
    text = f"{pct:.2f}%"
    return _c(Color.RED, text) if color else text


def _fmt_ops(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:,.0f}/s"


def _print_table(
    title: str,
    ops: list[str],
    off_s: dict | None,
    off_a: dict | None,
    apy_s: dict,
    apy_a: dict,
    metric: str,
    formatter,
    speedup_fn,
    color: bool = True,
    cross_op_baseline: dict[str, str] | None = None,
):
    has_off = off_s is not None
    w = COL_OP + 2 + COL_VAL * 4 + (COL_SP * 2 if has_off else 0) + 16

    print(f"\n  {_c(Color.BOLD_CYAN, title) if color else title}")
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")

    h = f"  {'Operation':<{COL_OP}}"
    if has_off:
        h += f" | {'Off_S':>{COL_VAL}}"
        h += f" | {'Off_A':>{COL_VAL}}"
    h += f" | {'APY_S':>{COL_VAL}}"
    h += f" | {'APY_A':>{COL_VAL}}"
    if has_off:
        h += f" | {'APY_S/Off_S':>{COL_SP}}"
        h += f" | {'APY_A/Off_A':>{COL_SP}}"
    print(h)
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")

    cross_ops_used = []
    for op in ops:
        osv = off_s[op].get(metric) if has_off and off_s else None
        oav = off_a[op].get(metric) if off_a else None
        asv = apy_s[op].get(metric)
        aav = apy_a[op].get(metric)

        # cross-op baseline: use another operation's official value
        baseline_op = cross_op_baseline.get(op) if cross_op_baseline else None
        if has_off and baseline_op and osv is None:
            osv = off_s[baseline_op].get(metric) if off_s and off_s.get(baseline_op) else None
        if off_a and baseline_op and oav is None:
            oav = off_a[baseline_op].get(metric) if off_a.get(baseline_op) else None

        line = f"  {op:<{COL_OP}}"
        if has_off:
            line += f" | {formatter(osv):>{COL_VAL}}"
            line += f" | {formatter(oav):>{COL_VAL}}"
        line += f" | {formatter(asv):>{COL_VAL}}"
        line += f" | {formatter(aav):>{COL_VAL}}"

        if has_off:
            suffix = f" (vs {baseline_op.upper()})" if baseline_op else ""
            sp1 = (speedup_fn(asv, osv, color=color) + suffix) if asv and osv else "-"
            sp2 = (speedup_fn(aav, oav, color=color) + suffix) if aav and oav else "-"
            line += f" | {_lpad(sp1, COL_SP)}"
            line += f" | {_lpad(sp2, COL_SP)}"
            if baseline_op and (osv is not None or oav is not None):
                cross_ops_used.append((op, baseline_op))

        print(line)

    for op, baseline_op in cross_ops_used:
        note = f"  * {op} compared against official {baseline_op.upper()}"
        print(_c(Color.DIM, note) if color else note)


def print_comparison(
    off_s: dict | None,
    off_a: dict | None,
    apy_s: dict,
    apy_a: dict,
    count: int,
    rounds: int,
    concurrency: int,
    batch_groups: int,
    color: bool = True,
):
    ops = [
        "put",
        "get",
        "operate",
        "remove",
        "batch_read",
        "batch_read_numpy",
        "batch_write",
        "batch_write_numpy",
        "query",
    ]

    print()
    banner = (
        f"  aerospike-py Benchmark  "
        f"({count:,} ops x {rounds} rounds, warmup={WARMUP_COUNT}, "
        f"async concurrency={concurrency}, batch_groups={batch_groups})"
    )
    if color:
        print(_c(Color.BOLD_CYAN, "=" * 120))
        print(_c(Color.BOLD_CYAN, banner))
        print(_c(Color.BOLD_CYAN, "=" * 120))
    else:
        print("=" * 120)
        print(banner)
        print("=" * 120)

    if off_s is None:
        print("\n  [!] aerospike (official) not installed. pip install aerospike")

    cross_op = {"batch_read_numpy": "batch_read", "batch_write_numpy": "batch_write"}

    _print_table(
        "Avg Latency (ms)  —  lower is better  [median of round means]",
        ops,
        off_s,
        off_a,
        apy_s,
        apy_a,
        metric="avg_ms",
        formatter=_fmt_ms,
        speedup_fn=_speedup_latency,
        color=color,
        cross_op_baseline=cross_op,
    )

    _print_table(
        "Throughput (ops/sec)  —  higher is better  [median of rounds]",
        ops,
        off_s,
        off_a,
        apy_s,
        apy_a,
        metric="ops_per_sec",
        formatter=_fmt_ops,
        speedup_fn=_speedup_throughput,
        color=color,
        cross_op_baseline=cross_op,
    )

    # P50/P99
    pct_ops = [op for op in ops if apy_s[op].get("p50_ms") is not None]
    if pct_ops:
        tail_title = "Tail Latency (ms)  [aggregated across all rounds]"
        print(f"\n  {_c(Color.BOLD_CYAN, tail_title) if color else tail_title}")
        w2 = COL_OP + 2 + 14 * 4 + 20
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'APY_S p50':>12} | {'p99':>10}"
        if off_s is not None:
            h += f" | {'Off_S p50':>12} | {'p99':>10}"
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        for op in pct_ops:
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(apy_s[op]['p50_ms']):>12}"
            line += f" | {_fmt_ms(apy_s[op]['p99_ms']):>10}"
            if off_s is not None:
                line += f" | {_fmt_ms(off_s[op].get('p50_ms')):>12}"
                line += f" | {_fmt_ms(off_s[op].get('p99_ms')):>10}"
            print(line)

    # Async Per-Op Latency Distribution
    async_per_op_ops = [op for op in ops if apy_a[op].get("per_op") is not None]
    if async_per_op_ops:
        async_title = "Async Per-Op Latency (ms)  [individual operation latency under concurrent load]"
        print(f"\n  {_c(Color.BOLD_CYAN, async_title) if color else async_title}")
        w4 = COL_OP + 2 + 12 * 3 + 16
        print(_c(Color.DIM, f"  {'':─<{w4}}") if color else f"  {'':─<{w4}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'p50':>10} | {'p99':>10}"
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w4}}") if color else f"  {'':─<{w4}}")
        for op in async_per_op_ops:
            po = apy_a[op]["per_op"]
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(po.get('p50_ms')):>10}"
            line += f" | {_fmt_ms(po.get('p99_ms')):>10}"
            print(line)

    note = (
        f"  Note: Sync clients are measured sequentially (one op at a time).\n"
        f"  Async clients use asyncio.gather with concurrency={concurrency}.\n"
        f"  Off_S/Off_A = official C client (sync/async via run_in_executor).\n"
        f"  APY_S/APY_A = aerospike-py (sync/async native Rust)."
    )
    print(_c(Color.DIM, note) if color else note)
    print()


# ══════════════════════════════════════════════════════════════
# Advanced scenarios (--scenario data_size|concurrency|memory|mixed|all)
# ══════════════════════════════════════════════════════════════

# ── data size helpers ─────────────────────────────────────────

DATA_SIZE_PROFILES = [
    ("tiny (3 bins, 10B)", 3, 10),
    ("small (5 bins, 10B)", 5, 10),
    ("medium (10 bins, 100B)", 10, 100),
    ("large (20 bins, 1KB)", 20, 1000),
    ("xlarge (50 bins, 1KB)", 50, 1000),
]

CONCURRENCY_LEVELS = [1, 2, 4, 8, 16, 32]

MIXED_RATIOS = [
    ("read_heavy (90:10)", 0.9),
    ("balanced (50:50)", 0.5),
    ("write_heavy (10:90)", 0.1),
]


def _make_bins_sized(num_bins: int, value_size: int, i: int) -> dict:
    """Create bins with controlled value sizes."""
    bins = {}
    for b in range(num_bins):
        if value_size <= 10:
            bins[f"b{b}"] = f"v_{i:08d}"[:value_size]
        else:
            bins[f"b{b}"] = f"v_{i:08d}_" + "x" * (value_size - 10)
        if b == 0:
            bins["n"] = i
    return bins


def _seed_sized(client, prefix: str, count: int, num_bins: int, value_size: int):
    _seed_sync(client.put, prefix, count, make_record=lambda i: _make_bins_sized(num_bins, value_size, i))


async def _seed_sized_async(client, prefix: str, count: int, num_bins: int, value_size: int, concurrency: int):
    await _seed_async(
        client, prefix, count, concurrency, make_record=lambda i: _make_bins_sized(num_bins, value_size, i)
    )


def _fmt_kb(val: float | None) -> str:
    if val is None:
        return "-"
    if val >= 1024:
        return f"{val / 1024:.1f}MB"
    return f"{val:.1f}KB"


# ── Scenario: Data Size Scaling ───────────────────────────────


def bench_data_size(host: str, port: int, count: int, rounds: int, warmup: int) -> dict:
    import aerospike_py

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS}
    ).connect()

    _warmup_sync(client, warmup, "_warm_ds_")

    data = []
    for label, num_bins, value_size in DATA_SIZE_PROFILES:
        prefix = f"ds_{num_bins}_{value_size}_"
        _log(f"Data Size: {label}")

        _log(f"  PUT {count} ops x {rounds} rounds")
        put_rounds = []
        for r in range(rounds):
            gc.disable()
            wt = _measure_loop(
                lambda i, _r=r: client.put(
                    (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                    _make_bins_sized(num_bins, value_size, i),
                ),
                count,
            )
            gc.enable()
            put_rounds.append(wt)
            for i in range(count):
                try:
                    client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
                except Exception:
                    pass

        _seed_sized(client, prefix, count, num_bins, value_size)
        _settle()

        _log(f"  GET {count} ops x {rounds} rounds")
        get_rounds = []
        for _ in range(rounds):
            gc.disable()
            wt = _measure_loop(lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")), count)
            gc.enable()
            get_rounds.append(wt)

        _cleanup_sync(client.remove, prefix, count)
        _settle()

        data.append(
            {
                "label": label,
                "num_bins": num_bins,
                "value_size": value_size,
                "put": _median_of_medians(put_rounds),
                "get": _median_of_medians(get_rounds),
            }
        )

    client.close()
    return {"count": count, "rounds": rounds, "data": data}


def _print_data_size(result: dict):
    header = f"Data Size Scaling ({result['count']:,} ops x {result['rounds']} rounds)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 28 + 14 * 4 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Profile':<26} | {'PUT p50':>10} | {'PUT p99':>10}"
    h += f" | {'GET p50':>10} | {'GET p99':>10}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        line = f"  {e['label']:<26}"
        line += f" | {_fmt_ms(e['put'].get('p50_ms')):>10} | {_fmt_ms(e['put'].get('p99_ms')):>10}"
        line += f" | {_fmt_ms(e['get'].get('p50_ms')):>10} | {_fmt_ms(e['get'].get('p99_ms')):>10}"
        print(line)


# ── Scenario: Concurrency Scaling ─────────────────────────────


def bench_concurrency_scaling(host: str, port: int, count: int, rounds: int, warmup: int) -> dict:
    from aerospike_py import AsyncClient

    data = []

    async def _run():
        client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS})
        await client.connect()
        await _warmup_async(client, warmup, 1, "_warm_cs_")

        prefix = "cs_"
        _log(f"seeding {count} records ...")
        await _seed_sized_async(client, prefix, count, 5, 10, 4)
        _settle()

        for conc in CONCURRENCY_LEVELS:
            _log(f"Concurrency={conc}: PUT+GET {count} ops x {rounds} rounds")
            sem = asyncio.Semaphore(conc)

            try:
                put_bulk, put_po = [], []
                for r in range(rounds):
                    per_op = []

                    async def _put(i, _r=r):
                        async with sem:
                            t0 = time.perf_counter()
                            await client.put((NAMESPACE, SET_NAME, f"{prefix}cp{_r}_{i}"), {"n": f"u{i}", "a": i})
                            per_op.append(time.perf_counter() - t0)

                    gc.disable()
                    t0 = time.perf_counter()
                    await asyncio.gather(*[_put(i) for i in range(count)])
                    elapsed = time.perf_counter() - t0
                    gc.enable()
                    put_bulk.append(elapsed)
                    put_po.append(per_op)
                    await _chunked_batch_remove(
                        client, [(NAMESPACE, SET_NAME, f"{prefix}cp{r}_{i}") for i in range(count)]
                    )

                pm = _bulk_median(put_bulk, count)
                pm["per_op"] = _median_of_medians(put_po)

                get_bulk, get_po = [], []
                for _ in range(rounds):
                    per_op = []

                    async def _get(i):
                        async with sem:
                            t0 = time.perf_counter()
                            await client.get((NAMESPACE, SET_NAME, f"{prefix}{i}"))
                            per_op.append(time.perf_counter() - t0)

                    gc.disable()
                    t0 = time.perf_counter()
                    await asyncio.gather(*[_get(i) for i in range(count)])
                    elapsed = time.perf_counter() - t0
                    gc.enable()
                    get_bulk.append(elapsed)
                    get_po.append(per_op)

                gm = _bulk_median(get_bulk, count)
                gm["per_op"] = _median_of_medians(get_po)
                _settle()
                data.append({"concurrency": conc, "put": pm, "get": gm})
            except Exception as exc:
                _log(f"Concurrency={conc}: skipped ({exc!r})")
                gc.enable()
                _settle()

        await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)])
        await client.close()

    asyncio.run(_run())
    return {"count": count, "rounds": rounds, "data": data}


def _print_concurrency_scaling(result: dict):
    header = f"Concurrency Scaling ({result['count']:,} ops x {result['rounds']} rounds, AsyncClient)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 12 + 14 * 6 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Conc':>6} | {'PUT ops/s':>12} | {'PUT p50':>10} | {'PUT p99':>10}"
    h += f" | {'GET ops/s':>12} | {'GET p50':>10} | {'GET p99':>10}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        ppo = e["put"].get("per_op", {})
        gpo = e["get"].get("per_op", {})
        line = f"  {e['concurrency']:>6}"
        line += f" | {_fmt_ops(e['put'].get('ops_per_sec')):>12}"
        line += f" | {_fmt_ms(ppo.get('p50_ms')):>10} | {_fmt_ms(ppo.get('p99_ms')):>10}"
        line += f" | {_fmt_ops(e['get'].get('ops_per_sec')):>12}"
        line += f" | {_fmt_ms(gpo.get('p50_ms')):>10} | {_fmt_ms(gpo.get('p99_ms')):>10}"
        print(line)


# ── Scenario: Memory Profiling ────────────────────────────────


def bench_memory(host: str, port: int, count: int, warmup: int) -> dict:
    import aerospike_py

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS}
    ).connect()
    _warmup_sync(client, min(warmup, 200), "_warm_mem_")

    has_c = False
    c_client = None
    try:
        import aerospike as aerospike_c

        c_client = aerospike_c.client({"hosts": [(host, port)], "policies": {"timeout": CLIENT_TIMEOUT_MS}}).connect()
        has_c = True
    except ImportError:
        pass

    data = []
    for label, num_bins, value_size in DATA_SIZE_PROFILES:
        prefix = f"mem_{num_bins}_{value_size}_"
        _log(f"Memory: {label}")
        _seed_sized(client, prefix, count, num_bins, value_size)
        _settle()

        keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
        entry = {"label": label, "num_bins": num_bins, "value_size": value_size}

        # PUT memory
        gc.collect()
        gc.disable()
        tracemalloc.start()
        tracemalloc.reset_peak()
        for i in range(count):
            client.put((NAMESPACE, SET_NAME, f"{prefix}mput_{i}"), _make_bins_sized(num_bins, value_size, i))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        gc.enable()
        entry["put_peak_kb"] = round(peak / 1024, 1)
        for i in range(count):
            try:
                client.remove((NAMESPACE, SET_NAME, f"{prefix}mput_{i}"))
            except Exception:
                pass

        # GET memory
        gc.collect()
        gc.disable()
        tracemalloc.start()
        tracemalloc.reset_peak()
        for i in range(count):
            client.get((NAMESPACE, SET_NAME, f"{prefix}{i}"))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        gc.enable()
        entry["get_peak_kb"] = round(peak / 1024, 1)

        # BATCH_READ memory
        gc.collect()
        gc.disable()
        tracemalloc.start()
        tracemalloc.reset_peak()
        client.batch_read(keys)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        gc.enable()
        entry["batch_read_peak_kb"] = round(peak / 1024, 1)

        # C client comparison
        if has_c and c_client:
            c_prefix = f"cmem_{num_bins}_{value_size}_"
            _seed_sized(c_client, c_prefix, count, num_bins, value_size)
            c_keys = [(NAMESPACE, SET_NAME, f"{c_prefix}{i}") for i in range(count)]

            gc.collect()
            gc.disable()
            tracemalloc.start()
            tracemalloc.reset_peak()
            for i in range(count):
                c_client.get((NAMESPACE, SET_NAME, f"{c_prefix}{i}"))
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            gc.enable()
            entry["c_get_peak_kb"] = round(peak / 1024, 1)

            gc.collect()
            gc.disable()
            tracemalloc.start()
            tracemalloc.reset_peak()
            c_client.batch_read(c_keys)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            gc.enable()
            entry["c_batch_read_peak_kb"] = round(peak / 1024, 1)

            _cleanup_sync(c_client.remove, c_prefix, count)

        _cleanup_sync(client.remove, prefix, count)
        _settle()
        data.append(entry)

    client.close()
    if c_client:
        c_client.close()
    return {"count": count, "has_c": has_c, "data": data}


def _print_memory(result: dict):
    header = f"Memory Profiling ({result['count']:,} ops, peak memory)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    has_c = result["has_c"]
    w = 28 + 14 * (5 if has_c else 3) + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Profile':<26} | {'PUT peak':>12} | {'GET peak':>12} | {'BATCH peak':>12}"
    if has_c:
        h += f" | {'C GET peak':>12} | {'C BATCH':>12}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        line = f"  {e['label']:<26}"
        line += f" | {_fmt_kb(e.get('put_peak_kb')):>12} | {_fmt_kb(e.get('get_peak_kb')):>12} | {_fmt_kb(e.get('batch_read_peak_kb')):>12}"
        if has_c:
            line += f" | {_fmt_kb(e.get('c_get_peak_kb')):>12} | {_fmt_kb(e.get('c_batch_read_peak_kb')):>12}"
        print(line)


# ── Scenario: Mixed Workload ─────────────────────────────────


def bench_mixed(host: str, port: int, count: int, rounds: int, warmup: int, concurrency: int) -> dict:
    from aerospike_py import AsyncClient

    data = []

    async def _run():
        client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS})
        await client.connect()
        await _warmup_async(client, warmup, 1, "_warm_mx_")

        prefix = "mx_"
        seed_count = min(count, 5000)
        _log(f"seeding {seed_count} records ...")
        await _seed_sized_async(client, prefix, seed_count, 5, 10, concurrency)
        _settle()

        for label, read_ratio in MIXED_RATIOS:
            _log(f"Mixed: {label}, {count} ops x {rounds} rounds")
            sem = asyncio.Semaphore(concurrency)

            round_results = []
            for _ in range(rounds):
                read_lats, write_lats = [], []
                read_count = int(count * read_ratio)
                write_count = count - read_count

                async def _read(i):
                    async with sem:
                        t0 = time.perf_counter()
                        await client.get((NAMESPACE, SET_NAME, f"{prefix}{i % seed_count}"))
                        read_lats.append(time.perf_counter() - t0)

                async def _write(i):
                    async with sem:
                        t0 = time.perf_counter()
                        await client.put((NAMESPACE, SET_NAME, f"{prefix}w{i}"), {"n": f"u{i}", "a": i})
                        write_lats.append(time.perf_counter() - t0)

                tasks = [_read(i) for i in range(read_count)] + [_write(i) for i in range(write_count)]
                random.seed(42)
                random.shuffle(tasks)

                gc.disable()
                t0 = time.perf_counter()
                await asyncio.gather(*tasks)
                elapsed = time.perf_counter() - t0
                gc.enable()

                round_results.append({"elapsed": elapsed, "read_lats": read_lats, "write_lats": write_lats})
                wk = [(NAMESPACE, SET_NAME, f"{prefix}w{i}") for i in range(write_count)]
                if wk:
                    await _chunked_batch_remove(client, wk)

            throughputs = _trim_iqr([count / r["elapsed"] for r in round_results])
            all_r = sorted(t * 1000 for r in round_results for t in r["read_lats"])
            all_w = sorted(t * 1000 for r in round_results for t in r["write_lats"])

            entry = {
                "label": label,
                "read_ratio": read_ratio,
                "throughput_ops_sec": statistics.median(throughputs) if throughputs else 0,
            }
            if all_r:
                nr = len(all_r)
                entry["read"] = {
                    "count": nr,
                    "p50_ms": _compute_percentile(all_r, 50),
                    "p95_ms": _compute_percentile(all_r, 95),
                    "p99_ms": _compute_percentile(all_r, 99) if nr >= 100 else all_r[-1],
                    "avg_ms": statistics.mean(all_r),
                }
            if all_w:
                nw = len(all_w)
                entry["write"] = {
                    "count": nw,
                    "p50_ms": _compute_percentile(all_w, 50),
                    "p95_ms": _compute_percentile(all_w, 95),
                    "p99_ms": _compute_percentile(all_w, 99) if nw >= 100 else all_w[-1],
                    "avg_ms": statistics.mean(all_w),
                }
            _settle()
            data.append(entry)

        await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(seed_count)])
        await client.close()

    asyncio.run(_run())
    return {"count": count, "rounds": rounds, "concurrency": concurrency, "data": data}


def _print_mixed(result: dict):
    header = (
        f"Mixed Workload ({result['count']:,} ops x {result['rounds']} rounds, "
        f"concurrency={result['concurrency']}, AsyncClient)"
    )
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 22 + 14 * 7 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Workload':<20} | {'Throughput':>12}"
    h += f" | {'Read p50':>10} | {'Read p95':>10} | {'Read p99':>10}"
    h += f" | {'Write p50':>10} | {'Write p95':>10} | {'Write p99':>10}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        r = e.get("read", {})
        wd = e.get("write", {})
        line = f"  {e['label']:<20} | {_fmt_ops(e.get('throughput_ops_sec')):>12}"
        line += f" | {_fmt_ms(r.get('p50_ms')):>10} | {_fmt_ms(r.get('p95_ms')):>10} | {_fmt_ms(r.get('p99_ms')):>10}"
        line += (
            f" | {_fmt_ms(wd.get('p50_ms')):>10} | {_fmt_ms(wd.get('p95_ms')):>10} | {_fmt_ms(wd.get('p99_ms')):>10}"
        )
        print(line)


# ── main ─────────────────────────────────────────────────────

SCENARIOS = ["basic", "data_size", "concurrency", "memory", "mixed", "all"]


def main():
    global _use_color

    parser = argparse.ArgumentParser(description="Benchmark: aerospike-py (Rust) vs official aerospike (C)")
    parser.add_argument("--count", type=int, default=1000, help="Ops per round")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per operation")
    parser.add_argument("--warmup", type=int, default=WARMUP_COUNT, help="Warmup ops")
    parser.add_argument("--concurrency", type=int, default=4, help="Async concurrency")
    parser.add_argument(
        "--batch-groups",
        type=int,
        default=10,
        help="Number of groups for concurrent batch_read benchmark",
    )
    parser.add_argument(
        "--scenario",
        default="basic",
        choices=SCENARIOS,
        help="Scenario: basic (default), data_size, concurrency, memory, mixed, all",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AEROSPIKE_PORT", 3000)))
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate benchmark report (JSON + charts)",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Report JSON output directory (default: docs/static/benchmark/results/)",
    )
    args = parser.parse_args()

    # Auto-detect color support
    if args.no_color or not sys.stdout.isatty():
        _use_color = False

    run_basic = args.scenario in ("basic", "all")
    extras = (
        ["data_size", "concurrency", "memory", "mixed"]
        if args.scenario == "all"
        else ([args.scenario] if args.scenario not in ("basic", "all") else [])
    )

    print("Benchmark config:")
    print(f"  ops/round    = {args.count:,}")
    print(f"  rounds       = {args.rounds}")
    print(f"  warmup       = {args.warmup}")
    print(f"  concurrency  = {args.concurrency}")
    print(f"  batch_groups = {args.batch_groups}")
    print(f"  scenario     = {args.scenario}")
    print(f"  server       = {args.host}:{args.port}")
    print()

    off_s, off_a, apy_s, apy_a = None, None, {}, {}

    if run_basic:
        print(_c(Color.BOLD_CYAN, "[1/4]") + " official sync (C) ...")
        off_s = bench_official_sync(args.host, args.port, args.count, args.rounds, args.warmup, args.batch_groups)
        if off_s is None:
            print("      not installed, skipping")
        else:
            print("      done")

        print(_c(Color.BOLD_CYAN, "[2/4]") + " official async (C via run_in_executor) ...")
        off_a = asyncio.run(
            bench_official_async(
                args.host,
                args.port,
                args.count,
                args.rounds,
                args.warmup,
                args.concurrency,
                args.batch_groups,
            )
        )
        if off_a is None:
            print("      not installed, skipping")
        else:
            print("      done")

        print(_c(Color.BOLD_CYAN, "[3/4]") + " aerospike-py sync ...")
        apy_s = bench_aerospike_py_sync(args.host, args.port, args.count, args.rounds, args.warmup, args.batch_groups)
        print("      done")

        print(_c(Color.BOLD_CYAN, "[4/4]") + " aerospike-py async ...")
        apy_a = asyncio.run(
            bench_aerospike_py_async(
                args.host,
                args.port,
                args.count,
                args.rounds,
                args.warmup,
                args.concurrency,
                args.batch_groups,
            )
        )
        print("      done")

        print_comparison(
            off_s,
            off_a,
            apy_s,
            apy_a,
            args.count,
            args.rounds,
            args.concurrency,
            args.batch_groups,
            color=_use_color,
        )

    # Advanced scenarios
    data_size_result = None
    concurrency_result = None
    memory_result = None
    mixed_result = None

    if extras:
        step = 0
        total = len(extras)

        if "data_size" in extras:
            step += 1
            print(_c(Color.BOLD_CYAN, f"\n[extra {step}/{total}]") + " Data Size Scaling ...")
            data_size_result = bench_data_size(args.host, args.port, args.count, args.rounds, args.warmup)
            _print_data_size(data_size_result)

        if "concurrency" in extras:
            step += 1
            print(_c(Color.BOLD_CYAN, f"\n[extra {step}/{total}]") + " Concurrency Scaling ...")
            concurrency_result = bench_concurrency_scaling(args.host, args.port, args.count, args.rounds, args.warmup)
            _print_concurrency_scaling(concurrency_result)

        if "memory" in extras:
            step += 1
            print(_c(Color.BOLD_CYAN, f"\n[extra {step}/{total}]") + " Memory Profiling ...")
            memory_result = bench_memory(args.host, args.port, args.count, args.warmup)
            _print_memory(memory_result)

        if "mixed" in extras:
            step += 1
            print(_c(Color.BOLD_CYAN, f"\n[extra {step}/{total}]") + " Mixed Workload ...")
            mixed_result = bench_mixed(
                args.host,
                args.port,
                args.count,
                args.rounds,
                args.warmup,
                args.concurrency,
            )
            _print_mixed(mixed_result)

        print()

    # NumPy batch benchmarks (included when scenario=all)
    numpy_record_scaling = None
    numpy_bin_scaling = None
    numpy_post_processing = None
    numpy_memory = None
    numpy_rounds = 10
    numpy_concurrency = args.concurrency
    numpy_batch_groups = args.batch_groups

    if args.scenario == "all":
        from bench_batch_numpy import (
            _run_bin_scaling as _np_run_bin_scaling,
            _run_memory as _np_run_memory,
            _run_post_processing as _np_run_post_processing,
            _run_record_scaling as _np_run_record_scaling,
            _print_memory_table as _np_print_memory_table,
            _print_post_processing_table as _np_print_post_processing_table,
            _print_scaling_table as _np_print_scaling_table,
        )

        np_scenarios = ["record_scaling", "bin_scaling", "post_processing", "memory"]
        np_step = 0
        np_total = len(np_scenarios)

        print(_c(Color.BOLD_CYAN, "\n── NumPy Batch Benchmarks ──\n"))

        np_step += 1
        print(_c(Color.BOLD_CYAN, f"[numpy {np_step}/{np_total}]") + " Record Count Scaling ...")
        numpy_record_scaling = _np_run_record_scaling(
            args.host,
            args.port,
            numpy_rounds,
            WARMUP_COUNT,
            numpy_concurrency,
            numpy_batch_groups,
        )
        _np_print_scaling_table("Record Count Scaling", "Records", "record_count", numpy_record_scaling, numpy_rounds)
        print()

        np_step += 1
        print(_c(Color.BOLD_CYAN, f"[numpy {np_step}/{np_total}]") + " Bin Count Scaling ...")
        numpy_bin_scaling = _np_run_bin_scaling(
            args.host,
            args.port,
            numpy_rounds,
            WARMUP_COUNT,
            numpy_concurrency,
            numpy_batch_groups,
        )
        _np_print_scaling_table("Bin Count Scaling", "Bins", "bin_count", numpy_bin_scaling, numpy_rounds)
        print()

        np_step += 1
        print(_c(Color.BOLD_CYAN, f"[numpy {np_step}/{np_total}]") + " Post-Processing ...")
        numpy_post_processing = _np_run_post_processing(
            args.host,
            args.port,
            numpy_rounds,
            WARMUP_COUNT,
            numpy_concurrency,
            numpy_batch_groups,
        )
        _np_print_post_processing_table(numpy_post_processing, numpy_rounds)
        print()

        np_step += 1
        print(_c(Color.BOLD_CYAN, f"[numpy {np_step}/{np_total}]") + " Memory Usage ...")
        numpy_memory = _np_run_memory(
            args.host,
            args.port,
            numpy_rounds,
            WARMUP_COUNT,
            numpy_batch_groups,
        )
        _np_print_memory_table(numpy_memory, numpy_rounds)
        print()

    if args.report:
        from datetime import datetime as _dt

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        date_slug = _dt.now().strftime("%Y-%m-%d_%H-%M")
        json_dir = args.report_dir or os.path.join(project_root, "docs", "static", "benchmark", "results")

        results = BenchmarkResults(
            aerospike_py_sync=apy_s,
            official_sync=off_s,
            aerospike_py_async=apy_a,
            official_async=off_a,
            count=args.count,
            rounds=args.rounds,
            warmup=args.warmup,
            concurrency=args.concurrency,
            batch_groups=args.batch_groups,
            data_size=data_size_result,
            concurrency_scaling=concurrency_result,
            memory_profiling=memory_result,
            mixed_workload=mixed_result,
            numpy_record_scaling=numpy_record_scaling,
            numpy_bin_scaling=numpy_bin_scaling,
            numpy_post_processing=numpy_post_processing,
            numpy_memory=numpy_memory,
            numpy_rounds=numpy_rounds,
            numpy_warmup=WARMUP_COUNT,
            numpy_concurrency=numpy_concurrency,
            numpy_batch_groups=numpy_batch_groups,
        )

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_generator import generate_report

        generate_report(results, json_dir, date_slug)
        print(_c(Color.BOLD_CYAN, "[report]") + f" Generated: {json_dir}/{date_slug}.json")


if __name__ == "__main__":
    main()
