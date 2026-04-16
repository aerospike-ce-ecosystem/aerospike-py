"""ASGI benchmark runner — measures FastAPI + DLRM + Aerospike under concurrent load.

Usage: python -m serving.asgi_benchmark [OPTIONS]

Starts the FastAPI server in-process, fires concurrent HTTP requests, and
reports per-stage latency breakdown with Rich console + Markdown output.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ASGIResult:
    client_type: str
    iterations: int
    concurrency: int
    total_ms: list[float] = field(default_factory=list)
    aerospike_ms: list[float] = field(default_factory=list)
    inference_ms: list[float] = field(default_factory=list)
    http_latency_ms: list[float] = field(default_factory=list)
    errors: int = 0

    def _p(self, data: list[float], pct: int) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = min(int(len(s) * pct / 100), len(s) - 1)
        return s[idx]

    @property
    def mean_total(self) -> float:
        return statistics.mean(self.total_ms) if self.total_ms else 0.0

    @property
    def p50_total(self) -> float:
        return self._p(self.total_ms, 50)

    @property
    def p90_total(self) -> float:
        return self._p(self.total_ms, 90)

    @property
    def p95_total(self) -> float:
        return self._p(self.total_ms, 95)

    @property
    def p99_total(self) -> float:
        return self._p(self.total_ms, 99)

    @property
    def mean_aerospike(self) -> float:
        return statistics.mean(self.aerospike_ms) if self.aerospike_ms else 0.0

    @property
    def mean_inference(self) -> float:
        return statistics.mean(self.inference_ms) if self.inference_ms else 0.0

    @property
    def mean_http(self) -> float:
        return statistics.mean(self.http_latency_ms) if self.http_latency_ms else 0.0

    @property
    def tps(self) -> float:
        if not self.http_latency_ms:
            return 0.0
        avg_s = statistics.mean(self.http_latency_ms) / 1000
        return self.concurrency / avg_s if avg_s > 0 else 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _fire_request(
    client: httpx.AsyncClient,
    url: str,
    result: ASGIResult,
) -> None:
    """Send a single GET request and record metrics."""
    t0 = time.perf_counter()
    try:
        resp = await client.get(url, timeout=30.0)
        http_ms = (time.perf_counter() - t0) * 1000
        result.http_latency_ms.append(http_ms)

        if resp.status_code == 200:
            body = resp.json()
            result.total_ms.append(body.get("total_ms", 0.0))
            result.aerospike_ms.append(body.get("aerospike_ms", 0.0))
            result.inference_ms.append(body.get("inference_ms", 0.0))
        else:
            result.errors += 1
    except Exception:
        result.errors += 1


async def run_asgi_benchmark(
    base_url: str,
    client_types: list[str],
    iterations: int,
    concurrency: int,
    warmup: int,
    skip_inference: bool = False,
    mode: str = "gather",
) -> list[ASGIResult]:
    """Run the ASGI benchmark against a running FastAPI server."""
    results: list[ASGIResult] = []

    async with httpx.AsyncClient() as http_client:
        for ct in client_types:
            suffix = "skip_inference=true&" if skip_inference else ""
            url = f"{base_url}/predict/{ct}/sample?{suffix}mode={mode}"

            console.print(f"  [bold yellow]\\[{ct}][/bold yellow] Warming up ({warmup} requests)...")

            # Warmup
            for _ in range(warmup):
                await http_client.get(url, timeout=30.0)

            console.print(
                f"  [bold yellow]\\[{ct}][/bold yellow] Running {iterations} iterations (concurrency={concurrency})..."
            )
            result = ASGIResult(client_type=ct, iterations=iterations, concurrency=concurrency)

            # Measure: fire `concurrency` concurrent requests per round
            rounds = iterations // concurrency
            remainder = iterations % concurrency

            for _ in range(rounds):
                tasks = [_fire_request(http_client, url, result) for _ in range(concurrency)]
                await asyncio.gather(*tasks)

            if remainder > 0:
                tasks = [_fire_request(http_client, url, result) for _ in range(remainder)]
                await asyncio.gather(*tasks)

            ok = len(result.total_ms)
            console.print(
                f"  [bold yellow]\\[{ct}][/bold yellow] [green]Done.[/green] "
                f"{ok} ok, {result.errors} errors, "
                f"mean={result.mean_total:.2f}ms, p99={result.p99_total:.2f}ms"
            )
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Rich console output
# ---------------------------------------------------------------------------

_F = lambda v, d=2: f"{v:.{d}f}"  # noqa: E731


def print_asgi_table(results: list[ASGIResult]) -> None:
    """Print a Rich table with per-stage latency breakdown."""
    tbl = Table(
        title="ASGI Benchmark Results — Pipeline Breakdown",
        title_style="bold cyan",
        border_style="dim",
    )
    tbl.add_column("client", style="bold", min_width=14)
    tbl.add_column("total mean(ms)", justify="right", style="white")
    tbl.add_column("p50", justify="right")
    tbl.add_column("p90", justify="right")
    tbl.add_column("p95", justify="right")
    tbl.add_column("p99", justify="right", style="white")
    tbl.add_column("aerospike(ms)", justify="right", style="cyan")
    tbl.add_column("inference(ms)", justify="right", style="magenta")
    tbl.add_column("http(ms)", justify="right")
    tbl.add_column("tps", justify="right", style="white")
    tbl.add_column("errors", justify="right")

    for r in results:
        err_style = "red" if r.errors > 0 else "green"
        tbl.add_row(
            r.client_type,
            _F(r.mean_total),
            _F(r.p50_total),
            _F(r.p90_total),
            _F(r.p95_total),
            _F(r.p99_total),
            _F(r.mean_aerospike),
            _F(r.mean_inference),
            _F(r.mean_http),
            _F(r.tps, 1),
            f"[{err_style}]{r.errors}[/{err_style}]",
        )

    console.print()
    console.print(tbl)

    # Comparison summary
    if len(results) >= 2:
        by_name = {r.client_type: r for r in results}
        for base, chal in [("official", "py-async")]:
            if base in by_name and chal in by_name:
                br = by_name[base]
                cr = by_name[chal]
                if cr.mean_total > 0:
                    ratio = br.mean_total / cr.mean_total
                    tps_ratio = cr.tps / br.tps if br.tps > 0 else 0
                    colour = "green" if ratio > 1 else "red"
                    console.print(
                        Panel(
                            f"  Latency:    [bold]{base}[/bold] {_F(br.mean_total)}ms vs [bold]{chal}[/bold] {_F(cr.mean_total)}ms"
                            f"  →  [bold {colour}]{chal} is {ratio:.1f}x faster[/bold {colour}]\n"
                            f"  Throughput: [bold]{base}[/bold] {_F(br.tps, 1)} tps vs [bold]{chal}[/bold] {_F(cr.tps, 1)} tps"
                            f"  →  [bold {colour}]{chal} is {tps_ratio:.1f}x higher[/bold {colour}]\n"
                            f"  Aerospike:  [bold]{base}[/bold] {_F(br.mean_aerospike)}ms vs [bold]{chal}[/bold] {_F(cr.mean_aerospike)}ms\n"
                            f"  Inference:  [bold]{base}[/bold] {_F(br.mean_inference)}ms vs [bold]{chal}[/bold] {_F(cr.mean_inference)}ms",
                            title="[bold]Summary[/bold]",
                            border_style="bright_blue",
                            padding=(1, 2),
                        )
                    )
    console.print()


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------


def write_asgi_markdown(results: list[ASGIResult], output_dir: str | Path) -> Path:
    """Write ASGI benchmark results as a Markdown report."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    md_path = dest / "asgi-report.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# ASGI Benchmark Report — {ts}\n",
        "## Conditions\n",
    ]
    if results:
        r0 = results[0]
        lines.append("| Item | Value |")
        lines.append("|------|-------|")
        lines.append(f"| Clients | {', '.join(r.client_type for r in results)} |")
        lines.append(f"| Iterations | {r0.iterations} |")
        lines.append(f"| Concurrency | {r0.concurrency} |")
        lines.append("")

    # Main table
    lines.append("## Pipeline Breakdown\n")
    lines.append(
        "| client | total mean(ms) | p50 | p90 | p95 | p99 | aerospike(ms) | inference(ms) | http(ms) | tps | errors |"
    )
    lines.append(
        "|--------|----------------|-----|-----|-----|-----|---------------|---------------|----------|-----|--------|"
    )
    for r in results:
        lines.append(
            f"| {r.client_type} | {_F(r.mean_total)} | {_F(r.p50_total)} | "
            f"{_F(r.p90_total)} | {_F(r.p95_total)} | {_F(r.p99_total)} | "
            f"{_F(r.mean_aerospike)} | {_F(r.mean_inference)} | "
            f"{_F(r.mean_http)} | {_F(r.tps, 1)} | {r.errors} |"
        )
    lines.append("")

    # Comparison
    if len(results) >= 2:
        by_name = {r.client_type: r for r in results}
        lines.append("## Comparison\n")
        for base, chal in [("official", "py-async")]:
            if base in by_name and chal in by_name:
                br = by_name[base]
                cr = by_name[chal]
                if cr.mean_total > 0 and br.tps > 0:
                    lines.append(f"- **Latency**: {chal} is {br.mean_total / cr.mean_total:.1f}x faster")
                    lines.append(f"- **Throughput**: {chal} is {cr.tps / br.tps:.1f}x higher")
                    lines.append(
                        f"- **Aerospike**: {base}={_F(br.mean_aerospike)}ms vs {chal}={_F(cr.mean_aerospike)}ms"
                    )
                    lines.append(
                        f"- **Inference**: {base}={_F(br.mean_inference)}ms vs {chal}={_F(cr.mean_inference)}ms"
                    )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="asgi_benchmark",
        description="ASGI benchmark: FastAPI + DLRM + Aerospike under concurrent HTTP load",
    )
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Server URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--clients", nargs="+", default=["official", "py-async"], help="Client types to test")
    p.add_argument("--iterations", type=int, default=200, help="Total requests per client (default: 200)")
    p.add_argument("--concurrency", type=int, default=10, help="Concurrent requests (default: 10)")
    p.add_argument("--warmup", type=int, default=20, help="Warmup requests (default: 20)")
    p.add_argument("--skip-inference", action="store_true", help="Skip DLRM inference (Aerospike only)")
    p.add_argument("--mode", default="gather", choices=["gather", "sequential", "single"])
    p.add_argument("--output-dir", default=None, help="Output directory for Markdown report")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    output_dir = args.output_dir or str(Path("results") / f"asgi_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    console.print(
        Panel(
            f"Server: [bold]{args.base_url}[/bold]\n"
            f"Clients: [bold]{', '.join(args.clients)}[/bold]\n"
            f"Iterations: [bold]{args.iterations}[/bold]  Concurrency: [bold]{args.concurrency}[/bold]  "
            f"Warmup: [bold]{args.warmup}[/bold]  Mode: [bold]{args.mode}[/bold]",
            title="[bold]ASGI Benchmark[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    results = asyncio.run(
        run_asgi_benchmark(
            base_url=args.base_url,
            client_types=args.clients,
            iterations=args.iterations,
            concurrency=args.concurrency,
            warmup=args.warmup,
            skip_inference=args.skip_inference,
            mode=args.mode,
        )
    )

    print_asgi_table(results)
    md_path = write_asgi_markdown(results, output_dir)
    console.print(f"[bold green]Markdown saved to:[/bold green] {md_path}")


if __name__ == "__main__":
    main()
