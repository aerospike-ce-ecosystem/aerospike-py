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
batch = client.batch_read(keys, bins=["score", "rating"]).to_numpy(dtype)
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

High-concurrency Python services can saturate two layers beneath
`aerospike-py`. This includes FastAPI services, Gunicorn workers, and Celery
fan-out workloads:

1. The **internal Tokio runtime** that drives the Rust async client.
2. The **per-node connection pool** to the Aerospike server.

Tune these layers independently. Choose the setting that matches the symptom.

### `AEROSPIKE_RUNTIME_WORKERS` (env var)

This variable controls the number of Tokio worker threads in the embedded
async runtime. It defaults to `2` to limit CPU overhead when the process also
runs CPU-heavy work such as PyTorch inference or scikit-learn.

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

The client reads this variable once, when the first `AsyncClient.connect()`
initializes the runtime. Set it before importing `aerospike_py`; changing it
after initialization has no effect.

### `max_concurrent_operations` (client config)

This setting caps the number of operations dispatched to the Rust client at
one time. It is disabled by default (`0`) and adds no overhead. When enabled,
extra callers wait for a slot instead of failing or exhausting the connection
pool.

```python
config = {
    # "aerospike" = service name in your Podman/compose file; use 127.0.0.1 for local dev
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

**Choose a value:** keep it close to, but no higher than,
`max_conns_per_node` (default `256`). For a three-node cluster, start at `64`.
This conservative value protects the pool while preserving throughput.

**Enable it when:** high-fan-out batch reads stall the `spawn_blocking` queue,
or an upstream caller can issue more operations than the connection pool can
serve. A FastAPI load test is one common example.

### Quick before/after

```python
# Before: 100 concurrent FastAPI requests calling batch_read each
# may stall on the Tokio queue with default 2 workers and no cap.

# After (env): export AEROSPIKE_RUNTIME_WORKERS=4
# AND (programmatic):
import aerospike_py

client = aerospike_py.AsyncClient({
    # "aerospike" = service name in your Podman/compose file; use 127.0.0.1 for local dev
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

With these starting values, one Gunicorn worker can sustain about 64
concurrent Aerospike operations without exhausting the pool. Calculate total
cluster-side load as `gunicorn_workers * max_concurrent_operations`, then size
the cluster for that result.

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
