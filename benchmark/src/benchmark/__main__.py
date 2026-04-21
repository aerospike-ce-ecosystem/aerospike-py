"""CLI entrypoint — ``python -m benchmark``."""

from __future__ import annotations

import argparse
import asyncio
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from benchmark.clients import (
    batch_read_official_async,
    batch_read_official_sync,
    batch_read_py_async,
    close_official_async,
    close_official_sync,
    close_py_async,
    create_official_async,
    create_official_sync,
    create_py_async,
)
from benchmark.config import (
    ALL_SETS,
    DEFAULT_BATCH_SIZES,
    DEFAULT_ITERATIONS,
    DEFAULT_WARMUP,
    get_hosts,
)
from benchmark.keys import build_batch_keys, extract_all_keys, load_request
from benchmark.report import print_console_table, write_csv, write_markdown
from benchmark.runner import (
    BenchmarkResult,
    run_concurrent_async_benchmark,
    run_concurrent_benchmark,
    run_single_async_benchmark,
    run_single_benchmark,
)

console = Console()

# ---------------------------------------------------------------------------
# Client registry
# ---------------------------------------------------------------------------

CLIENT_REGISTRY: dict[str, dict[str, Any]] = {
    "official": {
        "factory": create_official_sync,
        "batch_read": batch_read_official_sync,
        "close": close_official_sync,
        "is_async": False,
    },
    "official-async": {
        "factory": create_official_async,
        "batch_read": batch_read_official_async,
        "close": close_official_async,
        "is_async": True,
    },
    "py-async": {
        "factory": create_py_async,
        "batch_read": batch_read_py_async,
        "close": close_py_async,
        "is_async": True,
    },
}

ALL_CLIENT_NAMES = list(CLIENT_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="Aerospike batch_read benchmark: official C client vs aerospike-py",
    )
    parser.add_argument(
        "--clients",
        nargs="+",
        choices=ALL_CLIENT_NAMES,
        default=["official", "py-async"],
        help="Clients to benchmark (default: official py-async)",
    )
    parser.add_argument(
        "--batch-sizes",
        nargs="+",
        type=int,
        default=DEFAULT_BATCH_SIZES,
        help=f"Batch sizes to test (default: {DEFAULT_BATCH_SIZES})",
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        default=ALL_SETS,
        help="Aerospike set names (default: all 9 sets)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Measurement iterations per combination (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help=f"Warmup iterations (default: {DEFAULT_WARMUP})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Concurrent batch_read calls per iteration (default: 1 = sequential)",
    )
    parser.add_argument(
        "--request-file",
        type=str,
        default=None,
        help="Path to request JSON (default: data/sample_request200real.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for CSV results (default: results/<timestamp>)",
    )
    parser.add_argument(
        "--interleave",
        action="store_true",
        default=False,
        help="Randomise client order per (set, batch_size) to reduce cache bias",
    )
    parser.add_argument(
        "--shuffle-keys",
        action="store_true",
        default=False,
        help="Shuffle key order each iteration to reduce server-side caching effects",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    asyncio.run(_execute(args))


async def _execute(args: argparse.Namespace) -> None:
    hosts = get_hosts()
    output_dir = args.output_dir or str(
        Path("results") / datetime.now().strftime("%Y%m%d_%H%M%S"),
    )

    # Size the default thread-pool to match the concurrency level
    if args.concurrency > 1:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=args.concurrency))

    request = load_request(args.request_file)
    keys_by_set = extract_all_keys(request)

    is_concurrent = args.concurrency > 1
    combos = len(args.clients) * len(args.sets) * len(args.batch_sizes)

    flags: list[str] = []
    if args.interleave:
        flags.append("interleave")
    if args.shuffle_keys:
        flags.append("shuffle-keys")
    flag_str = f"  Flags: [bold]{', '.join(flags)}[/bold]" if flags else ""

    console.print(
        Panel(
            f"[bold]{len(args.clients)}[/bold] clients x [bold]{len(args.sets)}[/bold] sets x "
            f"[bold]{len(args.batch_sizes)}[/bold] batch_sizes = [bold cyan]{combos}[/bold cyan] combinations\n"
            f"Iterations: [bold]{args.iterations}[/bold]  Warmup: [bold]{args.warmup}[/bold]  "
            f"Concurrency: [bold]{args.concurrency}[/bold]{flag_str}",
            title="[bold]Benchmark Matrix[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    all_results: list[BenchmarkResult] = []

    if args.interleave:
        await _run_interleaved(args, hosts, keys_by_set, is_concurrent, all_results)
    else:
        await _run_sequential(args, hosts, keys_by_set, is_concurrent, all_results)

    # Report
    print_console_table(all_results)
    csv_path = write_csv(all_results, output_dir)
    md_path = write_markdown(all_results, output_dir)
    console.print(f"\n[bold green]CSV saved to:[/bold green]      {csv_path}")
    console.print(f"[bold green]Markdown saved to:[/bold green] {md_path}")


# ---------------------------------------------------------------------------
# Execution modes
# ---------------------------------------------------------------------------


async def _run_interleaved(
    args: argparse.Namespace,
    hosts: list[tuple[str, int]],
    keys_by_set: dict[str, list[str]],
    is_concurrent: bool,
    all_results: list[BenchmarkResult],
) -> None:
    """Connect all clients upfront; randomise client order per (set, batch_size)."""
    live: dict[str, tuple[Any, dict[str, Any]]] = {}

    for name in args.clients:
        reg = CLIENT_REGISTRY[name]
        console.print(f"  [bold yellow]\\[{name}][/bold yellow] Connecting...")
        if reg["is_async"]:
            client = await reg["factory"](hosts)
        else:
            client = reg["factory"](hosts)
        live[name] = (client, reg)
        console.print(f"  [bold yellow]\\[{name}][/bold yellow] [green]Connected.[/green]")

    try:
        for set_name in args.sets:
            if set_name not in keys_by_set:
                console.print(f"    [dim]SKIP {set_name}: no keys[/dim]")
                continue
            key_strings = keys_by_set[set_name]

            for batch_size in args.batch_sizes:
                order = list(args.clients)
                random.shuffle(order)

                for name in order:
                    client, reg = live[name]
                    result = await _bench_one(
                        name,
                        reg,
                        client,
                        set_name,
                        key_strings,
                        batch_size,
                        args,
                        is_concurrent,
                    )
                    all_results.append(result)
    finally:
        for name, (client, reg) in live.items():
            if reg["is_async"]:
                await reg["close"](client)
            else:
                reg["close"](client)
            console.print(f"  [bold yellow]\\[{name}][/bold yellow] [dim]Disconnected.[/dim]")


async def _run_sequential(
    args: argparse.Namespace,
    hosts: list[tuple[str, int]],
    keys_by_set: dict[str, list[str]],
    is_concurrent: bool,
    all_results: list[BenchmarkResult],
) -> None:
    """Run each client end-to-end before moving to the next."""
    for name in args.clients:
        reg = CLIENT_REGISTRY[name]
        is_async = reg["is_async"]

        console.print(f"  [bold yellow]\\[{name}][/bold yellow] Connecting...")
        client = await reg["factory"](hosts) if is_async else reg["factory"](hosts)
        console.print(f"  [bold yellow]\\[{name}][/bold yellow] [green]Connected.[/green]")

        try:
            for set_name in args.sets:
                if set_name not in keys_by_set:
                    console.print(f"    [dim]SKIP {set_name}: no keys[/dim]")
                    continue
                key_strings = keys_by_set[set_name]

                for batch_size in args.batch_sizes:
                    result = await _bench_one(
                        name,
                        reg,
                        client,
                        set_name,
                        key_strings,
                        batch_size,
                        args,
                        is_concurrent,
                    )
                    all_results.append(result)
        finally:
            if is_async:
                await reg["close"](client)
            else:
                reg["close"](client)
            console.print(f"  [bold yellow]\\[{name}][/bold yellow] [dim]Disconnected.[/dim]")


# ---------------------------------------------------------------------------
# Single combination dispatcher
# ---------------------------------------------------------------------------


async def _bench_one(
    client_name: str,
    reg: dict[str, Any],
    client: Any,
    set_name: str,
    key_strings: list[str],
    batch_size: int,
    args: argparse.Namespace,
    is_concurrent: bool,
) -> BenchmarkResult:
    """Run and print progress for a single (client, set, batch_size) combo."""
    is_async = reg["is_async"]
    keys = build_batch_keys(set_name, key_strings, batch_size)
    actual = len(keys)

    label = f"[bold yellow]\\[{client_name}][/bold yellow] {set_name} batch_size={batch_size} (actual={actual})"
    if is_concurrent:
        label += f" x{args.concurrency}"
    console.print(f"    {label} ...", end="")

    shuffle = args.shuffle_keys
    common = dict(
        client_name=client_name,
        set_name=set_name,
        batch_size=batch_size,
        keys=keys,
        batch_read_fn=reg["batch_read"],
        client=client,
        iterations=args.iterations,
        warmup=args.warmup,
        shuffle_keys=shuffle,
    )

    if is_async and is_concurrent:
        result = await run_concurrent_async_benchmark(**common, concurrency=args.concurrency)
    elif is_async:
        result = await run_single_async_benchmark(**common)
    elif is_concurrent:
        result = await run_concurrent_benchmark(**common, concurrency=args.concurrency)
    else:
        result = run_single_benchmark(**common)

    # Inline status line
    fr = result.found_ratio * 100
    fs = "green" if fr >= 90 else ("yellow" if fr >= 50 else "red")
    console.print(
        f" mean=[white]{result.mean_ms:.2f}ms[/white]"
        f" p99=[white]{result.p99_ms:.2f}ms[/white]"
        f" stddev=[white]{result.stddev_ms:.2f}[/white]"
        f" found=[{fs}]{result.found_ratio:.1%}[/{fs}]"
        f" tps=[white]{result.tps:.1f}[/white]"
    )
    return result


if __name__ == "__main__":
    main()
