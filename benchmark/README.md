# Benchmark: aerospike-py vs Official aerospike (C Client)

Measures how aerospike-py (Rust/PyO3) compares to the official aerospike Python client (C extension).

## Methodology

For consistent, reproducible results:

1. **Warmup** (default 500 ops) — stabilizes connection pools and server cache before measuring
2. **Multiple rounds** (default 20) — reports median-of-medians across rounds with IQR outlier trimming
3. **Data separation** — read benchmarks use pre-seeded data; put is measured independently
4. **GC disabled** — Python garbage collection is off during measurement intervals
5. **Key isolation** — each client uses a unique key prefix to avoid interference

## Comparison Targets

| Column | Client | Description |
| ------ | ------ | ----------- |
| Sync (sequential) | `aerospike_py.client()` | Rust-based sync client |
| Official (sequential) | `aerospike.client()` (PyPI) | Official C extension sync client |
| Async (concurrent) | `aerospike_py.AsyncClient` | Rust-based async client + `asyncio.gather` |

## Prerequisites

```bash
# Aerospike server (via Makefile)
make run-aerospike-ce                    # docker (default)
make run-aerospike-ce RUNTIME=podman     # podman

# Install both clients
maturin develop --release    # aerospike-py (Rust)
pip install aerospike        # official C client (optional, for comparison)
```

## Run

```bash
# Default (5000 ops x 20 rounds, concurrency 50, batch_groups 10)
make run-benchmark

# With report generation (JSON for Docusaurus charts)
make run-benchmark-report

# Custom parameters
make run-benchmark BENCH_COUNT=2000 BENCH_ROUNDS=7 BENCH_CONCURRENCY=100 BENCH_BATCH_GROUPS=20

# Large-scale (100K ops x 5 rounds)
make run-benchmark-large

# Podman support
make run-benchmark-report RUNTIME=podman

# Direct execution
python benchmark/bench_compare.py --count 5000 --rounds 20 --warmup 500 --concurrency 50 --batch-groups 10
```

## Output

```text
====================================================================================================
  aerospike-py Benchmark  (5,000 ops x 20 rounds, warmup=500, async concurrency=50, batch_groups=10)
====================================================================================================

  Avg Latency (ms)  —  lower is better  [median of round means]
  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  Operation          |   Sync (sequential) | Official (sequential) |    Async (concurrent) | Sync vs Official | Async vs Official
  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  put                |             0.191ms |               0.147ms |               0.069ms |     1.3x slower  |     2.1x faster
  get                |             0.192ms |               0.146ms |               0.089ms |     1.3x slower  |     1.6x faster
  operate            |             0.195ms |               0.149ms |               0.090ms |     1.3x slower  |     1.7x faster
  remove             |             0.189ms |               0.142ms |               0.066ms |     1.3x slower  |     2.1x faster
  batch_read         |             0.008ms |               0.005ms |               0.002ms |     1.5x slower  |     2.2x faster
  batch_read_numpy   |             0.007ms |               0.005ms |               0.002ms |     1.3x slower  |     3.4x faster
  batch_write        |             0.008ms |               0.004ms |               0.002ms |     1.9x slower  |     2.5x faster
  scan               |             0.003ms |               0.001ms |               0.003ms |     1.8x slower  |     1.9x slower

  Throughput (ops/sec)  —  higher is better  [median of rounds]
  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  Operation          |   Sync (sequential) | Official (sequential) |    Async (concurrent) | Sync vs Official | Async vs Official
  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  put                |             5,248/s |               6,780/s |              14,481/s |     1.3x slower  |     2.1x faster
  get                |             5,214/s |               6,862/s |              11,214/s |     1.3x slower  |     1.6x faster
  operate            |             5,136/s |               6,717/s |              11,125/s |     1.3x slower  |     1.7x faster
  remove             |             5,304/s |               7,025/s |              15,083/s |     1.3x slower  |     2.1x faster
  batch_read         |           126,820/s |             197,391/s |             434,345/s |     1.6x slower  |     2.2x faster
  batch_read_numpy   |           151,619/s |             197,391/s |             664,809/s |     1.3x slower  |     3.4x faster
  batch_write        |           132,419/s |             246,465/s |             618,260/s |     1.9x slower  |     2.5x faster
  scan               |           383,436/s |             686,563/s |             373,625/s |     1.8x slower  |     1.8x slower

  Stability (stdev of round median latency, ms)  —  lower = more stable
  ─────────────────────────────────────────────────────────────────────
  Operation          |       Sync stdev |   Official stdev |      Async stdev
  ─────────────────────────────────────────────────────────────────────
  put                |          0.001ms |          0.001ms |          0.001ms
  get                |          0.001ms |          0.001ms |          0.000ms
  operate            |          0.001ms |          0.002ms |          0.001ms
  remove             |          0.001ms |          0.001ms |          0.001ms
  batch_read         |          0.001ms |          0.002ms |          0.000ms
  batch_read_numpy   |          0.001ms |                - |          0.000ms
  batch_write        |          0.001ms |          0.002ms |          0.000ms
  scan               |          0.000ms |          0.000ms |          0.000ms

  Tail Latency (ms)  [aggregated across all rounds]
  ──────────────────────────────────────────────────────────────────────────
  Operation          |   Sync p50 |   Sync p99 | Official p50 | Official p99
  ──────────────────────────────────────────────────────────────────────────
  put                |    0.183ms |    0.283ms |      0.144ms |      0.216ms
  get                |    0.184ms |    0.283ms |      0.142ms |      0.219ms
  operate            |    0.186ms |    0.291ms |      0.145ms |      0.224ms
  remove             |    0.181ms |    0.282ms |      0.138ms |      0.211ms
```

> Environment: macOS (Apple Silicon, M4 Pro), Aerospike CE 8.1.0.3, Python 3.13

## NumPy Batch Benchmark

Compares `batch_read` (dict) vs `batch_read_numpy` (numpy structured array) across 4 scenarios.

### Run

```bash
# Default (10 rounds, concurrency 50)
make run-numpy-benchmark

# With report generation
make run-numpy-benchmark-report

# Custom parameters
make run-numpy-benchmark NUMPY_BENCH_ROUNDS=20 NUMPY_BENCH_CONCURRENCY=100

# Podman support
make run-numpy-benchmark-report RUNTIME=podman
```

### Output

```text
  Record Count Scaling (bins=5, rounds=10)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
   Records | batch_read(Sync) | numpy(Sync) | batch_read(Async) | numpy(Async) | Speedup(Sync) | Speedup(Async)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
       100 |          0.056ms |     0.044ms |           0.026ms |      0.024ms |  1.3x faster  |  1.1x faster
       500 |          0.017ms |     0.015ms |           0.012ms |      0.006ms |  1.1x faster  |  2.0x faster
     1,000 |          0.033ms |     0.016ms |           0.005ms |      0.004ms |  2.0x faster  |  1.3x faster
     5,000 |          0.011ms |     0.007ms |           0.003ms |      0.002ms |  1.5x faster  |  1.6x faster
    10,000 |          0.007ms |     0.005ms |           0.002ms |      0.001ms |  1.5x faster  |  1.6x faster

  Bin Count Scaling (records=1000, rounds=10)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
      Bins | batch_read(Sync) | numpy(Sync) | batch_read(Async) | numpy(Async) | Speedup(Sync) | Speedup(Async)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
         1 |          0.020ms |     0.019ms |           0.005ms |      0.003ms |  1.1x faster  |  1.6x faster
         3 |          0.023ms |     0.019ms |           0.007ms |      0.004ms |  1.2x faster  |  1.9x faster
         5 |          0.028ms |     0.031ms |           0.008ms |      0.004ms |  1.1x slower  |  2.2x faster
        10 |          0.038ms |     0.029ms |           0.007ms |      0.004ms |  1.3x faster  |  1.7x faster
        20 |          0.023ms |     0.010ms |           0.006ms |      0.004ms |  2.2x faster  |  1.4x faster

  Memory Usage (bins=5, rounds=10, Sync only)
  ────────────────────────────────────────────────────────────────────
   Records | dict peak (KB) | numpy peak (KB) |    Savings
  ────────────────────────────────────────────────────────────────────
       100 |          169.9 |            74.8 |      56.0%
       500 |          704.2 |           129.0 |      81.7%
     1,000 |        1,365.8 |           186.3 |      86.4%
     5,000 |        6,612.3 |           782.3 |      88.2%
    10,000 |       13,179.8 |         1,575.4 |      88.0%
```

## Metrics

| Metric | Description |
| ------ | ----------- |
| avg_ms | Median of round means (lower is better) |
| p50_ms | Median of round medians |
| p99_ms | Aggregated 99th percentile |
| ops_per_sec | Median of round throughputs (higher is better) |
| stdev_ms | Stdev of round medians (lower = more stable) |

## Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `AEROSPIKE_HOST` | `127.0.0.1` | Aerospike host |
| `AEROSPIKE_PORT` | `3000` | Aerospike port |
| `RUNTIME` | `docker` | Container runtime (`docker` or `podman`) |

## Why Faster?

- **Rust async runtime**: Tokio-based async I/O under the hood
- **Zero-copy**: Efficient Python-Rust type conversion via PyO3
- **Native async**: `AsyncClient` + `asyncio.gather` for thousands of concurrent requests
- **No GIL bottleneck**: GIL released during Rust execution (`py.allow_threads`)
- **NumPy structured arrays**: Up to 88% memory savings with vectorized column operations
