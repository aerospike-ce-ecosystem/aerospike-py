"""Aggregate cell artifacts into one Markdown report + Phase 0 gate verdict.

Usage:
    uv run python scripts/compose_report.py results/saturation_<date>/

Reads each cell directory's:
    - k6_summary.json
    - container_stats.json
    - meta.json

Produces ``report.md`` and ``baseline.json`` at the parent directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASES = ["vu_10", "vu_50", "vu_100", "vu_150", "vu_200"]


def _extract_phase_metrics(k6_summary: dict, phase: str) -> dict:
    metrics = k6_summary.get("metrics", {})
    lat = metrics.get("endpoint_latency_ms", {}).get("values", {})
    reqs = metrics.get("predict_requests", {}).get("values", {})
    # k6's per-phase tagging requires reading the JSON stream, not the
    # summary. As a first approximation we read the whole-run summary and
    # let the user inspect raw k6 output for per-phase splits.
    return {
        "phase": phase,
        "p50": lat.get("med", 0.0),
        "p95": lat.get("p(95)", 0.0),
        "p99": lat.get("p(99)", 0.0),
        "mean": lat.get("avg", 0.0),
        "max": lat.get("max", 0.0),
        "requests_total": reqs.get("count", 0),
        "rps_run_avg": reqs.get("rate", 0.0),
    }


def _load_cell(cell_dir: Path) -> dict | None:
    try:
        k6 = json.loads((cell_dir / "k6_summary.json").read_text())
        stats = json.loads((cell_dir / "container_stats.json").read_text())
        meta = json.loads((cell_dir / "meta.json").read_text())
    except FileNotFoundError as e:
        print(f"skip {cell_dir.name}: missing {e.filename}", file=sys.stderr)
        return None

    return {
        "label": cell_dir.name,
        "client": meta.get("client"),
        "python": meta.get("python_version"),
        "cpu_p50": stats["summary"]["cpu_pct_p50"],
        "cpu_p95": stats["summary"]["cpu_pct_p95"],
        "cpu_max": stats["summary"]["cpu_pct_max"],
        "mem_max_mb": round(stats["summary"]["mem_bytes_max"] / 1_000_000, 1),
        "run_avg": _extract_phase_metrics(k6, "run"),
    }


def _gate_verdict(cells: list[dict]) -> tuple[bool, list[str]]:
    """Phase 0 gate: aerospike-py CPU% must be ≥30%p higher than C ext at
    matched latency. We use the run-average CPU% as a coarse proxy; manual
    per-phase analysis from k6_raw.json is needed to confirm."""
    reasons: list[str] = []
    by_client = {(c["client"], c["python"]): c for c in cells}
    for py in {c["python"] for c in cells}:
        py_cell = by_client.get(("aerospike-py", py))
        legacy_cell = by_client.get(("legacy", py))
        if not (py_cell and legacy_cell):
            reasons.append(f"py={py}: missing one client cell")
            continue
        diff = py_cell["cpu_p95"] - legacy_cell["cpu_p95"]
        if diff < 30.0:
            reasons.append(
                f"py={py}: CPU diff {diff:.1f}%p < 30%p threshold "
                f"(aerospike-py {py_cell['cpu_p95']:.1f}%, legacy {legacy_cell['cpu_p95']:.1f}%)"
            )
    return (not reasons), reasons


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("run_root", type=Path, help="results/saturation_<date>/ directory")
    args = p.parse_args()

    cell_dirs = sorted(d for d in args.run_root.iterdir() if d.is_dir())
    cells = [c for c in (_load_cell(d) for d in cell_dirs) if c is not None]
    if not cells:
        print("no valid cells found", file=sys.stderr)
        return 1

    passed, reasons = _gate_verdict(cells)

    lines = [
        f"# Saturation reproducer — {args.run_root.name}",
        "",
        "## Cell summary (run-average)",
        "",
        "| Cell | Client | Python | CPU p50 | CPU p95 | CPU max | RSS max | p95 latency | p99 latency | RPS |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        m = c["run_avg"]
        lines.append(
            f"| `{c['label']}` | {c['client']} | {c['python']} "
            f"| {c['cpu_p50']:.1f}% | {c['cpu_p95']:.1f}% | {c['cpu_max']:.1f}% "
            f"| {c['mem_max_mb']:.0f} MB | {m['p95']:.0f} ms | {m['p99']:.0f} ms "
            f"| {m['rps_run_avg']:.1f} |"
        )

    lines += [
        "",
        "## Phase 0 → Phase 1 gate",
        "",
        f"**Verdict: {'PASS ✅' if passed else 'FAIL ❌'}**",
        "",
    ]
    if reasons:
        lines.append("Failure reasons:")
        for r in reasons:
            lines.append(f"- {r}")
    else:
        lines.append("CPU% gap ≥ 30%p satisfied across all Python versions.")
    lines += [
        "",
        "> Per-phase analysis (VU 10/50/100/150/200) requires post-processing the",
        "> per-phase k6 `metrics` stream from `<cell>/k6_raw.json`. The run-average",
        "> shown here is a coarse first pass.",
    ]

    (args.run_root / "report.md").write_text("\n".join(lines) + "\n")
    baseline = {"gate_passed": passed, "reasons": reasons, "cells": cells}
    (args.run_root / "baseline.json").write_text(json.dumps(baseline, indent=2))

    print(f"wrote {args.run_root / 'report.md'}", file=sys.stderr)
    print(f"wrote {args.run_root / 'baseline.json'}", file=sys.stderr)
    return 0 if passed else 0  # don't fail CI on gate; let humans decide


if __name__ == "__main__":
    sys.exit(main())
