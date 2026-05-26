"""Render a markdown comparison table from results/*/oha.json + meta.json.

Groups runs by (scenario, batch_size, concurrency, python) and prints one
row per client. Speedup column is py / official from the same group.

Each scenario section starts with a one-line description from
``loadtest.scenarios.SCENARIO_DESCRIPTIONS``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from loadtest.scenarios import SCENARIO_DESCRIPTIONS

RESULTS = Path("results")


def _ms(seconds: float) -> float:
    return seconds * 1000.0


def _load_run(run_dir: Path) -> dict | None:
    meta_path = run_dir / "meta.json"
    oha_path = run_dir / "oha.json"
    if not (meta_path.exists() and oha_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text())
        oha = json.loads(oha_path.read_text())
    except json.JSONDecodeError as e:
        # A truncated oha.json typically means the run was killed mid-stream
        # (Ctrl-C, OOM, port conflict). Skip rather than abort the whole report.
        print(f"[skip] {run_dir.name}: {e}")
        return None

    summary = oha.get("summary", {})
    latency = oha.get("latencyPercentiles", {}) or oha.get("latency_percentiles", {})

    return {
        "meta": meta,
        "rps": summary.get("requestsPerSec") or summary.get("requests_per_sec"),
        "avg_ms": _ms(summary.get("average", 0.0)),
        "p50_ms": _ms(latency.get("p50", 0.0)),
        "p95_ms": _ms(latency.get("p95", 0.0)),
        "p99_ms": _ms(latency.get("p99", 0.0)),
        "successful": oha.get("statusCodeDistribution", {}).get("200", 0)
        or oha.get("status_code_distribution", {}).get("200", 0),
        "errors": oha.get("errorDistribution", {}) or oha.get("error_distribution", {}),
    }


def _group_key(meta: dict) -> tuple:
    return (meta["scenario"], meta["batch_size"], meta["concurrency"], meta["python"])


def main() -> None:
    if not RESULTS.exists():
        print(f"No {RESULTS}/ directory. Run a bench first.")
        return

    runs: list[dict] = []
    for run_dir in sorted(RESULTS.iterdir()):
        if not run_dir.is_dir():
            continue
        row = _load_run(run_dir)
        if row:
            runs.append(row)

    if not runs:
        print(f"No usable runs in {RESULTS}/.")
        return

    # group by scenario first so we can print a per-scenario heading +
    # description, then a sub-table grouped by (batch, conc, python).
    by_scenario: dict[str, dict[tuple, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    for r in runs:
        meta = r["meta"]
        sub_key = (meta["batch_size"], meta["concurrency"], meta["python"])
        by_scenario[meta["scenario"]][sub_key][meta["client"]] = r

    print("# Benchmark report\n")
    print("`speedup` = official metric ÷ py metric (higher = py is faster).\n")

    for scenario in sorted(by_scenario):
        description = SCENARIO_DESCRIPTIONS.get(scenario, "_(no description registered)_")
        print(f"## {scenario}\n")
        print(f"{description}\n")
        print("| batch | conc | py | client | RPS | avg ms | p50 | p95 | p99 | ok |")
        print("|---:|---:|---|---|---:|---:|---:|---:|---:|---:|")

        for (batch, conc, py), by_client in sorted(by_scenario[scenario].items()):
            for client_name in ("official", "py"):
                r = by_client.get(client_name)
                if not r:
                    continue
                print(
                    f"| {batch} | {conc} | {py} | {client_name} | "
                    f"{r['rps']:.1f} | {r['avg_ms']:.2f} | {r['p50_ms']:.2f} | "
                    f"{r['p95_ms']:.2f} | {r['p99_ms']:.2f} | {r['successful']} |"
                )

            if "official" in by_client and "py" in by_client:
                o, p = by_client["official"], by_client["py"]
                rps_sp = p["rps"] / o["rps"] if o["rps"] else float("nan")
                avg_sp = o["avg_ms"] / p["avg_ms"] if p["avg_ms"] else float("nan")
                p95_sp = o["p95_ms"] / p["p95_ms"] if p["p95_ms"] else float("nan")
                print(
                    f"| {batch} | {conc} | {py} | **speedup** | "
                    f"**{rps_sp:.2f}×** | **{avg_sp:.2f}×** | — | **{p95_sp:.2f}×** | — | — |"
                )
        print()


if __name__ == "__main__":
    main()
