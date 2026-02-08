"""Benchmark: dict-based BatchRecords vs NumpyBatchRecords (no server required).

Measures conversion time, column access, filtering, and memory usage at
various scales (100, 1K, 10K, 100K records) using mock data.

Usage:
    python benchmark/bench_numpy_compare.py [--max-scale 100000] [--rounds 5]
"""

from __future__ import annotations

import argparse
import gc
import statistics
import time
import tracemalloc
from types import SimpleNamespace

import numpy as np


# ── mock data generation ───────────────────────────────────────


def _make_mock_batch_records(n: int, num_bins: int = 5):
    """Generate mock BatchRecords with n records, each having num_bins bins."""
    records = []
    for i in range(n):
        bins = {}
        for b in range(num_bins):
            bins[f"bin{b}"] = float(i * num_bins + b) * 0.1
        records.append(
            SimpleNamespace(
                key=("test", "demo", f"k{i}"),
                result=0,
                record=(None, {"gen": 1, "ttl": 3600}, bins),
            )
        )
    return SimpleNamespace(batch_records=records)


def _make_dtype(num_bins: int = 5):
    """Create numpy dtype matching mock data."""
    return np.dtype([(f"bin{b}", "f8") for b in range(num_bins)])


# ── dict-based simulation ────────────────────────────────────


def _dict_convert(batch_obj):
    """Simulate dict-based BatchRecords → list[dict] conversion."""
    results = []
    for br in batch_obj.batch_records:
        if br.result == 0 and br.record is not None:
            _, meta, bins = br.record
            results.append({"key": br.key[2], "meta": meta, "bins": dict(bins)})
        else:
            results.append({"key": br.key[2], "meta": None, "bins": None})
    return results


def _dict_column_access(records, bin_name):
    """Extract a column from dict-based records (Python loop)."""
    return [r["bins"][bin_name] for r in records if r["bins"] is not None]


def _dict_filter(records):
    """Filter records where bin0 > 50.0 (Python loop)."""
    return [r for r in records if r["bins"] is not None and r["bins"]["bin0"] > 50.0]


# ── numpy-based ───────────────────────────────────────────────


def _numpy_convert(batch_obj, dtype):
    """NumpyBatchRecords conversion via Python fallback."""
    from aerospike_py.numpy_batch import _batch_records_to_numpy

    keys = [br.key for br in batch_obj.batch_records]
    return _batch_records_to_numpy(batch_obj, dtype, keys)


def _numpy_column_access(result, bin_name):
    """Extract a column from NumpyBatchRecords (zero-copy view)."""
    return result.batch_records[bin_name]


def _numpy_filter(result):
    """Filter records where bin0 > 50.0 (vectorized)."""
    mask = result.batch_records["bin0"] > 50.0
    return result.batch_records[mask]


# ── timing ────────────────────────────────────────────────────


def _measure(fn, rounds: int) -> dict:
    """Run fn() multiple rounds, return timing stats."""
    times = []
    for _ in range(rounds):
        gc.collect()
        gc.disable()
        t0 = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - t0
        gc.enable()
        times.append(elapsed * 1000)  # ms
    return {
        "avg_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0,
        "min_ms": min(times),
        "max_ms": max(times),
    }


def _measure_memory(fn) -> tuple:
    """Run fn() and measure peak memory usage with tracemalloc."""
    gc.collect()
    tracemalloc.start()
    result = fn()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, peak


# ── main benchmark ────────────────────────────────────────────


def run_benchmark(scales: list[int], rounds: int, num_bins: int = 5):
    """Run full benchmark across all scales."""
    dtype = _make_dtype(num_bins)

    print(f"{'':─<90}")
    print("  NumPy Batch Benchmark: dict vs NumpyBatchRecords")
    print(f"  rounds={rounds}, bins_per_record={num_bins}")
    print(f"{'':─<90}")

    # ── Conversion Time ──
    print(f"\n  {'Conversion Time (ms)':}")
    print(
        f"  {'Records':>10} | {'dict avg':>12} {'median':>10} | {'numpy avg':>12} {'median':>10} | {'speedup':>10}"
    )
    print(f"  {'':─<80}")

    for n in scales:
        batch = _make_mock_batch_records(n, num_bins)

        dict_stats = _measure(lambda: _dict_convert(batch), rounds)
        numpy_stats = _measure(lambda: _numpy_convert(batch, dtype), rounds)

        speedup = (
            dict_stats["avg_ms"] / numpy_stats["avg_ms"]
            if numpy_stats["avg_ms"] > 0
            else 0
        )
        marker = "numpy faster" if speedup > 1 else "dict faster"

        print(
            f"  {n:>10,} | {dict_stats['avg_ms']:>10.3f}ms {dict_stats['median_ms']:>10.3f}ms"
            f" | {numpy_stats['avg_ms']:>10.3f}ms {numpy_stats['median_ms']:>10.3f}ms"
            f" | {speedup:>8.2f}x ({marker})"
        )

    # ── Column Access Time ──
    print(f"\n  {'Column Access Time (ms) — extracting single column':}")
    print(f"  {'Records':>10} | {'dict avg':>12} | {'numpy avg':>12} | {'speedup':>10}")
    print(f"  {'':─<60}")

    for n in scales:
        batch = _make_mock_batch_records(n, num_bins)
        dict_records = _dict_convert(batch)
        numpy_result = _numpy_convert(batch, dtype)

        dict_stats = _measure(lambda: _dict_column_access(dict_records, "bin0"), rounds)
        numpy_stats = _measure(
            lambda: _numpy_column_access(numpy_result, "bin0"), rounds
        )

        speedup = (
            dict_stats["avg_ms"] / numpy_stats["avg_ms"]
            if numpy_stats["avg_ms"] > 0
            else 0
        )
        marker = "numpy faster" if speedup > 1 else "dict faster"

        print(
            f"  {n:>10,} | {dict_stats['avg_ms']:>10.3f}ms | {numpy_stats['avg_ms']:>10.3f}ms"
            f" | {speedup:>8.2f}x ({marker})"
        )

    # ── Filter Time ──
    print(f"\n  {'Filter Time (ms) — bin0 > 50.0':}")
    print(f"  {'Records':>10} | {'dict avg':>12} | {'numpy avg':>12} | {'speedup':>10}")
    print(f"  {'':─<60}")

    for n in scales:
        batch = _make_mock_batch_records(n, num_bins)
        dict_records = _dict_convert(batch)
        numpy_result = _numpy_convert(batch, dtype)

        dict_stats = _measure(lambda: _dict_filter(dict_records), rounds)
        numpy_stats = _measure(lambda: _numpy_filter(numpy_result), rounds)

        speedup = (
            dict_stats["avg_ms"] / numpy_stats["avg_ms"]
            if numpy_stats["avg_ms"] > 0
            else 0
        )
        marker = "numpy faster" if speedup > 1 else "dict faster"

        print(
            f"  {n:>10,} | {dict_stats['avg_ms']:>10.3f}ms | {numpy_stats['avg_ms']:>10.3f}ms"
            f" | {speedup:>8.2f}x ({marker})"
        )

    # ── Memory Usage ──
    print(f"\n  {'Memory Usage (peak, KB)':}")
    print(f"  {'Records':>10} | {'dict':>12} | {'numpy':>12} | {'savings':>10}")
    print(f"  {'':─<60}")

    for n in scales:
        batch = _make_mock_batch_records(n, num_bins)

        _, dict_mem = _measure_memory(lambda: _dict_convert(batch))
        _, numpy_mem = _measure_memory(lambda: _numpy_convert(batch, dtype))

        dict_kb = dict_mem / 1024
        numpy_kb = numpy_mem / 1024
        savings = (1 - numpy_kb / dict_kb) * 100 if dict_kb > 0 else 0

        print(
            f"  {n:>10,} | {dict_kb:>10.1f}KB | {numpy_kb:>10.1f}KB"
            f" | {savings:>8.1f}% less"
        )

    # ── Crossover Point ──
    print(f"\n  {'Crossover Point Analysis':}")
    print(f"  {'':─<60}")

    crossover_found = False
    test_sizes = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
    for n in test_sizes:
        batch = _make_mock_batch_records(n, num_bins)
        dict_stats = _measure(lambda: _dict_convert(batch), rounds)
        numpy_stats = _measure(lambda: _numpy_convert(batch, dtype), rounds)

        ratio = (
            numpy_stats["avg_ms"] / dict_stats["avg_ms"]
            if dict_stats["avg_ms"] > 0
            else 0
        )
        winner = "numpy" if ratio < 1 else "dict"

        if winner == "numpy" and not crossover_found:
            print(f"  → Crossover at ~{n} records: numpy becomes faster")
            crossover_found = True

        print(
            f"    {n:>5} records: dict={dict_stats['avg_ms']:.4f}ms  numpy={numpy_stats['avg_ms']:.4f}ms  ratio={ratio:.2f}x  ({winner} faster)"
        )

    if not crossover_found:
        print(f"  → dict is faster at all tested sizes (up to {test_sizes[-1]})")

    print(f"\n{'':─<90}")
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: dict-based vs NumpyBatchRecords (no server)"
    )
    parser.add_argument(
        "--max-scale",
        type=int,
        default=100_000,
        help="Maximum record count to test (default: 100000)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="Number of measurement rounds (default: 5)",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=5,
        help="Number of bins per record (default: 5)",
    )
    args = parser.parse_args()

    # Build scales list: 100, 1K, 10K, up to max-scale
    scales = []
    s = 100
    while s <= args.max_scale:
        scales.append(s)
        s *= 10

    run_benchmark(scales, args.rounds, args.bins)


if __name__ == "__main__":
    main()
