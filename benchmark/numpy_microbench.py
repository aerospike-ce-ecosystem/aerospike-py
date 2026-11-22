#!/usr/bin/env python3
"""Median-of-N microbenchmark for the NumPy batch read and write paths.

Three timings are reported for a structured array of ``--rows`` rows with
``--fields`` float64 bins:

``to_numpy``
    ``handle.to_numpy(dtype)`` on a ``batch_read`` handle that already exists.
    Pure conversion cost: no network.
``read``
    ``batch_read(keys)`` followed by ``to_numpy(dtype)``.
``write``
    ``batch_write_numpy(array, namespace, set, dtype)``.

Each timing is the median of ``--runs`` measured calls after ``--warmup``
discarded calls. This is the script behind the reference numbers in
``docs/rust-v3-numpy-handoff.md`` (720 rows x 8 float64 fields, 5 warmup calls,
51 measured calls).

Run it twice: once plain and once with ``--cpu-competitor``. The plain run
measures the client in isolation. The competitor run adds a pure-Python busy
thread, which is what exposes a change that holds the GIL for longer; a plain
microbenchmark missed exactly that regression in v0.5.6 (see
``POSTMORTEM-v0.5.6-batch-regression.md``).

    make run-aerospike-ce                          # from the repo root
    uv run python benchmark/numpy_microbench.py
    uv run python benchmark/numpy_microbench.py --cpu-competitor --json

The dtype is passed positionally to ``batch_write_numpy`` so the same script
runs against releases that require it and releases that infer it.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import threading
import time

DEFAULT_HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))
DEFAULT_CLUSTER = os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker")

NAMESPACE = "test"
SET_NAME = "np_microbench"


def _busy_loop(stop: threading.Event) -> None:
    """A pure-Python CPU competitor, standing in for co-located inference."""
    x = 0
    while not stop.is_set():
        for i in range(10_000):
            x += i * i
        x &= 0xFFFF


def _measure(fn, warmup: int, runs: int) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples_ms = []
    for _ in range(runs):
        start = time.perf_counter_ns()
        fn()
        samples_ms.append((time.perf_counter_ns() - start) / 1e6)
    samples_ms.sort()
    return {
        "median_ms": round(statistics.median(samples_ms), 4),
        "p95_ms": round(samples_ms[min(len(samples_ms) - 1, int(len(samples_ms) * 0.95))], 4),
        "min_ms": round(samples_ms[0], 4),
        "max_ms": round(samples_ms[-1], 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cluster-name", default=DEFAULT_CLUSTER)
    parser.add_argument("--rows", type=int, default=720)
    parser.add_argument("--fields", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=51)
    parser.add_argument("--cpu-competitor", action="store_true", help="add a GIL-holding busy thread")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()

    import aerospike_py
    import numpy as np

    bin_names = [f"f{i}" for i in range(args.fields)]
    write_dtype = np.dtype([("_key", "i8")] + [(name, "f8") for name in bin_names])
    read_dtype = np.dtype([(name, "f8") for name in bin_names])

    rng = np.random.default_rng(7)
    data = np.zeros(args.rows, dtype=write_dtype)
    data["_key"] = np.arange(args.rows)
    for name in bin_names:
        data[name] = rng.random(args.rows)
    keys = [(NAMESPACE, SET_NAME, i) for i in range(args.rows)]

    client = aerospike_py.client({"hosts": [(args.host, args.port)], "cluster_name": args.cluster_name}).connect()
    try:
        client.batch_write_numpy(data, NAMESPACE, SET_NAME, write_dtype)
        handle = client.batch_read(keys, bins=bin_names)
        check = handle.to_numpy(read_dtype)
        if int((check.result_codes != 0).sum()) != 0:
            raise SystemExit("seed verification failed: some rows did not read back")
        if not np.array_equal(check.batch_records[bin_names[0]], data[bin_names[0]]):
            raise SystemExit("seed verification failed: values differ after the round trip")

        stop = threading.Event()
        competitor = None
        if args.cpu_competitor:
            competitor = threading.Thread(target=_busy_loop, args=(stop,), daemon=True)
            competitor.start()
        try:
            results = {
                "to_numpy": _measure(lambda: handle.to_numpy(read_dtype), args.warmup, args.runs),
                "read": _measure(
                    lambda: client.batch_read(keys, bins=bin_names).to_numpy(read_dtype), args.warmup, args.runs
                ),
                "write": _measure(
                    lambda: client.batch_write_numpy(data, NAMESPACE, SET_NAME, write_dtype), args.warmup, args.runs
                ),
            }
        finally:
            stop.set()
            if competitor is not None:
                competitor.join(timeout=5)

        server_build = client.info_all("build")
    finally:
        client.close()

    report = {
        "aerospike_py": aerospike_py.__version__,
        "numpy": np.__version__,
        "python": platform.python_version(),
        "server_build": sorted({str(v[-1]).strip() for v in server_build}) if server_build else [],
        "rows": args.rows,
        "fields": args.fields,
        "warmup": args.warmup,
        "runs": args.runs,
        "cpu_competitor": args.cpu_competitor,
        "results": results,
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(
        f"aerospike-py {report['aerospike_py']}  numpy {report['numpy']}  python {report['python']}  "
        f"server {','.join(report['server_build']) or '?'}"
    )
    print(
        f"rows={args.rows} fields={args.fields} warmup={args.warmup} runs={args.runs} "
        f"cpu_competitor={args.cpu_competitor}"
    )
    print(f"{'metric':<10} {'median':>10} {'p95':>10} {'min':>10} {'max':>10}   (ms)")
    for name, stats in results.items():
        print(
            f"{name:<10} {stats['median_ms']:>10.3f} {stats['p95_ms']:>10.3f} "
            f"{stats['min_ms']:>10.3f} {stats['max_ms']:>10.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
