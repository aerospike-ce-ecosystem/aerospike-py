---
title: Write Operations
sidebar_label: Write
sidebar_position: 2
slug: /guides/write
description: Put, update, delete, operate, batch operate, and optimistic locking.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Write

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()
key: tuple[str, str, str] = ("test", "demo", "user1")

# 단순 write
client.put(key, {"name": "Alice", "age": 30})

# 지원 타입: str, int, float, bytes, list, dict, bool, None
client.put(key, {
    "str_bin": "hello",
    "int_bin": 42,
    "float_bin": 3.14,
    "list_bin": [1, 2, 3],
    "map_bin": {"nested": "dict"},
})

# TTL 포함
client.put(key, {"val": 1}, meta={"ttl": 300})

# Create only (존재 시 실패)
client.put(key, {"val": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
await client.put(key, {"name": "Alice", "age": 30})
await client.put(key, {"val": 1}, meta={"ttl": 300})
await client.put(key, {"val": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
</Tabs>

## Update

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
client.increment(key, "age", 1)
client.increment(key, "score", 0.5)
client.append(key, "name", " Smith")
client.prepend(key, "greeting", "Hello, ")
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
await client.increment(key, "age", 1)
await client.append(key, "name", " Smith")
```

  </TabItem>
</Tabs>

## Delete

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
client.remove(key)

# generation check 포함
client.remove(key, meta={"gen": 5}, policy={"gen": aerospike.POLICY_GEN_EQ})

# 특정 bin 만 제거
client.remove_bin(key, ["temp_bin", "debug_bin"])
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
await client.remove(key)
await client.remove_bin(key, ["temp_bin"])
```

  </TabItem>
</Tabs>

## Touch (TTL Reset)

```python
client.touch(key, val=600)  # 또는: await client.touch(key, val=600)
```

## Multi-Operation (Operate)

한 record에 여러 operation을 atomic하게 실행합니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
ops: list[dict] = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "name", "val": "Bob"},
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
record = client.operate(key, ops)
print(record.bins["counter"])

# 순서 보존 결과
result = client.operate_ordered(key, ops)
for bt in result.ordered_bins:
    print(f"{bt.name} = {bt.value}")
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
record = await client.operate(key, ops)
result = await client.operate_ordered(key, ops)
```

  </TabItem>
</Tabs>

## Batch Write

한 번의 batch call로 여러 record의 **per-record bin**을 씁니다. `put()`과 마찬가지로 record마다 서로 다른 bin name과 value를 사용할 수 있습니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
    (("test", "demo", "user3"), {"name": "Charlie", "age": 35}),
]
results = client.batch_write(records)
for br in results.batch_records:
    if br.result != 0:
        print(f"Failed: {br.key}, code={br.result}, in_doubt={br.in_doubt}")
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
    (("test", "demo", "user3"), {"name": "Charlie", "age": 35}),
]
results = await client.batch_write(records)
for br in results.batch_records:
    if br.result != 0:
        print(f"Failed: {br.key}, code={br.result}, in_doubt={br.in_doubt}")
```

  </TabItem>
</Tabs>

### TTL 이 있는 Batch Write

TTL 은 두 수준에서 설정 가능:

- **Batch-level**: `policy={"ttl": N}` 이 batch 의 모든 record 에 적용.
- **Per-record**: `(key, bins, {"ttl": N})` 이 해당 record 에 대해 batch-level TTL 을 override.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# Batch-level TTL — 모든 record 가 30일 후 만료
results = client.batch_write(records, policy={"ttl": 2592000})

# Per-record TTL — 각 record 가 자기 만료 시간
records_with_ttl = [
    (("test", "demo", "user1"), {"name": "Alice"}, {"ttl": 3600}),     # 1시간
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 86400}),      # 1일
    (("test", "demo", "user3"), {"name": "Charlie"}),                   # namespace default
]
results = client.batch_write(records_with_ttl)

# Mix: batch-level default + per-record override
results = client.batch_write(
    [
        (("test", "demo", "user1"), {"name": "Alice"}),                 # batch-level TTL 사용
        (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 3600}),   # 1시간으로 override
    ],
    policy={"ttl": 86400},  # default: 1일
)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# Batch-level TTL
results = await client.batch_write(records, policy={"ttl": 2592000})

# Per-record TTL
records_with_ttl = [
    (("test", "demo", "user1"), {"name": "Alice"}, {"ttl": 3600}),
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 86400}),
]
results = await client.batch_write(records_with_ttl)
```

  </TabItem>
</Tabs>

**자동 retry:** `retry`를 설정하면 timeout, device overload, key busy 같은 transient error를 exponential backoff로 다시 시도합니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# 실패 record 를 최대 5회 retry
results = client.batch_write(records, retry=5)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# 실패 record 를 최대 5회 retry
results = await client.batch_write(records, retry=5)
```

  </TabItem>
</Tabs>

:::tip[in_doubt flag]
`br.in_doubt`가 `True`이면 error가 발생했어도 server에서 write를 완료했을 수 있습니다. Write를 보낸 뒤 timeout이 난 경우가 한 예입니다. Non-idempotent operation을 두 번 적용하지 않도록 retry 전에 `in_doubt`를 확인하세요.
:::

## Batch Operate / Remove

```python
# Batch operate — BatchWriteResult (.batch_records: list[BatchRecord]) 반환.
#   참고: batch_read 는 LazyBatchRecords 를 반환; per-record `BatchRecord` row 만
#   batch_write / batch_operate / batch_remove 와 공유.
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)

# Batch remove
results = client.batch_remove(keys)
for br in results.batch_records:
    if br.result != 0:
        print(f"Failed to remove: {br.key}")
```

## Optimistic Locking

```python
from aerospike_py.exception import RecordGenerationError

record = client.get(key)
try:
    client.put(
        key,
        {"val": record.bins["val"] + 1},
        meta={"gen": record.meta.gen},
        policy={"gen": aerospike.POLICY_GEN_EQ},
    )
except RecordGenerationError:
    print("Concurrent modification, retry needed")
```

## 팁

- **Batch size**: batch 당 100-5,000 key 가 최적. 너무 크면 timeout 가능.
- **Timeout**: 큰 batch operation 의 경우 `total_timeout` 증가.
- **Error handling**: Batch 안의 record는 각각 독립적으로 실패할 수 있습니다. 항상 `br.record`가 `None`인지 확인하세요.
