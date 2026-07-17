---
title: Client API 레퍼런스
sidebar_label: Client (동기·비동기)
sidebar_position: 1
description: Client 및 AsyncClient 클래스 API 레퍼런스
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

aerospike-py는 동일한 기능을 가진 동기(`Client`)와 비동기(`AsyncClient`) API를 제공합니다.

## Factory 함수

### `client(config)`

새 동기 `Client` 인스턴스를 생성합니다. 생성 직후에는 아직 클러스터에 연결되지 않습니다.

| 파라미터 | 설명 |
|-----------|------|
| `config` | [`ClientConfig`](types.md#clientconfig) dict. `(host, port)` 튜플 리스트를 값으로 갖는 `"hosts"` 키가 필요합니다. |

**반환값:** 연결되지 않은 새 `Client` 인스턴스

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()
```

### `async_client(config)`

새 비동기 `AsyncClient` 인스턴스를 생성합니다. 생성 후 `await connect()`를 호출해야 합니다.

| 파라미터 | 설명 |
|-----------|------|
| `config` | [`ClientConfig`](types.md#clientconfig) dict. `(host, port)` 튜플 리스트를 값으로 갖는 `"hosts"` 키가 필요합니다. |

**반환값:** 연결되지 않은 새 `AsyncClient` 인스턴스

```python
import aerospike_py as aerospike

client = aerospike.async_client({
    "hosts": [("127.0.0.1", 3000)],
})
await client.connect()
```

## Context Manager

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

#### `__enter__()` / `__exit__()`

```python
import aerospike_py

with aerospike_py.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect() as client:
    client.put(key, bins)
# close()가 종료 시 자동으로 호출됩니다
```

  </TabItem>
  <TabItem value="async" label="Async Client">

#### `async __aenter__()` / `async __aexit__()`

```python
import aerospike_py

async with aerospike_py.async_client({
    "hosts": [("127.0.0.1", 3000)],
}) as client:
    await client.connect()
    await client.put(key, bins)
# close()가 자동으로 호출됩니다
```

  </TabItem>
</Tabs>

## Connection

### `connect(username=None, password=None)`

Aerospike 클러스터에 연결합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

메서드 체이닝을 위해 `self`를 반환합니다.

```python
client = aerospike.client(config).connect()
# 인증 포함
client = aerospike.client(config).connect("admin", "admin")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
# 인증 없이 연결
client = await aerospike.async_client(config).connect()

# 인증 정보로 연결
client = await aerospike.async_client(config).connect("admin", "admin")
```

  </TabItem>
</Tabs>

### `is_connected()`

클라이언트가 연결되어 있으면 `True`를 반환합니다. 두 클라이언트 모두에서 동기 메서드입니다.

```python
if client.is_connected():
    print("Connected")
```

### `ping()`

클러스터가 실제로 응답하는지 확인하는 가벼운 health check입니다. 임의의 노드에 `info("build")`를 보내므로, 로컬 연결 상태만 확인하는 `is_connected()`와 달리 실제 network round-trip이 발생합니다.

Kubernetes readiness probe, load balancer health check, connection pool 검증에 사용할 수 있습니다.

**반환값:** 클러스터 노드가 응답하면 `True`, 연결되지 않았거나 응답하지 않으면 `False`

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
if client.ping():
    print("Cluster is reachable")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
if await client.ping():
    print("Cluster is reachable")
```

  </TabItem>
</Tabs>

### `close()`

클러스터와의 연결을 종료합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.close()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.close()
```

  </TabItem>
</Tabs>

### `get_node_names()`

클러스터 노드 이름 목록을 반환합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
nodes = client.get_node_names()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
nodes = client.get_node_names()  # sync since alpha.10 — no await needed
```

  </TabItem>
</Tabs>

## Info 명령

### `info_all(command, policy=None)`

모든 클러스터 노드에 Info 명령을 보냅니다.

| 파라미터 | 설명 |
|-----------|------|
| `command` | Info 명령 문자열. 예: `"namespaces"` |
| `policy` | 선택적 [`AdminPolicy`](types.md#adminpolicy) dict |

**반환값:** `InfoNodeResult(node_name, error_code, response)` 튜플 리스트

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
results = client.info_all("namespaces")
for node, error_code, response in results:
    print(f"{node} (error={error_code}): {response}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
results = await client.info_all("namespaces")
for node, error_code, response in results:
    print(f"{node} (error={error_code}): {response}")
```

  </TabItem>
</Tabs>

### `info_random_node(command, policy=None)`

임의의 클러스터 노드 하나에 Info 명령을 보냅니다.

| 파라미터 | 설명 |
|-----------|------|
| `command` | Info 명령 문자열 |
| `policy` | 선택적 [`AdminPolicy`](types.md#adminpolicy) dict |

**반환값:** 노드가 반환한 Info 응답 문자열

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
build = client.info_random_node("build")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
build = await client.info_random_node("build")
```

  </TabItem>
</Tabs>

## CRUD 작업

### `put(key, bins, meta=None, policy=None)`

레코드를 작성합니다.

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | `tuple[str, str, str\|int\|bytes]` | `(namespace, set, pk)` |
| `bins` | `dict[str, Any]` | 빈 이름-값 쌍 |
| `meta` | [`WriteMeta`](types.md#writemeta) | 선택: `{"ttl": int, "gen": int}` |
| `policy` | [`WritePolicy`](types.md#writepolicy) | 선택: `{"key", "exists", "gen", "socket_timeout", "total_timeout", ...}` |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"x": 1}, meta={"ttl": 300})
client.put(key, {"x": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
key = ("test", "demo", "user1")
await client.put(key, {"name": "Alice", "age": 30})
await client.put(key, {"x": 1}, meta={"ttl": 300})
await client.put(key, {"x": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
</Tabs>

### `get(key, policy=None)`

레코드를 읽습니다. [`Record`](types.md#record) NamedTuple `(key, meta, bins)`를 반환합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
key, meta, bins = client.get(("test", "demo", "user1"))
# meta.gen == 1, meta.ttl == 2591998
# bins = {"name": "Alice", "age": 30}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
key, meta, bins = await client.get(("test", "demo", "user1"))
```

  </TabItem>
</Tabs>

:::note

레코드가 존재하지 않으면 `RecordNotFound`가 발생합니다.

:::

### `select(key, bins, policy=None)`

레코드에서 특정 빈만 읽습니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta, bins = client.select(key, ["name"])
# bins = {"name": "Alice"}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta, bins = await client.select(key, ["name"])
```

  </TabItem>
</Tabs>

### `exists(key, policy=None)`

레코드 존재 여부를 확인합니다. [`ExistsResult`](types.md#existsresult) NamedTuple `(key, meta)`를 반환하며, 레코드가 없으면 `meta`가 `None`입니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta = client.exists(key)
if meta is not None:
    print(f"Found, gen={meta.gen}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta = await client.exists(key)
if meta is not None:
    print(f"Found, gen={meta.gen}")
```

  </TabItem>
</Tabs>

### `remove(key, meta=None, policy=None)`

레코드를 삭제합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove(key)
# 세대 검사 포함
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove(key)
await client.remove(key, meta={"gen": 3}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
</Tabs>

### `touch(key, val=0, meta=None, policy=None)`

레코드의 TTL을 리셋합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.touch(key, val=300)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.touch(key, val=300)
```

  </TabItem>
</Tabs>

## String / Numeric Operations

### `append(key, bin, val, meta=None, policy=None)`

빈에 문자열을 추가합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.append(key, "name", "_suffix")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.append(key, "name", "_suffix")
```

  </TabItem>
</Tabs>

### `prepend(key, bin, val, meta=None, policy=None)`

빈 앞에 문자열을 삽입합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.prepend(key, "name", "prefix_")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.prepend(key, "name", "prefix_")
```

  </TabItem>
</Tabs>

### `increment(key, bin, offset, meta=None, policy=None)`

정수 또는 실수 빈 값을 증가시킵니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.increment(key, "age", 1)
client.increment(key, "score", 0.5)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.increment(key, "age", 1)
await client.increment(key, "score", 0.5)
```

  </TabItem>
</Tabs>

### `remove_bin(key, bin_names, meta=None, policy=None)`

레코드에서 특정 빈을 제거합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove_bin(key, ["temp_bin", "debug_bin"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove_bin(key, ["temp_bin", "debug_bin"])
```

  </TabItem>
</Tabs>

## Multi-Operation

### `operate(key, ops, meta=None, policy=None)`

단일 레코드에 여러 연산을 원자적으로 실행합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = client.operate(key, ops)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = await client.operate(key, ops)
```

  </TabItem>
</Tabs>

### `operate_ordered(key, ops, meta=None, policy=None)`

`operate`와 동일하지만 결과를 [`OperateOrderedResult`](types.md#operateorderedresult) NamedTuple의 `ordered_bins` 필드에 `BinTuple(name, value)` 리스트로 반환합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta, results = client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta, results = await client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

  </TabItem>
</Tabs>

## Batch Operations

### `batch_read(keys, bins=None, policy=None)`

여러 레코드를 읽습니다. `LazyBatchRecords` 핸들을 반환하며, `.to_dict()` / `.to_numpy(dtype)` 또는 dict-style Mapping 접근으로 materialise 합니다.

- `bins=None` - 모든 bin 읽기
- `bins=["a", "b"]` - 특정 bin만 읽기
- `bins=[]` - 존재 여부만 확인

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# 모든 bin 읽기
batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(bins)

# 특정 bin만 읽기
batch = client.batch_read(keys, bins=["name", "age"])

# 존재 여부만 확인
batch = client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# 모든 bin 읽기
batch = await client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(bins)

# 특정 bin만 읽기
batch = await client.batch_read(keys, bins=["name", "age"])

# 존재 여부만 확인
batch = await client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
</Tabs>

### `batch_write(records, policy=None, retry=0)`

레코드마다 서로 다른 bin을 한 번의 Batch 호출로 씁니다. 각 항목은 `(key, bins)` 또는 `(key, bins, meta)` 튜플입니다.

- `key`: `(namespace, set_name, primary_key)` 튜플
- `bins`: bin 이름과 값으로 구성된 dict
- `meta`: 선택적 [`WriteMeta`](types.md#writemeta) dict. 예: `{"ttl": 300}`

`ttl`, `key`, `exists`, `gen`, `commit_level`, `durable_delete`는 Batch `policy`와 레코드별 `meta`에 모두 지정할 수 있습니다. 같은 필드가 양쪽에 있으면 **레코드별 `meta`가 우선합니다**.

| 파라미터 | 설명 |
|-----------|------|
| `records` | `(key, bins)` 또는 `(key, bins, meta)` 튜플 리스트 |
| `policy` | 선택적 [`BatchPolicy`](types.md#batchpolicy) dict. Batch 전송 설정과 쓰기 기본값을 함께 지정합니다. |
| `retry` | 일시적 오류가 발생한 레코드의 최대 재시도 횟수. 기본값은 `0`이며 자동 재시도하지 않습니다. |

**반환값:** 레코드별 결과를 `batch_records`에 담은 [`BatchWriteResult`](types.md#batchwriteresult). 각 `BatchRecord.result`가 `0`인지 확인하세요.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py

records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]

# 모든 레코드에 적용할 Batch 기본값
result = client.batch_write(
    records,
    policy={
        "ttl": 3_600,
        "key": aerospike_py.POLICY_KEY_SEND,
    },
    retry=3,
)

# 레코드별 meta는 Batch 기본값보다 우선합니다.
result = client.batch_write([
    (("test", "demo", "user1"), {"name": "Alice"}, {"ttl": 60}),
    (("test", "demo", "user2"), {"name": "Bob"}),
])

for batch_record in result.batch_records:
    if batch_record.result != 0:
        print(batch_record.key, batch_record.result, batch_record.in_doubt)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]
result = await client.batch_write(records, policy={"ttl": 3_600}, retry=3)

for batch_record in result.batch_records:
    if batch_record.result != 0:
        print(batch_record.key, batch_record.result, batch_record.in_doubt)
```

  </TabItem>
</Tabs>

:::note

재시도 도중 전송 오류가 발생하면 재시도를 중단하고 부분 결과를 반환할 수 있습니다. `batch_write` 결과를 성공으로 간주하기 전에 모든 `BatchRecord.result`를 확인하세요.

:::

### `batch_write_numpy(data, namespace, set_name, _dtype, key_field='_key', policy=None, retry=0)`

NumPy 구조화 배열의 각 행을 별도 Record로 씁니다. `key_field`로 지정한 field가 Record key가 되고, 이름이 밑줄로 시작하지 않는 나머지 field가 bin이 됩니다.

| 파라미터 | 설명 |
|-----------|------|
| `data` | Record 데이터가 들어 있는 NumPy 구조화 배열 |
| `namespace` | 대상 namespace |
| `set_name` | 대상 set |
| `_dtype` | 배열 layout을 설명하는 NumPy dtype |
| `key_field` | user key로 사용할 dtype field 이름. 기본값은 `"_key"` |
| `policy` | 선택적 [`BatchPolicy`](types.md#batchpolicy) dict |
| `retry` | 일시적 오류가 발생한 Record의 최대 재시도 횟수. 기본값은 `0` |

**반환값:** 레코드별 결과를 `batch_records`에 담은 [`BatchWriteResult`](types.md#batchwriteresult)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np

dtype = np.dtype([
    ("_key", "i4"),
    ("score", "f8"),
    ("count", "i4"),
])
data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)

result = client.batch_write_numpy(
    data,
    "test",
    "demo",
    dtype,
    retry=3,
)
for batch_record in result.batch_records:
    if batch_record.result != 0:
        print(batch_record.key, batch_record.result)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import numpy as np

dtype = np.dtype([
    ("_key", "i4"),
    ("score", "f8"),
    ("count", "i4"),
])
data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)

result = await client.batch_write_numpy(
    data,
    "test",
    "demo",
    dtype,
    retry=3,
)
for batch_record in result.batch_records:
    if batch_record.result != 0:
        print(batch_record.key, batch_record.result)
```

  </TabItem>
</Tabs>

### `batch_operate(keys, ops, policy=None)`

여러 레코드에 연산을 실행합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = await client.batch_operate(keys, ops)
```

  </TabItem>
</Tabs>

### `batch_remove(keys, policy=None)`

여러 레코드를 삭제합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
results = client.batch_remove(keys)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.batch_remove(keys)
```

  </TabItem>
</Tabs>

### `batch_apply(keys, module, function, args=None, policy=None)`

등록된 Lua UDF를 여러 레코드에 한 번의 배치 호출로 실행합니다. [`apply()`](#applykey-module-function-argsnone-policynone)와 동일한 와이어 형태이지만, 라운드 트립 한 번으로 키들에 분산 처리합니다.

| 파라미터 | 설명 |
|-----------|-------------|
| `keys` | 일반 ``Key`` 튜플 리스트, 또는 일반 키와 ``(key, meta)`` 페어가 섞인 리스트. ``meta``는 [`BatchUDFMeta`](types.md#batchudfmeta) 평면 dict로, 특정 레코드에 대해 UDF 호출 형태(``module``/``function``/``args``)와 정책 필드(``ttl``/``commit_level``/``key``/``durable_delete``)를 오버라이드할 수 있습니다. |
| `module` | 레코드 단위 ``module`` 오버라이드가 없을 때 사용할 기본 UDF 모듈명. |
| `function` | 기본 UDF 함수명. |
| `args` | 선택적 기본 인자 리스트. ``BatchUDFMeta``의 ``args``(빈 리스트 ``[]`` 포함)가 이 기본값을 오버라이드합니다. |
| `policy` | 선택적 정책 dict. 전송-레벨 [`BatchPolicy`](types.md#batchpolicy)와 배치-레벨 [`BatchUDFPolicy`](types.md#batchudfpolicy) 기본값(``commit_level``, ``ttl``, ``key``, ``durable_delete``, ``filter_expression``)을 합칠 수 있습니다. |

**반환값:** ``BatchWriteResult``. 레코드별 결과 코드는 ``batch_records: list[BatchRecord]``에 담깁니다. UDF 반환값은 호출이 성공한 경우 레코드의 ``Record.bins`` 맵에 Lua 컨벤션인 ``"SUCCESS"`` 키로 저장됩니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# 모든 키에 동일한 UDF 적용
keys = [("test", "demo", f"u_{i}") for i in range(10)]
results = client.batch_apply(keys, "my_udf", "increment_counter", [1])

for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        # UDF 반환값은 "SUCCESS" 빈에 저장됨
        print(br.record.bins.get("SUCCESS"))

# 레코드별 오버라이드: 한 레코드만 다른 args + 긴 TTL
results = client.batch_apply(
    [
        ("test", "demo", "u_1"),  # 기본 args 사용
        (("test", "demo", "u_2"), {"args": [5], "ttl": 3600}),
    ],
    "my_udf", "increment_counter", args=[1],
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"u_{i}") for i in range(10)]
results = await client.batch_apply(keys, "my_udf", "increment_counter", [1])

for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins.get("SUCCESS"))

# 레코드별 오버라이드: 한 레코드만 다른 args + 긴 TTL
results = await client.batch_apply(
    [
        ("test", "demo", "u_1"),
        (("test", "demo", "u_2"), {"args": [5], "ttl": 3600}),
    ],
    "my_udf", "increment_counter", args=[1],
)
```

  </TabItem>
</Tabs>

## Query

### `query(namespace, set_name)`

Secondary Index 쿼리를 위한 `Query` 객체를 생성합니다. [Query API](query-scan.md)를 참조하세요.

```python
query = client.query("test", "demo")
```

## Index Management

### `index_integer_create(namespace, set_name, bin_name, index_name, policy=None)`

숫자 Secondary Index를 생성합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_integer_create("test", "demo", "age", "age_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_integer_create("test", "demo", "age", "age_idx")
```

  </TabItem>
</Tabs>

### `index_string_create(namespace, set_name, bin_name, index_name, policy=None)`

문자열 Secondary Index를 생성합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_string_create("test", "demo", "name", "name_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_string_create("test", "demo", "name", "name_idx")
```

  </TabItem>
</Tabs>

### `index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy=None)`

지리공간 Secondary Index를 생성합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

  </TabItem>
</Tabs>

### `index_remove(namespace, index_name, policy=None)`

Secondary Index를 제거합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_remove("test", "age_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_remove("test", "age_idx")
```

  </TabItem>
</Tabs>

## Truncate

### `truncate(namespace, set_name, nanos=0, policy=None)`

네임스페이스/세트의 모든 레코드를 제거합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.truncate("test", "demo")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.truncate("test", "demo")
```

  </TabItem>
</Tabs>

## UDF

### `udf_put(filename, udf_type=0, policy=None)`

Lua UDF 모듈을 등록합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.udf_put("my_udf.lua")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.udf_put("my_udf.lua")
```

  </TabItem>
</Tabs>

### `udf_remove(module, policy=None)`

등록된 UDF 모듈을 제거합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.udf_remove("my_udf")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.udf_remove("my_udf")
```

  </TabItem>
</Tabs>

### `apply(key, module, function, args=None, policy=None)`

레코드에 UDF를 실행합니다.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
result = await client.apply(key, "my_udf", "my_function", [1, "hello"])
```

  </TabItem>
</Tabs>

## 비동기 동시성 패턴

#### `asyncio.gather`를 사용한 병렬 쓰기

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
await asyncio.gather(*tasks)
```

#### 병렬 읽기

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.get(k) for k in keys]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

#### 혼합 연산

```python
async def process_user(client, user_id):
    key = ("test", "users", user_id)
    _, _, bins = await client.get(key)
    bins["visits"] = bins.get("visits", 0) + 1
    await client.put(key, bins)
    return bins

results = await asyncio.gather(*[
    process_user(client, f"user_{i}")
    for i in range(10)
])
```

## 사용자 관리

다음 메서드는 보안이 활성화된 Aerospike 클러스터의 사용자를 관리합니다. `AsyncClient`에서는 각 호출 앞에 `await`를 붙입니다.

### `admin_create_user(username, password, roles, policy=None)`

지정한 비밀번호와 역할로 사용자를 생성합니다.

### `admin_drop_user(username, policy=None)`

사용자를 삭제합니다.

### `admin_change_password(username, password, policy=None)`

사용자의 비밀번호를 변경합니다.

### `admin_grant_roles(username, roles, policy=None)`

사용자에게 역할을 부여합니다.

### `admin_revoke_roles(username, roles, policy=None)`

사용자에게서 역할을 회수합니다.

### `admin_query_user_info(username, policy=None)`

한 사용자의 정보를 반환합니다.

### `admin_query_users_info(policy=None)`

모든 사용자 정보를 반환합니다.

#### 사용자 관리 요약

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

| 메서드 | 설명 |
|--------|-------------|
| `admin_create_user(username, password, roles)` | 사용자 생성 |
| `admin_drop_user(username)` | 사용자 삭제 |
| `admin_change_password(username, password)` | 비밀번호 변경 |
| `admin_grant_roles(username, roles)` | 역할 부여 |
| `admin_revoke_roles(username, roles)` | 역할 회수 |
| `admin_query_user_info(username)` | 사용자 정보 조회 |
| `admin_query_users_info()` | 전체 사용자 목록 |

  </TabItem>
  <TabItem value="async" label="Async Client">

| 메서드 | 설명 |
|--------|-------------|
| `async admin_create_user(username, password, roles)` | 사용자 생성 |
| `async admin_drop_user(username)` | 사용자 삭제 |
| `async admin_change_password(username, password)` | 비밀번호 변경 |
| `async admin_grant_roles(username, roles)` | 역할 부여 |
| `async admin_revoke_roles(username, roles)` | 역할 회수 |
| `async admin_query_user_info(username)` | 사용자 정보 조회 |
| `async admin_query_users_info()` | 전체 사용자 목록 |

  </TabItem>
</Tabs>

## 역할 관리

역할과 privilege, network allowlist 및 quota를 관리합니다. `AsyncClient`에서는 각 호출 앞에 `await`를 붙입니다.

### `admin_create_role(role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0)`

privilege와 선택적 접근 제한을 포함한 역할을 생성합니다.

### `admin_drop_role(role, policy=None)`

역할을 삭제합니다.

### `admin_grant_privileges(role, privileges, policy=None)`

역할에 privilege를 부여합니다.

### `admin_revoke_privileges(role, privileges, policy=None)`

역할에서 privilege를 회수합니다.

### `admin_query_role(role, policy=None)`

한 역할의 정보를 반환합니다.

### `admin_query_roles(policy=None)`

모든 역할 정보를 반환합니다.

### `admin_set_whitelist(role, whitelist, policy=None)`

역할의 network allowlist를 설정합니다.

### `admin_set_quotas(role, read_quota=0, write_quota=0, policy=None)`

역할의 읽기 및 쓰기 quota를 설정합니다.

#### 역할 관리 요약

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

| 메서드 | 설명 |
|--------|-------------|
| `admin_create_role(role, privileges, ...)` | 역할 생성 |
| `admin_drop_role(role)` | 역할 삭제 |
| `admin_grant_privileges(role, privileges)` | 권한 부여 |
| `admin_revoke_privileges(role, privileges)` | 권한 회수 |
| `admin_query_role(role)` | 역할 정보 조회 |
| `admin_query_roles()` | 전체 역할 목록 |
| `admin_set_whitelist(role, whitelist)` | IP 화이트리스트 설정 |
| `admin_set_quotas(role, read_quota, write_quota)` | 쿼터 설정 |

```python
# 사용자 생성
client.admin_create_user("new_user", "password", ["read-write"])

# 권한이 포함된 역할 생성
client.admin_create_role("custom_role", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

| 메서드 | 설명 |
|--------|-------------|
| `async admin_create_role(role, privileges, ...)` | 역할 생성 |
| `async admin_drop_role(role)` | 역할 삭제 |
| `async admin_grant_privileges(role, privileges)` | 권한 부여 |
| `async admin_revoke_privileges(role, privileges)` | 권한 회수 |
| `async admin_query_role(role)` | 역할 정보 조회 |
| `async admin_query_roles()` | 전체 역할 목록 |
| `async admin_set_whitelist(role, whitelist)` | IP 화이트리스트 설정 |
| `async admin_set_quotas(role, read_quota, write_quota)` | 쿼터 설정 |

```python
# 사용자 생성
await client.admin_create_user("new_user", "password", ["read-write"])

# 역할 부여
await client.admin_grant_roles("new_user", ["sys-admin"])

# 권한이 포함된 역할 생성
await client.admin_create_role("custom_role", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
])
```

  </TabItem>
</Tabs>

## Query 및 AsyncQuery 객체

`Client.query(namespace, set_name)` 또는 `AsyncClient.query(namespace, set_name)`가 반환하는 Secondary Index Query 객체입니다. `where()`로 predicate를 지정하고, `select()`로 반환할 bin을 선택한 뒤 `results()` 또는 `foreach()`로 실행합니다.

<Tabs>
  <TabItem value="query" label="Query" default>

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()
```

  </TabItem>
  <TabItem value="async-query" label="AsyncQuery">

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = await query.results()
```

  </TabItem>
</Tabs>

### `select(*bins)`

Query 결과에 포함할 bin을 선택합니다.

| 파라미터 | 설명 |
|-----------|------|
| `*bins` | 결과에 포함할 bin 이름 |

```python
query = client.query("test", "demo")
query.select("name", "age")
```

### `where(predicate)`

Query에 predicate 필터를 지정합니다. 필터 대상 bin에는 일치하는 Secondary Index가 필요합니다.

| 파라미터 | 설명 |
|-----------|------|
| `predicate` | `aerospike_py.predicates` helper로 만든 predicate 튜플 |

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.where(predicates.equals("name", "Alice"))
```

### `results(policy=None)`

Query를 실행하고 일치하는 모든 Record를 반환합니다.

| 파라미터 | 설명 |
|-----------|------|
| `policy` | 선택적 [`QueryPolicy`](types.md#querypolicy) dict |

**반환값:** `Record` NamedTuple 리스트

<Tabs>
  <TabItem value="sync" label="Query" default>

```python
records = query.results()
for record in records:
    print(record.bins)
```

  </TabItem>
  <TabItem value="async" label="AsyncQuery">

```python
records = await query.results()
for record in records:
    print(record.bins)
```

  </TabItem>
</Tabs>

### `foreach(callback, policy=None)`

Query를 실행해 각 Record마다 callback을 호출합니다. callback이 `False`를 반환하면 순회를 일찍 종료합니다.

| 파라미터 | 설명 |
|-----------|------|
| `callback` | 각 Record를 받는 함수. `False`를 반환하면 중단합니다. |
| `policy` | 선택적 [`QueryPolicy`](types.md#querypolicy) dict |

<Tabs>
  <TabItem value="sync" label="Query" default>

```python
def process(record):
    print(record.bins)

query.foreach(process)
```

  </TabItem>
  <TabItem value="async" label="AsyncQuery">

```python
def process(record):
    print(record.bins)

await query.foreach(process)
```

  </TabItem>
</Tabs>

## Partition Filter helper

### `partition_filter_all()`

4096개 partition 전체를 포함하는 `PartitionFilter`를 만듭니다. policy에서 `partition_filter`를 생략한 것과 같습니다.

```python
import aerospike_py

partition_filter = aerospike_py.partition_filter_all()
```

### `partition_filter_by_id(partition_id)`

partition 하나만 대상으로 하는 `PartitionFilter`를 만듭니다.

| 파라미터 | 설명 |
|-----------|------|
| `partition_id` | `0` 이상 `4095` 이하의 partition index |

유효 범위를 벗어나면 `ValueError`가 발생합니다.

```python
partition_filter = aerospike_py.partition_filter_by_id(42)
```

### `partition_filter_by_range(begin, count)`

`begin`부터 `count`개 partition을 대상으로 하는 `PartitionFilter`를 만듭니다.

| 파라미터 | 설명 |
|-----------|------|
| `begin` | 첫 partition. `0` 이상 `4095` 이하 |
| `count` | partition 수. `begin + count`는 `4096` 이하여야 하며 `0`도 허용됩니다. |

범위가 4096을 넘으면 `ValueError`가 발생합니다.

```python
partition_filter = aerospike_py.partition_filter_by_range(0, 512)
```

## 로깅

### `set_log_level(level)`

`aerospike_py`의 Rust 내부 및 Python 측 log level을 함께 설정합니다.

| 파라미터 | 설명 |
|-----------|------|
| `level` | `LOG_LEVEL_OFF`, `LOG_LEVEL_ERROR`, `LOG_LEVEL_WARN`, `LOG_LEVEL_INFO`, `LOG_LEVEL_DEBUG`, `LOG_LEVEL_TRACE` 중 하나 |

```python
import aerospike_py

aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

### `dropped_log_count()`

Rust logging bridge가 Python GIL을 확보하지 못해 버린 log message 수를 반환합니다. interpreter 종료 중에도 WARN 및 ERROR message는 fallback으로 stderr에 출력됩니다.

**반환값:** process 시작 이후 버려진 message 수

```python
dropped = aerospike_py.dropped_log_count()
```

## 메트릭

### `get_metrics()`

수집한 메트릭을 Prometheus exposition format 문자열로 반환합니다.

```python
import aerospike_py

print(aerospike_py.get_metrics())
```

### `set_metrics_enabled(enabled)`

Prometheus 메트릭 수집을 켜거나 끕니다. 성능 측정 시 메트릭 오버헤드를 제외하려면 일시적으로 비활성화할 수 있습니다.

| 파라미터 | 설명 |
|-----------|------|
| `enabled` | 활성화하려면 `True`, 비활성화하려면 `False`. 기본 상태는 활성화입니다. |

```python
aerospike_py.set_metrics_enabled(False)
# benchmark 실행
aerospike_py.set_metrics_enabled(True)
```

### `is_metrics_enabled()`

Prometheus 메트릭 수집이 활성화되어 있는지 반환합니다.

```python
if aerospike_py.is_metrics_enabled():
    print(aerospike_py.get_metrics())
```

### `set_internal_stage_metrics_enabled(enabled)`

내부 단계 프로파일링 메트릭을 켜거나 끕니다. 이 설정은 `batch_read` 각 단계의 시간을 기록하는 `db_client_internal_stage_seconds` histogram을 제어합니다. 기본값은 비활성화이며, process 시작 시 `AEROSPIKE_PY_INTERNAL_METRICS=1`로 활성화할 수도 있습니다.

| 파라미터 | 설명 |
|-----------|------|
| `enabled` | 활성화하려면 `True`, 비활성화하려면 `False` |

```python
aerospike_py.set_internal_stage_metrics_enabled(True)
```

### `is_internal_stage_metrics_enabled()`

내부 단계 프로파일링 메트릭의 활성화 여부를 반환합니다.

```python
enabled = aerospike_py.is_internal_stage_metrics_enabled()
```

### `internal_stage_profiling()`

특정 코드 블록에서만 내부 단계 프로파일링을 활성화하는 Context Manager입니다. 블록을 나가면 이전 상태로 복원합니다.

```python
with aerospike_py.internal_stage_profiling():
    lazy_records = await client.batch_read(keys)
```

### `start_metrics_server(port=9464)`

Prometheus가 수집할 `/metrics` endpoint를 제공하는 background HTTP server를 시작합니다.

| 파라미터 | 설명 |
|-----------|------|
| `port` | listen할 TCP port. 기본값은 `9464` |

```python
aerospike_py.start_metrics_server(port=9464)
```

### `stop_metrics_server()`

background 메트릭 HTTP server를 중지합니다.

```python
aerospike_py.stop_metrics_server()
```

## Tracing

### `init_tracing()`

OpenTelemetry tracing을 초기화합니다. 설정은 표준 `OTEL_*` 환경 변수를 읽습니다.

```python
import aerospike_py

aerospike_py.init_tracing()
```

### `shutdown_tracing()`

대기 중인 span을 flush하고 tracer provider를 종료합니다. 모든 span이 전송되도록 process 종료 전에 호출하세요.

```python
aerospike_py.shutdown_tracing()
```

## Expression Filters

`policy` 파라미터를 받는 모든 읽기/쓰기/배치 작업은 서버사이드 필터링을 위한 `filter_expression` 키를 지원합니다 (Server 5.2+ 필요):

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import exp

expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# 필터와 함께 Get
_, _, bins = client.get(key, policy={"filter_expression": expr})

# 필터와 함께 Put (필터가 매칭될 때만 업데이트)
expr = exp.eq(exp.string_bin("status"), exp.string_val("active"))
client.put(key, {"visits": 1}, policy={"filter_expression": expr})

# 필터와 함께 Query
query = client.query("test", "demo")
records = query.results(policy={"filter_expression": expr})

# 필터와 함께 Batch
ops = [{"op": aerospike.OPERATOR_READ, "bin": "status", "val": None}]
records = client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import exp

expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# 필터와 함께 Get
_, _, bins = await client.get(key, policy={"filter_expression": expr})

# 필터와 함께 Batch
ops = [{"op": aerospike.OPERATOR_READ, "bin": "age", "val": None}]
records = await client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

  </TabItem>
</Tabs>

:::tip

레코드가 필터 expression과 매칭되지 않으면 `FilteredOut`이 발생합니다.
자세한 문서는 [Expression 필터 가이드](../guides/query-scan/expression-filters.md)를 참조하세요.

:::
