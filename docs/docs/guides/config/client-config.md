---
title: Client Configuration
sidebar_label: Connection & Config
sidebar_position: 1
slug: /guides/client-config
description: Configure connections, timeouts, auth, and connection pools.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Basic Configuration

```python
import aerospike_py as aerospike
from aerospike_py.types import ClientConfig

config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}
client = aerospike.client(config).connect()
```

## All Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | Seed node addresses |
| `cluster_name` | `str` | `""` | Expected cluster name |
| `auth_mode` | `int` | `AUTH_INTERNAL` | Auth mode |
| `user` / `password` | `str` | `""` | Credentials |
| `timeout` | `int` | `1000` | Connection timeout (ms) |
| `idle_timeout` | `int` | `55` | Idle connection timeout (s) |
| `max_conns_per_node` | `int` | `256` | Max connections per node |
| `min_conns_per_node` | `int` | `0` | Pre-warm connections |
| `conn_pools_per_node` | `int` | `1` | Connection pools per node (increase on 8+ CPU cores) |
| `tend_interval` | `int` | `1000` | Cluster tend interval (ms) |
| `use_services_alternate` | `bool` | `false` | Use alternate addresses |
| `max_concurrent_operations` | `int` | `0` (disabled) | Max in-flight operations per client. `0` = unlimited. |
| `operation_queue_timeout_ms` | `int` | `0` (infinite) | Max wait time for a backpressure slot (ms). `0` = wait forever. |

## Multi-Node Cluster

The client discovers all nodes from any reachable seed:

```python
config: ClientConfig = {
    "hosts": [
        ("node1.example.com", 3000),
        ("node2.example.com", 3000),
        ("node3.example.com", 3000),
    ],
}
```

## Connection Pool

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "max_conns_per_node": 300,
    "min_conns_per_node": 10,
    "conn_pools_per_node": 1,
    "idle_timeout": 55,
}
```

- `max_conns_per_node`: Match to expected concurrent requests per node
- `min_conns_per_node`: Avoid cold-start latency
- `conn_pools_per_node`: Number of connection pools per node. Machines with 8 or fewer CPU cores typically need only 1. On machines with more cores, increasing this value reduces lock contention on pooled connections
- `idle_timeout`: Keep below server `proto-fd-idle-ms` (default 60s)

## Backpressure

When running many concurrent operations (e.g., `asyncio.gather` with hundreds of tasks), the upstream connection pool can be exhausted, causing `NoMoreConnections` errors. Backpressure limits how many operations are in-flight simultaneously:

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "max_concurrent_operations": 64,       # at most 64 in-flight ops
    "operation_queue_timeout_ms": 5000,    # wait up to 5s for a slot
}
```

- **Disabled by default** (`max_concurrent_operations=0`): zero overhead.
- When enabled, excess operations wait for a free slot instead of failing.
- If `operation_queue_timeout_ms` expires while waiting, raises `BackpressureError`.

## Per-Operation Timeouts

```python
from aerospike_py.types import ReadPolicy, WritePolicy

read_policy: ReadPolicy = {
    "socket_timeout": 5000,
    "total_timeout": 10000,
    "max_retries": 2,
}
record = client.get(key, policy=read_policy)
```

## Authentication

```python
# Internal
client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_INTERNAL,
}).connect("admin", "admin")

# External (LDAP)
client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_EXTERNAL,
}).connect("ldap_user", "ldap_pass")
```

## Cluster Info

```python
from aerospike_py.types import InfoNodeResult

results: list[InfoNodeResult] = client.info_all("namespaces")
for r in results:
    print(f"{r.node_name}: {r.response}")

version: str = client.info_random_node("build")
```

## Health Check

The client provides two ways to check cluster health:

- **`is_connected()`** — checks local state only (no I/O). Fast but may return `True` even if the cluster is temporarily unreachable.
- **`ping()`** — sends a lightweight `info("build")` command to a random node. Performs an actual network round-trip to verify liveness. Returns `True` if the node responds, `False` otherwise (never raises).

```python
# Kubernetes readiness probe / load-balancer health check
if client.ping():
    return {"status": "healthy"}

# Async health endpoint (e.g., FastAPI)
@app.get("/health")
async def health():
    ok = await async_client.ping()
    return {"status": "ok" if ok else "degraded"}
```

The background **tend** process (configured via `tend_interval`, default 1000 ms) automatically monitors cluster membership and connection health. `ping()` complements this by providing on-demand verification.

## Sync vs Async

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# Context manager (recommended)
with aerospike.client(config).connect() as client:
    record = client.get(key)
# close() called automatically

# Manual
client = aerospike.client(config).connect()
try:
    record = client.get(key)
finally:
    client.close()
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# Context manager
async with aerospike.AsyncClient(config) as client:
    await client.connect()
    record = await client.get(key)

# Manual
client = aerospike.AsyncClient(config)
await client.connect()
try:
    record = await client.get(key)
finally:
    await client.close()
```

  </TabItem>
</Tabs>

**Use async for:** High-concurrency web servers, fan-out reads, mixed I/O.
**Sync is fine for:** Scripts, batch jobs, sequential pipelines.
