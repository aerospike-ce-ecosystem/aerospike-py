---
title: Performance Tuning
sidebar_label: Performance Tuning
sidebar_position: 2
slug: /guides/performance-tuning
description: Tips for optimizing aerospike-py throughput and latency.
---

## Connection Pool

```python
config = {
    "hosts": [("node1", 3000), ("node2", 3000)],
    "max_conns_per_node": 300,   # default: 256
    "min_conns_per_node": 10,    # pre-warm
    "idle_timeout": 55,          # below server proto-fd-idle-ms (60s)
}
```

## Read Optimization

### Select Specific Bins

```python
# Reads ALL bins from server
record = client.get(key)

# Reads only what you need (less network I/O)
record = client.select(key, ["name", "age"])
```

### Use Batch Reads

```python
# N sequential round-trips
results = [client.get(k) for k in keys]

# Single round-trip
batch = client.batch_read(keys, bins=["name", "age"])
```

### NumPy Batch Reads

For numeric workloads, skip Python dict overhead entirely:

```python
import numpy as np

dtype = np.dtype([("score", "i8"), ("rating", "f8")])
batch = client.batch_read(keys, bins=["score", "rating"], _dtype=dtype)
# batch.batch_records is a numpy structured array
```

See [NumPy Batch Guide](../crud/numpy-batch.md).

## Write Optimization

### Combine Operations

```python
# Two round-trips
client.put(key, {"counter": 1})
client.put(key, {"updated_at": now})

# Single round-trip
ops = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_WRITE, "bin": "updated_at", "val": now},
]
client.operate(key, ops)
```

### TTL Strategy

```python
client.put(key, bins, meta={"ttl": aerospike.TTL_NEVER_EXPIRE})     # never expire
client.put(key, bins, meta={"ttl": aerospike.TTL_DONT_UPDATE})      # keep existing TTL
client.put(key, bins, meta={"ttl": aerospike.TTL_NAMESPACE_DEFAULT}) # use namespace default
```

## Concurrency & Backpressure Tuning

High-concurrency Python services (FastAPI, Gunicorn workers, Celery
fan-out) can saturate the two layers underneath `aerospike-py`:

1. The **internal Tokio runtime** that drives the Rust async client.
2. The **per-node connection pool** to the Aerospike server.

There are two independent knobs — pick the right one for the symptom.

### `AEROSPIKE_RUNTIME_WORKERS` (env var)

Controls the number of Tokio worker threads used by the embedded async
runtime. **Default: `2`**, which keeps CPU overhead low when colocated
with CPU-heavy workloads (PyTorch inference, sklearn, etc.).

```bash
# Bump worker count when 10+ concurrent FastAPI requests each call
# batch_read and you observe `spawn_blocking` queue stalls.
export AEROSPIKE_RUNTIME_WORKERS=4
```

| Workers | Use case |
|---------|----------|
| `2` (default) | Most applications, ML serving, single-tenant web servers |
| `4` | Concurrent batch_read fan-out, FastAPI with many in-flight requests |
| `4–8` | High-throughput pipelines, Gunicorn with `--workers >= 4` per process |
| `8+` | Rarely needed — profile first with `py-spy`/`tokio-console` |

**Symptoms that mean "increase workers":**

- `await client.batch_read(...)` p99 latency rises sharply at >10 in-flight
  callers, while server-side metrics show the cluster is healthy.
- `tokio-console` (or a Tokio runtime metric) shows a queue depth that
  grows unboundedly during load.

The env var is read **once at runtime initialization** (first
`AsyncClient.connect()`). Changing it after the runtime is up has no
effect — set it before importing `aerospike_py`.

### `max_concurrent_operations` (client config)

Caps the number of in-flight operations dispatched into the Rust client
at any moment. **Disabled by default** (`0`, zero overhead). When set,
excess callers **queue** for a slot instead of failing or exhausting the
connection pool.

```python
config = {
    "hosts": [("aerospike", 3000)],
    "max_concurrent_operations": 64,    # at most 64 in-flight ops
    "operation_queue_timeout_ms": 5000, # raise BackpressureError after 5s
}
```

When enabled:

- Operations beyond the limit **wait** for a free slot.
- Waiting operations resume as soon as a previous one completes.
- `aerospike_py.BackpressureError` is raised only if
  `operation_queue_timeout_ms` expires before a slot frees up.

**Choosing the value:** set this close to (but no higher than)
`max_conns_per_node` (default `256`). For a 3-node cluster, `64` is a
conservative starting point that prevents pool exhaustion while keeping
throughput high.

**Enable when:** high-fanout batch reads where the `spawn_blocking`
queue would otherwise stall, or when an upstream caller (FastAPI under
load test) can issue more concurrent ops than the connection pool can
serve.

### Quick before/after

```python
# Before: 100 concurrent FastAPI requests calling batch_read each
# may stall on the Tokio queue with default 2 workers and no cap.

# After (env): export AEROSPIKE_RUNTIME_WORKERS=4
# AND (programmatic):
import aerospike_py

client = aerospike_py.AsyncClient({
    "hosts": [("aerospike", 3000)],
    "max_concurrent_operations": 64,    # caps in-flight ops
    "operation_queue_timeout_ms": 5000,
})
await client.connect()
```

### FastAPI / Gunicorn recommendations

For a FastAPI service deployed under Gunicorn with `uvicorn` workers
(see `examples/sample-fastapi/`):

| Setting | Recommended starting value | Notes |
|---------|---------------------------|-------|
| `AEROSPIKE_RUNTIME_WORKERS` | `4` | Set in the deployment env, not in code. |
| `max_concurrent_operations` | `64` | Per `AsyncClient` instance, per worker process. |
| `operation_queue_timeout_ms` | `5000` | Pair with FastAPI request timeout. |
| Gunicorn `--workers` | `2 * CPU` | Each worker has its own client + Tokio runtime. |
| `max_conns_per_node` | `256` | Stay well above `max_concurrent_operations`. |

A single Gunicorn worker with the values above can sustain ~64 concurrent
in-flight Aerospike ops without exhausting the pool. Total cluster-side
load = `gunicorn_workers * max_concurrent_operations`; size accordingly.

## Async Client

For high-concurrency workloads (web servers, fan-out reads):

```python
import asyncio

async def main() -> None:
    client = aerospike.AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "max_concurrent_operations": 64,  # prevent pool exhaustion
    })
    await client.connect()

    keys = [("test", "demo", f"key{i}") for i in range(1000)]
    results = await asyncio.gather(*(client.get(k) for k in keys))

    await client.close()
```

## Expression Filters

Push filtering to the server to reduce network transfer:

```python
from aerospike_py import exp

# Without filter: transfers ALL records, filters in Python
results = client.query("test", "demo").results()
active = [r for r in results if r.bins.get("active")]

# With filter: server returns only matching records
expr = exp.eq(exp.bool_bin("active"), exp.bool_val(True))
results = client.query("test", "demo").results(policy={"filter_expression": expr})
```

## Timeout Guidelines

| Setting | Recommendation |
|---------|---------------|
| `socket_timeout` | 1-5s. Catches hung connections. |
| `total_timeout` | Set based on SLA. Includes retries. |
| `max_retries` | 2-3 for reads, 0 for writes (idempotency). |
