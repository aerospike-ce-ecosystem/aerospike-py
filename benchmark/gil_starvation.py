#!/usr/bin/env python3
"""Event-loop starvation and CPU efficiency under concurrent ``batch_read`` load.

Issue #347 reports that in a CPU-saturated multi-worker production service,
aerospike-py uses ~2.4x more CPU per RPS than the official C-extension client,
and that the *inference* thread slows down 2.6x — a symptom of GIL contention
rather than of database latency. The existing ``benchmark/`` harness measures
end-to-end HTTP throughput, which cannot separate those two.

This script measures the two quantities that can:

**Event-loop starvation.** A sibling asyncio task samples ``perf_counter()`` in a
tight loop while N ``batch_read`` calls are in flight. Every gap between
consecutive samples is time the event loop was *not* running — because some other
thread held the GIL. This is the closest dependency-free proxy for "how long does
this client keep the GIL from my inference code", and it needs no torch, no oha
and no cluster: a busy-loop thread is a sufficient GIL competitor.

**Operations per CPU-second.** ``RUSAGE_SELF`` user+system time divided into
completed operations. This is issue #347's "RPS / core" expressed for a single
process, and it is the number that decides where a CPU-bound pod saturates.

Both are reported for aerospike-py and, when it is installed, for the official
``aerospike`` client driven the way the issue describes (sync calls pushed
through ``run_in_executor``). Run it against a local Aerospike:

    make run-aerospike-ce                      # from the repo root
    uv run python benchmark/gil_starvation.py

Useful knobs::

    --keys 720 --concurrency 16 --duration 10   # shape from issue #347
    --cpu-competitor                            # add a GIL-holding busy thread
    --client py                                 # or: official, both
    --materialise none                          # skip building Python objects

**``--materialise none`` is deliberately asymmetric, and that is what makes it
useful.** aerospike-py can genuinely skip conversion — ``batch_read`` returns a
zero-conversion handle and ``to_dict()`` is a separate step. The C client cannot:
it converts every record to Python objects inside its own read callback, so
``none`` only skips the final dict build. If aerospike-py is *still* less
CPU-efficient while doing strictly less work, the difference is in the request
path rather than in per-record conversion.

Interpreting the output: a client that holds the GIL in long stretches shows a
high starvation p99 even when its throughput looks fine, and that is what makes a
co-located CPU-bound workload slow down. Comparing the two clients' starvation
profiles under identical load is the point; the absolute numbers are specific to
the machine and the server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import threading
import time
from dataclasses import dataclass, field

DEFAULT_HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))
DEFAULT_CLUSTER = os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker")

NAMESPACE = "test"
SET_NAME = "gil_bench"


# ── measurement helpers ─────────────────────────────────────────────────────


def _cpu_seconds() -> float:
    """User + system CPU consumed by this process, including all its threads."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return float("nan")
    index = min(len(sorted_values) - 1, int(len(sorted_values) * fraction))
    return sorted_values[index]


@dataclass
class Result:
    client: str
    operations: int = 0
    records: int = 0
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    starvation_ms: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float | int | str]:
        latencies = sorted(self.latencies_ms)
        starvation = sorted(self.starvation_ms)
        return {
            "client": self.client,
            "operations": self.operations,
            "records": self.records,
            "wall_s": round(self.wall_seconds, 3),
            "cpu_s": round(self.cpu_seconds, 3),
            "ops_per_s": round(self.operations / self.wall_seconds, 1) if self.wall_seconds else 0.0,
            "ops_per_cpu_s": round(self.operations / self.cpu_seconds, 1) if self.cpu_seconds else 0.0,
            "cpu_utilisation": round(self.cpu_seconds / self.wall_seconds, 2) if self.wall_seconds else 0.0,
            "latency_p50_ms": round(_percentile(latencies, 0.50), 3),
            "latency_p95_ms": round(_percentile(latencies, 0.95), 3),
            "latency_p99_ms": round(_percentile(latencies, 0.99), 3),
            "starvation_samples": len(starvation),
            "starvation_p50_ms": round(_percentile(starvation, 0.50), 3),
            "starvation_p95_ms": round(_percentile(starvation, 0.95), 3),
            "starvation_p99_ms": round(_percentile(starvation, 0.99), 3),
            "starvation_max_ms": round(starvation[-1], 3) if starvation else float("nan"),
        }


async def _starvation_sampler(stop: asyncio.Event, out: list[float]) -> None:
    """Record every gap between consecutive event-loop turns.

    ``asyncio.sleep(0)`` yields to the loop and comes straight back, so a gap
    materially larger than the loop's own overhead is time this coroutine was
    ready but could not run — the GIL was held elsewhere.
    """
    previous = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(0)
        now = time.perf_counter()
        out.append((now - previous) * 1000.0)
        previous = now


def _busy_loop(stop: threading.Event) -> None:
    """A pure-Python CPU competitor, standing in for co-located inference."""
    total = 0
    while not stop.is_set():
        for i in range(10_000):
            total += i * i
    return None


# ── clients ─────────────────────────────────────────────────────────────────


class PyClientRunner:
    """aerospike-py AsyncClient, awaited natively."""

    name = "aerospike-py"

    def __init__(self, host: str, port: int, cluster: str, materialise: str = "dict") -> None:
        import aerospike_py

        self._client = aerospike_py.AsyncClient({"hosts": [(host, port)], "cluster_name": cluster})
        self._materialise = materialise

    async def connect(self) -> None:
        await self._client.connect()

    async def close(self) -> None:
        await self._client.close()

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> int:
        handle = await self._client.batch_read(keys)
        # `none` stops at the zero-conversion Handle, isolating request-path cost
        # from per-record conversion cost.
        if self._materialise == "none":
            return 0
        return len(handle.to_dict())


class OfficialClientRunner:
    """Official C-extension client, sync calls pushed through run_in_executor.

    This mirrors how issue #347 describes the production comparison: the C
    client has no native async API, so the service wraps it in the default
    executor.
    """

    name = "aerospike (C ext)"

    def __init__(self, host: str, port: int, cluster: str, materialise: str = "dict") -> None:
        import aerospike

        self._client = aerospike.client({"hosts": [(host, port)]})
        self._materialise = materialise

    async def connect(self) -> None:
        self._client.connect()

    async def close(self) -> None:
        self._client.close()

    def _batch_read_sync(self, keys: list[tuple[str, str, str]]) -> int:
        records = self._client.batch_read(keys)
        if self._materialise == "none":
            return 0
        materialised = {}
        for batch_record in records.batch_records:
            if batch_record.result == 0 and batch_record.record is not None:
                materialised[batch_record.key[2]] = batch_record.record[2]
        return len(materialised)

    async def batch_read(self, keys: list[tuple[str, str, str]]) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._batch_read_sync, keys)


# ── benchmark ───────────────────────────────────────────────────────────────


async def run_one(
    runner,
    keys: list[tuple[str, str, str]],
    concurrency: int,
    duration: float,
    cpu_competitor: bool,
) -> Result:
    await runner.connect()
    result = Result(client=runner.name)

    # Warm up connections and the executor pool so neither is charged to the
    # measured window.
    await asyncio.gather(*(runner.batch_read(keys) for _ in range(concurrency)))

    stop_sampler = asyncio.Event()
    sampler = asyncio.create_task(_starvation_sampler(stop_sampler, result.starvation_ms))

    competitor_stop = threading.Event()
    competitor: threading.Thread | None = None
    if cpu_competitor:
        competitor = threading.Thread(target=_busy_loop, args=(competitor_stop,), daemon=True)
        competitor.start()

    deadline = time.perf_counter() + duration
    cpu_before = _cpu_seconds()
    wall_before = time.perf_counter()

    async def worker() -> None:
        while time.perf_counter() < deadline:
            started = time.perf_counter()
            count = await runner.batch_read(keys)
            result.latencies_ms.append((time.perf_counter() - started) * 1000.0)
            result.operations += 1
            result.records += count

    await asyncio.gather(*(worker() for _ in range(concurrency)))

    result.wall_seconds = time.perf_counter() - wall_before
    result.cpu_seconds = _cpu_seconds() - cpu_before

    competitor_stop.set()
    if competitor is not None:
        competitor.join(timeout=5)

    stop_sampler.set()
    await sampler
    await runner.close()
    return result


def build_keys(count: int) -> list[tuple[str, str, str]]:
    return [(NAMESPACE, SET_NAME, f"gk{i}") for i in range(count)]


def seed(host: str, port: int, cluster: str, count: int, bins: int) -> None:
    import aerospike_py

    client = aerospike_py.client({"hosts": [(host, port)], "cluster_name": cluster}).connect()
    payload = {f"b{i}": float(i) for i in range(bins)}
    records = [((NAMESPACE, SET_NAME, f"gk{i}"), dict(payload, idx=i)) for i in range(count)]
    for start in range(0, len(records), 1000):
        client.batch_write(records[start : start + 1000])
    client.close()
    print(f"seeded {count} records x {bins} bins into {NAMESPACE}/{SET_NAME}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cluster-name", default=DEFAULT_CLUSTER)
    parser.add_argument("--keys", type=int, default=720, help="keys per batch_read (issue #347 uses 720)")
    parser.add_argument("--bins", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=8, help="batch_read calls in flight")
    parser.add_argument("--duration", type=float, default=10.0, help="measured seconds per client")
    parser.add_argument("--client", choices=("py", "official", "both"), default="both")
    parser.add_argument(
        "--materialise",
        choices=("dict", "none"),
        default="dict",
        help="`none` returns the raw handle without building Python objects, "
        "isolating request-path cost from per-record conversion cost",
    )
    parser.add_argument(
        "--cpu-competitor",
        action="store_true",
        help="run a pure-Python busy loop alongside, standing in for co-located inference",
    )
    parser.add_argument("--no-seed", action="store_true", help="assume the data is already present")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()

    if not args.no_seed:
        seed(args.host, args.port, args.cluster_name, args.keys, args.bins)

    keys = build_keys(args.keys)
    runners = []
    if args.client in ("py", "both"):
        runners.append(PyClientRunner(args.host, args.port, args.cluster_name, args.materialise))
    if args.client in ("official", "both"):
        try:
            runners.append(OfficialClientRunner(args.host, args.port, args.cluster_name, args.materialise))
        except ImportError:
            print(
                "official `aerospike` client not installed — measuring aerospike-py only (pip install aerospike)",
                file=sys.stderr,
            )

    results = [
        asyncio.run(run_one(runner, keys, args.concurrency, args.duration, args.cpu_competitor)) for runner in runners
    ]
    summaries = [r.summary() for r in results]

    if args.json:
        print(json.dumps({"config": vars(args), "results": summaries}, indent=2))
        return 0

    print(
        f"\nbatch_read: {args.keys} keys x {args.bins} bins, concurrency={args.concurrency}, "
        f"{args.duration:g}s per client, materialise={args.materialise}, "
        f"cpu_competitor={args.cpu_competitor}"
    )
    columns = [
        ("client", 18),
        ("ops_per_s", 10),
        ("ops_per_cpu_s", 14),
        ("cpu_utilisation", 16),
        ("latency_p99_ms", 15),
        ("starvation_p99_ms", 18),
        ("starvation_max_ms", 18),
    ]
    print("".join(name.rjust(width) for name, width in columns))
    for summary in summaries:
        print("".join(str(summary[name]).rjust(width) for name, width in columns))

    if len(summaries) == 2:
        py, official = summaries[0], summaries[1]
        if official["ops_per_cpu_s"]:
            ratio = official["ops_per_cpu_s"] / py["ops_per_cpu_s"]
            print(
                f"\nCPU efficiency: the C client completes {ratio:.2f}x the operations per "
                f"CPU-second that aerospike-py does (issue #347 reports 2.4x in production)."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
