---
title: Client Configuration
sidebar_label: Connection & Config
sidebar_position: 1
slug: /guides/client-config
description: Complete guide for configuring aerospike-py client connections, timeouts, and connection pools.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## ClientConfig Overview

The [`ClientConfig`](../../api/types.md#clientconfig) TypedDict defines all connection options passed to `aerospike.client()` or `AsyncClient()`.

```python
import aerospike_py as aerospike

config = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}
client = aerospike.client(config).connect()
```

## All Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | Seed node addresses `(host, port)` |
| `cluster_name` | `str` | `""` | Expected cluster name for validation |
| `auth_mode` | `int` | `AUTH_INTERNAL` | Authentication mode (`AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI`) |
| `user` | `str` | `""` | Username for authentication |
| `password` | `str` | `""` | Password for authentication |
| `timeout` | `int` | `1000` | Connection timeout in ms |
| `idle_timeout` | `int` | `55` | Max idle time for pooled connections in seconds |
| `max_conns_per_node` | `int` | `100` | Max connections per cluster node |
| `min_conns_per_node` | `int` | `0` | Pre-warm connections per node |
| `tend_interval` | `int` | `1000` | Cluster tend interval in ms |
| `use_services_alternate` | `bool` | `false` | Use alternate addresses from service responses |

## Hosts Configuration

### Single Node

```python
config = {"hosts": [("127.0.0.1", 3000)]}
```

### Multi-Node Cluster

Provide multiple seed nodes for automatic cluster discovery:

```python
config = {
    "hosts": [
        ("node1.example.com", 3000),
        ("node2.example.com", 3000),
        ("node3.example.com", 3000),
    ],
}
```

The client discovers all cluster nodes from any reachable seed node.

### Cluster Name Validation

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "production",  # fails if cluster name doesn't match
}
```

## Connection Pool

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "max_conns_per_node": 300,   # default: 100
    "min_conns_per_node": 10,    # pre-warm connections
    "idle_timeout": 55,          # seconds
}
```

**Guidelines:**
- Set `max_conns_per_node` based on expected concurrent requests per node
- Use `min_conns_per_node` to avoid cold-start latency
- Set `idle_timeout` slightly below the server's `proto-fd-idle-ms` (default 60s)

## Timeouts

### Client-Level Timeout

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "timeout": 30000,  # connection + tend timeout in ms
}
```

### Per-Operation Timeouts

Use [`ReadPolicy`](../../api/types.md#readpolicy) or [`WritePolicy`](../../api/types.md#writepolicy) for per-operation timeouts:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# Per-operation timeout via policy
policy = {
    "socket_timeout": 5000,   # per-socket timeout in ms
    "total_timeout": 10000,   # total operation timeout in ms
    "max_retries": 2,         # retry attempts
}
client.get(key, policy=policy)
client.put(key, bins, policy=policy)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
policy = {
    "socket_timeout": 5000,
    "total_timeout": 10000,
    "max_retries": 2,
}
await client.get(key, policy=policy)
await client.put(key, bins, policy=policy)
```

  </TabItem>
</Tabs>

**Guidelines:**
- `socket_timeout` catches hung connections; keep it tight (1-5s)
- `total_timeout` limits end-to-end including retries; set based on SLA
- `max_retries` adds resilience but multiplies latency on failure

## Authentication

### Internal Authentication

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_INTERNAL,
}
client = aerospike.client(config).connect(username="admin", password="admin")
```

### External Authentication (LDAP)

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_EXTERNAL,
}
client = aerospike.client(config).connect(username="ldap_user", password="ldap_pass")
```

## Cluster Info Commands

Use `info_all()` and `info_random_node()` to query cluster state:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import InfoNodeResult

# Query all nodes
results: list[InfoNodeResult] = client.info_all("status")
for r in results:
    print(f"{r.node_name}: {r.response}")

# Query a random node
response: str = client.info_random_node("build")
print(f"Server version: {response}")

# Common info commands
client.info_all("namespaces")          # list namespaces
client.info_all("sets/test")           # list sets in 'test' namespace
client.info_all("statistics")          # server statistics
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import InfoNodeResult

results: list[InfoNodeResult] = await client.info_all("status")
for r in results:
    print(f"{r.node_name}: {r.response}")

response: str = await client.info_random_node("build")
```

  </TabItem>
</Tabs>

## Logging

```python
import aerospike_py as aerospike

# Set log verbosity
aerospike.set_log_level(aerospike.LOG_LEVEL_DEBUG)
```

| Constant | Value | Description |
|----------|-------|-------------|
| `LOG_LEVEL_OFF` | -1 | Disable logging |
| `LOG_LEVEL_ERROR` | 0 | Errors only |
| `LOG_LEVEL_WARN` | 1 | Warnings and above |
| `LOG_LEVEL_INFO` | 2 | Info and above |
| `LOG_LEVEL_DEBUG` | 3 | Debug and above |
| `LOG_LEVEL_TRACE` | 4 | Full trace |

## Observability

### Prometheus Metrics

```python
# Start metrics HTTP server on /metrics
aerospike.start_metrics_server(port=9464)

# Get metrics as Prometheus text format
metrics_text = aerospike.get_metrics()

# Stop metrics server
aerospike.stop_metrics_server()
```

### OpenTelemetry Tracing

```python
# Initialize OTel tracer (configure via OTEL_* env vars)
aerospike.init_tracing()

# ... perform operations ...

# Flush spans and shutdown
aerospike.shutdown_tracing()
```

Span attributes: `db.system.name`, `db.namespace`, `db.collection.name`, `db.operation.name`, `server.address`, `server.port`, `db.aerospike.cluster_name`

## Sync vs Async Client

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

# Context manager (recommended)
with aerospike.client(config).connect() as client:
    client.put(key, bins)
    record = client.get(key)
# client.close() called automatically

# Manual lifecycle
client = aerospike.client(config).connect()
try:
    client.put(key, bins)
finally:
    client.close()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py as aerospike

# Context manager
async with aerospike.AsyncClient(config) as client:
    await client.connect()
    await client.put(key, bins)
    record = await client.get(key)

# Manual lifecycle
client = aerospike.AsyncClient(config)
await client.connect()
try:
    await client.put(key, bins)
finally:
    await client.close()
```

  </TabItem>
</Tabs>

**When to use async:**

- High-concurrency web servers (FastAPI, aiohttp)
- Fan-out read patterns (many keys in parallel)
- Mixed I/O workloads (database + HTTP + cache)

**When sync is fine:**

- Simple scripts and batch jobs
- Sequential processing pipelines
- Low-concurrency applications
