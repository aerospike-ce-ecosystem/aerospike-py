# Benchmark: aerospike-py vs Official aerospike (C Client)

Measures how aerospike-py (Rust/PyO3) compares to the official aerospike Python client (C extension).

## Quick Start

```bash
make run-benchmark-report                      # basic scenario + JSON report
make run-benchmark-report BENCH_SCENARIO=all   # all scenarios (+ numpy) + JSON report
```

## Run

All benchmark commands accept these variables:

```bash
make run-benchmark-report BENCH_COUNT=2000 BENCH_ROUNDS=10 BENCH_CONCURRENCY=100 BENCH_SCENARIO=data_size
```

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCH_SCENARIO` | `basic` | Scenario to run (see below) |
| `BENCH_COUNT` | `5000` | Operations per round |
| `BENCH_ROUNDS` | `20` | Number of rounds |
| `BENCH_CONCURRENCY` | `50` | Async concurrency level |
| `BENCH_BATCH_GROUPS` | `10` | Batch read groups |
| `RUNTIME` | `podman` | Container runtime (`podman` or `docker`) |

### Scenarios (`BENCH_SCENARIO`)

| Value | Description |
|-------|-------------|
| `basic` | Standard CRUD benchmark (PUT, GET, OPERATE, REMOVE, BATCH_READ, BATCH_WRITE, QUERY) |
| `data_size` | Latency + CPU breakdown across record sizes (tiny → xlarge) |
| `concurrency` | AsyncClient throughput at concurrency levels 1, 10, 50, 100, 200, 500 |
| `memory` | Peak memory profiling via `tracemalloc` |
| `mixed` | Read/write mixed workload simulation (90:10, 50:50, 10:90) |
| `all` | Run basic + all above scenarios + NumPy batch benchmark |

### Examples

```bash
# Basic benchmark + report (default)
make run-benchmark-report

# Specific scenario with report
make run-benchmark-report BENCH_SCENARIO=memory

# All scenarios + numpy + report
make run-benchmark-report BENCH_SCENARIO=all

# Large-scale test (100K ops x 5 rounds)
make run-benchmark-report BENCH_COUNT=100000 BENCH_ROUNDS=5
```

### Typical Workflow

```bash
# 1. Run benchmark and generate report JSON
make run-benchmark-report BENCH_SCENARIO=all

# 2. Build docs (includes benchmark charts)
make docs-build

# 3. Preview locally
make docs-serve
```

## Prerequisites

```bash
make run-aerospike-ce               # start Aerospike CE (auto-started by benchmark targets)
maturin develop --release           # build aerospike-py (auto-built by benchmark targets)
pip install aerospike               # official C client (optional, for comparison)
```

## Output

```text
  Avg Latency (ms)  —  lower is better
  Operation          |   Sync (sequential) | Official (sequential) |    Async (concurrent) | Sync vs Official | Async vs Official
  put                |             0.191ms |               0.147ms |               0.069ms |     1.3x slower  |     2.1x faster
  get                |             0.192ms |               0.146ms |               0.089ms |     1.3x slower  |     1.6x faster
  batch_read         |             0.008ms |               0.005ms |               0.002ms |     1.5x slower  |     2.2x faster
  batch_read_numpy   |             0.007ms |               0.005ms |               0.002ms |     1.3x slower  |     3.4x faster

  Throughput (ops/sec)  —  higher is better
  put                |             5,248/s |               6,780/s |              14,481/s |     1.3x slower  |     2.1x faster
  get                |             5,214/s |               6,862/s |              11,214/s |     1.3x slower  |     1.6x faster
  batch_read_numpy   |           151,619/s |             197,391/s |             664,809/s |     1.3x slower  |     3.4x faster
```

> Environment: macOS (Apple Silicon, M4 Pro), Aerospike CE 8.1.0.3, Python 3.13

## Advanced Scenario Outputs

### Data Size Scaling (`BENCH_SCENARIO=data_size`)

```text
  Profile                    | PUT p50    | PUT p99    | PUT CPU% | GET p50    | GET p99    | GET CPU%
  tiny (3 bins, 10B)         |    0.120ms |    0.185ms |    18.2% |    0.115ms |    0.180ms |    17.5%
  xlarge (50 bins, 1KB)      |    0.245ms |    0.410ms |    22.8% |    0.230ms |    0.380ms |    21.0%
```

### Concurrency Scaling (`BENCH_SCENARIO=concurrency`)

```text
    Conc | PUT ops/s    | PUT p50    | PUT p99    | GET ops/s    | GET p50    | GET p99
       1 |      5,200/s |    0.190ms |    0.310ms |      5,400/s |    0.180ms |    0.300ms
      50 |     14,500/s |    3.200ms |    5.200ms |     15,000/s |    3.000ms |    4.900ms
     500 |     18,200/s |   25.000ms |   40.000ms |     18,500/s |   24.000ms |   38.000ms
```

### Memory Profiling (`BENCH_SCENARIO=memory`)

```text
  Profile                    | PUT peak     | GET peak     | BATCH peak
  tiny (3 bins, 10B)         |       128KB  |       256KB  |       512KB
  xlarge (50 bins, 1KB)      |       2.1MB  |       4.2MB  |       8.5MB
```

### Mixed Workload (`BENCH_SCENARIO=mixed`)

```text
  Workload               | Throughput   | Read p50   | Read p95   | Write p50  | Write p95
  read_heavy (90:10)     |     12,500/s |    0.085ms |    0.150ms |    0.095ms |    0.180ms
  balanced (50:50)       |     11,800/s |    0.090ms |    0.165ms |    0.098ms |    0.190ms
  write_heavy (10:90)    |     10,500/s |    0.095ms |    0.170ms |    0.102ms |    0.200ms
```

## Methodology

1. **Warmup** (500 ops) — stabilizes connection pools and server cache
2. **Multiple rounds** (20) — median-of-medians with IQR outlier trimming
3. **Pre-seeded data** — read benchmarks use pre-inserted records
4. **GC disabled** — Python GC off during measurement
5. **Key isolation** — unique key prefix per client
6. **CPU/IO separation** — `process_time()` vs `perf_counter()` for CPU vs I/O breakdown

## Metrics

| Metric | Description |
|--------|-------------|
| avg_ms | Median of round means (lower is better) |
| p50 / p95 / p99 / p99.9 | Percentile latencies |
| ops_per_sec | Median of round throughputs (higher is better) |
| stdev_ms / mad_ms | Stability metrics (lower = more stable) |
| cpu_pct | CPU% of wall time (lower = more I/O bound) |

## Why Faster?

- **Rust async runtime**: Tokio-based async I/O
- **Zero-copy**: Efficient Python-Rust type conversion via PyO3
- **Native async**: `AsyncClient` + `asyncio.gather` for concurrent requests
- **No GIL bottleneck**: GIL released during Rust execution (`py.allow_threads`)
- **NumPy**: Structured arrays with up to 88% memory savings
