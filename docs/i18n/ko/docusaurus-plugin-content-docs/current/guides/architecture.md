---
sidebar_position: 1
title: Architecture
description: How aerospike-py works under the hood — layers, GIL handling, data flow, and batch operations.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Architecture

aerospike-py는 [PyO3](https://pyo3.rs)를 사용해 [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust)를 native Python extension으로 제공합니다. Python application은 type annotation을 갖춘 익숙한 API를 사용하고, Rust core가 Aerospike I/O를 처리합니다.

**주요 속성:**

- **GIL-free I/O** — 모든 database call 중에 GIL을 해제하므로 다른 Python thread와 coroutine이 동시에 실행될 수 있습니다.
- **Type-safe** — IDE autocompletion과 type checker를 지원하는 `.pyi` stub을 제공합니다.
- **Zero dependencies** — 기본 설치에는 외부 Python dependency가 없습니다. NumPy와 OpenTelemetry는 선택 사항입니다.

## Layers

```
┌─────────────────────────────────────────────┐
│  Your Python Application                    │
├─────────────────────────────────────────────┤
│  Python Wrapper Layer                       │
│  _client.py / _async_client.py              │
│  NamedTuple wrapping, error decoration      │
├─────────────────────────────────────────────┤
│  PyO3 Binding Layer                         │
│  client.rs / async_client.rs                │
│  GIL management, Python ↔ Rust conversion   │
├─────────────────────────────────────────────┤
│  Aerospike Rust Client                      │
│  aerospike-core crate (fully async)         │
│  Aerospike wire protocol, connection pool   │
├─────────────────────────────────────────────┤
│  Aerospike Server                           │
└─────────────────────────────────────────────┘
```

| Layer | 역할 |
|-------|------|
| **Python Wrapper** | Rust 로부터의 raw tuple 을 `Record`, `ExistsResult`, 기타 NamedTuple 로 변환하는 얇은 layer. context-manager 지원과 `@catch_unexpected` decorator 추가. |
| **PyO3 Binding** | Python 호출을 async Rust client 로 bridge 하는 `#[pyclass]` struct. GIL release/reacquire 와 Python object ↔ Rust type 변환 처리. |
| **Aerospike Rust Client** | `aerospike-core` crate — Aerospike binary wire protocol 을 TCP 위에서 말하는 완전 async client. Connection pooling, cluster discovery, partition map 관리. |
| **Aerospike Server** | Aerospike 데이터베이스 (Community 또는 Enterprise). |

## Sync vs Async

두 client는 같은 API를 제공합니다. 차이는 내부 Tokio runtime에서 I/O를 schedule하는 방식입니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
import aerospike_py

client = aerospike_py.client({"hosts": [("localhost", 3000)]}).connect()
client.put(("test", "demo", "user1"), {"name": "Alice"})
record = client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice"}
client.close()
```

각 호출은 GIL을 해제하고 `block_on()`을 통해 Tokio runtime에서 Rust future를 실행합니다. 결과를 반환할 때만 GIL을 다시 획득하므로 I/O를 기다리는 동안 다른 Python thread가 실행될 수 있습니다.

  </TabItem>
  <TabItem value="async" label="Async">

```python
import aerospike_py

client = aerospike_py.AsyncClient({"hosts": [("localhost", 3000)]})
await client.connect()
await client.put(("test", "demo", "user1"), {"name": "Alice"})
record = await client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice"}
await client.close()
```

각 호출이 Tokio future 로 backed 된 Python awaitable 을 반환합니다. I/O 동안 GIL 이 유지되지 않아, 동시 `await` 호출이 `asyncio.gather()` 또는 task group 으로 자연스럽게 overlap.

  </TabItem>
</Tabs>

### Performance 비교 (공식 C client 대비)

| Path | put | get | batch_read (NumPy) |
|------|-----|-----|--------------------|
| Sync (sequential) | ~1.1x 느림 | ~1.1x 느림 | — |
| Async (concurrent) | **2.1x 빠름** | **1.6x 빠름** | **3.4x 빠름** |

Sync path에서는 호출마다 `block_on()` 비용이 들어 약 10%의 차이가 납니다. Async path는 여러 I/O를 겹쳐 실행해 이 scheduling 비용을 피합니다.

## Data Flow

### Write path (`put`)

1. Python dict `{"name": "Alice"}` 가 Rust `Vec<Bin>` 으로 변환.
2. Key tuple `("test", "demo", "user1")` 이 Aerospike `Key` 로 (RIPEMD-160 digest 포함).
3. GIL을 해제합니다. Rust client가 bin을 Aerospike wire protocol로 직렬화해 TCP로 전송합니다.
4. Server 가 ack. GIL 재획득하고 `None` 을 Python 으로 반환.

### Read path (`get`)

1. GIL을 해제합니다. Rust client가 read request를 보내고 response를 받습니다.
2. Rust `Record` (bins + generation + TTL) 가 Python tuple `(key, meta, bins)` 로 변환.
3. Python wrapper layer 가 이를 `Record` NamedTuple 로 wrap:

```python
record = client.get(("test", "demo", "user1"))
record.bins          # {"name": "Alice"}
record.meta.gen      # 1 (generation counter)
record.meta.ttl      # 0 (expiration 까지 초)
record.key.user_key  # "user1"
```

### Type 변환

| Python | Aerospike | 비고 |
|--------|-----------|-------|
| `int` | Integer | 64-bit signed |
| `float` | Double | 64-bit IEEE 754 |
| `str` | String | UTF-8 |
| `bytes` | Blob | raw bytes |
| `list` | List | 중첩 타입 지원 |
| `dict` | Map | 중첩 타입 지원 |
| `bool` | Bool | |
| `None` | Nil | write 시 bin 제거 |

## Batch Operations

### batch_read

각 user key 를 그 bin 으로 매핑하는 `dict[UserKey, dict]` 반환. 성공한 read 만 포함 — missing 또는 failed key 는 dict 에 없음.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(1000)]
batch = client.batch_read(keys, bins=["name", "age"])

for user_key, bins in batch.items():
    print(user_key, bins["name"])

# 어떤 key 가 missing 인지 확인
requested = {k[2] for k in keys}
missing = requested - set(batch.keys())
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
batch = await client.batch_read(keys, bins=["name", "age"])
for user_key, bins in batch.items():
    print(user_key, bins["name"])
```

  </TabItem>
</Tabs>

처리량이 높은 pipeline에서는 NumPy dtype을 전달해 zero-copy columnar access를 지원하는 structured array를 받을 수 있습니다. 자세한 내용은 [NumPy Batch Read guide](./crud/numpy-batch.md)를 참고하세요.

```python
import numpy as np

dtype = np.dtype([("score", "f8"), ("count", "i4")])
result = client.batch_read(keys).to_numpy(dtype)
print(result.batch_records["score"].mean())  # columnar 접근
```

### batch_write

각 record는 `(key, bins)` tuple입니다. 세 번째 element에 TTL 같은 record별 metadata를 선택적으로 추가할 수 있습니다.

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 3600}),  # 1시간 후 만료
]
results = client.batch_write(records, policy={"ttl": 86400})  # default: 1일
```

**TTL 우선순위:** per-record `{"ttl": N}` > batch-level `policy={"ttl": N}` > namespace default.

**Retry:** 실패한 record (timeout, device overload, key busy) 는 exponential backoff 로 자동 재시도. elapsed time 이 `total_timeout` 에 근접하면 retry 조기 종료.

```python
results = client.batch_write(records, retry=3)
for br in results.batch_records:
    if br.result != 0:
        if br.in_doubt:
            print(f"Key {br.key} may have succeeded — verify before retrying")
        else:
            print(f"Key {br.key} failed (code={br.result})")
```

## Error Handling

Server error는 `AerospikeError`를 최상위로 하는 Python exception hierarchy에 매핑됩니다. 각 exception에는 원본 error message와 result code가 들어 있습니다.

```python
from aerospike_py.exception import RecordNotFound, AerospikeError

try:
    record = client.get(("test", "demo", "missing"))
except RecordNotFound:
    print("Record does not exist")
except AerospikeError as e:
    print(f"Unexpected error: {e}")
```

Batch operation은 개별 record가 실패해도 전체 batch에 exception을 발생시키지 않습니다. 각 `BatchRecord`의 `br.result`를 확인하세요. 전체 exception hierarchy와 batch error 처리 방법은 [Error Handling guide](./admin/error-handling.md)를 참고하세요.

## Observability

aerospike-py는 tracing, metrics, logging을 기본으로 지원합니다. 세 기능 모두 선택 사항이며, 비활성화하면 overhead가 거의 없습니다.

### OpenTelemetry Tracing

모든 데이터베이스 operation 이 `db.system.name`, `db.namespace`, `db.operation.name`, 기타 semantic attribute 를 가진 OTel span 을 emit. `aerospike-py[otel]` 설치 후 초기화:

```python
from aerospike_py import init_tracing, shutdown_tracing

init_tracing()   # exporter 설정에 OTEL_* env var 사용
# ... client 사용 ...
shutdown_tracing()
```

### Prometheus Metrics

Operation duration 이 histogram 으로 기록됨. 내장 HTTP server 로 노출하거나 programmatic 으로 read:

```python
from aerospike_py import start_metrics_server, get_metrics

start_metrics_server(9090)  # GET http://localhost:9090/metrics
print(get_metrics())        # text format
```

### Logging

Rust 내부 log 가 Python `logging` module 로 bridge:

```python
from aerospike_py import set_log_level, LOG_LEVEL_DEBUG
set_log_level(LOG_LEVEL_DEBUG)
```

자세한 설정은 [Observability guides](../integrations/observability/tracing.md) 참조.

## 디자인 원칙

1. **Rust-first** — 핵심 로직은 Rust 에. Python 은 ergonomic 한 얇은 wrapper (NamedTuple, context manager, factory function).
2. **Zero Python dependencies** — base install 은 외부 Python dep 없음. NumPy 와 OpenTelemetry 는 선택적 extras (`pip install aerospike-py[numpy,otel]`).
3. **Type-safe** — `.pyi` stub 이 완전한 IDE 지원 제공. 모든 반환 타입은 raw dict 나 tuple 이 아니라 named field 를 가진 NamedTuple.
4. **API 호환성** — Method 이름, constant, exception 이 가능한 한 [공식 Aerospike Python client](https://github.com/aerospike/aerospike-client-python) 와 정렬.
5. **GIL-free I/O** — 모든 데이터베이스 operation 이 네트워크 호출 동안 GIL release. Sync 는 `py.detach()` + Tokio `block_on()`, async 는 `future_into_py()` 사용. Runtime worker 설정은 [Performance Tuning](./config/performance-tuning.md) 참조.
