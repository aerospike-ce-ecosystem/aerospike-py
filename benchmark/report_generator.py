"""Generate benchmark report: JSON + SVG charts for Docusaurus docs.

Called from bench_compare.py with --report flag.
Outputs date-stamped JSON files and maintains an index.json for the React UI.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench_compare import BenchmarkResults

# ── chart colors ─────────────────────────────────────────────

COLOR_SYNC = "#673ab7"  # purple
COLOR_OFFICIAL = "#78909c"  # grey
COLOR_ASYNC = "#4caf50"  # green

OPERATIONS = ["put", "get", "batch_read", "batch_write", "scan"]
OP_LABELS = {
    "put": "PUT",
    "get": "GET",
    "batch_read": "BATCH_READ",
    "batch_write": "BATCH_WRITE",
    "scan": "SCAN",
}


# ── chart generation ─────────────────────────────────────────


def generate_charts(results: BenchmarkResults, img_dir: str) -> dict[str, str]:
    """Generate SVG charts and return mapping of chart_name -> file_path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(img_dir, exist_ok=True)

    chart_paths = {}
    has_c = results.c_sync is not None

    # Common style for all charts
    plt.rcParams.update(
        {
            "figure.facecolor": "none",
            "axes.facecolor": "none",
            "savefig.facecolor": "none",
            "text.color": "#333333",
            "axes.labelcolor": "#333333",
            "xtick.color": "#333333",
            "ytick.color": "#333333",
            "axes.edgecolor": "#cccccc",
            "font.family": "sans-serif",
            "font.size": 11,
        }
    )

    # --- 1. Latency comparison chart ---
    chart_paths["latency"] = _generate_bar_chart(
        results,
        metric="avg_ms",
        ylabel="Latency (ms)",
        title="Avg Latency Comparison (lower is better)",
        filename="latency_comparison.svg",
        img_dir=img_dir,
        has_c=has_c,
        lower_is_better=True,
    )

    # --- 2. Throughput comparison chart ---
    chart_paths["throughput"] = _generate_bar_chart(
        results,
        metric="ops_per_sec",
        ylabel="Throughput (ops/sec)",
        title="Throughput Comparison (higher is better)",
        filename="throughput_comparison.svg",
        img_dir=img_dir,
        has_c=has_c,
        lower_is_better=False,
    )

    # --- 3. Tail latency chart ---
    chart_paths["tail_latency"] = _generate_tail_latency_chart(results, img_dir, has_c)

    return chart_paths


def _generate_bar_chart(
    results: BenchmarkResults,
    metric: str,
    ylabel: str,
    title: str,
    filename: str,
    img_dir: str,
    has_c: bool,
    lower_is_better: bool,
) -> str:
    import matplotlib.pyplot as plt
    import numpy as np

    ops = OPERATIONS
    labels = [OP_LABELS[op] for op in ops]

    rust_vals = [results.rust_sync[op].get(metric, 0) or 0 for op in ops]
    async_vals = [results.rust_async[op].get(metric, 0) or 0 for op in ops]
    c_vals = [results.c_sync[op].get(metric, 0) or 0 for op in ops] if has_c else None

    x = np.arange(len(ops))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))

    if has_c:
        offsets = [-width, 0, width]
        bars_rust = ax.bar(
            x + offsets[0],
            rust_vals,
            width,
            label="aerospike-py (SyncClient)",
            color=COLOR_SYNC,
        )
        ax.bar(
            x + offsets[1],
            c_vals,
            width,
            label="aerospike (official)",
            color=COLOR_OFFICIAL,
        )
        bars_async = ax.bar(
            x + offsets[2],
            async_vals,
            width,
            label="aerospike-py (AsyncClient)",
            color=COLOR_ASYNC,
        )
    else:
        offsets = [-width / 2, width / 2]
        bars_rust = ax.bar(
            x + offsets[0],
            rust_vals,
            width,
            label="aerospike-py (SyncClient)",
            color=COLOR_SYNC,
        )
        bars_async = ax.bar(
            x + offsets[1],
            async_vals,
            width,
            label="aerospike-py (AsyncClient)",
            color=COLOR_ASYNC,
        )

    # Add percentage difference labels on bars (vs C client)
    if has_c:
        for bars, vals in [(bars_rust, rust_vals), (bars_async, async_vals)]:
            for i, (bar, val) in enumerate(zip(bars, vals)):
                c_val = c_vals[i]
                if c_val > 0 and val > 0:
                    if lower_is_better:
                        pct = ((c_val - val) / c_val) * 100
                    else:
                        pct = ((val - c_val) / c_val) * 100
                    if pct > 0:
                        label = f"{pct:.0f}% faster"
                        color = COLOR_ASYNC
                    else:
                        label = f"{abs(pct):.0f}% slower"
                        color = "#e53935"
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height(),
                        label,
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color=color,
                        fontweight="bold",
                    )

    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc="upper right", framealpha=0.8)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    path = os.path.join(img_dir, filename)
    fig.savefig(path, format="svg", transparent=True, bbox_inches="tight")
    plt.close(fig)
    return path


def _generate_tail_latency_chart(
    results: BenchmarkResults, img_dir: str, has_c: bool
) -> str:
    import matplotlib.pyplot as plt
    import numpy as np

    # Only operations with per-op timing (p50/p99)
    ops = [op for op in OPERATIONS if results.rust_sync[op].get("p50_ms") is not None]
    if not ops:
        return ""

    labels = [OP_LABELS[op] for op in ops]
    n_ops = len(ops)

    fig, ax = plt.subplots(figsize=(10, 5))

    x = np.arange(n_ops)
    width = 0.15
    bar_groups = []

    # Rust p50/p99
    rust_p50 = [results.rust_sync[op]["p50_ms"] for op in ops]
    rust_p99 = [results.rust_sync[op]["p99_ms"] for op in ops]
    offset = 0
    bar_groups.append(
        ax.bar(
            x + offset * width,
            rust_p50,
            width,
            label="Sync p50",
            color=COLOR_SYNC,
            alpha=0.7,
        )
    )
    offset += 1
    bar_groups.append(
        ax.bar(
            x + offset * width,
            rust_p99,
            width,
            label="Sync p99",
            color=COLOR_SYNC,
            alpha=1.0,
        )
    )
    offset += 1

    if has_c:
        c_p50 = [results.c_sync[op].get("p50_ms") or 0 for op in ops]
        c_p99 = [results.c_sync[op].get("p99_ms") or 0 for op in ops]
        bar_groups.append(
            ax.bar(
                x + offset * width,
                c_p50,
                width,
                label="Official p50",
                color=COLOR_OFFICIAL,
                alpha=0.7,
            )
        )
        offset += 1
        bar_groups.append(
            ax.bar(
                x + offset * width,
                c_p99,
                width,
                label="Official p99",
                color=COLOR_OFFICIAL,
                alpha=1.0,
            )
        )
        offset += 1

    # Center the bar groups
    center_offset = (offset - 1) * width / 2
    ax.set_xticks(x + center_offset)
    ax.set_xticklabels(labels)

    ax.set_ylabel("Latency (ms)")
    ax.set_title(
        "Tail Latency: p50 vs p99 (lower is better)", fontweight="bold", pad=15
    )
    ax.legend(loc="upper right", framealpha=0.8)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    path = os.path.join(img_dir, "tail_latency.svg")
    fig.savefig(path, format="svg", transparent=True, bbox_inches="tight")
    plt.close(fig)
    return path


# ── takeaways ────────────────────────────────────────────────


def _generate_takeaways(results: BenchmarkResults) -> list[str]:
    """Generate auto-generated key insights from benchmark results."""
    takeaways = []
    has_c = results.c_sync is not None

    if has_c:
        # Find biggest latency win for Rust sync vs C
        best_op = None
        best_ratio = 0
        for op in OPERATIONS:
            rv = results.rust_sync[op].get("avg_ms", 0)
            cv = results.c_sync[op].get("avg_ms", 0)
            if rv and cv and rv > 0:
                ratio = cv / rv
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_op = op
        if best_op and best_ratio > 1:
            takeaways.append(
                f"aerospike-py (SyncClient) shows **{best_ratio:.1f}x** faster latency "
                f"than the official client in {OP_LABELS[best_op]} operations"
            )

        # Find biggest async win vs C
        best_async_op = None
        best_async_ratio = 0
        for op in OPERATIONS:
            av = results.rust_async[op].get("avg_ms", 0)
            cv = results.c_sync[op].get("avg_ms", 0)
            if av and cv and av > 0:
                ratio = cv / av
                if ratio > best_async_ratio:
                    best_async_ratio = ratio
                    best_async_op = op
        if best_async_op and best_async_ratio > 1:
            takeaways.append(
                f"AsyncClient shows **{best_async_ratio:.1f}x** faster latency "
                f"than the official client in {OP_LABELS[best_async_op]} operations"
            )

    # Async vs sync advantage
    best_async_sync_op = None
    best_async_sync_ratio = 0
    for op in OPERATIONS:
        av = results.rust_async[op].get("ops_per_sec", 0)
        rv = results.rust_sync[op].get("ops_per_sec", 0)
        if av and rv and rv > 0:
            ratio = av / rv
            if ratio > best_async_sync_ratio:
                best_async_sync_ratio = ratio
                best_async_sync_op = op
    if best_async_sync_op and best_async_sync_ratio > 1:
        takeaways.append(
            f"AsyncClient shows **{best_async_sync_ratio:.1f}x** higher throughput "
            f"than SyncClient in {OP_LABELS[best_async_sync_op]} operations (concurrency={results.concurrency})"
        )

    if not takeaways:
        takeaways.append("Benchmark results collected successfully")

    return takeaways


# ── JSON helpers ─────────────────────────────────────────────


def _op_dict(data: dict, op: str) -> dict:
    """Extract metrics for a single operation."""
    d = data.get(op, {})
    return {
        "avg_ms": d.get("avg_ms"),
        "p50_ms": d.get("p50_ms"),
        "p99_ms": d.get("p99_ms"),
        "ops_per_sec": d.get("ops_per_sec"),
        "stdev_ms": d.get("stdev_ms"),
    }


def _build_client_section(data: dict) -> dict:
    """Build the per-client section of JSON (put, get, batch_read, ...)."""
    return {op: _op_dict(data, op) for op in OPERATIONS}


def _chart_paths_to_web(chart_paths: dict[str, str], date_slug: str) -> dict[str, str]:
    """Convert absolute chart file paths to web-relative paths."""
    result = {}
    for name, path in chart_paths.items():
        if path:
            filename = os.path.basename(path)
            result[name] = f"/img/benchmark/{date_slug}/{filename}"
    return result


def _update_index(json_dir: str, date_slug: str, json_filename: str) -> None:
    """Add/update entry in index.json, keeping newest-first order."""
    index_path = os.path.join(json_dir, "index.json")

    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"reports": []}

    reports: list[dict] = index["reports"]

    # Remove existing entry with same date if re-running
    reports = [r for r in reports if r["date"] != date_slug]

    reports.insert(0, {"date": date_slug, "file": json_filename})

    # Sort newest first
    reports.sort(key=lambda r: r["date"], reverse=True)

    index["reports"] = reports

    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ── main entry point ─────────────────────────────────────────


def generate_report(
    results: BenchmarkResults, json_dir: str, img_dir: str, date_slug: str
) -> None:
    """Generate full benchmark report: charts + JSON."""
    now = datetime.fromisoformat(results.timestamp)
    json_filename = f"{date_slug}.json"

    # img_dir already includes the date folder from caller
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    print("\n  Generating benchmark report...")
    print(f"    JSON dir: {json_dir}")
    print(f"    Image dir: {img_dir}")

    # Generate charts
    chart_paths = generate_charts(results, img_dir)
    for name, path in chart_paths.items():
        if path:
            print(f"    Chart: {os.path.basename(path)}")

    # Build JSON report
    report = {
        "timestamp": now.isoformat(),
        "date": date_slug,
        "environment": {
            "platform": results.platform_info,
            "python_version": results.python_version,
            "count": results.count,
            "rounds": results.rounds,
            "warmup": results.warmup,
            "concurrency": results.concurrency,
            "batch_groups": results.batch_groups,
        },
        "rust_sync": _build_client_section(results.rust_sync),
        "c_sync": _build_client_section(results.c_sync) if results.c_sync else None,
        "rust_async": _build_client_section(results.rust_async),
        "charts": _chart_paths_to_web(chart_paths, date_slug),
        "takeaways": _generate_takeaways(results),
    }

    # Write JSON
    json_path = os.path.join(json_dir, json_filename)
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"    JSON: {json_filename}")

    # Update index.json
    _update_index(json_dir, date_slug, json_filename)
    print("    Index: index.json updated")
    print("  Done.\n")
