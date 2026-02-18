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
    "max_conns_per_node": 300,   # default: 100
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

## Async Client

For high-concurrency workloads (web servers, fan-out reads):

```python
import asyncio

async def main() -> None:
    client = aerospike.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
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
