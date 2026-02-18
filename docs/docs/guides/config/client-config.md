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
| `max_conns_per_node` | `int` | `100` | Max connections per node |
| `min_conns_per_node` | `int` | `0` | Pre-warm connections |
| `tend_interval` | `int` | `1000` | Cluster tend interval (ms) |
| `use_services_alternate` | `bool` | `false` | Use alternate addresses |

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
    "idle_timeout": 55,
}
```

- `max_conns_per_node`: Match to expected concurrent requests per node
- `min_conns_per_node`: Avoid cold-start latency
- `idle_timeout`: Keep below server `proto-fd-idle-ms` (default 60s)

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
