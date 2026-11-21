"""Latency and CPU cost of the calls the NumPy benchmarks do not cover.

``numpy_microbench.py`` and ``gil_starvation.py`` measure batch reads and
writes of records that all exist. This script measures the rest of the request
path, in three groups:

``single``
    ``get``, ``put``, ``operate`` and ``operate_ordered`` on one record, with
    the sync client (one call at a time) and the async client (``--in-flight``
    calls at a time). Two shapes are there on purpose: an operate that returns
    a 5,000-element list and one made of ten writes. Rust client 3.0 keeps a
    second copy of every value an operate returns and makes the server answer
    every operation of an operate that writes.
``missing``
    ``batch_read`` of N keys of which 0 %, 50 % or 100 % do not exist,
    converted with ``to_dict()`` and with ``to_numpy()``. Rust client 3.0
    allocates an error object for every row that was not found.
``write``
    ``batch_write`` of dicts, without and with ``retry=``.

Each scenario runs for ``--seconds`` and reports calls per second, the p50 and
p99 latency of one call and the process CPU time per call.

To compare two builds, run it once in each environment and compare the JSON::

    uv run python benchmark/op_latency.py --json > new.json
    uv run python benchmark/op_latency.py --cpu-competitor --json > new_busy.json

``--cpu-competitor`` adds a pure-Python busy thread, as the other benchmarks
do: a client that holds the GIL longer shows up there and nowhere else.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import threading
import time

import aerospike_py
import numpy as np
from aerospike_py import list_operations

NAMESPACE = "test"
SINGLE_SET = "op_latency_single"
BATCH_SET = "op_latency_batch"
RECORDS = 1000
BIG_LIST = 5000
FLOAT_BINS = [f"f{i}" for i in range(8)]
READ = aerospike_py.OPERATOR_READ
WRITE = aerospike_py.OPERATOR_WRITE
INCR = aerospike_py.OPERATOR_INCR


def _busy_loop(stop: threading.Event) -> None:
    """A pure-Python CPU competitor, standing in for co-located inference."""
    total = 0
    while not stop.is_set():
        for i in range(10_000):
            total += i * i


def _summary(latencies_ns: list[int], wall_s: float, cpu_s: float) -> dict[str, float]:
    ordered = sorted(latencies_ns)
    return {
        "calls_per_s": round(len(ordered) / wall_s, 1),
        "p50_ms": round(statistics.median(ordered) / 1e6, 4),
        "p99_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))] / 1e6, 4),
        "cpu_us_per_call": round(cpu_s * 1e6 / len(ordered), 2),
    }


def _run_sync(call, seconds: float) -> dict[str, float]:
    for i in range(20):
        call(i)
    latencies: list[int] = []
    cpu_start, start = time.process_time(), time.perf_counter()
    deadline = start + seconds
    i = 0
    while time.perf_counter() < deadline:
        begin = time.perf_counter_ns()
        call(i)
        latencies.append(time.perf_counter_ns() - begin)
        i += 1
    return _summary(latencies, time.perf_counter() - start, time.process_time() - cpu_start)


async def _run_async(call, seconds: float, in_flight: int) -> dict[str, float]:
    for i in range(20):
        await call(i)
    latencies: list[int] = []
    cpu_start, start = time.process_time(), time.perf_counter()
    deadline = start + seconds

    async def worker(offset: int) -> None:
        i = offset
        while time.perf_counter() < deadline:
            begin = time.perf_counter_ns()
            await call(i)
            latencies.append(time.perf_counter_ns() - begin)
            i += in_flight

    await asyncio.gather(*(worker(n) for n in range(in_flight)))
    return _summary(latencies, time.perf_counter() - start, time.process_time() - cpu_start)


def _single_calls(client) -> dict[str, object]:
    """Scenario name -> ``call(i)``; the same table serves both clients."""

    def key(i: int):
        return (NAMESPACE, SINGLE_SET, i % RECORDS)

    big = (NAMESPACE, SINGLE_SET, "big")
    ten_writes = [{"op": WRITE, "bin": f"w{n}", "val": n} for n in range(10)]
    incr_read = [{"op": INCR, "bin": "a", "val": 1}, {"op": READ, "bin": "a"}]
    two_reads = [{"op": READ, "bin": "a"}, {"op": READ, "bin": "s"}]
    big_read = [list_operations.list_get_range("big", 0, BIG_LIST)]
    return {
        "get": lambda i: client.get(key(i)),
        "put": lambda i: client.put(key(i), {"a": i}),
        "operate, 2 reads": lambda i: client.operate(key(i), two_reads),
        "operate, incr + read": lambda i: client.operate(key(i), incr_read),
        "operate_ordered, incr + read": lambda i: client.operate_ordered(key(i), incr_read),
        "operate, 10 writes": lambda i: client.operate(key(i), ten_writes),
        f"operate, read a {BIG_LIST}-element list": lambda _i: client.operate(big, big_read),
    }


def _seed(client, batch_keys: int) -> None:
    for start in range(0, RECORDS, 500):
        client.batch_write(
            [
                ((NAMESPACE, SINGLE_SET, i), {"a": i, "b": 0.5, "s": "x" * 32, **{f"w{n}": 0 for n in range(10)}})
                for i in range(start, min(start + 500, RECORDS))
            ]
        )
    client.put((NAMESPACE, SINGLE_SET, "big"), {"big": list(range(BIG_LIST))})
    for start in range(0, batch_keys, 1000):
        client.batch_write(
            [
                ((NAMESPACE, BATCH_SET, i), {name: i + 0.5 for name in FLOAT_BINS})
                for i in range(start, min(start + 1000, batch_keys))
            ]
        )


def _clean(client, batch_keys: int) -> None:
    single = [(NAMESPACE, SINGLE_SET, i) for i in range(RECORDS)] + [(NAMESPACE, SINGLE_SET, "big")]
    batch = [(NAMESPACE, BATCH_SET, i) for i in range(batch_keys)]
    for keys in (single, batch):
        for start in range(0, len(keys), 1000):
            client.batch_remove(keys[start : start + 1000])


def _batch_keys(count: int, missing_percent: int) -> list[tuple]:
    """``count`` keys; every key whose position falls in the missing share was never written."""
    absent_every = {0: 0, 50: 2, 100: 1}[missing_percent]
    return [
        (NAMESPACE, BATCH_SET, i + 10_000_000 if absent_every and i % absent_every == 0 else i) for i in range(count)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18710)
    parser.add_argument("--cluster-name", default="docker")
    parser.add_argument("--seconds", type=float, default=3.0, help="how long each scenario runs")
    parser.add_argument("--in-flight", type=int, default=64, help="concurrent calls of the async scenarios")
    parser.add_argument("--groups", default="single,missing,write", help="comma-separated groups to run")
    parser.add_argument("--cpu-competitor", action="store_true", help="add a GIL-holding busy thread")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()
    groups = set(args.groups.split(","))
    config = {"hosts": [(args.host, args.port)], "cluster_name": args.cluster_name}
    batch_sizes = (50, 5000)
    read_dtype = np.dtype([(name, "f8") for name in FLOAT_BINS])
    results: dict[str, dict[str, float]] = {}

    client = aerospike_py.client(config).connect()
    _seed(client, max(batch_sizes))
    stop = threading.Event()
    competitor = threading.Thread(target=_busy_loop, args=(stop,), daemon=True) if args.cpu_competitor else None
    if competitor is not None:
        competitor.start()
    try:
        if "single" in groups:
            for name, call in _single_calls(client).items():
                results[f"sync {name}"] = _run_sync(call, args.seconds)

            async def run_async_group() -> None:
                async_client = aerospike_py.AsyncClient(config)
                await async_client.connect()
                try:
                    for name, call in _single_calls(async_client).items():
                        results[f"async x{args.in_flight} {name}"] = await _run_async(
                            call, args.seconds, args.in_flight
                        )
                finally:
                    await async_client.close()

            asyncio.run(run_async_group())

        if "missing" in groups:
            for count in batch_sizes:
                for missing in (0, 50, 100):
                    keys = _batch_keys(count, missing)
                    results[f"batch_read {count} keys, {missing}% missing, to_dict"] = _run_sync(
                        lambda _i, keys=keys: client.batch_read(keys, bins=FLOAT_BINS).to_dict(), args.seconds
                    )
                    results[f"batch_read {count} keys, {missing}% missing, to_numpy"] = _run_sync(
                        lambda _i, keys=keys: client.batch_read(keys, bins=FLOAT_BINS).to_numpy(read_dtype),
                        args.seconds,
                    )

        if "write" in groups:
            records = [((NAMESPACE, BATCH_SET, i), {name: i + 0.5 for name in FLOAT_BINS}) for i in range(720)]
            results["batch_write 720 dicts"] = _run_sync(lambda _i: client.batch_write(records), args.seconds)
            results["batch_write 720 dicts, retry=3"] = _run_sync(
                lambda _i: client.batch_write(records, retry=3), args.seconds
            )
    finally:
        stop.set()
        if competitor is not None:
            competitor.join(timeout=5)
        _clean(client, max(batch_sizes))
        client.close()

    report = {
        "aerospike_py": aerospike_py.__version__,
        "numpy": np.__version__,
        "seconds": args.seconds,
        "in_flight": args.in_flight,
        "cpu_competitor": args.cpu_competitor,
        "results": results,
    }
    if args.json:
        print(json.dumps(report))
    else:
        print(f"aerospike_py {report['aerospike_py']}, numpy {report['numpy']}, cpu_competitor={args.cpu_competitor}")
        width = max(len(name) for name in results)
        for name, row in results.items():
            print(
                f"{name:<{width}}  {row['calls_per_s']:>10.1f} calls/s  p50 {row['p50_ms']:>8.3f} ms  "
                f"p99 {row['p99_ms']:>8.3f} ms  cpu {row['cpu_us_per_call']:>9.1f} us/call"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
