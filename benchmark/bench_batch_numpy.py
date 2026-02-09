"""Benchmark: batch_read (dict) vs batch_read_numpy (numpy structured array).

Four scenarios comparing aerospike-py's batch_read return formats:
  1. Record Count Scaling   – varying record counts
  2. Bin Count Scaling      – varying bin counts
  3. Post-Processing        – raw read → column access → filter → aggregation
  4. Memory Usage           – peak memory via tracemalloc

Usage:
    python benchmark/bench_batch_numpy.py \
        --scenario all|record_scaling|bin_scaling|post_processing|memory \
        --rounds 10 --warmup 200 --concurrency 50 --batch-groups 10 \
        --host 127.0.0.1 --port 3000 \
        --report --report-dir DIR --no-color
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import os
import platform
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

# Re-use helpers from bench_compare
from bench_compare import (
    Color,
    _bulk_median,
    _c,
    _log,
    _measure_bulk,
    _settle,
)

NAMESPACE = "test"
SET_NAME = "bench_np"
WARMUP_COUNT = 200

RECORD_COUNTS = [100, 500, 1000, 5000, 10000]
BIN_COUNTS = [1, 3, 5, 10, 20]
POST_STAGES = [
    ("raw_read", "Raw Read"),
    ("read_column_access", "Read + Column Access"),
    ("read_filter", "Read + Filter"),
    ("read_aggregation", "Read + Aggregation"),
]

_use_color = True


# ── data helpers ──────────────────────────────────────────────


def _make_bins(num_bins: int, i: int) -> dict:
    """Create bin data for record i with num_bins bins."""
    return {f"bin{b}": float(i * num_bins + b) * 0.1 for b in range(num_bins)}


def _make_dtype(num_bins: int) -> np.dtype:
    """Create numpy dtype for num_bins float bins."""
    return np.dtype([(f"bin{b}", "f8") for b in range(num_bins)])


def _seed_data(client, prefix: str, count: int, num_bins: int):
    """Seed count records with num_bins bins using sync client."""
    for i in range(count):
        client.put(
            (NAMESPACE, SET_NAME, f"{prefix}{i}"),
            _make_bins(num_bins, i),
        )


def _cleanup_data(client, prefix: str, count: int):
    """Remove seeded records."""
    for i in range(count):
        try:
            client.remove((NAMESPACE, SET_NAME, f"{prefix}{i}"))
        except Exception:
            pass


async def _seed_data_async(client, prefix: str, count: int, num_bins: int, concurrency: int):
    """Seed count records async."""
    sem = asyncio.Semaphore(concurrency)

    async def _p(i):
        async with sem:
            await client.put(
                (NAMESPACE, SET_NAME, f"{prefix}{i}"),
                _make_bins(num_bins, i),
            )

    await asyncio.gather(*[_p(i) for i in range(count)])


async def _cleanup_data_async(client, prefix: str, count: int):
    """Remove seeded records async."""
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    await client.batch_remove(keys)


# ── warmup ────────────────────────────────────────────────────


def _warmup_sync(client, warmup: int):
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_np_{i}")
        try:
            client.put(key, {"w": i})
            client.get(key)
            client.remove(key)
        except Exception:
            pass


async def _warmup_async(client, warmup: int):
    _log(f"warmup {warmup} ops ...")
    for i in range(warmup):
        key = (NAMESPACE, SET_NAME, f"_warm_npa_{i}")
        try:
            await client.put(key, {"w": i})
            await client.get(key)
            await client.remove(key)
        except Exception:
            pass


# ── formatting helpers ────────────────────────────────────────


def _visible_len(s: str) -> int:
    import re

    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _lpad(s: str, width: int) -> str:
    pad = width - _visible_len(s)
    return " " * max(0, pad) + s


def _rpad(s: str, width: int) -> str:
    pad = width - _visible_len(s)
    return s + " " * max(0, pad)


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.3f}ms"


def _speedup(target: float | None, baseline: float | None) -> str:
    if target is None or baseline is None or target <= 0 or baseline <= 0:
        return "-"
    ratio = baseline / target
    if ratio >= 1.0:
        text = f"{ratio:.1f}x faster"
        return _c(Color.GREEN, text) if _use_color else text
    text = f"{1 / ratio:.1f}x slower"
    return _c(Color.RED, text) if _use_color else text


# ── Scenario 1: Record Count Scaling ─────────────────────────


def _run_record_scaling(
    host: str,
    port: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict:
    import aerospike_py
    from aerospike_py import AsyncClient

    fixed_bins = 5
    dtype = _make_dtype(fixed_bins)
    data = []

    # Sync client
    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": "docker"}).connect()
    _warmup_sync(client, warmup)

    for rc in RECORD_COUNTS:
        prefix = f"rs_{rc}_"
        _log(f"Record Scaling: seeding {rc} records (bins={fixed_bins}) ...")
        _seed_data(client, prefix, rc, fixed_bins)
        _settle()

        keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(rc)]
        groups = [keys[i::batch_groups] for i in range(batch_groups)]

        # batch_read sync
        _log(f"  batch_read(Sync) {rc} records x {rounds} rounds")
        br_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
            gc.enable()
            br_rounds.append(elapsed)
        br_sync = _bulk_median(br_rounds, rc)

        # batch_read_numpy sync
        _log(f"  batch_read_numpy(Sync) {rc} records x {rounds} rounds")
        np_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(lambda: [client.batch_read(g, _dtype=dtype) for g in groups])
            gc.enable()
            np_rounds.append(elapsed)
        np_sync = _bulk_median(np_rounds, rc)

        _cleanup_data(client, prefix, rc)
        _settle()

        data.append(
            {
                "record_count": rc,
                "batch_read_sync": br_sync,
                "batch_read_numpy_sync": np_sync,
            }
        )

    client.close()

    # Async client
    async def _async_part():
        aclient = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker"})
        await aclient.connect()
        await _warmup_async(aclient, warmup)

        for entry in data:
            rc = entry["record_count"]
            prefix = f"ra_{rc}_"
            _log(f"Record Scaling (Async): seeding {rc} records (bins={fixed_bins}) ...")
            await _seed_data_async(aclient, prefix, rc, fixed_bins, concurrency)
            _settle()

            keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(rc)]
            groups = [keys[i::batch_groups] for i in range(batch_groups)]

            # batch_read async
            _log(f"  batch_read(Async) {rc} records x {rounds} rounds")
            br_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await asyncio.gather(*[aclient.batch_read(g) for g in groups])
                elapsed = time.perf_counter() - t0
                gc.enable()
                br_rounds.append(elapsed)
            entry["batch_read_async"] = _bulk_median(br_rounds, rc)

            # batch_read_numpy async
            _log(f"  batch_read_numpy(Async) {rc} records x {rounds} rounds")
            np_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in groups])
                elapsed = time.perf_counter() - t0
                gc.enable()
                np_rounds.append(elapsed)
            entry["batch_read_numpy_async"] = _bulk_median(np_rounds, rc)

            await _cleanup_data_async(aclient, prefix, rc)
            _settle()

        await aclient.close()

    asyncio.run(_async_part())

    return {"fixed_bins": fixed_bins, "data": data}


# ── Scenario 2: Bin Count Scaling ────────────────────────────


def _run_bin_scaling(
    host: str,
    port: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict:
    import aerospike_py
    from aerospike_py import AsyncClient

    fixed_records = 1000
    data = []

    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": "docker"}).connect()
    _warmup_sync(client, warmup)

    for bc in BIN_COUNTS:
        prefix = f"bs_{bc}_"
        dtype = _make_dtype(bc)
        _log(f"Bin Scaling: seeding {fixed_records} records (bins={bc}) ...")
        _seed_data(client, prefix, fixed_records, bc)
        _settle()

        keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(fixed_records)]
        groups = [keys[i::batch_groups] for i in range(batch_groups)]

        # batch_read sync
        _log(f"  batch_read(Sync) bins={bc} x {rounds} rounds")
        br_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(lambda: [client.batch_read(g) for g in groups])
            gc.enable()
            br_rounds.append(elapsed)
        br_sync = _bulk_median(br_rounds, fixed_records)

        # batch_read_numpy sync
        _log(f"  batch_read_numpy(Sync) bins={bc} x {rounds} rounds")
        np_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(lambda: [client.batch_read(g, _dtype=dtype) for g in groups])
            gc.enable()
            np_rounds.append(elapsed)
        np_sync = _bulk_median(np_rounds, fixed_records)

        _cleanup_data(client, prefix, fixed_records)
        _settle()

        data.append(
            {
                "bin_count": bc,
                "batch_read_sync": br_sync,
                "batch_read_numpy_sync": np_sync,
            }
        )

    client.close()

    # Async part
    async def _async_part():
        aclient = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker"})
        await aclient.connect()
        await _warmup_async(aclient, warmup)

        for entry in data:
            bc = entry["bin_count"]
            prefix = f"ba_{bc}_"
            dtype = _make_dtype(bc)
            _log(f"Bin Scaling (Async): seeding {fixed_records} records (bins={bc}) ...")
            await _seed_data_async(aclient, prefix, fixed_records, bc, concurrency)
            _settle()

            keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(fixed_records)]
            groups = [keys[i::batch_groups] for i in range(batch_groups)]

            _log(f"  batch_read(Async) bins={bc} x {rounds} rounds")
            br_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await asyncio.gather(*[aclient.batch_read(g) for g in groups])
                elapsed = time.perf_counter() - t0
                gc.enable()
                br_rounds.append(elapsed)
            entry["batch_read_async"] = _bulk_median(br_rounds, fixed_records)

            _log(f"  batch_read_numpy(Async) bins={bc} x {rounds} rounds")
            np_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in groups])
                elapsed = time.perf_counter() - t0
                gc.enable()
                np_rounds.append(elapsed)
            entry["batch_read_numpy_async"] = _bulk_median(np_rounds, fixed_records)

            await _cleanup_data_async(aclient, prefix, fixed_records)
            _settle()

        await aclient.close()

    asyncio.run(_async_part())

    return {"fixed_records": fixed_records, "data": data}


# ── Scenario 3: Post-Processing ──────────────────────────────


def _run_post_processing(
    host: str,
    port: int,
    rounds: int,
    warmup: int,
    concurrency: int,
    batch_groups: int,
) -> dict:
    import aerospike_py
    from aerospike_py import AsyncClient

    record_count = 1000
    num_bins = 5
    dtype = _make_dtype(num_bins)
    prefix = "pp_"
    data = []

    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": "docker"}).connect()
    _warmup_sync(client, warmup)

    _log(f"Post-Processing: seeding {record_count} records (bins={num_bins}) ...")
    _seed_data(client, prefix, record_count, num_bins)
    _settle()

    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(record_count)]
    groups = [keys[i::batch_groups] for i in range(batch_groups)]

    # Define stage functions for dict (sync)
    def _dict_raw_read():
        for g in groups:
            client.batch_read(g)

    def _dict_column_access():
        for g in groups:
            results = client.batch_read(g)
            _ = [br.record[2]["bin0"] for br in results.batch_records if br.record is not None]

    def _dict_filter():
        for g in groups:
            results = client.batch_read(g)
            _ = [br for br in results.batch_records if br.record is not None and br.record[2].get("bin0", 0) > 50.0]

    def _dict_aggregation():
        for g in groups:
            results = client.batch_read(g)
            _ = sum(br.record[2]["bin0"] for br in results.batch_records if br.record is not None)

    # Define stage functions for numpy (sync)
    def _numpy_raw_read():
        for g in groups:
            client.batch_read(g, _dtype=dtype)

    def _numpy_column_access():
        for g in groups:
            result = client.batch_read(g, _dtype=dtype)
            _ = result.batch_records["bin0"]

    def _numpy_filter():
        for g in groups:
            result = client.batch_read(g, _dtype=dtype)
            arr = result.batch_records
            _ = arr[arr["bin0"] > 50.0]

    def _numpy_aggregation():
        for g in groups:
            result = client.batch_read(g, _dtype=dtype)
            _ = result.batch_records["bin0"].sum()

    dict_fns = [_dict_raw_read, _dict_column_access, _dict_filter, _dict_aggregation]
    numpy_fns = [
        _numpy_raw_read,
        _numpy_column_access,
        _numpy_filter,
        _numpy_aggregation,
    ]

    for (stage_key, stage_label), dict_fn, numpy_fn in zip(POST_STAGES, dict_fns, numpy_fns):
        _log(f"  Post-Processing: {stage_label} (Sync)")

        # batch_read sync
        br_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(dict_fn)
            gc.enable()
            br_rounds.append(elapsed)
        br_sync = _bulk_median(br_rounds, record_count)

        # batch_read_numpy sync
        np_rounds = []
        for _ in range(rounds):
            gc.disable()
            elapsed = _measure_bulk(numpy_fn)
            gc.enable()
            np_rounds.append(elapsed)
        np_sync = _bulk_median(np_rounds, record_count)

        data.append(
            {
                "stage": stage_key,
                "stage_label": stage_label,
                "batch_read_sync": br_sync,
                "batch_read_numpy_sync": np_sync,
            }
        )

    _cleanup_data(client, prefix, record_count)
    client.close()

    # Async part
    async def _async_part():
        aclient = AsyncClient({"hosts": [(host, port)], "cluster_name": "docker"})
        await aclient.connect()
        await _warmup_async(aclient, warmup)

        a_prefix = "ppa_"
        _log(f"Post-Processing (Async): seeding {record_count} records (bins={num_bins}) ...")
        await _seed_data_async(aclient, a_prefix, record_count, num_bins, concurrency)
        _settle()

        a_keys = [(NAMESPACE, SET_NAME, f"{a_prefix}{i}") for i in range(record_count)]
        a_groups = [a_keys[i::batch_groups] for i in range(batch_groups)]

        # Async stage functions for dict
        async def _adict_raw_read():
            await asyncio.gather(*[aclient.batch_read(g) for g in a_groups])

        async def _adict_column_access():
            all_results = await asyncio.gather(*[aclient.batch_read(g) for g in a_groups])
            for results in all_results:
                _ = [br.record[2]["bin0"] for br in results.batch_records if br.record is not None]

        async def _adict_filter():
            all_results = await asyncio.gather(*[aclient.batch_read(g) for g in a_groups])
            for results in all_results:
                _ = [br for br in results.batch_records if br.record is not None and br.record[2].get("bin0", 0) > 50.0]

        async def _adict_aggregation():
            all_results = await asyncio.gather(*[aclient.batch_read(g) for g in a_groups])
            for results in all_results:
                _ = sum(br.record[2]["bin0"] for br in results.batch_records if br.record is not None)

        # Async stage functions for numpy
        async def _anumpy_raw_read():
            await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in a_groups])

        async def _anumpy_column_access():
            all_results = await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in a_groups])
            for result in all_results:
                _ = result.batch_records["bin0"]

        async def _anumpy_filter():
            all_results = await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in a_groups])
            for result in all_results:
                arr = result.batch_records
                _ = arr[arr["bin0"] > 50.0]

        async def _anumpy_aggregation():
            all_results = await asyncio.gather(*[aclient.batch_read(g, _dtype=dtype) for g in a_groups])
            for result in all_results:
                _ = result.batch_records["bin0"].sum()

        adict_fns = [
            _adict_raw_read,
            _adict_column_access,
            _adict_filter,
            _adict_aggregation,
        ]
        anumpy_fns = [
            _anumpy_raw_read,
            _anumpy_column_access,
            _anumpy_filter,
            _anumpy_aggregation,
        ]

        for entry, adict_fn, anumpy_fn in zip(data, adict_fns, anumpy_fns):
            _log(f"  Post-Processing: {entry['stage_label']} (Async)")

            br_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await adict_fn()
                elapsed = time.perf_counter() - t0
                gc.enable()
                br_rounds.append(elapsed)
            entry["batch_read_async"] = _bulk_median(br_rounds, record_count)

            np_rounds = []
            for _ in range(rounds):
                gc.disable()
                t0 = time.perf_counter()
                await anumpy_fn()
                elapsed = time.perf_counter() - t0
                gc.enable()
                np_rounds.append(elapsed)
            entry["batch_read_numpy_async"] = _bulk_median(np_rounds, record_count)

        await _cleanup_data_async(aclient, a_prefix, record_count)
        await aclient.close()

    asyncio.run(_async_part())
    _settle()

    return {"record_count": record_count, "bin_count": num_bins, "data": data}


# ── Scenario 4: Memory Usage ─────────────────────────────────


def _run_memory(
    host: str,
    port: int,
    rounds: int,
    warmup: int,
    batch_groups: int,
) -> dict:
    import aerospike_py

    num_bins = 5
    dtype = _make_dtype(num_bins)
    data = []

    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": "docker"}).connect()
    _warmup_sync(client, warmup)

    for rc in RECORD_COUNTS:
        prefix = f"mem_{rc}_"
        _log(f"Memory: seeding {rc} records (bins={num_bins}) ...")
        _seed_data(client, prefix, rc, num_bins)
        _settle()

        keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(rc)]
        groups = [keys[i::batch_groups] for i in range(batch_groups)]

        # Measure dict peak memory
        _log(f"  dict peak memory ({rc} records)")
        gc.collect()
        tracemalloc.start()
        for _ in range(rounds):
            _ = [client.batch_read(g) for g in groups]
        _, dict_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        dict_peak_kb = dict_peak / 1024

        # Measure numpy peak memory
        _log(f"  numpy peak memory ({rc} records)")
        gc.collect()
        tracemalloc.start()
        for _ in range(rounds):
            _ = [client.batch_read(g, _dtype=dtype) for g in groups]
        _, numpy_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        numpy_peak_kb = numpy_peak / 1024

        savings_pct = ((dict_peak_kb - numpy_peak_kb) / dict_peak_kb * 100) if dict_peak_kb > 0 else 0

        _cleanup_data(client, prefix, rc)
        _settle()

        data.append(
            {
                "record_count": rc,
                "dict_peak_kb": round(dict_peak_kb, 1),
                "numpy_peak_kb": round(numpy_peak_kb, 1),
                "savings_pct": round(savings_pct, 1),
            }
        )

    client.close()
    return {"bin_count": num_bins, "data": data}


# ── terminal output ──────────────────────────────────────────


COL_W = 18


def _print_scaling_table(title: str, x_label: str, x_key: str, result: dict, rounds: int):
    data = result["data"]
    fixed_info = ""
    if "fixed_bins" in result:
        fixed_info = f"bins={result['fixed_bins']}"
    elif "fixed_records" in result:
        fixed_info = f"records={result['fixed_records']}"

    header = f"{title} ({fixed_info}, rounds={rounds})"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 10 + COL_W * 4 + COL_W * 2 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    h = f"  {x_label:>8}"
    h += f" | {'batch_read(Sync)':>{COL_W}}"
    h += f" | {'numpy(Sync)':>{COL_W}}"
    h += f" | {'batch_read(Async)':>{COL_W}}"
    h += f" | {'numpy(Async)':>{COL_W}}"
    h += f" | {'Speedup(Sync)':>{COL_W}}"
    h += f" | {'Speedup(Async)':>{COL_W}}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    for entry in data:
        x_val = entry[x_key]
        br_s = entry["batch_read_sync"]["avg_ms"]
        np_s = entry["batch_read_numpy_sync"]["avg_ms"]
        br_a = entry.get("batch_read_async", {}).get("avg_ms")
        np_a = entry.get("batch_read_numpy_async", {}).get("avg_ms")

        sp_s = _speedup(np_s, br_s)
        sp_a = _speedup(np_a, br_a)

        line = f"  {x_val:>8,}"
        line += f" | {_fmt_ms(br_s):>{COL_W}}"
        line += f" | {_fmt_ms(np_s):>{COL_W}}"
        line += f" | {_fmt_ms(br_a):>{COL_W}}"
        line += f" | {_fmt_ms(np_a):>{COL_W}}"
        line += f" | {_lpad(sp_s, COL_W)}"
        line += f" | {_lpad(sp_a, COL_W)}"
        print(line)


def _print_post_processing_table(result: dict, rounds: int):
    data = result["data"]
    header = f"Post-Processing (records={result['record_count']}, bins={result['bin_count']}, rounds={rounds})"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 24 + COL_W * 4 + COL_W * 2 + 20
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    h = f"  {'Stage':<22}"
    h += f" | {'batch_read(Sync)':>{COL_W}}"
    h += f" | {'numpy(Sync)':>{COL_W}}"
    h += f" | {'batch_read(Async)':>{COL_W}}"
    h += f" | {'numpy(Async)':>{COL_W}}"
    h += f" | {'Speedup(Sync)':>{COL_W}}"
    h += f" | {'Speedup(Async)':>{COL_W}}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    for entry in data:
        label = entry["stage_label"]
        br_s = entry["batch_read_sync"]["avg_ms"]
        np_s = entry["batch_read_numpy_sync"]["avg_ms"]
        br_a = entry.get("batch_read_async", {}).get("avg_ms")
        np_a = entry.get("batch_read_numpy_async", {}).get("avg_ms")

        sp_s = _speedup(np_s, br_s)
        sp_a = _speedup(np_a, br_a)

        line = f"  {label:<22}"
        line += f" | {_fmt_ms(br_s):>{COL_W}}"
        line += f" | {_fmt_ms(np_s):>{COL_W}}"
        line += f" | {_fmt_ms(br_a):>{COL_W}}"
        line += f" | {_fmt_ms(np_a):>{COL_W}}"
        line += f" | {_lpad(sp_s, COL_W)}"
        line += f" | {_lpad(sp_a, COL_W)}"
        print(line)


def _print_memory_table(result: dict, rounds: int):
    data = result["data"]
    header = f"Memory Usage (bins={result['bin_count']}, rounds={rounds}, Sync only)"
    print(f"\n  {_c(Color.BOLD_CYAN, header) if _use_color else header}")
    w = 10 + 16 * 3 + 10
    sep = "─" * w
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    h = f"  {'Records':>8}"
    h += f" | {'dict peak (KB)':>14}"
    h += f" | {'numpy peak (KB)':>15}"
    h += f" | {'Savings':>10}"
    print(h)
    print(f"  {_c(Color.DIM, sep) if _use_color else sep}")

    for entry in data:
        savings = f"{entry['savings_pct']:.1f}%"
        if entry["savings_pct"] > 0:
            savings = _c(Color.GREEN, savings) if _use_color else savings
        elif entry["savings_pct"] < 0:
            savings = _c(Color.RED, savings) if _use_color else savings

        line = f"  {entry['record_count']:>8,}"
        line += f" | {entry['dict_peak_kb']:>14,.1f}"
        line += f" | {entry['numpy_peak_kb']:>15,.1f}"
        line += f" | {_lpad(savings, 10)}"
        print(line)


# ── main ──────────────────────────────────────────────────────


@dataclass
class NumpyBenchmarkResults:
    record_scaling: dict | None = None
    bin_scaling: dict | None = None
    post_processing: dict | None = None
    memory: dict | None = None
    rounds: int = 10
    warmup: int = 200
    concurrency: int = 50
    batch_groups: int = 10
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    python_version: str = field(default_factory=platform.python_version)
    platform_info: str = field(default_factory=lambda: f"{platform.system()} {platform.machine()}")


def main():
    global _use_color

    parser = argparse.ArgumentParser(description="Benchmark: batch_read (dict) vs batch_read_numpy (numpy)")
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", "record_scaling", "bin_scaling", "post_processing", "memory"],
        help="Scenario to run (default: all)",
    )
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per measurement")
    parser.add_argument("--warmup", type=int, default=WARMUP_COUNT, help="Warmup ops")
    parser.add_argument("--concurrency", type=int, default=50, help="Async concurrency")
    parser.add_argument(
        "--batch-groups",
        type=int,
        default=10,
        help="Number of groups for batch_read",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate benchmark report (JSON)",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Report JSON output directory",
    )
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        _use_color = False

    scenarios = (
        ["record_scaling", "bin_scaling", "post_processing", "memory"] if args.scenario == "all" else [args.scenario]
    )

    print("NumPy Batch Benchmark config:")
    print(f"  scenarios    = {', '.join(scenarios)}")
    print(f"  rounds       = {args.rounds}")
    print(f"  warmup       = {args.warmup}")
    print(f"  concurrency  = {args.concurrency}")
    print(f"  batch_groups = {args.batch_groups}")
    print(f"  server       = {args.host}:{args.port}")
    print()

    results = NumpyBenchmarkResults(
        rounds=args.rounds,
        warmup=args.warmup,
        concurrency=args.concurrency,
        batch_groups=args.batch_groups,
    )

    step = 0
    total = len(scenarios)

    if "record_scaling" in scenarios:
        step += 1
        print(_c(Color.BOLD_CYAN, f"[{step}/{total}]") + " Record Count Scaling ...")
        results.record_scaling = _run_record_scaling(
            args.host,
            args.port,
            args.rounds,
            args.warmup,
            args.concurrency,
            args.batch_groups,
        )
        _print_scaling_table(
            "Record Count Scaling",
            "Records",
            "record_count",
            results.record_scaling,
            args.rounds,
        )
        print()

    if "bin_scaling" in scenarios:
        step += 1
        print(_c(Color.BOLD_CYAN, f"[{step}/{total}]") + " Bin Count Scaling ...")
        results.bin_scaling = _run_bin_scaling(
            args.host,
            args.port,
            args.rounds,
            args.warmup,
            args.concurrency,
            args.batch_groups,
        )
        _print_scaling_table(
            "Bin Count Scaling",
            "Bins",
            "bin_count",
            results.bin_scaling,
            args.rounds,
        )
        print()

    if "post_processing" in scenarios:
        step += 1
        print(_c(Color.BOLD_CYAN, f"[{step}/{total}]") + " Post-Processing ...")
        results.post_processing = _run_post_processing(
            args.host,
            args.port,
            args.rounds,
            args.warmup,
            args.concurrency,
            args.batch_groups,
        )
        _print_post_processing_table(results.post_processing, args.rounds)
        print()

    if "memory" in scenarios:
        step += 1
        print(_c(Color.BOLD_CYAN, f"[{step}/{total}]") + " Memory Usage ...")
        results.memory = _run_memory(
            args.host,
            args.port,
            args.rounds,
            args.warmup,
            args.batch_groups,
        )
        _print_memory_table(results.memory, args.rounds)
        print()

    if args.report:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        date_slug = datetime.now().strftime("%Y-%m-%d_%H-%M")
        json_dir = args.report_dir or os.path.join(project_root, "docs", "static", "benchmark", "numpy-results")

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_generator import generate_numpy_report

        generate_numpy_report(results, json_dir, date_slug)
        print(_c(Color.BOLD_CYAN, "[report]") + f" Generated: {json_dir}/{date_slug}.json")


if __name__ == "__main__":
    main()
