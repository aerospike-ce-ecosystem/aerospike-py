"""Generate benchmark report: JSON data for Docusaurus React charts.

Called from bench_compare.py with --report flag.
Outputs a single latest.json file that the React UI loads directly.
Charts are rendered client-side by Recharts components.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench_compare import BenchmarkResults

OPERATIONS = [
    "put",
    "get",
    "operate",
    "remove",
    "batch_read",
    "batch_read_numpy",
    "batch_write",
    "batch_write_numpy",
    "query",
]
OP_LABELS = {
    "put": "PUT",
    "get": "GET",
    "operate": "OPERATE",
    "remove": "REMOVE",
    "batch_read": "BATCH_READ",
    "batch_read_numpy": "BATCH_READ_NUMPY",
    "batch_write": "BATCH_WRITE",
    "batch_write_numpy": "BATCH_WRITE_NUMPY",
    "query": "QUERY",
}


# ── takeaways ────────────────────────────────────────────────


def _generate_takeaways(results: BenchmarkResults) -> list[str]:
    """Generate auto-generated key insights from benchmark results."""
    takeaways = []
    has_off = results.official_sync is not None

    if has_off:
        # Find biggest latency win for aerospike-py sync vs official sync
        best_op, best_ratio = _find_best_op(
            OPERATIONS,
            results.aerospike_py_sync,
            results.official_sync,
            "avg_ms",
        )
        if best_op and best_ratio > 1:
            takeaways.append(
                f"aerospike-py (SyncClient) shows **{best_ratio:.1f}x** faster latency "
                f"than the official client in {OP_LABELS[best_op]} operations"
            )

        # Find biggest async win: aerospike-py async vs official async
        if results.official_async:
            best_async_op, best_async_ratio = _find_best_op(
                OPERATIONS,
                results.aerospike_py_async,
                results.official_async,
                "avg_ms",
            )
            if best_async_op and best_async_ratio > 1:
                takeaways.append(
                    f"AsyncClient shows **{best_async_ratio:.1f}x** faster latency "
                    f"than the official async client in {OP_LABELS[best_async_op]} operations"
                )

    # batch_read_numpy (Sync/Async) vs Official batch_read comparison
    if has_off:
        numpy_sync = results.aerospike_py_sync.get("batch_read_numpy", {}).get("avg_ms", 0)
        numpy_async = results.aerospike_py_async.get("batch_read_numpy", {}).get("avg_ms", 0)
        official_br = results.official_sync.get("batch_read", {}).get("avg_ms", 0)
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

    # Async vs sync advantage (aerospike-py internal)
    best_async_sync_op, best_async_sync_ratio = _find_best_op(
        OPERATIONS,
        results.aerospike_py_sync,
        results.aerospike_py_async,
        "ops_per_sec",
    )
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
    result = {
        "avg_ms": d.get("avg_ms"),
        "p50_ms": d.get("p50_ms"),
        "p99_ms": d.get("p99_ms"),
        "ops_per_sec": d.get("ops_per_sec"),
    }
    # Async per-op latency distribution
    if d.get("per_op") is not None:
        po = d["per_op"]
        result["per_op"] = {
            "p50_ms": po.get("p50_ms"),
            "p99_ms": po.get("p99_ms"),
        }
    return result


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


def _numpy_takeaways_from_results(results: BenchmarkResults) -> list[str]:
    """Generate numpy takeaways directly from BenchmarkResults fields."""

    class _Adapter:
        """Lightweight adapter to reuse _numpy_takeaways with BenchmarkResults."""

        def __init__(self, r: BenchmarkResults):
            self.record_scaling = r.numpy_record_scaling
            self.bin_scaling = r.numpy_bin_scaling
            self.post_processing = r.numpy_post_processing
            self.memory = r.numpy_memory

    return _numpy_takeaways(_Adapter(results))


def _metrics_dict(d: dict) -> dict:
    """Extract avg_ms, ops_per_sec from a bulk_median result."""
    return {
        "avg_ms": d.get("avg_ms"),
        "ops_per_sec": d.get("ops_per_sec"),
    }


def _build_scaling_entry(d: dict, key_field: str) -> dict:
    """Build a single scaling entry with the key field + 4 metrics dicts."""
    entry = {key_field: d[key_field]}
    for k in ("batch_read_sync", "batch_read_numpy_sync"):
        entry[k] = _metrics_dict(d[k])
    for k in ("batch_read_async", "batch_read_numpy_async"):
        entry[k] = _metrics_dict(d.get(k, {}))
    return entry


def _build_scaling_data(raw: dict, key_field: str) -> list[dict]:
    """Convert raw scaling data entries into report-ready dicts."""
    return [_build_scaling_entry(d, key_field) for d in raw["data"]]


def _find_best_op(ops: list[str], data_a: dict, data_b: dict, metric: str) -> tuple[str | None, float]:
    """Find the op with the best ratio data_b[op][metric] / data_a[op][metric]."""
    best_op = None
    best_ratio = 0.0
    for op in ops:
        av = data_a[op].get(metric, 0)
        bv = data_b[op].get(metric, 0)
        if av and bv and av > 0:
            ratio = bv / av
            if ratio > best_ratio:
                best_ratio = ratio
                best_op = op
    return best_op, best_ratio


def _write_json_report(report: dict, json_dir: str, json_filename: str, date_slug: str) -> None:
    """Write JSON report and update index."""
    json_path = os.path.join(json_dir, json_filename)
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    print(f"    JSON: {json_filename}")

    _update_index(json_dir, date_slug, json_filename)
    print("    Index: index.json updated")
    print("  Done.\n")


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
            "data": _build_scaling_data(results.record_scaling, "record_count"),
        }

    # Bin scaling
    if results.bin_scaling:
        report["bin_scaling"] = {
            "fixed_records": results.bin_scaling["fixed_records"],
            "data": _build_scaling_data(results.bin_scaling, "bin_count"),
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

    _write_json_report(report, json_dir, json_filename, date_slug)


# ── main entry point ─────────────────────────────────────────


def _advanced_takeaways(results: BenchmarkResults) -> list[str]:
    """Generate takeaways from advanced scenarios (data_size, concurrency, memory, mixed)."""
    takeaways = []

    if results.data_size:
        data = results.data_size["data"]
        if len(data) >= 2:
            smallest, largest = data[0], data[-1]
            sp50, lp50 = smallest["get"].get("p50_ms", 0), largest["get"].get("p50_ms", 0)
            if sp50 and lp50 and sp50 > 0:
                ratio = lp50 / sp50
                if ratio > 1:
                    takeaways.append(
                        f"GET latency increases **{ratio:.1f}x** from {smallest['label']} to {largest['label']}"
                    )

    if results.memory_profiling:
        data = results.memory_profiling["data"]
        if data:
            largest = data[-1]
            get_kb = largest.get("get_peak_kb")
            if get_kb:
                label = f"{get_kb / 1024:.1f}MB" if get_kb >= 1024 else f"{get_kb:.1f}KB"
                takeaways.append(f"Peak GET memory for {largest['label']}: **{label}**")

    if results.mixed_workload:
        data = results.mixed_workload["data"]
        if data:
            best = max(data, key=lambda e: e.get("throughput_ops_sec", 0))
            takeaways.append(f"Highest mixed throughput: **{best['throughput_ops_sec']:,.0f} ops/s** ({best['label']})")

    if results.high_concurrency_scaling:
        data = results.high_concurrency_scaling["data"]
        has_official = results.high_concurrency_scaling.get("has_official", False)
        if data and has_official:
            # Find the concurrency level with the best speedup
            best_entry = None
            best_ratio = 0.0
            for e in data:
                apy_ops = (e.get("aerospike_py") or {}).get("ops_per_sec") or 0
                off_ops = (e.get("official") or {}).get("ops_per_sec") or 0
                if off_ops > 0 and apy_ops / off_ops > best_ratio:
                    best_ratio = apy_ops / off_ops
                    best_entry = e
            if best_entry and best_ratio > 1:
                takeaways.append(
                    f"At concurrency={best_entry['concurrency']}, aerospike-py is "
                    f"**{best_ratio:.1f}x** faster throughput than official async"
                )
        elif data:
            peak = max(data, key=lambda e: (e.get("aerospike_py") or {}).get("ops_per_sec") or 0)
            apy_ops = (peak.get("aerospike_py") or {}).get("ops_per_sec")
            if apy_ops:
                takeaways.append(
                    f"Peak GET throughput at concurrency={peak['concurrency']}: **{apy_ops:,.0f} ops/s** (aerospike-py)"
                )

    if results.latency_sim:
        data = results.latency_sim["data"]
        has_official = results.latency_sim.get("has_official", False)
        if data and has_official:
            # Show the impact at highest latency level
            highest = data[-1]
            apy_ops = (highest.get("aerospike_py") or {}).get("ops_per_sec") or 0
            off_ops = (highest.get("official") or {}).get("ops_per_sec") or 0
            if off_ops > 0 and apy_ops > 0:
                ratio = apy_ops / off_ops
                takeaways.append(
                    f"At RTT={highest['rtt_ms']}ms, aerospike-py maintains **{ratio:.1f}x** "
                    f"higher throughput (latency sim, concurrency={results.latency_sim['concurrency']})"
                )

    return takeaways


def generate_architecture_data(results: BenchmarkResults, json_dir: str) -> None:
    """Generate architecture comparison data from real benchmark results.

    Outputs architecture-data.json for the ArchitectureComparison React component.
    Falls back gracefully if data is not available.
    """
    arch_data: dict = {"source": "measured", "date": datetime.now().strftime("%Y-%m-%d")}

    # High concurrency scaling data (for ThroughputSlider)
    if results.high_concurrency_scaling:
        hc = results.high_concurrency_scaling
        arch_data["high_concurrency"] = {
            "has_official": hc.get("has_official", False),
            "data": [
                {
                    "concurrency": e["concurrency"],
                    "aerospike_py_ops": (e.get("aerospike_py") or {}).get("ops_per_sec"),
                    "aerospike_py_p99": ((e.get("aerospike_py") or {}).get("per_op") or {}).get("p99_ms"),
                    "official_ops": (e.get("official") or {}).get("ops_per_sec"),
                    "official_p99": ((e.get("official") or {}).get("per_op") or {}).get("p99_ms"),
                }
                for e in hc["data"]
            ],
        }

    # Latency simulation data
    if results.latency_sim:
        ls = results.latency_sim
        arch_data["latency_sim"] = {
            "has_official": ls.get("has_official", False),
            "concurrency": ls.get("concurrency", 100),
            "simulation": True,
            "data": [
                {
                    "rtt_ms": e["rtt_ms"],
                    "aerospike_py_ops": (e.get("aerospike_py") or {}).get("ops_per_sec"),
                    "official_ops": (e.get("official") or {}).get("ops_per_sec"),
                }
                for e in ls["data"]
            ],
        }

    if len(arch_data) <= 2:
        # No useful data to write
        return

    arch_path = os.path.join(json_dir, "..", "architecture-data.json")
    arch_path = os.path.normpath(arch_path)
    with open(arch_path, "w") as f:
        json.dump(arch_data, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    print("    Architecture data: architecture-data.json")


def generate_report(results: BenchmarkResults, json_dir: str, date_slug: str) -> None:
    """Generate benchmark report JSON."""
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
    }

    # Basic benchmark results
    if results.aerospike_py_sync:
        report["aerospike_py_sync"] = _build_client_section(results.aerospike_py_sync)
    if results.official_sync:
        report["official_sync"] = _build_client_section(results.official_sync)
    if results.aerospike_py_async:
        report["aerospike_py_async"] = _build_client_section(results.aerospike_py_async)
    if results.official_async:
        report["official_async"] = _build_client_section(results.official_async)

    # Advanced scenario results
    if results.data_size:
        report["data_size"] = results.data_size
    if results.memory_profiling:
        report["memory_profiling"] = results.memory_profiling
    if results.mixed_workload:
        report["mixed_workload"] = results.mixed_workload
    if results.high_concurrency_scaling:
        report["high_concurrency_scaling"] = results.high_concurrency_scaling
    if results.latency_sim:
        report["latency_sim"] = results.latency_sim

    # NumPy batch benchmark results (embedded in same JSON)
    has_numpy = any(
        [
            results.numpy_record_scaling,
            results.numpy_bin_scaling,
            results.numpy_post_processing,
            results.numpy_memory,
        ]
    )
    if has_numpy:
        numpy_section: dict = {
            "environment": {
                "platform": results.platform_info,
                "python_version": results.python_version,
                "rounds": results.numpy_rounds,
                "warmup": results.numpy_warmup,
                "concurrency": results.numpy_concurrency,
                "batch_groups": results.numpy_batch_groups,
            },
        }
        if results.numpy_record_scaling:
            numpy_section["record_scaling"] = {
                "fixed_bins": results.numpy_record_scaling["fixed_bins"],
                "data": _build_scaling_data(results.numpy_record_scaling, "record_count"),
            }
        if results.numpy_bin_scaling:
            numpy_section["bin_scaling"] = {
                "fixed_records": results.numpy_bin_scaling["fixed_records"],
                "data": _build_scaling_data(results.numpy_bin_scaling, "bin_count"),
            }
        if results.numpy_post_processing:
            numpy_section["post_processing"] = {
                "record_count": results.numpy_post_processing["record_count"],
                "bin_count": results.numpy_post_processing["bin_count"],
                "data": [
                    {
                        "stage": d["stage"],
                        "stage_label": d["stage_label"],
                        "batch_read_sync": _metrics_dict(d["batch_read_sync"]),
                        "batch_read_numpy_sync": _metrics_dict(d["batch_read_numpy_sync"]),
                        "batch_read_async": _metrics_dict(d.get("batch_read_async", {})),
                        "batch_read_numpy_async": _metrics_dict(d.get("batch_read_numpy_async", {})),
                    }
                    for d in results.numpy_post_processing["data"]
                ],
            }
        if results.numpy_memory:
            numpy_section["memory"] = {
                "bin_count": results.numpy_memory["bin_count"],
                "data": results.numpy_memory["data"],
            }

        # Generate numpy takeaways using a lightweight adapter
        numpy_section["takeaways"] = _numpy_takeaways_from_results(results)
        report["numpy_batch"] = numpy_section

    # Takeaways
    takeaways = _generate_takeaways(results) if results.aerospike_py_sync else []
    takeaways.extend(_advanced_takeaways(results))
    if not takeaways:
        takeaways.append("Benchmark results collected successfully")
    report["takeaways"] = takeaways

    _write_json_report(report, json_dir, json_filename, date_slug)
    generate_architecture_data(results, json_dir)
