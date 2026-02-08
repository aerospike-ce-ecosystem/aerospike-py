---
title: Performance Tuning
sidebar_label: Performance Tuning
sidebar_position: 8
description: Tips for optimizing aerospike-py throughput and latency.
---

# Performance Tuning Guide

## Client Configuration

### Connection Pool

```python
config = {
    "hosts": [("node1", 3000), ("node2", 3000)],
    "max_conns_per_node": 300,   # default: 100
    "min_conns_per_node": 10,    # pre-warm connections
    "idle_timeout": 55,          # seconds, keep below server proto-fd-idle-ms
}
client = aerospike.client(config).connect()
```

**Guidelines:**
- Set `max_conns_per_node` based on expected concurrent requests per node
- Use `min_conns_per_node` to avoid cold-start latency
- Set `idle_timeout` slightly below the server's `proto-fd-idle-ms` (default 60s)

### Timeouts

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "timeout": 30000,  # client-level timeout in ms (connect + tend)
}

# Per-operation timeouts via policy
policy = {
    "socket_timeout": 5000,  # per-socket timeout in ms
    "total_timeout": 10000,  # total operation timeout in ms
    "max_retries": 2,
}
client.get(key, policy=policy)
```

**Guidelines:**
- `socket_timeout` catches hung connections; keep it tight (1-5s)
- `total_timeout` limits end-to-end including retries; set based on SLA
- `max_retries` adds resilience but multiplies latency on failure

## Read Optimization

### Select Specific Bins

```python
# Slow: reads ALL bins from server
_, _, bins = client.get(key)

# Fast: reads only the bins you need
_, _, bins = client.select(key, ["name", "age"])
```

### Batch Reads

```python
# Slow: N sequential round-trips
results = [client.get(k) for k in keys]

# Fast: single round-trip
results = client.batch_read(keys, bins=["name", "age"])
```

### NumPy Batch Reads

For numeric workloads, use the numpy dtype to avoid Python dict overhead:

```python
import numpy as np

dtype = np.dtype([("score", "i8"), ("rating", "f8")])
result = client.batch_read(keys, bins=["score", "rating"], _dtype=dtype)
# result.array is a numpy structured array — no per-record dict allocation
```

## Write Optimization

### Batch Writes via operate()

When updating multiple bins in one record:

```python
# Slow: two round-trips
client.put(key, {"counter": 1})
client.put(key, {"updated_at": now})

# Fast: single round-trip
from aerospike_py import list_operations as lops
ops = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_WRITE, "bin": "updated_at", "val": now},
]
client.operate(key, ops)
```

### TTL Strategy

```python
# Never expire (careful with storage)
client.put(key, bins, meta={"ttl": aerospike.TTL_NEVER_EXPIRE})

# Don't update TTL on writes (preserves existing expiration)
client.put(key, bins, meta={"ttl": aerospike.TTL_DONT_UPDATE})

# Use namespace default
client.put(key, bins, meta={"ttl": aerospike.TTL_NAMESPACE_DEFAULT})
```

## Async Client

The async client uses a Tokio multi-threaded runtime under the hood.
For I/O-bound workloads with high concurrency, it significantly outperforms
the sync client:

```python
import asyncio
import aerospike_py as aerospike

async def main():
    client = aerospike.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()

    # Concurrent reads
    keys = [("test", "demo", f"key{i}") for i in range(1000)]
    tasks = [client.get(k) for k in keys]
    results = await asyncio.gather(*tasks)

    await client.close()
```

**When to use async:**
- High-concurrency web servers (FastAPI, aiohttp)
- Fan-out read patterns (many keys in parallel)
- Mixed I/O workloads (database + HTTP + cache)

**When sync is fine:**
- Simple scripts and batch jobs
- Sequential processing pipelines
- Low-concurrency applications

## Expression Filters

Push filtering to the server to reduce network transfer:

```python
from aerospike_py import exp

# Without filter: transfers ALL records, filters in Python
results = client.query("test", "demo").results()
active = [r for r in results if r[2].get("active")]

# With filter: server only returns matching records
policy = {
    "filter_expression": exp.eq(exp.bool_bin("active"), exp.bool_val(True))
}
results = client.query("test", "demo").results(policy)
```

## Monitoring

Key metrics to watch:
- **Connection pool usage**: If consistently near `max_conns_per_node`, increase the limit
- **Timeout rate**: High timeout rates suggest network issues or undersized timeouts
- **Record size**: Large records increase serialization cost; consider splitting into multiple bins or records
