---
title: Client Configuration
sidebar_label: Connection & Config
sidebar_position: 1
slug: /guides/client-config
description: Configure connections, timeouts, auth, and connection pools.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## 기본 설정

```python
import aerospike_py as aerospike
from aerospike_py.types import ClientConfig

config: ClientConfig = {
    "hosts": [("127.0.0.1", 18710)],
    "cluster_name": "docker",
}
client = aerospike.client(config).connect()
```

## 모든 필드

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | seed node 주소 |
| `cluster_name` | `str \| None` | `""` | 예상 cluster name. `None` 은 field 생략과 동일 처리. |
| `auth_mode` | `int` | `AUTH_INTERNAL` | auth mode |
| `user` / `password` | `str` | `""` | 자격 증명 |
| `timeout` | `int` | `1000` | 연결 timeout (ms) |
| `idle_timeout` | `int` | `55` | idle connection timeout (초) |
| `max_conns_per_node` | `int` | `256` | node 당 최대 connection |
| `min_conns_per_node` | `int` | `0` | pre-warm connection |
| `conn_pools_per_node` | `int` | `1` | node 당 connection pool 수 (8+ CPU core 에서 증가) |
| `tend_interval` | `int` | `1000` | cluster tend interval (ms) |
| `use_services_alternate` | `bool` | `false` | alternate address 사용 |
| `max_concurrent_operations` | `int` | `0` (disabled) | client 당 in-flight operation 최대 수. `0` = 무제한. |
| `operation_queue_timeout_ms` | `int` | `0` (infinite) | backpressure slot 의 최대 wait time (ms). `0` = 영원히 대기. |

## Multi-Node Cluster

Client는 연결할 수 있는 seed 하나를 통해 cluster의 모든 node를 찾습니다.

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

- `max_conns_per_node`: node당 예상 동시 request 수에 맞춥니다.
- `min_conns_per_node`: connection을 미리 열어 cold-start latency를 줄입니다.
- `conn_pools_per_node`: CPU core가 8개 이하인 machine에서는 보통 1이면 충분합니다. Core가 더 많다면 값을 늘려 connection pool의 lock contention을 줄일 수 있습니다.
- `idle_timeout`: server의 `proto-fd-idle-ms`보다 낮게 설정합니다. 기본값은 60초입니다.

## Backpressure

수백 개 task를 `asyncio.gather`로 실행하면 connection pool이 고갈되어 `NoMoreConnections`가 발생할 수 있습니다. Backpressure는 동시에 실행할 수 있는 operation 수를 제한해 이를 방지합니다.

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "max_concurrent_operations": 64,       # 최대 64개 in-flight op
    "operation_queue_timeout_ms": 5000,    # slot 을 최대 5초 대기
}
```

- **기본 비활성** (`max_concurrent_operations=0`): zero overhead.
- 활성 시 초과 operation 은 실패하지 않고 빈 slot 을 대기.
- 대기 중 `operation_queue_timeout_ms` 만료 시 `BackpressureError` raise.

## Per-Operation Timeout

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

Client는 두 가지 방법으로 cluster health를 확인합니다.

- **`is_connected()`** — 로컬 상태만 확인 (I/O 없음). 빠르지만 cluster 가 일시적으로 도달 불가여도 `True` 반환 가능.
- **`ping()`** — 임의의 node에 가벼운 `info("build")` command를 보내 실제 network round trip으로 liveness를 확인합니다. Node가 응답하면 `True`, 응답하지 않으면 exception 대신 `False`를 반환합니다.

```python
# Kubernetes readiness probe / load-balancer health check
if client.ping():
    return {"status": "healthy"}

# Async health endpoint (예: FastAPI)
@app.get("/health")
async def health():
    ok = await async_client.ping()
    return {"status": "ok" if ok else "degraded"}
```

백그라운드 **tend** process는 cluster membership과 connection health를 자동으로 확인합니다. `tend_interval`의 기본값은 1,000 ms입니다. 즉시 상태를 확인해야 할 때는 `ping()`을 함께 사용하세요.

## Sync vs Async

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# Context manager (권장)
with aerospike.client(config).connect() as client:
    record = client.get(key)
# close() 자동 호출

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

**Async가 적합한 경우:** 동시성이 높은 web server, fan-out read, 여러 종류의 I/O를 함께 처리하는 workload.

**Sync가 적합한 경우:** script, batch job, 순차 pipeline.
