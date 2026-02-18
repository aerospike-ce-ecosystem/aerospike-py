---
title: Client
sidebar_label: Client (Sync & Async)
sidebar_position: 1
description: Client 및 AsyncClient 클래스 API 레퍼런스
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

aerospike-py는 동일한 기능을 가진 동기(`Client`)와 비동기(`AsyncClient`) API를 제공합니다.

## Creating a Client

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Context Manager

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

### `__enter__()` / `__exit__()`

```python
with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:
    client.put(key, bins)
# close()가 종료 시 자동으로 호출됩니다
```

  </TabItem>
  <TabItem value="async" label="Async Client">

### `async __aenter__()` / `async __aexit__()`

```python
async with AsyncClient({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
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
await client.connect()
await client.connect("admin", "admin")
```

  </TabItem>
</Tabs>

### `is_connected()`

클라이언트가 연결되어 있으면 `True`를 반환합니다. 두 클라이언트 모두에서 동기 메서드입니다.

```python
if client.is_connected():
    print("Connected")
```

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
nodes = await client.get_node_names()
```

  </TabItem>
</Tabs>

## CRUD Operations

### `put(key, bins, meta=None, policy=None)`

레코드를 작성합니다.

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | `tuple[str, str, str\|int\|bytes]` | `(namespace, set, pk)` |
| `bins` | `dict[str, Any]` | 빈 이름-값 쌍 |
| `meta` | [`WriteMeta`](types.md#writemeta) | 선택: `{"ttl": int, "gen": int}` |
| `policy` | [`WritePolicy`](types.md#writepolicy) | 선택: `{"key", "exists", "gen", "timeout", ...}` |

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

여러 레코드를 읽습니다. `BatchRecords`를 반환합니다.

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

## Query & Scan

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

### `query(namespace, set_name)`

Secondary Index 쿼리를 위한 `Query` 객체를 생성합니다. [Query & Scan API](query-scan.md)를 참조하세요.

```python
query = client.query("test", "demo")
```

### `scan(namespace, set_name)`

전체 네임스페이스/세트 스캔을 위한 `Scan` 객체를 생성합니다. [Query & Scan API](query-scan.md)를 참조하세요.

```python
scan = client.scan("test", "demo")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

### `async scan(namespace, set_name, policy=None)`

네임스페이스/세트의 모든 레코드를 스캔합니다. 결과 리스트를 직접 반환합니다.

```python
records = await client.scan("test", "demo")
for key, meta, bins in records:
    print(bins)
```

:::note

AsyncClient에는 `query()` 메서드가 없습니다. 서버사이드 필터링은 `scan()`과 [Expression Filters](../guides/expression-filters.md)를 조합하여 사용하세요.

:::

  </TabItem>
</Tabs>

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

## Concurrency Patterns (Async)

### `asyncio.gather`를 사용한 병렬 쓰기

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
await asyncio.gather(*tasks)
```

### 병렬 읽기

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.get(k) for k in keys]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 혼합 연산

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

## Admin Operations

### User Management

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

| 메서드 | 설명 |
|--------|-------------|
| `admin_create_user(username, password, roles)` | 사용자 생성 |
| `admin_drop_user(username)` | 사용자 삭제 |
| `admin_change_password(username, password)` | 비밀번호 변경 |
| `admin_grant_roles(username, roles)` | 역할 부여 |
| `admin_revoke_roles(username, roles)` | 역할 회수 |
| `admin_query_user(username)` | 사용자 정보 조회 |
| `admin_query_users()` | 전체 사용자 목록 |

  </TabItem>
  <TabItem value="async" label="Async Client">

| 메서드 | 설명 |
|--------|-------------|
| `async admin_create_user(username, password, roles)` | 사용자 생성 |
| `async admin_drop_user(username)` | 사용자 삭제 |
| `async admin_change_password(username, password)` | 비밀번호 변경 |
| `async admin_grant_roles(username, roles)` | 역할 부여 |
| `async admin_revoke_roles(username, roles)` | 역할 회수 |
| `async admin_query_user(username)` | 사용자 정보 조회 |
| `async admin_query_users()` | 전체 사용자 목록 |

  </TabItem>
</Tabs>

### Role Management

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

# 필터와 함께 Scan
scan = client.scan("test", "demo")
records = scan.results(policy={"filter_expression": expr})

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

# 필터와 함께 Scan
records = await client.scan("test", "demo", policy={"filter_expression": expr})

# 필터와 함께 Batch
ops = [{"op": aerospike.OPERATOR_READ, "bin": "age", "val": None}]
records = await client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

  </TabItem>
</Tabs>

:::tip

레코드가 필터 expression과 매칭되지 않으면 `FilteredOut`이 발생합니다.
자세한 문서는 [Expression 필터 가이드](../guides/expression-filters.md)를 참조하세요.

:::
