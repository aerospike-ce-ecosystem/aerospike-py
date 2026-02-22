---
title: Write Operations
sidebar_label: Write
sidebar_position: 2
slug: /guides/write
description: put, update, delete, operate, batch operate 및 낙관적 잠금 가이드
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Write (Put)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

key = ("test", "demo", "user1")

# 단순 쓰기
client.put(key, {"name": "Alice", "age": 30})

# 지원되는 bin 값 타입
client.put(key, {
    "str_bin": "hello",
    "int_bin": 42,
    "float_bin": 3.14,
    "bytes_bin": b"\x00\x01\x02",
    "list_bin": [1, 2, 3],
    "map_bin": {"nested": "dict"},
    "bool_bin": True,
    "none_bin": None,
})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
import aerospike_py as aerospike
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()

    key = ("test", "demo", "user1")

    # 단순 쓰기
    await client.put(key, {"name": "Alice", "age": 30})

    # 지원되는 bin 값 타입
    await client.put(key, {
        "str_bin": "hello",
        "int_bin": 42,
        "float_bin": 3.14,
        "bytes_bin": b"\x00\x01\x02",
        "list_bin": [1, 2, 3],
        "map_bin": {"nested": "dict"},
        "bool_bin": True,
        "none_bin": None,
    })

asyncio.run(main())
```

  </TabItem>
</Tabs>

### Write with TTL

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# TTL (초 단위)
client.put(key, {"val": 1}, meta={"ttl": 300})

# 만료하지 않음
client.put(key, {"val": 1}, meta={"ttl": aerospike.TTL_NEVER_EXPIRE})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.put(key, {"val": 1}, meta={"ttl": 300})
await client.put(key, {"val": 1}, meta={"ttl": aerospike.TTL_NEVER_EXPIRE})
```

  </TabItem>
</Tabs>

### Write Policies

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import WritePolicy

# 생성 전용 (record가 이미 존재하면 실패)
policy: WritePolicy = {"exists": aerospike.POLICY_EXISTS_CREATE_ONLY}
client.put(key, bins, policy=policy)

# 교체 전용 (record가 존재하지 않으면 실패)
client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_REPLACE_ONLY})

# key를 서버로 전송 (record와 함께 저장)
client.put(key, bins, policy={"key": aerospike.POLICY_KEY_SEND})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
await client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_REPLACE_ONLY})
await client.put(key, bins, policy={"key": aerospike.POLICY_KEY_SEND})
```

  </TabItem>
</Tabs>

## Update (Increment, Append, Prepend)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# 정수 bin 증가
client.increment(key, "age", 1)

# 실수 bin 증가
client.increment(key, "score", 0.5)

# 문자열에 추가
client.append(key, "name", " Smith")

# 문자열 앞에 추가
client.prepend(key, "greeting", "Hello, ")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.increment(key, "age", 1)
await client.increment(key, "score", 0.5)
await client.append(key, "name", " Smith")
await client.prepend(key, "greeting", "Hello, ")
```

  </TabItem>
</Tabs>

## Delete (Remove)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# 단순 삭제
client.remove(key)

# generation 확인 후 삭제
client.remove(key, meta={"gen": 5}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove(key)
await client.remove(key, meta={"gen": 5}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
</Tabs>

### Remove Specific Bins

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

## Touch (Reset TTL)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.touch(key, val=600)  # TTL을 600초로 재설정
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.touch(key, val=600)
```

  </TabItem>
</Tabs>

## Multi-Operation (Operate)

단일 record에서 여러 작업을 원자적으로 실행합니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
ops = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "name", "val": "Bob"},
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = client.operate(key, ops)
print(bins["counter"])
```

### Ordered Results

```python
_, meta, results = client.operate_ordered(key, ops)
# results = [("name", "Bob"), ("counter", 2)]
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
ops = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "name", "val": "Bob"},
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = await client.operate(key, ops)
print(bins["counter"])
```

### Ordered Results

```python
_, meta, results = await client.operate_ordered(key, ops)
# results = [("name", "Bob"), ("counter", 2)]
```

  </TabItem>
</Tabs>

## Batch Operate

여러 record에 대해 작업을 실행합니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import Record

keys = [("test", "demo", f"counter_{i}") for i in range(10)]
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "views", "val": None},
]
results: list[Record] = client.batch_operate(keys, ops)

for record in results:
    if record.bins:
        print(f"views: {record.bins['views']}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import Record

keys = [("test", "demo", f"counter_{i}") for i in range(10)]
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "views", "val": None},
]
results: list[Record] = await client.batch_operate(keys, ops)

for record in results:
    if record.bins:
        print(f"views: {record.bins['views']}")
```

  </TabItem>
</Tabs>

## Batch Remove

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"temp_{i}") for i in range(100)]
results = client.batch_remove(keys)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"temp_{i}") for i in range(100)]
await client.batch_remove(keys)
```

  </TabItem>
</Tabs>

## Optimistic Locking

generation 기반 충돌 해결을 사용합니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py.exception import RecordGenerationError

# 현재 상태 읽기
_, meta, bins = client.get(key)

try:
    # generation이 일치하는 경우에만 업데이트
    client.put(
        key,
        {"val": bins["val"] + 1},
        meta={"gen": meta.gen},
        policy={"gen": aerospike.POLICY_GEN_EQ},
    )
except RecordGenerationError:
    print("Record was modified concurrently, retry needed")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py.exception import RecordGenerationError

_, meta, bins = await client.get(key)

try:
    await client.put(
        key,
        {"val": bins["val"] + 1},
        meta={"gen": meta.gen},
        policy={"gen": aerospike.POLICY_GEN_EQ},
    )
except RecordGenerationError:
    print("Record was modified concurrently, retry needed")
```

  </TabItem>
</Tabs>

## Error Handling

```python
from aerospike_py.exception import (
    RecordNotFound,
    RecordExistsError,
    AerospikeError,
)

try:
    _, _, bins = client.get(key)      # or: await client.get(key)
except RecordNotFound:
    print("Not found")
except AerospikeError as e:
    print(f"Error: {e}")
```

## Best Practices

- **배치 크기**: 배치 크기를 적절하게 유지하세요 (100-5000 keys). 매우 큰 배치는 타임아웃이 발생할 수 있습니다.
- **타임아웃**: 대규모 배치 작업에 대해 policy를 통해 적절한 타임아웃을 설정하세요.
- **오류 처리**: 배치 내의 개별 record는 독립적으로 실패할 수 있습니다. 각 결과의 bin이 `None`인지 확인하세요.
