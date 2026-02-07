"""Unified benchmark: aerospike-py vs official aerospike C client.

Methodology for consistent results:
  1. Warmup phase (discarded) to stabilize connections & server cache
  2. Multiple rounds per operation, report median of round medians
  3. Data is pre-seeded before read benchmarks
  4. GC disabled during measurement
  5. Each client uses isolated key prefixes

Usage:
    python benchmark/bench_compare.py [--count N] [--rounds R] [--warmup W]
                                      [--concurrency C] [--host HOST] [--port PORT]

Requirements:
    pip install aerospike   # official C client (comparison target)
"""

import argparse
import asyncio
import gc
import statistics
import time

NAMESPACE = "test"
SET_NAME = "bench_cmp"
WARMUP_COUNT = 500
SETTLE_SECS = 0.5  # pause between phases to let I/O settle


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
    print(f"      [{time.strftime('%H:%M:%S')}] {msg}")


def _settle():
    """GC collect + short sleep to stabilize between phases."""
    _log(f"gc.collect() + sleep {SETTLE_SECS}s ...")
    gc.collect()
    time.sleep(SETTLE_SECS)


# ── seed / cleanup ───────────────────────────────────────────


def _seed_sync(put_fn, prefix: str, count: int):
    for i in range(count):
        put_fn(
            (NAMESPACE, SET_NAME, f"{prefix}{i}"), {"n": f"u{i}", "a": i, "s": i * 1.1}
        )


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


def bench_rust_sync(host: str, port: int, count: int, rounds: int, warmup: int) -> dict:
    import aerospike_py

    client = aerospike_py.client(
        {"hosts": [(host, port)], "cluster_name": "docker"}
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

    # --- BATCH GET ---
    _log(f"BATCH_GET  {count} keys x {rounds} rounds  (gc disabled)")
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: client.batch_read(keys))
        gc.enable()
        batch_rounds.append(elapsed)
    results["batch_get"] = _bulk_median(batch_rounds, count)
    _settle()

    # --- SCAN ---
    _log(f"SCAN  x {rounds} rounds  (gc disabled)")
    scan_rounds = []
    for _ in range(rounds):
        scan = client.scan(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda: scan.results())
        gc.enable()
        scan_rounds.append(elapsed)
    results["scan"] = _bulk_median(scan_rounds, count)

    # cleanup
    _log("cleanup ...")
    _cleanup_sync(client.remove, prefix, count)
    client.close()

    return results


# ── 2) official aerospike C client ───────────────────────────


def bench_c_sync(
    host: str, port: int, count: int, rounds: int, warmup: int
) -> dict | None:
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

    # --- BATCH GET ---
    _log(f"BATCH_GET  {count} keys x {rounds} rounds  (gc disabled)")
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        elapsed = _measure_bulk(lambda: client.batch_read(keys))
        gc.enable()
        batch_rounds.append(elapsed)
    results["batch_get"] = _bulk_median(batch_rounds, count)
    _settle()

    # --- SCAN ---
    _log(f"SCAN  x {rounds} rounds  (gc disabled)")
    scan_rounds = []
    for _ in range(rounds):
        scan = client.scan(NAMESPACE, SET_NAME)
        gc.disable()
        elapsed = _measure_bulk(lambda: scan.results())
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
    host: str, port: int, count: int, rounds: int, warmup: int, concurrency: int
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
    _log(
        f"PUT  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)"
    )
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
        await client.batch_remove(
            [(NAMESPACE, SET_NAME, f"{prefix}p{r}_{i}") for i in range(count)]
        )
    results["put"] = _bulk_median(put_rounds, count)
    _settle()

    # --- seed ---
    _log(f"seeding {count} records ...")
    await _seed_async(client, prefix, count, concurrency)
    _settle()

    # --- GET (concurrent) ---
    _log(
        f"GET  {count} ops x {rounds} rounds, concurrency={concurrency}  (gc disabled)"
    )
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

    # --- BATCH GET ---
    _log(f"BATCH_GET  {count} keys x {rounds} rounds  (gc disabled)")
    keys = [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    batch_rounds = []
    for _ in range(rounds):
        gc.disable()
        t0 = time.perf_counter()
        await client.batch_read(keys)
        elapsed = time.perf_counter() - t0
        gc.enable()
        batch_rounds.append(elapsed)
    results["batch_get"] = _bulk_median(batch_rounds, count)
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
    await client.batch_remove(
        [(NAMESPACE, SET_NAME, f"{prefix}{i}") for i in range(count)]
    )
    await client.close()

    return results


# ── comparison output ────────────────────────────────────────

COL_OP = 12
COL_VAL = 22
COL_SP = 16


def _speedup_latency(target: float, baseline: float) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    ratio = baseline / target
    if ratio >= 1.0:
        return f"{ratio:.1f}x faster"
    return f"{1 / ratio:.1f}x slower"


def _speedup_throughput(target: float, baseline: float) -> str:
    if target <= 0 or baseline <= 0:
        return "-"
    ratio = target / baseline
    if ratio >= 1.0:
        return f"{ratio:.1f}x faster"
    return f"{1 / ratio:.1f}x slower"


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.3f}ms"


def _fmt_ops(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:,.0f}/s"


def _print_table(
    title: str,
    ops: list[str],
    rust: dict,
    c: dict | None,
    async_r: dict,
    metric: str,
    formatter,
    speedup_fn,
):
    has_c = c is not None
    w = COL_OP + 2 + COL_VAL * 3 + (COL_SP * 2 if has_c else 0) + 12

    print(f"\n  {title}")
    print(f"  {'':─<{w}}")

    h = f"  {'Operation':<{COL_OP}}"
    h += f" | {'aerospike-py (Rust)':>{COL_VAL}}"
    if has_c:
        h += f" | {'official aerospike (C)':>{COL_VAL}}"
    h += f" | {'aerospike-py async':>{COL_VAL}}"
    if has_c:
        h += f" | {'Rust vs C':>{COL_SP}}"
        h += f" | {'Async vs C':>{COL_SP}}"
    print(h)
    print(f"  {'':─<{w}}")

    for op in ops:
        rv = rust[op].get(metric)
        cv = c[op].get(metric) if has_c else None
        av = async_r[op].get(metric)

        line = f"  {op:<{COL_OP}}"
        line += f" | {formatter(rv):>{COL_VAL}}"
        if has_c:
            line += f" | {formatter(cv):>{COL_VAL}}"
        line += f" | {formatter(av):>{COL_VAL}}"

        if has_c and cv is not None:
            line += f" | {speedup_fn(rv, cv) if rv else '-':>{COL_SP}}"
            line += f" | {speedup_fn(av, cv) if av else '-':>{COL_SP}}"

        print(line)


def print_comparison(
    rust: dict,
    c: dict | None,
    async_r: dict,
    count: int,
    rounds: int,
    concurrency: int,
):
    ops = ["put", "get", "batch_get", "scan"]

    print()
    print("=" * 100)
    print(
        f"  aerospike-py Benchmark  "
        f"({count:,} ops x {rounds} rounds, warmup={WARMUP_COUNT}, "
        f"async concurrency={concurrency})"
    )
    print("=" * 100)

    if c is None:
        print("\n  [!] official aerospike (C) not installed. pip install aerospike")

    _print_table(
        "Avg Latency (ms)  —  lower is better  [median of round means]",
        ops,
        rust,
        c,
        async_r,
        metric="avg_ms",
        formatter=_fmt_ms,
        speedup_fn=_speedup_latency,
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
    )

    # Stability indicator (stdev)
    print("\n  Stability (stdev of round median latency, ms)  —  lower = more stable")
    w = COL_OP + 2 + COL_VAL * 3 + 6
    print(f"  {'':─<{w}}")
    h = f"  {'Operation':<{COL_OP}}"
    h += f" | {'Rust stdev':>{COL_VAL}}"
    if c is not None:
        h += f" | {'C stdev':>{COL_VAL}}"
    h += f" | {'Async stdev':>{COL_VAL}}"
    print(h)
    print(f"  {'':─<{w}}")
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
        print("\n  Tail Latency (ms)  [aggregated across all rounds]")
        w2 = COL_OP + 2 + 18 * 4 + 10
        print(f"  {'':─<{w2}}")
        h = f"  {'Operation':<{COL_OP}}"
        h += f" | {'Rust p50':>16} | {'Rust p99':>16}"
        if c is not None:
            h += f" | {'C p50':>16} | {'C p99':>16}"
        print(h)
        print(f"  {'':─<{w2}}")
        for op in pct_ops:
            line = f"  {op:<{COL_OP}}"
            line += f" | {_fmt_ms(rust[op]['p50_ms']):>16}"
            line += f" | {_fmt_ms(rust[op]['p99_ms']):>16}"
            if c is not None:
                line += f" | {_fmt_ms(c[op].get('p50_ms')):>16}"
                line += f" | {_fmt_ms(c[op].get('p99_ms')):>16}"
            print(line)

    print()


# ── main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: aerospike-py (Rust) vs official aerospike (C)"
    )
    parser.add_argument("--count", type=int, default=1000, help="Ops per round")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per operation")
    parser.add_argument("--warmup", type=int, default=WARMUP_COUNT, help="Warmup ops")
    parser.add_argument("--concurrency", type=int, default=50, help="Async concurrency")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    print("Benchmark config:")
    print(f"  ops/round  = {args.count:,}")
    print(f"  rounds     = {args.rounds}")
    print(f"  warmup     = {args.warmup}")
    print(f"  concurrency= {args.concurrency}")
    print(f"  server     = {args.host}:{args.port}")
    print()

    print("[1/3] aerospike-py sync (Rust) ...")
    rust = bench_rust_sync(args.host, args.port, args.count, args.rounds, args.warmup)
    print("      done")

    print("[2/3] official aerospike sync (C) ...")
    c = bench_c_sync(args.host, args.port, args.count, args.rounds, args.warmup)
    if c is None:
        print("      not installed, skipping")
    else:
        print("      done")

    print("[3/3] aerospike-py async (Rust) ...")
    async_r = asyncio.run(
        bench_rust_async(
            args.host, args.port, args.count, args.rounds, args.warmup, args.concurrency
        )
    )
    print("      done")

    print_comparison(rust, c, async_r, args.count, args.rounds, args.concurrency)


if __name__ == "__main__":
    main()
