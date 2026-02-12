"""Generate benchmark report: JSON data for Docusaurus React charts.

Called from bench_compare.py with --report flag.
Outputs date-stamped JSON files and maintains an index.json for the React UI.
Charts are rendered client-side by Recharts components.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench_compare import BenchmarkResults

OPERATIONS = ["put", "get", "batch_read", "batch_read_numpy", "batch_write", "scan"]
OP_LABELS = {
    "put": "PUT",
    "get": "GET",
    "batch_read": "BATCH_READ",
    "batch_read_numpy": "BATCH_READ_NUMPY",
    "batch_write": "BATCH_WRITE",
    "scan": "SCAN",
}


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

    # batch_read_numpy (Sync/Async) vs Official batch_read comparison
    if has_c:
        numpy_sync = results.rust_sync.get("batch_read_numpy", {}).get("avg_ms", 0)
        numpy_async = results.rust_async.get("batch_read_numpy", {}).get("avg_ms", 0)
        official_br = results.c_sync.get("batch_read", {}).get("avg_ms", 0)
        if numpy_sync and official_br and numpy_sync > 0 and official_br > 0:
            ratio = official_br / numpy_sync
            if ratio >= 1.0:
                takeaways.append(
                    f"BATCH_READ_NUMPY (SyncClient) is **{ratio:.1f}x** faster than "
                    f"official BATCH_READ (returns numpy structured array vs Python dict)"
                )
            else:
                inv = 1 / ratio
                takeaways.append(
                    f"BATCH_READ_NUMPY (SyncClient) is **{inv:.1f}x** slower than "
                    f"official BATCH_READ (returns numpy structured array vs Python dict)"
                )
        if numpy_async and official_br and numpy_async > 0 and official_br > 0:
            ratio = official_br / numpy_async
            if ratio >= 1.0:
                takeaways.append(
                    f"BATCH_READ_NUMPY (AsyncClient) is **{ratio:.1f}x** faster than "
                    f"official BATCH_READ (returns numpy structured array vs Python dict)"
                )
            else:
                inv = 1 / ratio
                takeaways.append(
                    f"BATCH_READ_NUMPY (AsyncClient) is **{inv:.1f}x** slower than "
                    f"official BATCH_READ (returns numpy structured array vs Python dict)"
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


# ── numpy batch report ────────────────────────────────────────


def _safe_ratio(numerator_ms: float | None, denominator_ms: float | None) -> float:
    """Return numerator / denominator safely, 0 if invalid."""
    if not numerator_ms or not denominator_ms or denominator_ms <= 0:
        return 0.0
    return numerator_ms / denominator_ms


def _numpy_takeaways(results) -> list[str]:
    """Generate key insights from numpy batch benchmark results."""
    takeaways = []

    # Record scaling insight (sync + async)
    if results.record_scaling:
        data = results.record_scaling["data"]
        if len(data) >= 2:
            last = data[-1]
            rc = last["record_count"]

            sync_ratio = _safe_ratio(
                last["batch_read_sync"]["avg_ms"],
                last["batch_read_numpy_sync"]["avg_ms"],
            )
            if sync_ratio > 1:
                takeaways.append(
                    f"At {rc:,} records, batch_read_numpy is **{sync_ratio:.1f}x** faster than batch_read (Sync)"
                )

            async_ratio = _safe_ratio(
                last.get("batch_read_async", {}).get("avg_ms"),
                last.get("batch_read_numpy_async", {}).get("avg_ms"),
            )
            if async_ratio > 1:
                takeaways.append(
                    f"At {rc:,} records, batch_read_numpy is **{async_ratio:.1f}x** faster than batch_read (Async)"
                )

    # Bin scaling insight - report the bin count with the best async speedup
    if results.bin_scaling:
        data = results.bin_scaling["data"]
        best_async = {"ratio": 0.0, "bins": 0}
        best_sync = {"ratio": 0.0, "bins": 0}
        for entry in data:
            sr = _safe_ratio(
                entry["batch_read_sync"]["avg_ms"],
                entry["batch_read_numpy_sync"]["avg_ms"],
            )
            ar = _safe_ratio(
                entry.get("batch_read_async", {}).get("avg_ms"),
                entry.get("batch_read_numpy_async", {}).get("avg_ms"),
            )
            if sr > best_sync["ratio"]:
                best_sync = {"ratio": sr, "bins": entry["bin_count"]}
            if ar > best_async["ratio"]:
                best_async = {"ratio": ar, "bins": entry["bin_count"]}

        if best_sync["ratio"] > 1:
            takeaways.append(
                f"Bin scaling: numpy is up to **{best_sync['ratio']:.1f}x** faster "
                f"at {best_sync['bins']} bins (Sync, {results.bin_scaling['fixed_records']:,} records)"
            )
        if best_async["ratio"] > 1:
            takeaways.append(
                f"Bin scaling: numpy is up to **{best_async['ratio']:.1f}x** faster "
                f"at {best_async['bins']} bins (Async)"
            )

    # Post-processing insight - find the stage with the best speedup
    if results.post_processing:
        data = results.post_processing["data"]
        best_stage_sync = {"ratio": 0.0, "label": ""}
        best_stage_async = {"ratio": 0.0, "label": ""}
        for entry in data:
            sr = _safe_ratio(
                entry["batch_read_sync"]["avg_ms"],
                entry["batch_read_numpy_sync"]["avg_ms"],
            )
            ar = _safe_ratio(
                entry.get("batch_read_async", {}).get("avg_ms"),
                entry.get("batch_read_numpy_async", {}).get("avg_ms"),
            )
            if sr > best_stage_sync["ratio"]:
                best_stage_sync = {"ratio": sr, "label": entry["stage_label"]}
            if ar > best_stage_async["ratio"]:
                best_stage_async = {"ratio": ar, "label": entry["stage_label"]}

        if best_stage_sync["ratio"] > 1:
            takeaways.append(
                f"Post-processing: numpy **{best_stage_sync['label']}** is "
                f"**{best_stage_sync['ratio']:.1f}x** faster (Sync)"
            )
        if best_stage_async["ratio"] > 1:
            takeaways.append(
                f"Post-processing: numpy **{best_stage_async['label']}** is "
                f"**{best_stage_async['ratio']:.1f}x** faster (Async)"
            )

    # Memory insight
    if results.memory:
        data = results.memory["data"]
        if data:
            last = data[-1]
            if last["savings_pct"] > 0:
                takeaways.append(
                    f"At {last['record_count']:,} records, numpy uses "
                    f"**{last['savings_pct']:.0f}%** less memory than dict"
                )

    if not takeaways:
        takeaways.append("Benchmark results collected successfully")

    return takeaways


def _metrics_dict(d: dict) -> dict:
    """Extract avg_ms, ops_per_sec, stdev_ms from a bulk_median result."""
    return {
        "avg_ms": d.get("avg_ms"),
        "ops_per_sec": d.get("ops_per_sec"),
        "stdev_ms": d.get("stdev_ms"),
    }


def generate_numpy_report(results, json_dir: str, date_slug: str) -> None:
    """Generate numpy batch benchmark report JSON."""
    now = datetime.fromisoformat(results.timestamp)
    json_filename = f"{date_slug}.json"

    os.makedirs(json_dir, exist_ok=True)

    print("\n  Generating numpy batch benchmark report...")
    print(f"    JSON dir: {json_dir}")

    report: dict = {
        "timestamp": now.isoformat(),
        "date": date_slug,
        "report_type": "numpy_batch",
        "environment": {
            "platform": results.platform_info,
            "python_version": results.python_version,
            "rounds": results.rounds,
            "warmup": results.warmup,
            "concurrency": results.concurrency,
            "batch_groups": results.batch_groups,
        },
    }

    # Record scaling
    if results.record_scaling:
        report["record_scaling"] = {
            "fixed_bins": results.record_scaling["fixed_bins"],
            "data": [
                {
                    "record_count": d["record_count"],
                    "batch_read_sync": _metrics_dict(d["batch_read_sync"]),
                    "batch_read_numpy_sync": _metrics_dict(d["batch_read_numpy_sync"]),
                    "batch_read_async": _metrics_dict(d.get("batch_read_async", {})),
                    "batch_read_numpy_async": _metrics_dict(d.get("batch_read_numpy_async", {})),
                }
                for d in results.record_scaling["data"]
            ],
        }

    # Bin scaling
    if results.bin_scaling:
        report["bin_scaling"] = {
            "fixed_records": results.bin_scaling["fixed_records"],
            "data": [
                {
                    "bin_count": d["bin_count"],
                    "batch_read_sync": _metrics_dict(d["batch_read_sync"]),
                    "batch_read_numpy_sync": _metrics_dict(d["batch_read_numpy_sync"]),
                    "batch_read_async": _metrics_dict(d.get("batch_read_async", {})),
                    "batch_read_numpy_async": _metrics_dict(d.get("batch_read_numpy_async", {})),
                }
                for d in results.bin_scaling["data"]
            ],
        }

    # Post-processing
    if results.post_processing:
        report["post_processing"] = {
            "record_count": results.post_processing["record_count"],
            "bin_count": results.post_processing["bin_count"],
            "data": [
                {
                    "stage": d["stage"],
                    "stage_label": d["stage_label"],
                    "batch_read_sync": _metrics_dict(d["batch_read_sync"]),
                    "batch_read_numpy_sync": _metrics_dict(d["batch_read_numpy_sync"]),
                    "batch_read_async": _metrics_dict(d.get("batch_read_async", {})),
                    "batch_read_numpy_async": _metrics_dict(d.get("batch_read_numpy_async", {})),
                }
                for d in results.post_processing["data"]
            ],
        }

    # Memory
    if results.memory:
        report["memory"] = {
            "bin_count": results.memory["bin_count"],
            "data": results.memory["data"],
        }

    report["takeaways"] = _numpy_takeaways(results)

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


# ── main entry point ─────────────────────────────────────────


def generate_report(results: BenchmarkResults, json_dir: str, date_slug: str) -> None:
    """Generate benchmark report JSON (charts rendered client-side by Recharts)."""
    now = datetime.fromisoformat(results.timestamp)
    json_filename = f"{date_slug}.json"

    os.makedirs(json_dir, exist_ok=True)

    print("\n  Generating benchmark report...")
    print(f"    JSON dir: {json_dir}")

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
