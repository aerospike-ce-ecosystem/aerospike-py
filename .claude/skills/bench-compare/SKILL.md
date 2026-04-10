---
name: bench-compare
description: Run benchmark comparison against official Aerospike C client
disable-model-invocation: true
---

# Benchmark Compare

Runs a performance comparison between aerospike-py and the official Aerospike C client.

## Prerequisites

1. An Aerospike server must be running.
2. The official C client (`aerospike` PyPI package) must be installed (included in the `bench` dependency group).

If no server is available, start one first:
```bash
make run-aerospike-ce
```

## Steps

### 1. Check Server Status
```bash
podman ps | grep aerospike || docker ps | grep aerospike
```

### 2. Build (reflect latest code)
```bash
make build
```

### 3. Run Default Benchmark
```bash
make run-benchmark
```

**Default parameters** (Makefile defaults):
| Parameter | Env Variable | Default | Description |
|---------|---------|--------|------|
| Record count | `BENCH_COUNT` | 5000 | Total number of records for testing |
| Rounds | `BENCH_ROUNDS` | 20 | Number of measurement iterations per operation |
| Concurrency | `BENCH_CONCURRENCY` | 50 | Number of concurrent requests |
| Batch groups | `BENCH_BATCH_GROUPS` | 10 | Number of batch operation groups |
| Host | `AEROSPIKE_HOST` | 127.0.0.1 | Server address |
| Port | `AEROSPIKE_PORT` | 18710 | Server port |

**Custom parameter example:**
```bash
BENCH_COUNT=10000 BENCH_ROUNDS=10 BENCH_CONCURRENCY=100 make run-benchmark
```

### 4. Large-scale Benchmark (optional)
```bash
make run-benchmark-large
```
Runs with 100K ops, 5 rounds. Suitable for stable performance measurement.

### 5. Generate Benchmark Report (optional)
```bash
make run-benchmark-report
```
Generates a JSON file + chart images.

### 6. NumPy Batch Benchmark (optional)
```bash
make run-numpy-benchmark
```

Compares dict-based `batch_read` vs NumPy `batch_read_numpy` performance.

**NumPy benchmark parameters:**
| Parameter | Env Variable | Default |
|---------|---------|--------|
| Rounds | `NUMPY_BENCH_ROUNDS` | 10 |
| Concurrency | `NUMPY_BENCH_CONCURRENCY` | 50 |
| Batch groups | `NUMPY_BENCH_BATCH_GROUPS` | 10 |

**NumPy benchmark scenarios** (`--scenario` option):
| Scenario | Description |
|---------|------|
| `record_scaling` | Performance across varying record counts (100, 500, 1K, 5K, 10K) |
| `bin_scaling` | Performance across varying bin counts (1, 3, 5, 10, 20) |
| `post_processing` | Performance by post-processing stage (raw read -> column access -> filter -> aggregation) |
| `memory` | tracemalloc-based memory usage comparison |
| `all` | All scenarios (default) |

Generate NumPy report:
```bash
make run-numpy-benchmark-report
```

## Benchmark Methodology

Measurement approach in `benchmark/bench_compare.py`:
1. **Warmup phase** (500 ops): stabilize connections, discard results
2. **Multiple rounds**: repeat each operation `BENCH_ROUNDS` times, measure median per round
3. **Data pre-seeding**: pre-create data before read benchmarks
4. **GC disabled**: disable GC during measurements
5. **Isolated key prefixes**: each client uses isolated key prefixes

## Result Analysis

Analyze benchmark results and report the following:
- **Per-operation comparison**: sync put/get, async put/get, batch_read, etc.
- **Throughput**: ops/sec comparison
- **Latency**: median (median of round medians) comparison
- **aerospike-py vs official client ratio**: how many times faster/slower
- **Performance changes compared to previous benchmarks** (if available)
- **Root cause analysis and improvement suggestions if performance regressions are found**

## Automatic Cleanup After Benchmarks

All benchmark Makefile targets (`make run-benchmark`, `make run-numpy-benchmark`, etc.) automatically call `make stop-aerospike-ce` after execution to clean up containers.
