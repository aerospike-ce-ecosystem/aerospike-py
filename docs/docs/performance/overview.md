---
title: Performance Overview
sidebar_label: Overview
sidebar_position: 1
---

# Performance Overview

aerospike-py provides a high-performance Aerospike client based on the **Rust + PyO3 + Tokio** architecture.

## Architecture

```
Python (sync/async API)
    ↓ PyO3 FFI
Rust (aerospike-rs client)
    ↓ Tokio async runtime
TCP/IP → Aerospike Server
```

- **Rust core**: Handles network I/O, serialization/deserialization, and connection pool management in Rust
- **PyO3 bindings**: Minimizes Python GIL usage and calls Rust functions directly
- **Tokio runtime**: The async client maximizes concurrency on Tokio's multi-threaded runtime

## Benchmark Methodology

To ensure a fair comparison, we follow these principles:

1. **Warmup phase**: Pre-execution to stabilize connections and server caches (results excluded)
2. **Multiple rounds**: Multiple rounds per operation, reporting median of medians
3. **Pre-seeded data**: Data pre-loaded before read benchmarks
4. **GC disabled**: Python GC disabled during measurement intervals
5. **Isolated key prefixes**: Separate key prefixes for each client

## Comparison Targets

| Client | Language | Description |
|--------|----------|-------------|
| aerospike-py (sync) | Rust + Python | Synchronous API of this project |
| aerospike-py (async) | Rust + Python | Asynchronous API of this project |
| official aerospike | C + Python | [Official Aerospike C client](https://github.com/aerospike/aerospike-client-python) |

## Running Locally

### Basic Benchmark (console output only)

```bash
make run-benchmark
```

### Generate Report (MD + charts)

```bash
make run-benchmark-report
```

Generated files:
- `docs/docs/performance/benchmark-results.md` — Markdown report
- `docs/static/img/benchmark/*.svg` — 3 SVG charts

### Customizing Parameters

```bash
make run-benchmark BENCH_COUNT=10000 BENCH_ROUNDS=30 BENCH_CONCURRENCY=100
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BENCH_COUNT` | 5,000 | Operations per round |
| `BENCH_ROUNDS` | 20 | Rounds per operation |
| `BENCH_CONCURRENCY` | 50 | Async concurrency level |
| `BENCH_BATCH_GROUPS` | 10 | Number of batch_read groups |

## Latest Results

See the [Benchmark Results](./benchmark-results) page for the latest benchmark results.

See the [NumPy Batch Benchmark](./numpy-benchmark-results) page for dict vs numpy batch_read comparison.
