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
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

NAMESPACE = "test"
SET_NAME = "bench_cmp"
WARMUP_COUNT = 500
SETTLE_SECS = 0.5  # pause between phases to let I/O settle


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
    rust_sync: dict = field(default_factory=dict)
    c_sync: dict | None = None
    rust_async: dict = field(default_factory=dict)
    count: int = 0
    rounds: int = 0
    warmup: int = 0
    concurrency: int = 0
    batch_groups: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    python_version: str = field(default_factory=platform.python_version)
    platform_info: str = field(default_factory=lambda: f"{platform.system()} {platform.machine()}")


# ── timing helpers ───────────────────────────────────────────


def _measure_loop(fn, count: int) -> list[float]:
    """Call fn(i) for i in range(count), return per-op times in seconds."""
    times = []
    for i in range(count):
        t0 = time.perf_counter()
        fn(i)
        times.append(time.perf_counter() - t0)
    return times


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


def _median_of_medians(rounds: list[list[float]]) -> dict:
    """Given multiple rounds of per-op times, return stable metrics."""
    round_medians = _trim_iqr([statistics.median(r) * 1000 for r in rounds])
    round_means = _trim_iqr([statistics.mean(r) * 1000 for r in rounds])
    round_throughputs = _trim_iqr([len(r) / sum(r) for r in rounds if sum(r) > 0])

    # Combine all times for p99
    all_ms = [t * 1000 for r in rounds for t in r]
    all_ms.sort()

    return {
        "avg_ms": statistics.median(round_means),
        "p50_ms": statistics.median(round_medians),
        "p99_ms": all_ms[int(len(all_ms) * 0.99)] if len(all_ms) >= 100 else all_ms[-1],
        "ops_per_sec": statistics.median(round_throughputs) if round_throughputs else 0,
        "stdev_ms": statistics.stdev(round_medians) if len(round_medians) > 1 else 0,
    }


def _bulk_median(round_times: list[float], count: int) -> dict:
    """Given multiple round elapsed times for a bulk op, return metrics."""
    avg_ms = _trim_iqr([(t / count) * 1000 for t in round_times])
    ops_per_sec = _trim_iqr([count / t for t in round_times if t > 0])
    return {
        "avg_ms": statistics.median(avg_ms),
        "p50_ms": None,
        "p99_ms": None,
        "ops_per_sec": statistics.median(ops_per_sec) if ops_per_sec else 0,
        "stdev_ms": statistics.stdev(avg_ms) if len(avg_ms) > 1 else 0,
    }


def _log(msg: str):
    ts = _c(Color.DIM, f"[{time.strftime('%H:%M:%S')}]")
    print(f"      {ts} {msg}")


def _settle():
    """GC collect + short sleep to stabilize between phases."""
    _log(f"gc.collect() + sleep {SETTLE_SECS}s ...")
    gc.collect()
    time.sleep(SETTLE_SECS)


# ── seed / cleanup ───────────────────────────────────────────


def _seed_sync(put_fn, prefix: str, count: int):
    for i in range(count):
        put_fn((NAMESPACE, SET_NAME, f"{prefix}{i}"), {"n": f"u{i}", "a": i, "s": i * 1.1})


def _cleanup_sync(remove_fn, prefix: str, count: int):
    for i in range(count):
        try:
            remove_fn((NAMESPACE, SET_NAME, f"{prefix}{i}"))
        except Exception:
            pass


async def _seed_async(client, prefix: str, count: int, concurrency: int):
    sem = asyncio.Semaphore(concurrency)

    async def _p(i):
        async with sem:
            await client.put(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                {"n": f"u{i}", "a": i, "s": i * 1.1},
            )

    await asyncio.gather(*[_p(i) for i in range(count)])


# ── 1) aerospike-py sync (Rust) ─────────────────────────────


def bench_rust_sync(host: str, port: int, count: int, rounds: int, warmup: int, batch_groups: int) -> dict:
    import aerospike_py

    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": "docker"}).connect()

    prefix = "rs_"
    results = {}

    # --- warmup (discarded) ---
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_rs_{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass

    # --- PUT ---
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled)")
    put_rounds = []
    for r in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                {"n": f"u{i}", "a": i, "s": i * 1.1},
            ),
            count,
        )
        gc.enable()
        put_rounds.append(times)
        for i in range(count):
            client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
    results["put"] = _median_of_medians(put_rounds)
    _settle()

    # --- seed data for GET/BATCH/SCAN ---
    _log(f"seeding {count} records ...")
    _seed_sync(client.put, prefix, count)
    _settle()

    # --- GET ---
    _log(f"GET  {count} ops x {rounds} rounds  (gc disabled)")
    get_rounds = []
    for _ in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")),
            count,
        )
        gc.enable()
        get_rounds.append(times)
    results["get"] = _median_of_medians(get_rounds)
    _settle()

    # --- OPERATE (read + increment in single call) ---
    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled)")
    operate_rounds = []
    for _ in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i: client.operate(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                [
                    {"op": aerospike_py.OPERATOR_READ, "bin": "n"},
                    {"op": aerospike_py.OPERATOR_INCR, "bin": "a", "val": 1},
                ],
            ),
            count,
        )
        gc.enable()
        operate_rounds.append(times)
    results["operate"] = _median_of_medians(operate_rounds)
    _settle()

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled)")
    remove_rounds = []
    for r in range(rounds):
        # seed fresh keys for removal
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        times = _measure_loop(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(times)
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

        numpy_dtype = np.dtype([("n", "S32"), ("a", "i8"), ("s", "f8")])
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
        results["batch_read_numpy"] = {
            "avg_ms": None,
            "p50_ms": None,
            "p99_ms": None,
            "ops_per_sec": None,
            "stdev_ms": None,
        }
    _settle()

    # --- BATCH WRITE (batch_operate with OPERATOR_WRITE) ---
    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    write_ops = [
        {"op": aerospike_py.OPERATOR_WRITE, "bin": "n", "val": "batch_val"},
        {"op": aerospike_py.OPERATOR_WRITE, "bin": "a", "val": 999},
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

    # --- SCAN ---
    _log(f"SCAN  x {rounds} rounds  (gc disabled)")
    scan_rounds = []
    for _ in range(rounds):
        scan = client.scan(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda s=scan: s.results())
        gc.enable()
        scan_rounds.append(elapsed)
    results["scan"] = _bulk_median(scan_rounds, count)

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(client.remove, prefix, count)
    client.close()

    return results


# ── 2) official aerospike C client ───────────────────────────


def bench_c_sync(host: str, port: int, count: int, rounds: int, warmup: int, batch_groups: int) -> dict | None:
    try:
        import aerospike as aerospike_c  # noqa: F811
    except ImportError:
        return None

    client = aerospike_c.client({"hosts": [(host, port)]}).connect()

    prefix = "cc_"
    results = {}

    # --- warmup (discarded) ---
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_cc_{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass

    # --- PUT ---
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled)")
    put_rounds = []
    for r in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                {"n": f"u{i}", "a": i, "s": i * 1.1},
            ),
            count,
        )
        gc.enable()
        put_rounds.append(times)
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
    get_rounds = []
    for _ in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")),
            count,
        )
        gc.enable()
        get_rounds.append(times)
    results["get"] = _median_of_medians(get_rounds)
    _settle()

    # --- OPERATE (read + increment in single call) ---
    from aerospike_helpers.operations import operations as as_ops_single

    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled)")
    operate_rounds = []
    for _ in range(rounds):
        gc.disable()
        times = _measure_loop(
            lambda i: client.operate(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                [as_ops_single.read("n"), as_ops_single.increment("a", 1)],
            ),
            count,
        )
        gc.enable()
        operate_rounds.append(times)
    results["operate"] = _median_of_medians(operate_rounds)
    _settle()

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled)")
    remove_rounds = []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        times = _measure_loop(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(times)
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
    results["batch_read_numpy"] = {
        "avg_ms": None,
        "p50_ms": None,
        "p99_ms": None,
        "ops_per_sec": None,
        "stdev_ms": None,
    }
    _settle()

    # --- BATCH WRITE (batch_operate with write ops) ---
    from aerospike_helpers.operations import operations as as_ops

    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    c_write_ops = [
        as_ops.write("n", "batch_val"),
        as_ops.write("a", 999),
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
    _settle()

    # --- SCAN ---
    _log(f"SCAN  x {rounds} rounds  (gc disabled)")
    scan_rounds = []
    for _ in range(rounds):
        scan = client.scan(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda s=scan: s.results())
        gc.enable()
        scan_rounds.append(elapsed)
    results["scan"] = _bulk_median(scan_rounds, count)

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(client.remove, prefix, count)
    client.close()

    return results


# ── 3) aerospike-py async (Rust) ─────────────────────────────


async def bench_rust_async(
    host: str,
    port: int,
    count: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict:
    from aerospike_py import AsyncClient

    client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker"})
    await client.connect()

    prefix = "ra_"
    results = {}
    sem = asyncio.Semaphore(concurrency)

    # --- warmup (discarded) ---
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_ra_{i}")
        try:
            await client.put(key, {"w": i})
            await client.get(key)
            await client.remove(key)
        except Exception:
            pass

    # --- PUT (concurrent) ---
    _log(f"PUT  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)")
    put_rounds = []
    for r in range(rounds):

        async def _put(i, _r=r):
            async with sem:
                await client.put(
                    (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                    {"n": f"u{i}", "a": i, "s": i * 1.1},
                )

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_put(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        put_rounds.append(elapsed)

        # cleanup
        await client.batch_remove([(NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}") for i in range(count)])
    results["put"] = _bulk_median(put_rounds, count)
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    await _seed_async(client, prefix, count, concurrency)
    _settle()

    # --- GET (concurrent) ---
    _log(f"GET  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)")
    get_rounds = []
    for _ in range(rounds):

        async def _get(i):
            async with sem:
                await client.get((NAMESPACE, SET_NAME, f"{prefix}{i}"))

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_get(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        get_rounds.append(elapsed)
    results["get"] = _bulk_median(get_rounds, count)
    _settle()

    # --- OPERATE (concurrent: read + increment) ---
    from aerospike_py import OPERATOR_READ, OPERATOR_INCR

    _log(f"OPERATE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)")
    operate_ops = [
        {"op": OPERATOR_READ, "bin": "n"},
        {"op": OPERATOR_INCR, "bin": "a", "val": 1},
    ]
    operate_rounds = []
    for _ in range(rounds):

        async def _operate(i):
            async with sem:
                await client.operate(
                    (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                    operate_ops,
                )

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_operate(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        operate_rounds.append(elapsed)
    results["operate"] = _bulk_median(operate_rounds, count)
    _settle()

    # --- REMOVE (concurrent) ---
    _log(f"REMOVE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)")
    remove_rounds = []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        await _seed_async(client, rm_prefix, count, concurrency)

        async def _rm(i, _p=rm_prefix):
            async with sem:
                await client.remove((NAMESPACE, SET_NAME, f"{_p}{i}"))

        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[_rm(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        gc.enable()
        remove_rounds.append(elapsed)
    results["remove"] = _bulk_median(remove_rounds, count)
    _settle()

    # --- BATCH READ MULTI (concurrent) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[client.batch_read(g) for g in groups])
        elapsed = time.perf_counter() - t0
        gc.enable()
        multi_batch_rounds.append(elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count)
    _settle()

    # --- BATCH READ NUMPY (concurrent) ---
    try:
        import numpy as np

        numpy_dtype = np.dtype([("n", "S32"), ("a", "i8"), ("s", "f8")])
        _log(f"BATCH_READ_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_batch_rounds = []
        for _ in range(rounds):
            gc.disable()
            t0 = time.perf_counter()
            await asyncio.gather(*[client.batch_read(g, _dtype=numpy_dtype) for g in groups])
            elapsed = time.perf_counter() - t0
            gc.enable()
            numpy_batch_rounds.append(elapsed)
        results["batch_read_numpy"] = _bulk_median(numpy_batch_rounds, count)
    except ImportError:
        _log("numpy not installed, skipping BATCH_READ_NUMPY")
        results["batch_read_numpy"] = {
            "avg_ms": None,
            "p50_ms": None,
            "p99_ms": None,
            "ops_per_sec": None,
            "stdev_ms": None,
        }
    _settle()

    # --- BATCH WRITE (batch_operate with OPERATOR_WRITE, concurrent) ---
    from aerospike_py import OPERATOR_WRITE as ASYNC_OP_WRITE

    _log(f"BATCH_WRITE  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    write_ops = [
        {"op": ASYNC_OP_WRITE, "bin": "n", "val": "batch_val"},
        {"op": ASYNC_OP_WRITE, "bin": "a", "val": 999},
    ]
    bw_keys = [(NAMESPACE, SET_NAME, f"{prefix}bw_{i}") for i in range(count)]
    bw_groups = [bw_keys[i::batch_groups] for i in range(batch_groups)]
    batch_write_rounds = []
    for _ in range(rounds):
        gc.disable()
        t0 = time.perf_counter()
        await asyncio.gather(*[client.batch_operate(g, write_ops) for g in bw_groups])
        elapsed = time.perf_counter() - t0
        gc.enable()
        batch_write_rounds.append(elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count)
    # cleanup batch_write keys
    await client.batch_remove(bw_keys)
    _settle()

    # --- SCAN ---
    _log(f"SCAN  x {rounds} rounds  (gc disabled)")
    scan_rounds = []
    for _ in range(rounds):
        gc.disable()
        t0 = time.perf_counter()
        await client.scan(NAMESPACE, SET_NAME)
        elapsed = time.perf_counter() - t0
        gc.enable()
        scan_rounds.append(elapsed)
    results["scan"] = _bulk_median(scan_rounds, count)

    # cleanup
    _log("cleanup ...")
    await client.batch_remove([(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)])
    await client.close()

    return results


# ── comparison output ────────────────────────────────────────

COL_OP = 18
COL_VAL = 27
COL_SP = 18


def _speedup_latency(target: float, baseline: float, color: bool = True) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    ratio = baseline / target
    if ratio >= 1.0:
        text = f"{ratio:.1f}x faster"
        return _c(Color.GREEN, text) if color else text
    text = f"{1 / ratio:.1f}x slower"
    return _c(Color.RED, text) if color else text


def _speedup_throughput(target: float, baseline: float, color: bool = True) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    ratio = target / baseline
    if ratio >= 1.0:
        text = f"{ratio:.1f}x faster"
        return _c(Color.GREEN, text) if color else text
    text = f"{1 / ratio:.1f}x slower"
    return _c(Color.RED, text) if color else text


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.3f}ms"


def _fmt_ops(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:,.0f}/s"


def _visible_len(s: str) -> int:
    """Return display width of string, ignoring ANSI escape codes."""
    import re

    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _rpad(s: str, width: int) -> str:
    """Right-pad string to width, accounting for ANSI codes."""
    pad = width - _visible_len(s)
    return s + " " * max(0, pad)


def _lpad(s: str, width: int) -> str:
    """Left-pad string to width, accounting for ANSI codes."""
    pad = width - _visible_len(s)
    return " " * max(0, pad) + s


def _print_table(
    title: str,
    ops: list[str],
    rust: dict,
    c: dict | None,
    async_r: dict,
    metric: str,
    formatter,
    speedup_fn,
    color: bool = True,
    cross_op_baseline: dict[str, str] | None = None,
):
    has_c = c is not None
    w = COL_OP + 2 + COL_VAL * 3 + (COL_SP * 2 if has_c else 0) + 12

    print(f"\n  {_c(Color.BOLD_CYAN, title) if color else title}")
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")

    h = f"  {'Operation':<{COL_OP}}"
    h += f" | {'Sync (sequential)':>{COL_VAL}}"
    if has_c:
        h += f" | {'Official (sequential)':>{COL_VAL}}"
    h += f" | {'Async (concurrent)':>{COL_VAL}}"
    if has_c:
        h += f" | {'Sync vs Official':>{COL_SP}}"
        h += f" | {'Async vs Official':>{COL_SP}}"
    print(h)
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")

    cross_ops_used = []
    for op in ops:
        rv = rust[op].get(metric)
        cv = c[op].get(metric) if has_c else None
        av = async_r[op].get(metric)

        # cross-op baseline: use another operation's official value
        baseline_op = cross_op_baseline.get(op) if cross_op_baseline else None
        if has_c and baseline_op and cv is None:
            cv = c[baseline_op].get(metric) if c[baseline_op] else None

        line = f"  {op:<{COL_OP}}"
        line += f" | {formatter(rv):>{COL_VAL}}"
        if has_c:
            line += f" | {formatter(cv):>{COL_VAL}}"
        line += f" | {formatter(av):>{COL_VAL}}"

        if has_c and cv is not None:
            suffix = f" (vs {baseline_op.upper()})" if baseline_op else ""
            sp1 = (speedup_fn(rv, cv, color=color) + suffix) if rv else "-"
            sp2 = (speedup_fn(av, cv, color=color) + suffix) if av else "-"
            line += f" | {_lpad(sp1, COL_SP)}"
            line += f" | {_lpad(sp2, COL_SP)}"
            if baseline_op:
                cross_ops_used.append((op, baseline_op))

        print(line)

    for op, baseline_op in cross_ops_used:
        note = f"  * {op} compared against official {baseline_op.upper()}"
        print(_c(Color.DIM, note) if color else note)


def print_comparison(
    rust: dict,
    c: dict | None,
    async_r: dict,
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
        "scan",
    ]

    print()
    banner = (
        f"  aerospike-py Benchmark  "
        f"({count:,} ops x {rounds} rounds, warmup={WARMUP_COUNT}, "
        f"async concurrency={concurrency}, batch_groups={batch_groups})"
    )
    if color:
        print(_c(Color.BOLD_CYAN, "=" * 100))
        print(_c(Color.BOLD_CYAN, banner))
        print(_c(Color.BOLD_CYAN, "=" * 100))
    else:
        print("=" * 100)
        print(banner)
        print("=" * 100)

    if c is None:
        print("\n  [!] aerospike (official) not installed. pip install aerospike")

    cross_op = {"batch_read_numpy": "batch_read"}

    _print_table(
        "Avg Latency (ms)  —  lower is better  [median of round means]",
        ops,
        rust,
        c,
        async_r,
        metric="avg_ms",
        formatter=_fmt_ms,
        speedup_fn=_speedup_latency,
        color=color,
        cross_op_baseline=cross_op,
    )

    _print_table(
        "Throughput (ops/sec)  —  higher is better  [median of rounds]",
        ops,
        rust,
        c,
        async_r,
        metric="ops_per_sec",
        formatter=_fmt_ops,
        speedup_fn=_speedup_throughput,
        color=color,
        cross_op_baseline=cross_op,
    )

    # Stability indicator (stdev)
    stab_title = "Stability (stdev of round median latency, ms)  —  lower = more stable"
    print(f"\n  {_c(Color.BOLD_CYAN, stab_title) if color else stab_title}")
    w = COL_OP + 2 + COL_VAL * 3 + 6
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")
    h = f"  {'Operation':<{COL_OP}}"
    h += f" | {'Sync stdev':>{COL_VAL}}"
    if c is not None:
        h += f" | {'Official stdev':>{COL_VAL}}"
    h += f" | {'Async stdev':>{COL_VAL}}"
    print(h)
    print(_c(Color.DIM, f"  {'':─<{w}}") if color else f"  {'':─<{w}}")
    for op in ops:
        line = f"  {op:<{COL_OP}}"
        line += f" | {_fmt_ms(rust[op].get('stdev_ms')):>{COL_VAL}}"
        if c is not None:
            line += f" | {_fmt_ms(c[op].get('stdev_ms')):>{COL_VAL}}"
        line += f" | {_fmt_ms(async_r[op].get('stdev_ms')):>{COL_VAL}}"
        print(line)

    # P50/P99
    pct_ops = [op for op in ops if rust[op].get("p50_ms") is not None]
    if pct_ops:
        tail_title = "Tail Latency (ms)  [aggregated across all rounds]"
        print(f"\n  {_c(Color.BOLD_CYAN, tail_title) if color else tail_title}")
        w2 = COL_OP + 2 + 18 * 4 + 10
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'Sync p50':>16} | {'Sync p99':>16}"
        if c is not None:
            h += f" | {'Official p50':>16} | {'Official p99':>16}"
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        for op in pct_ops:
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(rust[op]['p50_ms']):>16}"
            line += f" | {_fmt_ms(rust[op]['p99_ms']):>16}"
            if c is not None:
                line += f" | {_fmt_ms(c[op].get('p50_ms')):>16}"
                line += f" | {_fmt_ms(c[op].get('p99_ms')):>16}"
            print(line)

    note = (
        f"  Note: Sync clients are measured sequentially (one op at a time).\n"
        f"  Async client uses asyncio.gather with concurrency={concurrency}.\n"
        f"  Async per-op latency reflects amortized time under concurrent load."
    )
    print(_c(Color.DIM, note) if color else note)
    print()


# ── main ─────────────────────────────────────────────────────


def main():
    global _use_color

    parser = argparse.ArgumentParser(description="Benchmark: aerospike-py (Rust) vs official aerospike (C)")
    parser.add_argument("--count", type=int, default=1000, help="Ops per round")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per operation")
    parser.add_argument("--warmup", type=int, default=WARMUP_COUNT, help="Warmup ops")
    parser.add_argument("--concurrency", type=int, default=50, help="Async concurrency")
    parser.add_argument(
        "--batch-groups",
        type=int,
        default=10,
        help="Number of groups for concurrent batch_read benchmark",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
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

    print("Benchmark config:")
    print(f"  ops/round    = {args.count:,}")
    print(f"  rounds       = {args.rounds}")
    print(f"  warmup       = {args.warmup}")
    print(f"  concurrency  = {args.concurrency}")
    print(f"  batch_groups = {args.batch_groups}")
    print(f"  server       = {args.host}:{args.port}")
    print()

    print(_c(Color.BOLD_CYAN, "[1/3]") + " aerospike-py sync (Rust) ...")
    rust = bench_rust_sync(args.host, args.port, args.count, args.rounds, args.warmup, args.batch_groups)
    print("      done")

    print(_c(Color.BOLD_CYAN, "[2/3]") + " official aerospike sync (C) ...")
    c = bench_c_sync(args.host, args.port, args.count, args.rounds, args.warmup, args.batch_groups)
    if c is None:
        print("      not installed, skipping")
    else:
        print("      done")

    print(_c(Color.BOLD_CYAN, "[3/3]") + " aerospike-py async (Rust) ...")
    async_r = asyncio.run(
        bench_rust_async(
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
        rust,
        c,
        async_r,
        args.count,
        args.rounds,
        args.concurrency,
        args.batch_groups,
        color=_use_color,
    )

    if args.report:
        from datetime import datetime as _dt

        # Determine project root (benchmark/ is one level down)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        date_slug = _dt.now().strftime("%Y-%m-%d_%H-%M")
        json_dir = args.report_dir or os.path.join(project_root, "docs", "static", "benchmark", "results")

        results = BenchmarkResults(
            rust_sync=rust,
            c_sync=c,
            rust_async=async_r,
            count=args.count,
            rounds=args.rounds,
            warmup=args.warmup,
            concurrency=args.concurrency,
            batch_groups=args.batch_groups,
        )

        # Import from same directory (script is run as `python benchmark/bench_compare.py`)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_generator import generate_report

        generate_report(results, json_dir, date_slug)
        print(_c(Color.BOLD_CYAN, "[report]") + f" Generated: {json_dir}/{date_slug}.json")


if __name__ == "__main__":
    main()
