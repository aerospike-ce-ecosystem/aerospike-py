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
import resource
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime

NAMESPACE = "test"
SET_NAME = "bench_cmp"
WARMUP_COUNT = 500
SETTLE_SECS = 0.5  # pause between phases to let I/O settle
CLIENT_TIMEOUT_MS = 10_000  # generous client-level timeout (10s) to avoid flaky benchmark failures


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
    # Advanced scenario results
    data_size: dict | None = None
    concurrency_scaling: dict | None = None
    memory_profiling: dict | None = None
    mixed_workload: dict | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    python_version: str = field(default_factory=platform.python_version)
    platform_info: str = field(default_factory=lambda: f"{platform.system()} {platform.machine()}")


# ── timing helpers ───────────────────────────────────────────


def _get_process_cpu() -> float:
    """Return total process CPU time (user + system) in seconds via getrusage."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    return ru.ru_utime + ru.ru_stime


def _measure_loop_cpu(fn, count: int) -> tuple[list[float], list[float], float]:
    """Call fn(i) for i in range(count), return (wall_times, cpu_times, process_cpu_delta) in seconds.

    Captures both wall-clock time (perf_counter) and CPU time (thread_time)
    to measure only the calling thread's CPU, excluding Tokio worker threads.
    Also captures process-level CPU (all threads including Tokio workers) via getrusage.
    """
    wall_times = []
    cpu_times = []
    proc0 = _get_process_cpu()
    for i in range(count):
        w0 = time.perf_counter()
        c0 = time.thread_time()
        fn(i)
        c1 = time.thread_time()
        w1 = time.perf_counter()
        wall_times.append(w1 - w0)
        cpu_times.append(c1 - c0)
    proc1 = _get_process_cpu()
    return wall_times, cpu_times, proc1 - proc0


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


def _compute_mad(values: list[float]) -> float:
    """Compute Median Absolute Deviation (MAD) — robust stability metric."""
    if len(values) < 2:
        return 0
    med = statistics.median(values)
    return statistics.median([abs(v - med) for v in values])


def _median_of_medians(
    rounds: list[list[float]],
    cpu_rounds: list[list[float]] | None = None,
    process_cpu_rounds: list[tuple[float, float]] | None = None,
) -> dict:
    """Given multiple rounds of per-op times, return stable metrics.

    Enhanced with p75/p90/p95/p99.9 percentiles, MAD, and optional CPU time breakdown.

    *process_cpu_rounds*: list of (process_cpu_delta_sec, wall_total_sec) per round.
    """
    round_medians = _trim_iqr([statistics.median(r) * 1000 for r in rounds])
    round_means = _trim_iqr([statistics.mean(r) * 1000 for r in rounds])
    round_throughputs = _trim_iqr([len(r) / sum(r) for r in rounds if sum(r) > 0])

    # Combine all times for full percentile distribution
    all_ms = sorted(t * 1000 for r in rounds for t in r)
    n = len(all_ms)

    result = {
        "avg_ms": statistics.median(round_means),
        "p50_ms": statistics.median(round_medians),
        "p75_ms": _compute_percentile(all_ms, 75),
        "p90_ms": _compute_percentile(all_ms, 90),
        "p95_ms": _compute_percentile(all_ms, 95),
        "p99_ms": _compute_percentile(all_ms, 99) if n >= 100 else all_ms[-1] if all_ms else None,
        "p999_ms": _compute_percentile(all_ms, 99.9) if n >= 1000 else None,
        "ops_per_sec": statistics.median(round_throughputs) if round_throughputs else 0,
        "stdev_ms": statistics.stdev(round_medians) if len(round_medians) > 1 else 0,
        "mad_ms": _compute_mad(round_medians),
    }

    # CPU time breakdown (if available)
    if cpu_rounds:
        cpu_median = statistics.median([statistics.median(r) * 1000 for r in cpu_rounds])
        wall_median = result["p50_ms"]
        result["cpu_p50_ms"] = cpu_median
        result["io_wait_p50_ms"] = round(wall_median - cpu_median, 4) if wall_median and cpu_median else None
        result["cpu_pct"] = round((cpu_median / wall_median) * 100, 1) if wall_median and wall_median > 0 else None

    # Process-level CPU (all threads including Tokio workers)
    if process_cpu_rounds:
        count_per_round = len(rounds[0]) if rounds else 0
        proc_per_op_ms = _trim_iqr(
            [(pc / count_per_round) * 1000 for pc, _ in process_cpu_rounds if count_per_round > 0]
        )
        proc_pcts = _trim_iqr([(pc / wt) * 100 for pc, wt in process_cpu_rounds if wt > 0])
        ops_per_cpu = _trim_iqr([count_per_round / pc for pc, _ in process_cpu_rounds if pc > 0])
        result["process_cpu_ms"] = round(statistics.median(proc_per_op_ms), 4) if proc_per_op_ms else None
        result["process_cpu_pct"] = round(statistics.median(proc_pcts), 1) if proc_pcts else None
        result["ops_per_cpu_sec"] = round(statistics.median(ops_per_cpu), 1) if ops_per_cpu else None

    return result


def _bulk_median(
    round_times: list[float],
    count: int,
    cpu_round_times: list[float] | None = None,
    process_cpu_round_times: list[float] | None = None,
) -> dict:
    """Given multiple round elapsed times for a bulk op, return metrics.

    If *cpu_round_times* is provided (per-round thread_time deltas), CPU
    breakdown fields are added.
    If *process_cpu_round_times* is provided (per-round process CPU deltas),
    process-level CPU fields are added.
    """
    avg_ms = _trim_iqr([(t / count) * 1000 for t in round_times])
    ops_per_sec = _trim_iqr([count / t for t in round_times if t > 0])
    result = {
        "avg_ms": statistics.median(avg_ms),
        "p50_ms": None,
        "p99_ms": None,
        "ops_per_sec": statistics.median(ops_per_sec) if ops_per_sec else 0,
        "stdev_ms": statistics.stdev(avg_ms) if len(avg_ms) > 1 else 0,
    }

    if cpu_round_times:
        cpu_avg_ms = _trim_iqr([(t / count) * 1000 for t in cpu_round_times])
        cpu_median = statistics.median(cpu_avg_ms)
        wall_median = result["avg_ms"]
        result["cpu_p50_ms"] = round(cpu_median, 4)
        result["io_wait_p50_ms"] = round(wall_median - cpu_median, 4) if wall_median else None
        result["cpu_pct"] = round((cpu_median / wall_median) * 100, 1) if wall_median and wall_median > 0 else None

    if process_cpu_round_times:
        proc_per_op_ms = _trim_iqr([(t / count) * 1000 for t in process_cpu_round_times])
        proc_pcts = _trim_iqr([(pc / wt) * 100 for pc, wt in zip(process_cpu_round_times, round_times) if wt > 0])
        ops_per_cpu = _trim_iqr([count / t for t in process_cpu_round_times if t > 0])
        result["process_cpu_ms"] = round(statistics.median(proc_per_op_ms), 4) if proc_per_op_ms else None
        result["process_cpu_pct"] = round(statistics.median(proc_pcts), 1) if proc_pcts else None
        result["ops_per_cpu_sec"] = round(statistics.median(ops_per_cpu), 1) if ops_per_cpu else None

    return result


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


_BATCH_REMOVE_CHUNK = 5000


async def _chunked_batch_remove(client, keys: list[tuple]) -> None:
    """batch_remove in chunks to avoid timeout on large key sets."""
    for i in range(0, len(keys), _BATCH_REMOVE_CHUNK):
        await client.batch_remove(keys[i : i + _BATCH_REMOVE_CHUNK])


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

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS}
    ).connect()

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
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    put_rounds = []
    put_cpu_rounds = []
    put_process_cpu_rounds = []
    for r in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                {"n": f"u{i}", "a": i, "s": i * 1.1},
            ),
            count,
        )
        gc.enable()
        put_rounds.append(wall_times)
        put_cpu_rounds.append(cpu_times)
        put_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
        for i in range(count):
            client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
    results["put"] = _median_of_medians(
        put_rounds, cpu_rounds=put_cpu_rounds, process_cpu_rounds=put_process_cpu_rounds
    )
    _settle()

    # --- seed data for GET/BATCH/QUERY ---
    _log(f"seeding {count} records ...")
    _seed_sync(client.put, prefix, count)
    _settle()

    # --- GET ---
    _log(f"GET  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    get_rounds = []
    get_cpu_rounds = []
    get_process_cpu_rounds = []
    for _ in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")),
            count,
        )
        gc.enable()
        get_rounds.append(wall_times)
        get_cpu_rounds.append(cpu_times)
        get_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["get"] = _median_of_medians(
        get_rounds, cpu_rounds=get_cpu_rounds, process_cpu_rounds=get_process_cpu_rounds
    )
    _settle()

    # --- OPERATE (read + increment in single call) ---
    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    operate_rounds = []
    operate_cpu_rounds = []
    operate_process_cpu_rounds = []
    for _ in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
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
        operate_rounds.append(wall_times)
        operate_cpu_rounds.append(cpu_times)
        operate_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["operate"] = _median_of_medians(
        operate_rounds, cpu_rounds=operate_cpu_rounds, process_cpu_rounds=operate_process_cpu_rounds
    )
    _settle()

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    remove_rounds = []
    remove_cpu_rounds = []
    remove_process_cpu_rounds = []
    for r in range(rounds):
        # seed fresh keys for removal
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(wall_times)
        remove_cpu_rounds.append(cpu_times)
        remove_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["remove"] = _median_of_medians(
        remove_rounds, cpu_rounds=remove_cpu_rounds, process_cpu_rounds=remove_process_cpu_rounds
    )
    _settle()

    # --- BATCH READ MULTI (sequential) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    multi_batch_cpu_rounds = []
    multi_batch_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        multi_batch_rounds.append(elapsed)
        multi_batch_cpu_rounds.append(cpu_elapsed)
        multi_batch_proc_rounds.append(proc_elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count, multi_batch_cpu_rounds, multi_batch_proc_rounds)
    _settle()

    # --- BATCH READ NUMPY (sequential) ---
    try:
        import numpy as np

        numpy_dtype = np.dtype([("n", "S32"), ("a", "i8"), ("s", "f8")])
        _log(f"BATCH_READ_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_batch_rounds = []
        numpy_batch_cpu_rounds = []
        numpy_batch_proc_rounds = []
        for _ in range(rounds):
            gc.disable()
            proc0 = _get_process_cpu()
            c0 = time.thread_time()
            elapsed = _measure_bulk(lambda: [client.batch_read(g, _dtype=numpy_dtype) for g in groups])
            cpu_elapsed = time.thread_time() - c0
            proc_elapsed = _get_process_cpu() - proc0
            gc.enable()
            numpy_batch_rounds.append(elapsed)
            numpy_batch_cpu_rounds.append(cpu_elapsed)
            numpy_batch_proc_rounds.append(proc_elapsed)
        results["batch_read_numpy"] = _bulk_median(
            numpy_batch_rounds, count, numpy_batch_cpu_rounds, numpy_batch_proc_rounds
        )
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
    batch_write_cpu_rounds = []
    batch_write_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        elapsed = _measure_bulk(lambda: [client.batch_operate(g, write_ops) for g in bw_groups])
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        batch_write_rounds.append(elapsed)
        batch_write_cpu_rounds.append(cpu_elapsed)
        batch_write_proc_rounds.append(proc_elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count, batch_write_cpu_rounds, batch_write_proc_rounds)
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

        numpy_write_dtype = np.dtype([("_key", "i4"), ("n", "S32"), ("a", "i8"), ("s", "f8")])
        _log(f"BATCH_WRITE_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_write_data = [
            np.array(
                [(i, f"nw_{i}".encode(), i * 10, float(i) * 0.1) for i in _group_range(g, count, batch_groups)],
                dtype=numpy_write_dtype,
            )
            for g in range(batch_groups)
        ]
        numpy_write_rounds = []
        numpy_write_cpu_rounds = []
        numpy_write_proc_rounds = []
        for _ in range(rounds):
            gc.disable()
            proc0 = _get_process_cpu()
            c0 = time.thread_time()
            elapsed = _measure_bulk(
                lambda: [client.batch_write_numpy(d, NAMESPACE, SET_NAME, numpy_write_dtype) for d in numpy_write_data]
            )
            cpu_elapsed = time.thread_time() - c0
            proc_elapsed = _get_process_cpu() - proc0
            gc.enable()
            numpy_write_rounds.append(elapsed)
            numpy_write_cpu_rounds.append(cpu_elapsed)
            numpy_write_proc_rounds.append(proc_elapsed)
        results["batch_write_numpy"] = _bulk_median(
            numpy_write_rounds, count, numpy_write_cpu_rounds, numpy_write_proc_rounds
        )
        # cleanup numpy write keys
        nw_keys = [(NAMESPACE, SET_NAME, i) for g in range(batch_groups) for i in _group_range(g, count, batch_groups)]
        for k in nw_keys:
            try:
                client.remove(k)
            except Exception:
                pass
    except ImportError:
        _log("numpy not installed, skipping BATCH_WRITE_NUMPY")
        results["batch_write_numpy"] = {
            "avg_ms": None,
            "p50_ms": None,
            "p99_ms": None,
            "ops_per_sec": None,
            "stdev_ms": None,
        }
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    query_rounds = []
    query_proc_rounds = []
    for _ in range(rounds):
        q = client.query(NAMESPACE, SET_NAME)
        gc.disable()
        proc0 = _get_process_cpu()
        elapsed = _measure_bulk(lambda q=q: q.results())
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        query_rounds.append(elapsed)
        query_proc_rounds.append(proc_elapsed)
    results["query"] = _bulk_median(query_rounds, count, process_cpu_round_times=query_proc_rounds)

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

    client = aerospike_c.client({"hosts": [(host, port)], "policies": {"timeout": CLIENT_TIMEOUT_MS}}).connect()

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
    _log(f"PUT  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    put_rounds = []
    put_cpu_rounds = []
    put_process_cpu_rounds = []
    for r in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i, _r=r: client.put(
                (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                {"n": f"u{i}", "a": i, "s": i * 1.1},
            ),
            count,
        )
        gc.enable()
        put_rounds.append(wall_times)
        put_cpu_rounds.append(cpu_times)
        put_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
        for i in range(count):
            client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
    results["put"] = _median_of_medians(
        put_rounds, cpu_rounds=put_cpu_rounds, process_cpu_rounds=put_process_cpu_rounds
    )
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    _seed_sync(client.put, prefix, count)
    _settle()

    # --- GET ---
    _log(f"GET  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    get_rounds = []
    get_cpu_rounds = []
    get_process_cpu_rounds = []
    for _ in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")),
            count,
        )
        gc.enable()
        get_rounds.append(wall_times)
        get_cpu_rounds.append(cpu_times)
        get_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["get"] = _median_of_medians(
        get_rounds, cpu_rounds=get_cpu_rounds, process_cpu_rounds=get_process_cpu_rounds
    )
    _settle()

    # --- OPERATE (read + increment in single call) ---
    from aerospike_helpers.operations import operations as as_ops_single

    _log(f"OPERATE  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    operate_rounds = []
    operate_cpu_rounds = []
    operate_process_cpu_rounds = []
    for _ in range(rounds):
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i: client.operate(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                [as_ops_single.read("n"), as_ops_single.increment("a", 1)],
            ),
            count,
        )
        gc.enable()
        operate_rounds.append(wall_times)
        operate_cpu_rounds.append(cpu_times)
        operate_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["operate"] = _median_of_medians(
        operate_rounds, cpu_rounds=operate_cpu_rounds, process_cpu_rounds=operate_process_cpu_rounds
    )
    _settle()

    # --- REMOVE ---
    _log(f"REMOVE  {count} ops x {rounds} rounds  (gc disabled, cpu tracked)")
    remove_rounds = []
    remove_cpu_rounds = []
    remove_process_cpu_rounds = []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        _seed_sync(client.put, rm_prefix, count)
        gc.disable()
        wall_times, cpu_times, proc_cpu_delta = _measure_loop_cpu(
            lambda i: client.remove((NAMESPACE, SET_NAME, f"{rm_prefix}{i}")),
            count,
        )
        gc.enable()
        remove_rounds.append(wall_times)
        remove_cpu_rounds.append(cpu_times)
        remove_process_cpu_rounds.append((proc_cpu_delta, sum(wall_times)))
    results["remove"] = _median_of_medians(
        remove_rounds, cpu_rounds=remove_cpu_rounds, process_cpu_rounds=remove_process_cpu_rounds
    )
    _settle()

    # --- BATCH READ MULTI (sequential) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    multi_batch_cpu_rounds = []
    multi_batch_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        multi_batch_rounds.append(elapsed)
        multi_batch_cpu_rounds.append(cpu_elapsed)
        multi_batch_proc_rounds.append(proc_elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count, multi_batch_cpu_rounds, multi_batch_proc_rounds)
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
    batch_write_cpu_rounds = []
    batch_write_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        elapsed = _measure_bulk(lambda: [client.batch_operate(g, c_write_ops) for g in bw_groups])
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        batch_write_rounds.append(elapsed)
        batch_write_cpu_rounds.append(cpu_elapsed)
        batch_write_proc_rounds.append(proc_elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count, batch_write_cpu_rounds, batch_write_proc_rounds)
    # cleanup batch_write keys
    for k in bw_keys:
        try:
            client.remove(k)
        except Exception:
            pass
    # C client does not support batch_write_numpy
    results["batch_write_numpy"] = {
        "avg_ms": None,
        "p50_ms": None,
        "p99_ms": None,
        "ops_per_sec": None,
        "stdev_ms": None,
    }
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    query_rounds = []
    query_proc_rounds = []
    for _ in range(rounds):
        q = client.query(NAMESPACE, SET_NAME)
        gc.disable()
        proc0 = _get_process_cpu()
        elapsed = _measure_bulk(lambda q=q: q.results())
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        query_rounds.append(elapsed)
        query_proc_rounds.append(proc_elapsed)
    results["query"] = _bulk_median(query_rounds, count, process_cpu_round_times=query_proc_rounds)

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

    client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS})
    await client.connect()

    prefix = "ra_"
    results = {}
    sem = asyncio.Semaphore(concurrency)

    # --- warmup (discarded, concurrent to warm up connection pool + Tokio threads) ---
    _log(f"warmup {warmup} ops (concurrent, concurrency={concurrency}) ...")
    warm_sem = asyncio.Semaphore(concurrency)

    async def _warm(i):
        async with warm_sem:
            key = (NAMESPACE, SET_NAME, f"_warm_ra_{i}")
            try:
                await client.put(key, {"w": i})
                await client.get(key)
                await client.remove(key)
            except Exception:
                pass

    await asyncio.gather(*[_warm(i) for i in range(warmup)])

    # --- PUT (concurrent, per-op latency tracked) ---
    _log(f"PUT  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    put_rounds = []
    put_cpu_rounds = []
    put_proc_rounds = []
    put_per_op_rounds = []
    for r in range(rounds):
        per_op_times = []

        async def _put(i, _r=r):
            async with sem:
                t0 = time.perf_counter()
                await client.put(
                    (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                    {"n": f"u{i}", "a": i, "s": i * 1.1},
                )
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[_put(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        put_rounds.append(elapsed)
        put_cpu_rounds.append(cpu_elapsed)
        put_proc_rounds.append(proc_elapsed)
        put_per_op_rounds.append(per_op_times)

        # cleanup
        await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}") for i in range(count)])
    results["put"] = _bulk_median(put_rounds, count, put_cpu_rounds, put_proc_rounds)
    results["put"]["per_op"] = _median_of_medians(put_per_op_rounds) if put_per_op_rounds else None
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    await _seed_async(client, prefix, count, concurrency)
    _settle()

    # --- GET (concurrent, per-op latency tracked) ---
    _log(f"GET  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    get_rounds = []
    get_cpu_rounds = []
    get_proc_rounds = []
    get_per_op_rounds = []
    for _ in range(rounds):
        per_op_times = []

        async def _get(i):
            async with sem:
                t0 = time.perf_counter()
                await client.get((NAMESPACE, SET_NAME, f"{prefix}{i}"))
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[_get(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        get_rounds.append(elapsed)
        get_cpu_rounds.append(cpu_elapsed)
        get_proc_rounds.append(proc_elapsed)
        get_per_op_rounds.append(per_op_times)
    results["get"] = _bulk_median(get_rounds, count, get_cpu_rounds, get_proc_rounds)
    results["get"]["per_op"] = _median_of_medians(get_per_op_rounds) if get_per_op_rounds else None
    _settle()

    # --- OPERATE (concurrent: read + increment, per-op latency tracked) ---
    from aerospike_py import OPERATOR_READ, OPERATOR_INCR

    _log(f"OPERATE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    operate_ops = [
        {"op": OPERATOR_READ, "bin": "n"},
        {"op": OPERATOR_INCR, "bin": "a", "val": 1},
    ]
    operate_rounds = []
    operate_cpu_rounds = []
    operate_proc_rounds = []
    operate_per_op_rounds = []
    for _ in range(rounds):
        per_op_times = []

        async def _operate(i):
            async with sem:
                t0 = time.perf_counter()
                await client.operate(
                    (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                    operate_ops,
                )
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[_operate(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        operate_rounds.append(elapsed)
        operate_cpu_rounds.append(cpu_elapsed)
        operate_proc_rounds.append(proc_elapsed)
        operate_per_op_rounds.append(per_op_times)
    results["operate"] = _bulk_median(operate_rounds, count, operate_cpu_rounds, operate_proc_rounds)
    results["operate"]["per_op"] = _median_of_medians(operate_per_op_rounds) if operate_per_op_rounds else None
    _settle()

    # --- REMOVE (concurrent, per-op latency tracked) ---
    _log(f"REMOVE  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled, per-op latency)")
    remove_rounds = []
    remove_cpu_rounds = []
    remove_proc_rounds = []
    remove_per_op_rounds = []
    for r in range(rounds):
        rm_prefix = f"{prefix}rm{r}_"
        await _seed_async(client, rm_prefix, count, concurrency)
        per_op_times = []

        async def _rm(i, _p=rm_prefix):
            async with sem:
                t0 = time.perf_counter()
                await client.remove((NAMESPACE, SET_NAME, f"{_p}{i}"))
                per_op_times.append(time.perf_counter() - t0)

        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[_rm(i) for i in range(count)])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        remove_rounds.append(elapsed)
        remove_cpu_rounds.append(cpu_elapsed)
        remove_proc_rounds.append(proc_elapsed)
        remove_per_op_rounds.append(per_op_times)
    results["remove"] = _bulk_median(remove_rounds, count, remove_cpu_rounds, remove_proc_rounds)
    results["remove"]["per_op"] = _median_of_medians(remove_per_op_rounds) if remove_per_op_rounds else None
    _settle()

    # --- BATCH READ MULTI (concurrent) ---
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    _log(f"BATCH_READ  {batch_groups} groups x {rounds} rounds  (gc disabled)")
    groups = [keys[i::batch_groups] for i in range(batch_groups)]
    multi_batch_rounds = []
    multi_batch_cpu_rounds = []
    multi_batch_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[client.batch_read(g) for g in groups])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        multi_batch_rounds.append(elapsed)
        multi_batch_cpu_rounds.append(cpu_elapsed)
        multi_batch_proc_rounds.append(proc_elapsed)
    results["batch_read"] = _bulk_median(multi_batch_rounds, count, multi_batch_cpu_rounds, multi_batch_proc_rounds)
    _settle()

    # --- BATCH READ NUMPY (concurrent) ---
    try:
        import numpy as np

        numpy_dtype = np.dtype([("n", "S32"), ("a", "i8"), ("s", "f8")])
        _log(f"BATCH_READ_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_batch_rounds = []
        numpy_batch_cpu_rounds = []
        numpy_batch_proc_rounds = []
        for _ in range(rounds):
            gc.disable()
            proc0 = _get_process_cpu()
            c0 = time.thread_time()
            t0 = time.perf_counter()
            await asyncio.gather(*[client.batch_read(g, _dtype=numpy_dtype) for g in groups])
            elapsed = time.perf_counter() - t0
            cpu_elapsed = time.thread_time() - c0
            proc_elapsed = _get_process_cpu() - proc0
            gc.enable()
            numpy_batch_rounds.append(elapsed)
            numpy_batch_cpu_rounds.append(cpu_elapsed)
            numpy_batch_proc_rounds.append(proc_elapsed)
        results["batch_read_numpy"] = _bulk_median(
            numpy_batch_rounds, count, numpy_batch_cpu_rounds, numpy_batch_proc_rounds
        )
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
    batch_write_cpu_rounds = []
    batch_write_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        await asyncio.gather(*[client.batch_operate(g, write_ops) for g in bw_groups])
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        batch_write_rounds.append(elapsed)
        batch_write_cpu_rounds.append(cpu_elapsed)
        batch_write_proc_rounds.append(proc_elapsed)
    results["batch_write"] = _bulk_median(batch_write_rounds, count, batch_write_cpu_rounds, batch_write_proc_rounds)
    # cleanup batch_write keys
    await _chunked_batch_remove(client, bw_keys)
    _settle()

    # --- BATCH WRITE NUMPY (concurrent) ---
    try:
        import numpy as np

        numpy_write_dtype = np.dtype([("_key", "i4"), ("n", "S32"), ("a", "i8"), ("s", "f8")])
        _log(f"BATCH_WRITE_NUMPY  {batch_groups} groups x {rounds} rounds  (gc disabled)")
        numpy_write_data = [
            np.array(
                [(i, f"nw_{i}".encode(), i * 10, float(i) * 0.1) for i in _group_range(g, count, batch_groups)],
                dtype=numpy_write_dtype,
            )
            for g in range(batch_groups)
        ]
        numpy_write_rounds = []
        numpy_write_cpu_rounds = []
        numpy_write_proc_rounds = []
        for _ in range(rounds):
            gc.disable()
            proc0 = _get_process_cpu()
            c0 = time.thread_time()
            t0 = time.perf_counter()
            await asyncio.gather(
                *[client.batch_write_numpy(d, NAMESPACE, SET_NAME, numpy_write_dtype) for d in numpy_write_data]
            )
            elapsed = time.perf_counter() - t0
            cpu_elapsed = time.thread_time() - c0
            proc_elapsed = _get_process_cpu() - proc0
            gc.enable()
            numpy_write_rounds.append(elapsed)
            numpy_write_cpu_rounds.append(cpu_elapsed)
            numpy_write_proc_rounds.append(proc_elapsed)
        results["batch_write_numpy"] = _bulk_median(
            numpy_write_rounds, count, numpy_write_cpu_rounds, numpy_write_proc_rounds
        )
        # cleanup numpy write keys
        nw_keys = [(NAMESPACE, SET_NAME, i) for g in range(batch_groups) for i in _group_range(g, count, batch_groups)]
        await _chunked_batch_remove(client, nw_keys)
    except ImportError:
        _log("numpy not installed, skipping BATCH_WRITE_NUMPY")
        results["batch_write_numpy"] = {
            "avg_ms": None,
            "p50_ms": None,
            "p99_ms": None,
            "ops_per_sec": None,
            "stdev_ms": None,
        }
    _settle()

    # --- QUERY ---
    _log(f"QUERY  x {rounds} rounds  (gc disabled)")
    query_rounds = []
    query_cpu_rounds = []
    query_proc_rounds = []
    for _ in range(rounds):
        gc.disable()
        proc0 = _get_process_cpu()
        c0 = time.thread_time()
        t0 = time.perf_counter()
        async_q = client.query(NAMESPACE, SET_NAME)
        await async_q.results()
        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.thread_time() - c0
        proc_elapsed = _get_process_cpu() - proc0
        gc.enable()
        query_rounds.append(elapsed)
        query_cpu_rounds.append(cpu_elapsed)
        query_proc_rounds.append(proc_elapsed)
    results["query"] = _bulk_median(query_rounds, count, query_cpu_rounds, query_proc_rounds)

    # cleanup
    _log("cleanup ...")
    await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)])
    await client.close()

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


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.3f}ms"


def _fmt_ops(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:,.0f}/s"


def _fmt_eff(val: float | None) -> str:
    """Format ops/CPU-sec with K/M suffixes."""
    if val is None:
        return "-"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return f"{val:.0f}"


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
        print(_c(Color.BOLD_CYAN, "=" * 100))
        print(_c(Color.BOLD_CYAN, banner))
        print(_c(Color.BOLD_CYAN, "=" * 100))
    else:
        print("=" * 100)
        print(banner)
        print("=" * 100)

    if c is None:
        print("\n  [!] aerospike (official) not installed. pip install aerospike")

    cross_op = {"batch_read_numpy": "batch_read", "batch_write_numpy": "batch_write"}

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

    # P50/P95/P99/P99.9
    pct_ops = [op for op in ops if rust[op].get("p50_ms") is not None]
    if pct_ops:
        tail_title = "Tail Latency (ms)  [aggregated across all rounds]"
        print(f"\n  {_c(Color.BOLD_CYAN, tail_title) if color else tail_title}")
        w2 = COL_OP + 2 + 14 * 8 + 20
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'Sync p50':>12} | {'p95':>10} | {'p99':>10} | {'p99.9':>10}"
        if c is not None:
            h += f" | {'Off. p50':>12} | {'p95':>10} | {'p99':>10} | {'p99.9':>10}"
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w2}}") if color else f"  {'':─<{w2}}")
        for op in pct_ops:
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(rust[op]['p50_ms']):>12}"
            line += f" | {_fmt_ms(rust[op].get('p95_ms')):>10}"
            line += f" | {_fmt_ms(rust[op]['p99_ms']):>10}"
            line += f" | {_fmt_ms(rust[op].get('p999_ms')):>10}"
            if c is not None:
                line += f" | {_fmt_ms(c[op].get('p50_ms')):>12}"
                line += f" | {_fmt_ms(c[op].get('p95_ms')):>10}"
                line += f" | {_fmt_ms(c[op].get('p99_ms')):>10}"
                line += f" | {_fmt_ms(c[op].get('p999_ms')):>10}"
            print(line)

    # CPU Efficiency (thread CPU, process CPU, ops/CPU-sec)
    cpu_ops = [op for op in ops if rust[op].get("cpu_p50_ms") is not None or rust[op].get("process_cpu_ms") is not None]
    if cpu_ops:
        has_c_cpu = c is not None and any(
            c[op].get("cpu_p50_ms") is not None or c[op].get("process_cpu_ms") is not None for op in cpu_ops
        )
        cpu_title = "CPU Efficiency  [thread CPU, process CPU (all threads), ops/CPU-sec]"
        print(f"\n  {_c(Color.BOLD_CYAN, cpu_title) if color else cpu_title}")
        # Build header
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'Wall p50':>12} | {'Thr.CPU':>10} | {'Proc.CPU':>10} | {'Proc.CPU%':>10} | {'Ops/CPU-s':>10}"
        if has_c_cpu:
            h += f" | {'Off.Wall':>12} | {'Off.Thr':>10} | {'Off.Proc':>10} | {'Off.CPU%':>10} | {'Off.Ops/CPU':>11}"
            h += f" | {'Eff. vs Off.':>{COL_SP}}"
        w3 = len(h)
        print(_c(Color.DIM, f"  {'':─<{w3}}") if color else f"  {'':─<{w3}}")
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w3}}") if color else f"  {'':─<{w3}}")
        for op in cpu_ops:
            # For bulk ops (batch), p50_ms is None; fall back to avg_ms
            rust_wall = rust[op].get("p50_ms") or rust[op].get("avg_ms")
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(rust_wall):>12}"
            line += f" | {_fmt_ms(rust[op].get('cpu_p50_ms')):>10}"
            line += f" | {_fmt_ms(rust[op].get('process_cpu_ms')):>10}"
            proc_pct = rust[op].get("process_cpu_pct")
            line += f" | {f'{proc_pct:.1f}%' if proc_pct is not None else '-':>10}"
            line += f" | {_fmt_eff(rust[op].get('ops_per_cpu_sec')):>10}"
            if has_c_cpu:
                c_data = c[op] if c is not None else {}
                c_wall = c_data.get("p50_ms") or c_data.get("avg_ms")
                if c_data.get("cpu_p50_ms") is not None or c_data.get("process_cpu_ms") is not None:
                    line += f" | {_fmt_ms(c_wall):>12}"
                    line += f" | {_fmt_ms(c_data.get('cpu_p50_ms')):>10}"
                    line += f" | {_fmt_ms(c_data.get('process_cpu_ms')):>10}"
                    c_proc_pct = c_data.get("process_cpu_pct")
                    line += f" | {f'{c_proc_pct:.1f}%' if c_proc_pct is not None else '-':>10}"
                    line += f" | {_fmt_eff(c_data.get('ops_per_cpu_sec')):>11}"
                    # Efficiency comparison: ops/CPU-sec (higher = GREEN = better)
                    rust_eff = rust[op].get("ops_per_cpu_sec")
                    c_eff = c_data.get("ops_per_cpu_sec")
                    if rust_eff and c_eff and c_eff > 0:
                        pct = (rust_eff - c_eff) / c_eff * 100
                        if pct >= 0:
                            sp = f"+{pct:.1f}%"
                            sp = _c(Color.GREEN, sp) if color else sp
                        else:
                            sp = f"{pct:.1f}%"
                            sp = _c(Color.RED, sp) if color else sp
                        line += f" | {_lpad(sp, COL_SP)}"
                    else:
                        line += f" | {'-':>{COL_SP}}"
                else:
                    line += f" | {'-':>12} | {'-':>10} | {'-':>10} | {'-':>10} | {'-':>11} | {'-':>{COL_SP}}"
            print(line)

    # Async Per-Op Latency Distribution
    async_per_op_ops = [op for op in ops if async_r[op].get("per_op") is not None]
    if async_per_op_ops:
        async_title = "Async Per-Op Latency (ms)  [individual operation latency under concurrent load]"
        print(f"\n  {_c(Color.BOLD_CYAN, async_title) if color else async_title}")
        w4 = COL_OP + 2 + 12 * 5 + 16
        print(_c(Color.DIM, f"  {'':─<{w4}}") if color else f"  {'':─<{w4}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'p50':>10} | {'p95':>10} | {'p99':>10} | {'p99.9':>10} | {'MAD':>10}"
        print(h)
        print(_c(Color.DIM, f"  {'':─<{w4}}") if color else f"  {'':─<{w4}}")
        for op in async_per_op_ops:
            po = async_r[op]["per_op"]
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(po.get('p50_ms')):>10}"
            line += f" | {_fmt_ms(po.get('p95_ms')):>10}"
            line += f" | {_fmt_ms(po.get('p99_ms')):>10}"
            line += f" | {_fmt_ms(po.get('p999_ms')):>10}"
            line += f" | {_fmt_ms(po.get('mad_ms')):>10}"
            print(line)

    note = (
        f"  Note: Sync clients are measured sequentially (one op at a time).\n"
        f"  Async client uses asyncio.gather with concurrency={concurrency}.\n"
        f"  Thr.CPU: Python calling thread CPU only. Proc.CPU: entire process CPU (Tokio workers included).\n"
        f"  Proc.CPU% can exceed 100% with multiple threads. Ops/CPU-s: ops per CPU-second (higher = more efficient).\n"
        f"  Rust async utilizes CPU during I/O wait for other tasks → high Proc.CPU% with high Ops/CPU-s.\n"
        f"  C sync blocks threads idle during I/O → low CPU% but wastes available CPU capacity."
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

CONCURRENCY_LEVELS = [1, 10, 50, 100, 200, 500]

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
    for i in range(count):
        client.put((NAMESPACE, SET_NAME, f"{prefix}{i}"), _make_bins_sized(num_bins, value_size, i))


async def _seed_sized_async(client, prefix: str, count: int, num_bins: int, value_size: int, concurrency: int):
    sem = asyncio.Semaphore(concurrency)

    async def _p(i):
        async with sem:
            await client.put((NAMESPACE, SET_NAME, f"{prefix}{i}"), _make_bins_sized(num_bins, value_size, i))

    await asyncio.gather(*[_p(i) for i in range(count)])


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

    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_ds_{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass

    data = []
    for label, num_bins, value_size in DATA_SIZE_PROFILES:
        prefix = f"ds_{num_bins}_{value_size}_"
        _log(f"Data Size: {label}")

        _log(f"  PUT {count} ops x {rounds} rounds")
        put_rounds, put_cpu, put_proc = [], [], []
        for r in range(rounds):
            gc.disable()
            wt, ct, pcd = _measure_loop_cpu(
                lambda i, _r=r: client.put(
                    (NAMESPACE, SET_NAME, f"{prefix}p{_r}_{i}"),
                    _make_bins_sized(num_bins, value_size, i),
                ),
                count,
            )
            gc.enable()
            put_rounds.append(wt)
            put_cpu.append(ct)
            put_proc.append((pcd, sum(wt)))
            for i in range(count):
                try:
                    client.remove((NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}"))
                except Exception:
                    pass

        _seed_sized(client, prefix, count, num_bins, value_size)
        _settle()

        _log(f"  GET {count} ops x {rounds} rounds")
        get_rounds, get_cpu, get_proc = [], [], []
        for _ in range(rounds):
            gc.disable()
            wt, ct, pcd = _measure_loop_cpu(lambda i: client.get((NAMESPACE, SET_NAME, f"{prefix}{i}")), count)
            gc.enable()
            get_rounds.append(wt)
            get_cpu.append(ct)
            get_proc.append((pcd, sum(wt)))

        _cleanup_sync(client.remove, prefix, count)
        _settle()

        data.append(
            {
                "label": label,
                "num_bins": num_bins,
                "value_size": value_size,
                "put": _median_of_medians(put_rounds, cpu_rounds=put_cpu, process_cpu_rounds=put_proc),
                "get": _median_of_medians(get_rounds, cpu_rounds=get_cpu, process_cpu_rounds=get_proc),
            }
        )

    client.close()
    return {"count": count, "rounds": rounds, "data": data}


def _print_data_size(result: dict):
    header = f"Data Size Scaling ({result['count']:,} ops x {result['rounds']} rounds)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 28 + 14 * 8 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Profile':<26} | {'PUT p50':>10} | {'PUT p99':>10} | {'PUT CPU%':>8} | {'Proc.CPU%':>10}"
    h += f" | {'GET p50':>10} | {'GET p99':>10} | {'GET CPU%':>8} | {'Proc.CPU%':>10}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        pcp = e["put"].get("cpu_pct")
        ppcp = e["put"].get("process_cpu_pct")
        gcp = e["get"].get("cpu_pct")
        gpcp = e["get"].get("process_cpu_pct")
        line = f"  {e['label']:<26}"
        line += f" | {_fmt_ms(e['put'].get('p50_ms')):>10} | {_fmt_ms(e['put'].get('p99_ms')):>10}"
        line += f" | {f'{pcp:.1f}%' if pcp else '-':>8}"
        line += f" | {f'{ppcp:.1f}%' if ppcp is not None else '-':>10}"
        line += f" | {_fmt_ms(e['get'].get('p50_ms')):>10} | {_fmt_ms(e['get'].get('p99_ms')):>10}"
        line += f" | {f'{gcp:.1f}%' if gcp else '-':>8}"
        line += f" | {f'{gpcp:.1f}%' if gpcp is not None else '-':>10}"
        print(line)


# ── Scenario: Concurrency Scaling ─────────────────────────────


def bench_concurrency_scaling(host: str, port: int, count: int, rounds: int, warmup: int) -> dict:
    from aerospike_py import AsyncClient

    data = []

    async def _run():
        client = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS})
        await client.connect()
        _log(f"warmup {warmup} ops ...")
        for i in range(warmup):
            key = (NAMESPACE, SET_NAME, f"_warm_cs_{i}")
            try:
                await client.put(key, {"w": i})
                await client.get(key)
                await client.remove(key)
            except Exception:
                pass

        prefix = "cs_"
        _log(f"seeding {count} records ...")
        await _seed_sized_async(client, prefix, count, 5, 10, 50)
        _settle()

        for conc in CONCURRENCY_LEVELS:
            _log(f"Concurrency={conc}: PUT+GET {count} ops x {rounds} rounds")
            sem = asyncio.Semaphore(conc)

            put_bulk, put_po, put_proc = [], [], []
            for r in range(rounds):
                per_op = []

                async def _put(i, _r=r):
                    async with sem:
                        t0 = time.perf_counter()
                        await client.put((NAMESPACE, SET_NAME, f"{prefix}cp{_r}_{i}"), {"n": f"u{i}", "a": i})
                        per_op.append(time.perf_counter() - t0)

                gc.disable()
                proc0 = _get_process_cpu()
                t0 = time.perf_counter()
                await asyncio.gather(*[_put(i) for i in range(count)])
                elapsed = time.perf_counter() - t0
                proc_elapsed = _get_process_cpu() - proc0
                gc.enable()
                put_bulk.append(elapsed)
                put_po.append(per_op)
                put_proc.append(proc_elapsed)
                await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}cp{r}_{i}") for i in range(count)])

            pm = _bulk_median(put_bulk, count, process_cpu_round_times=put_proc)
            pm["per_op"] = _median_of_medians(put_po)

            get_bulk, get_po, get_proc = [], [], []
            for _ in range(rounds):
                per_op = []

                async def _get(i):
                    async with sem:
                        t0 = time.perf_counter()
                        await client.get((NAMESPACE, SET_NAME, f"{prefix}{i}"))
                        per_op.append(time.perf_counter() - t0)

                gc.disable()
                proc0 = _get_process_cpu()
                t0 = time.perf_counter()
                await asyncio.gather(*[_get(i) for i in range(count)])
                elapsed = time.perf_counter() - t0
                proc_elapsed = _get_process_cpu() - proc0
                gc.enable()
                get_bulk.append(elapsed)
                get_po.append(per_op)
                get_proc.append(proc_elapsed)

            gm = _bulk_median(get_bulk, count, process_cpu_round_times=get_proc)
            gm["per_op"] = _median_of_medians(get_po)
            _settle()
            data.append({"concurrency": conc, "put": pm, "get": gm})

        await _chunked_batch_remove(client, [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)])
        await client.close()

    asyncio.run(_run())
    return {"count": count, "rounds": rounds, "data": data}


def _print_concurrency_scaling(result: dict):
    header = f"Concurrency Scaling ({result['count']:,} ops x {result['rounds']} rounds, AsyncClient)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 12 + 14 * 10 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    h = f"  {'Conc':>6} | {'PUT ops/s':>12} | {'PUT p50':>10} | {'PUT p95':>10} | {'PUT p99':>10} | {'PUT Ops/CPU':>11}"
    h += f" | {'GET ops/s':>12} | {'GET p50':>10} | {'GET p95':>10} | {'GET p99':>10} | {'GET Ops/CPU':>11}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")
    for e in result["data"]:
        ppo = e["put"].get("per_op", {})
        gpo = e["get"].get("per_op", {})
        line = f"  {e['concurrency']:>6}"
        line += f" | {_fmt_ops(e['put'].get('ops_per_sec')):>12}"
        line += (
            f" | {_fmt_ms(ppo.get('p50_ms')):>10} | {_fmt_ms(ppo.get('p95_ms')):>10} | {_fmt_ms(ppo.get('p99_ms')):>10}"
        )
        line += f" | {_fmt_eff(e['put'].get('ops_per_cpu_sec')):>11}"
        line += f" | {_fmt_ops(e['get'].get('ops_per_sec')):>12}"
        line += (
            f" | {_fmt_ms(gpo.get('p50_ms')):>10} | {_fmt_ms(gpo.get('p95_ms')):>10} | {_fmt_ms(gpo.get('p99_ms')):>10}"
        )
        line += f" | {_fmt_eff(e['get'].get('ops_per_cpu_sec')):>11}"
        print(line)


# ── Scenario: Memory Profiling ────────────────────────────────


def bench_memory(host: str, port: int, count: int, warmup: int) -> dict:
    import aerospike_py

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker", "timeout": CLIENT_TIMEOUT_MS}
    ).connect()
    _log(f"warmup {warmup} ops ...")
    for i in range(min(warmup, 200)):
        key = (NAMESPACE, SET_NAME, f"_warm_mem_{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass

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
        _log(f"warmup {warmup} ops ...")
        for i in range(warmup):
            key = (NAMESPACE, SET_NAME, f"_warm_mx_{i}")
            try:
                await client.put(key, {"w": i})
                await client.get(key)
                await client.remove(key)
            except Exception:
                pass

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
    parser.add_argument("--concurrency", type=int, default=50, help="Async concurrency")
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

    rust, c, async_r = {}, None, {}

    if run_basic:
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

    if args.report:
        from datetime import datetime as _dt

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
            data_size=data_size_result,
            concurrency_scaling=concurrency_result,
            memory_profiling=memory_result,
            mixed_workload=mixed_result,
        )

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_generator import generate_report

        generate_report(results, json_dir, date_slug)
        print(_c(Color.BOLD_CYAN, "[report]") + f" Generated: {json_dir}/{date_slug}.json")


if __name__ == "__main__":
    main()
