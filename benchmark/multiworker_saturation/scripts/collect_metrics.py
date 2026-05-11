"""Poll ``podman stats`` for container CPU% and RSS during a benchmark run.

Usage:
    uv run python scripts/collect_metrics.py \
        --container saturation-app \
        --duration 500 \
        --out results/<run>/<cell>.container_stats.json

Output JSON:
    {
        "container": "saturation-app",
        "samples": [{"ts": <unix>, "cpu_pct": <float>, "mem_bytes": <int>}, ...],
        "summary": {
            "cpu_pct_p50": <float>,
            "cpu_pct_p95": <float>,
            "cpu_pct_max": <float>,
            "mem_bytes_max": <int>,
        }
    }
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path


def _parse_pct(s: str) -> float:
    # podman stats prints "42.13%"
    return float(s.strip().rstrip("%"))


def _parse_size(s: str) -> int:
    """Parse strings like '123.4MB' / '1.2GiB' / '512kB' to bytes."""
    s = s.strip()
    units = {
        "B": 1,
        "kB": 1_000,
        "KB": 1_024,
        "KiB": 1_024,
        "MB": 1_000_000,
        "MiB": 1_024**2,
        "GB": 1_000_000_000,
        "GiB": 1_024**3,
    }
    for unit, mult in sorted(units.items(), key=lambda x: -len(x[0])):
        if s.endswith(unit):
            return int(float(s[: -len(unit)]) * mult)
    return int(float(s))


def _sample(container: str) -> dict | None:
    proc = subprocess.run(
        ["podman", "stats", "--no-stream", "--format", "json", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not data:
        return None
    row = data[0]
    # podman 5.x uses lowercase keys: cpu_percent, mem_usage, mem_percent.
    # mem_usage format: "346.2MB / 2.147GB" (note spaces around the slash).
    mem_field = row.get("mem_usage") or row.get("MemUsage") or "0B / 0B"
    used_str = mem_field.split("/")[0].strip()
    cpu_field = row.get("cpu_percent") or row.get("CPU") or "0%"
    return {
        "ts": time.time(),
        "cpu_pct": _parse_pct(cpu_field),
        "mem_bytes": _parse_size(used_str),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--container", required=True)
    p.add_argument("--duration", type=int, required=True, help="seconds")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    samples: list[dict] = []
    end_at = time.time() + args.duration
    while time.time() < end_at:
        s = _sample(args.container)
        if s is not None:
            samples.append(s)
        time.sleep(args.interval)

    cpu = [s["cpu_pct"] for s in samples]
    mem = [s["mem_bytes"] for s in samples]
    summary = {
        "cpu_pct_p50": statistics.median(cpu) if cpu else 0.0,
        "cpu_pct_p95": _percentile(cpu, 95),
        "cpu_pct_max": max(cpu) if cpu else 0.0,
        "mem_bytes_max": max(mem) if mem else 0,
        "sample_count": len(samples),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"container": args.container, "samples": samples, "summary": summary}, indent=2)
    )
    print(f"wrote {args.out} ({len(samples)} samples)", file=sys.stderr)
    return 0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


if __name__ == "__main__":
    sys.exit(main())
