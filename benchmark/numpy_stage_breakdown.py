#!/usr/bin/env python3
"""Where the time of a NumPy batch write and a batch read goes, stage by stage.

``numpy_microbench.py`` reports one number per call. This script splits it with
the client's own stage timers (``db_client_internal_stage_seconds``), which are
compiled in and cost one atomic load when they are off:

write (``batch_write_numpy``)
    ``row_parse``      NumPy rows -> Aerospike keys and bins
    ``attach_policy``  the intermediate vector that pairs each row with the policy
    ``build_ops``      rows -> batch operations (clones every key)
    ``io``             the batch call itself

read (``batch_read`` + ``to_numpy``)
    ``key_parse``      Python key tuples -> Aerospike keys
    ``io``             the batch call itself
    ``to_numpy``       results -> structured array (includes ``key_index``)
    ``key_index``      the key -> row dict of the result

The per-stage figure is the mean over ``--runs`` calls, which is what a
histogram's sum and count give; compare stages with one another, and use
``numpy_microbench.py`` for the medians of whole calls.

    make run-aerospike-ce                          # from the repo root
    uv run python benchmark/numpy_stage_breakdown.py
    uv run python benchmark/numpy_stage_breakdown.py --rows 720 --fields 8 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time

DEFAULT_HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))
DEFAULT_CLUSTER = os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker")

NAMESPACE = "test"
SET_NAME = "np_stage_breakdown"

_SAMPLE = re.compile(r"^db_client_internal_stage_seconds_(sum|count)\{(?P<labels>[^}]*)\} (?P<value>\S+)$")


def _stages(metrics_text: str) -> dict[tuple[str, str], dict[str, float]]:
    """{(operation, stage): {"sum": seconds, "count": calls}} from a metrics exposition."""
    stages: dict[tuple[str, str], dict[str, float]] = {}
    for line in metrics_text.splitlines():
        match = _SAMPLE.match(line)
        if not match:
            continue
        labels = dict(item.split("=", 1) for item in match["labels"].split(","))
        key = (labels["db_operation_name"].strip('"'), labels["stage"].strip('"'))
        stages.setdefault(key, {})[match[1]] = float(match["value"])
    return stages


def _delta(before, after):
    out = {}
    for key, totals in after.items():
        count = totals.get("count", 0.0) - before.get(key, {}).get("count", 0.0)
        seconds = totals.get("sum", 0.0) - before.get(key, {}).get("sum", 0.0)
        if count > 0:
            out[key] = {"calls": int(count), "mean_us": seconds / count * 1e6}
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cluster-name", default=DEFAULT_CLUSTER)
    parser.add_argument("--rows", type=int, default=720)
    parser.add_argument("--fields", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=51)
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()

    import aerospike_py
    import numpy as np

    dtype = np.dtype([("_key", "i8")] + [(f"f{i}", "f8") for i in range(args.fields)])
    array = np.zeros(args.rows, dtype=dtype)
    array["_key"] = np.arange(args.rows)
    for i in range(args.fields):
        array[f"f{i}"] = np.linspace(0.0, 1.0, args.rows) + i
    keys = [(NAMESPACE, SET_NAME, int(k)) for k in array["_key"]]
    read_dtype = np.dtype([(f"f{i}", "f8") for i in range(args.fields)])

    client = aerospike_py.AsyncClient({"hosts": [(args.host, args.port)], "cluster_name": args.cluster_name})
    await client.connect()
    try:
        for _ in range(args.warmup):
            await client.batch_write_numpy(array, NAMESPACE, SET_NAME, dtype)
            (await client.batch_read(keys)).to_numpy(read_dtype)

        whole = {"write": [], "read": []}
        with aerospike_py.internal_stage_profiling():
            before = _stages(aerospike_py.get_metrics())
            for _ in range(args.runs):
                started = time.perf_counter()
                await client.batch_write_numpy(array, NAMESPACE, SET_NAME, dtype)
                whole["write"].append(time.perf_counter() - started)
                started = time.perf_counter()
                (await client.batch_read(keys)).to_numpy(read_dtype)
                whole["read"].append(time.perf_counter() - started)
            after = _stages(aerospike_py.get_metrics())
    finally:
        await client.truncate(NAMESPACE, SET_NAME, 0)
        await client.close()

    stages = _delta(before, after)
    report = {
        "rows": args.rows,
        "fields": args.fields,
        "runs": args.runs,
        "whole_call_mean_us": {name: sum(times) / len(times) * 1e6 for name, times in whole.items()},
        "stages": {f"{operation}.{stage}": figures for (operation, stage), figures in sorted(stages.items())},
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"{args.rows} rows x {args.fields} float64 fields, mean of {args.runs} calls (microseconds)")
    for name, mean_us in report["whole_call_mean_us"].items():
        print(f"  whole {name:<26} {mean_us:10.1f}")
    for name, figures in report["stages"].items():
        print(f"  {name:<32} {figures['mean_us']:10.1f}")


if __name__ == "__main__":
    asyncio.run(main())
