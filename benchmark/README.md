# Benchmark: aerospike-py vs Official aerospike (C Client)

Measures how aerospike-py (Rust/PyO3) compares to the official aerospike Python client (C extension).

## Methodology

For consistent, reproducible results:

1. **Warmup** (default 200 ops) — stabilizes connection pools and server cache before measuring
2. **Multiple rounds** (default 5) — reports median-of-medians across rounds
3. **Data separation** — read benchmarks use pre-seeded data; put is measured independently
4. **GC disabled** — Python garbage collection is off during measurement intervals
5. **Key isolation** — each client uses a unique key prefix to avoid interference

## Comparison Targets

| Column | Client | Description |
| ------ | ------ | ----------- |
| aerospike-py (SyncClient) | `aerospike.Client` | Rust-based sync client |
| aerospike (official) | `aerospike.client` (PyPI) | Official C extension sync client |
| aerospike-py (AsyncClient) | `aerospike.AsyncClient` | Rust-based async client + `asyncio.gather` |

## Prerequisites

```bash
# Aerospike server
docker run -d --name aerospike \
  -p 3000:3000 \
  -e "NAMESPACE=test" \
  -e "CLUSTER_NAME=docker" \
  aerospike/aerospike-server

# Install both clients
maturin develop              # aerospike-py (Rust)
pip install aerospike        # official C client
```

## Run

```bash
# Default (5000 ops x 20 rounds, concurrency 50, batch_groups 10)
make run-benchmark

# Custom parameters
make run-benchmark BENCH_COUNT=2000 BENCH_ROUNDS=7 BENCH_CONCURRENCY=100 BENCH_BATCH_GROUPS=20

# Direct execution
python benchmark/bench_compare.py --count 1000 --rounds 5 --warmup 200 --concurrency 50 --batch-groups 10
```

## Output

```text
Benchmark config:
  ops/round    = 1,000
  rounds       = 5
  warmup       = 200
  concurrency  = 50
  batch_groups = 10

====================================================================================================
  aerospike-py Benchmark  (1,000 ops x 5 rounds, warmup=200, async concurrency=50, batch_groups=10)
====================================================================================================

  Avg Latency (ms)  —  lower is better  [median of round means]
  ──────────────────────────────────────────────────────────────────────────────────────
  Operation          | aerospike-py (SyncClient) | aerospike (official) | aerospike-py (AsyncClient) | Sync vs Official | Async vs Official
  put                |              0.310ms  |               0.580ms  |              0.041ms | 1.9x faster   | 14.1x faster
  get                |              0.195ms  |               0.398ms  |              0.028ms | 2.0x faster   | 14.2x faster
  batch_read   |              0.XXXms  |               0.XXXms  |              0.XXXms | X.Xx faster   |  ~Mx faster
  scan               |              0.011ms  |               0.030ms  |              0.009ms | 2.7x faster   |  3.3x faster

  Stability (stdev of round median latency, ms)  —  lower = more stable
  ──────────────────────────────────────────────────────────────────────────────────────
  Operation          |            Sync stdev |        Official stdev |         Async stdev
  put                |              0.008ms  |              0.015ms  |              0.003ms
  get                |              0.005ms  |              0.012ms  |              0.002ms
```

## Metrics

| Metric | Description |
| ------ | ----------- |
| avg_ms | Median of round means (lower is better) |
| p50_ms | Median of round medians |
| p99_ms | Aggregated 99th percentile |
| ops_per_sec | Median of round throughputs (higher is better) |
| stdev_ms | Stdev of round medians (lower = more stable) |
| Sync vs Official | Speedup of aerospike-py sync vs official client |
| Async vs Official | Speedup of aerospike-py async vs official client |

## Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `AEROSPIKE_HOST` | `127.0.0.1` | Aerospike host |
| `AEROSPIKE_PORT` | `3000` | Aerospike port |

## Why Faster?

- **Rust async runtime**: Tokio-based async I/O under the hood
- **Zero-copy**: Efficient Python-Rust type conversion via PyO3
- **Native async**: `AsyncClient` + `asyncio.gather` for thousands of concurrent requests
- **No GIL bottleneck**: GIL released during Rust execution (`py.allow_threads`)
