"""Report generation — Rich console tables, comparison view, CSV and Markdown export."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from benchmark.runner import BenchmarkResult

console = Console()

CSV_COLUMNS = [
    "client",
    "set_name",
    "batch_size",
    "concurrency",
    "iterations",
    "mean_ms",
    "p50_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "min_ms",
    "max_ms",
    "stddev_ms",
    "cv",
    "found_ratio",
    "tps",
]


def _f(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _found_style(ratio: float) -> str:
    pct = ratio * 100
    if pct >= 90:
        return "green"
    if pct >= 50:
        return "yellow"
    return "red"


def _speedup_style(ratio: float) -> str:
    if ratio > 1.2:
        return "bold green"
    if ratio < 0.8:
        return "bold red"
    return "yellow"


# ---------------------------------------------------------------------------
# Main results table
# ---------------------------------------------------------------------------


def print_console_table(results: list[BenchmarkResult]) -> None:
    """Render the full results table to the terminal."""
    tbl = Table(
        title="Benchmark Results",
        title_style="bold cyan",
        border_style="dim",
        show_lines=False,
        pad_edge=False,
    )

    tbl.add_column("client", style="bold", min_width=14)
    tbl.add_column("set", style="cyan", min_width=28)
    tbl.add_column("batch", justify="right", min_width=5)
    tbl.add_column("conc", justify="right", min_width=4)
    tbl.add_column("mean", justify="right", min_width=8, style="white")
    tbl.add_column("p50", justify="right", min_width=8)
    tbl.add_column("p90", justify="right", min_width=8)
    tbl.add_column("p95", justify="right", min_width=8)
    tbl.add_column("p99", justify="right", min_width=8, style="white")
    tbl.add_column("tps", justify="right", min_width=8, style="white")
    tbl.add_column("found%", justify="right", min_width=7)
    tbl.add_column("cv", justify="right", min_width=6)

    for r in results:
        style = _found_style(r.found_ratio)
        tbl.add_row(
            r.client_name,
            r.set_name,
            str(r.batch_size),
            str(r.concurrency),
            _f(r.mean_ms),
            _f(r.p50_ms),
            _f(r.p90_ms),
            _f(r.p95_ms),
            _f(r.p99_ms),
            _f(r.tps, 1),
            Text(f"{_f(r.found_ratio * 100, 1)}%", style=style),
            _f(r.cv, 3),
        )

    console.print()
    console.print(tbl)
    console.print()

    # Automatically show comparison tables for relevant pairs
    seen_clients = {r.client_name for r in results}
    for base, challenger in [("official", "py-async"), ("official-async", "py-async")]:
        if base in seen_clients and challenger in seen_clients:
            _print_comparison(results, base, challenger)


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------


def _print_comparison(
    results: list[BenchmarkResult],
    left: str,
    right: str,
) -> None:
    """Side-by-side comparison of *left* vs *right* with speedup ratios."""
    index: dict[tuple[str, str, int], BenchmarkResult] = {}
    for r in results:
        index[(r.client_name, r.set_name, r.batch_size)] = r

    # Preserve insertion order for sets and batch sizes
    ordered_sets: list[str] = list(dict.fromkeys(r.set_name for r in results))
    ordered_batches: list[int] = list(dict.fromkeys(r.batch_size for r in results))

    tbl = Table(
        title=f"[bold]{left} vs {right}[/bold]",
        title_style="bold white on blue",
        border_style="bright_blue",
        show_lines=False,
        padding=(0, 1),
    )

    tbl.add_column("set", style="cyan", min_width=28)
    tbl.add_column("batch", justify="right", min_width=5)
    # Left columns
    tbl.add_column(f"{left} mean", justify="right", style="white", min_width=10)
    tbl.add_column(f"{left} p99", justify="right", min_width=10)
    tbl.add_column("found%", justify="right", min_width=7)
    tbl.add_column("tps", justify="right", min_width=7)
    # Right columns
    tbl.add_column(f"{right} mean", justify="right", style="white", min_width=10)
    tbl.add_column(f"{right} p99", justify="right", min_width=10)
    tbl.add_column("found%", justify="right", min_width=7)
    tbl.add_column("tps", justify="right", min_width=7)
    # Delta columns
    tbl.add_column("mean x", justify="right", header_style="bold", min_width=7)
    tbl.add_column("p99 x", justify="right", header_style="bold", min_width=7)
    tbl.add_column("tps x", justify="right", header_style="bold", min_width=7)

    for si, sn in enumerate(ordered_sets):
        for bs in ordered_batches:
            rl = index.get((left, sn, bs))
            rr = index.get((right, sn, bs))
            if not rl and not rr:
                continue

            def _v(r: BenchmarkResult | None, attr: str) -> str:
                return _f(getattr(r, attr)) + "ms" if r else "--"

            def _tp(r: BenchmarkResult | None) -> str:
                return _f(r.tps, 1) if r else "--"

            def _fp(r: BenchmarkResult | None) -> Text:
                if not r:
                    return Text("--", style="dim")
                return Text(f"{_f(r.found_ratio * 100, 1)}%", style=_found_style(r.found_ratio))

            def _delta(a: float, b: float, higher_better: bool = False) -> Text:
                if a == 0 or b == 0:
                    return Text("--", style="dim")
                ratio = (b / a) if higher_better else (a / b)
                return Text(f"{ratio:.1f}x", style=_speedup_style(ratio))

            mean_x = _delta(rl.mean_ms, rr.mean_ms) if rl and rr else Text("--", style="dim")
            p99_x = _delta(rl.p99_ms, rr.p99_ms) if rl and rr else Text("--", style="dim")
            tps_x = _delta(rl.tps, rr.tps, higher_better=True) if rl and rr else Text("--", style="dim")

            tbl.add_row(
                sn,
                str(bs),
                _v(rl, "mean_ms"),
                _v(rl, "p99_ms"),
                _fp(rl),
                _tp(rl),
                _v(rr, "mean_ms"),
                _v(rr, "p99_ms"),
                _fp(rr),
                _tp(rr),
                mean_x,
                p99_x,
                tps_x,
            )

        if si < len(ordered_sets) - 1:
            tbl.add_section()

    console.print()
    console.print(tbl)

    # Summary panel
    left_rs = [r for r in results if r.client_name == left]
    right_rs = [r for r in results if r.client_name == right]
    if left_rs and right_rs:
        avg_l = sum(r.mean_ms for r in left_rs) / len(left_rs)
        avg_r = sum(r.mean_ms for r in right_rs) / len(right_rs)
        tps_l = sum(r.tps for r in left_rs) / len(left_rs)
        tps_r = sum(r.tps for r in right_rs) / len(right_rs)

        lines: list[str] = []
        if avg_r > 0:
            ratio = avg_l / avg_r
            winner = right if ratio > 1 else left
            rv = ratio if ratio > 1 else 1 / ratio
            colour = "green" if ratio > 1 else "red"
            lines.append(
                f"  Latency:    [bold]{left}[/bold] avg {_f(avg_l)}ms  vs  "
                f"[bold]{right}[/bold] avg {_f(avg_r)}ms  ->  "
                f"[bold {colour}]{winner} is {rv:.1f}x faster[/bold {colour}]"
            )
        if tps_l > 0:
            tr = tps_r / tps_l
            winner = right if tr > 1 else left
            tv = tr if tr > 1 else 1 / tr
            colour = "green" if tr > 1 else "red"
            lines.append(
                f"  Throughput: [bold]{left}[/bold] avg {_f(tps_l, 1)} tps  vs  "
                f"[bold]{right}[/bold] avg {_f(tps_r, 1)} tps  ->  "
                f"[bold {colour}]{winner} is {tv:.1f}x higher[/bold {colour}]"
            )

        console.print()
        console.print(
            Panel(
                "\n".join(lines),
                title="[bold]Summary[/bold]",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )
    console.print()


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def write_csv(results: list[BenchmarkResult], output_dir: str | Path) -> Path:
    """Persist results as a CSV file. Returns the written path."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    csv_path = dest / "summary.csv"

    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for r in results:
            writer.writerow(
                [
                    r.client_name,
                    r.set_name,
                    r.batch_size,
                    r.concurrency,
                    r.iterations,
                    _f(r.mean_ms),
                    _f(r.p50_ms),
                    _f(r.p90_ms),
                    _f(r.p95_ms),
                    _f(r.p99_ms),
                    _f(r.min_ms),
                    _f(r.max_ms),
                    _f(r.stddev_ms),
                    _f(r.cv, 4),
                    _f(r.found_ratio, 4),
                    _f(r.tps, 1),
                ]
            )

    return csv_path


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def write_markdown(results: list[BenchmarkResult], output_dir: str | Path) -> Path:
    """Generate a Markdown report with results tables and comparison analysis."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    md_path = dest / "report.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append(f"# Benchmark Report — {ts}\n")

    # --- Conditions ---
    clients = sorted({r.client_name for r in results})
    sets = list(dict.fromkeys(r.set_name for r in results))
    batches = sorted({r.batch_size for r in results})
    conc = results[0].concurrency if results else 1
    iters = results[0].iterations if results else 0
    lines.append("## Conditions\n")
    lines.append("| Item | Value |")
    lines.append("|------|-------|")
    lines.append(f"| Clients | {', '.join(clients)} |")
    lines.append(f"| Sets | {len(sets)} |")
    lines.append(f"| Batch sizes | {batches} |")
    lines.append(f"| Concurrency | {conc} |")
    lines.append(f"| Iterations | {iters} |")
    lines.append("")

    # --- Full results table ---
    lines.append("## Results\n")
    lines.append("| client | set | batch | conc | mean(ms) | p50 | p90 | p95 | p99 | tps | found% | cv |")
    lines.append("|--------|-----|-------|------|----------|-----|-----|-----|-----|-----|--------|----|")
    for r in results:
        lines.append(
            f"| {r.client_name} | {r.set_name} | {r.batch_size} | {r.concurrency} | "
            f"{_f(r.mean_ms)} | {_f(r.p50_ms)} | {_f(r.p90_ms)} | {_f(r.p95_ms)} | "
            f"{_f(r.p99_ms)} | {_f(r.tps, 1)} | {_f(r.found_ratio * 100, 1)}% | {_f(r.cv, 3)} |"
        )
    lines.append("")

    # --- Comparison tables ---
    seen = {r.client_name for r in results}
    for base, challenger in [("official", "py-async"), ("official-async", "py-async")]:
        if base in seen and challenger in seen:
            lines.extend(_md_comparison(results, base, challenger))
            lines.append("")

    # --- Summary ---
    lines.extend(_md_summary(results))

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def _md_comparison(
    results: list[BenchmarkResult],
    left: str,
    right: str,
) -> list[str]:
    """Generate a comparison markdown table for two clients."""
    index: dict[tuple[str, str, int], BenchmarkResult] = {}
    for r in results:
        index[(r.client_name, r.set_name, r.batch_size)] = r

    ordered_sets = list(dict.fromkeys(r.set_name for r in results))
    ordered_batches = list(dict.fromkeys(r.batch_size for r in results))

    lines = [
        f"## {left} vs {right}\n",
        f"| set | batch | {left} mean | {left} p99 | {right} mean | {right} p99 | mean speedup | p99 speedup | tps speedup |",
        "|-----|-------|-------------|------------|--------------|-------------|--------------|-------------|-------------|",
    ]
    for sn in ordered_sets:
        for bs in ordered_batches:
            rl = index.get((left, sn, bs))
            rr = index.get((right, sn, bs))
            if not rl or not rr:
                continue

            def _ratio(a: float, b: float) -> str:
                if a == 0 or b == 0:
                    return "--"
                return f"{a / b:.1f}x"

            def _tps_ratio(a: float, b: float) -> str:
                if a == 0:
                    return "--"
                return f"{b / a:.1f}x"

            lines.append(
                f"| {sn} | {bs} | {_f(rl.mean_ms)}ms | {_f(rl.p99_ms)}ms | "
                f"{_f(rr.mean_ms)}ms | {_f(rr.p99_ms)}ms | "
                f"{_ratio(rl.mean_ms, rr.mean_ms)} | {_ratio(rl.p99_ms, rr.p99_ms)} | "
                f"{_tps_ratio(rl.tps, rr.tps)} |"
            )
    return lines


def _md_summary(results: list[BenchmarkResult]) -> list[str]:
    """Generate a summary section comparing overall averages."""
    lines = ["## Summary\n"]
    clients = sorted({r.client_name for r in results})
    if len(clients) < 2:
        return lines

    for name in clients:
        rs = [r for r in results if r.client_name == name]
        avg_mean = sum(r.mean_ms for r in rs) / len(rs)
        avg_tps = sum(r.tps for r in rs) / len(rs)
        avg_p99 = sum(r.p99_ms for r in rs) / len(rs)
        lines.append(f"- **{name}**: avg mean={_f(avg_mean)}ms, avg p99={_f(avg_p99)}ms, avg tps={_f(avg_tps, 1)}")

    # Compare pairs
    seen = {r.client_name for r in results}
    for base, challenger in [("official", "py-async"), ("official-async", "py-async")]:
        if base in seen and challenger in seen:
            base_rs = [r for r in results if r.client_name == base]
            chal_rs = [r for r in results if r.client_name == challenger]
            bm = sum(r.mean_ms for r in base_rs) / len(base_rs)
            cm = sum(r.mean_ms for r in chal_rs) / len(chal_rs)
            bt = sum(r.tps for r in base_rs) / len(base_rs)
            ct = sum(r.tps for r in chal_rs) / len(chal_rs)
            if cm > 0:
                lines.append(
                    f"- **{challenger} vs {base}**: {bm / cm:.1f}x faster latency, {ct / bt:.1f}x higher throughput"
                )

    lines.append("")
    return lines
