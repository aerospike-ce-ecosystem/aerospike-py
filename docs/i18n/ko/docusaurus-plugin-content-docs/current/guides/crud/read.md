---
title: Read Operations
sidebar_label: Read
sidebar_position: 1
slug: /guides/read
description: Get, select, exists, and batch read operations.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Key

모든 record는 `(namespace, set, primary_key)` key tuple로 식별합니다.

```python
key = ("test", "demo", "user1")      # string PK
key = ("test", "demo", 12345)         # integer PK
key = ("test", "demo", b"\x01\x02")   # bytes PK
```

## Read

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
from aerospike_py import Record

record: Record = client.get(key)
print(record.bins)       # {"name": "Alice", "age": 30}
print(record.meta.gen)   # 1
print(record.meta.ttl)   # 2591998

# Tuple unpacking (backward compat)
_, meta, bins = client.get(key)

# 특정 bin 만 읽기
record = client.select(key, ["name"])
# record.bins = {"name": "Alice"}
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
record: Record = await client.get(key)
_, meta, bins = await client.get(key)
record = await client.select(key, ["name"])
```

  </TabItem>
</Tabs>

## Exists

```python
from aerospike_py import ExistsResult

result: ExistsResult = client.exists(key)  # 또는: await client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

## Batch Read

여러 record를 한 번의 network call로 읽습니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
keys: list[tuple] = [("test", "demo", f"user_{i}") for i in range(10)]

# 모든 bin — `LazyBatchRecords` 반환. dict-style Mapping
# protocol (`items`, `keys`, `values`, `get`, `__getitem__`, `__iter__`,
# `__contains__`, `__len__`) 이 단일 cached `to_dict()` materialisation 으로
# backed 되어 명시 변환 없이 iterate 가능. plain mutable dict 가 명시적으로
# 필요하면 `batch.to_dict()` 호출.
batch = client.batch_read(keys)
for user_key, bins in batch.items():
    print(user_key, bins)

# 특정 bin
batch = client.batch_read(keys, bins=["name", "age"])

# 존재만 확인
batch = client.batch_read(keys, bins=[])
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# sync path 와 동일한 `LazyBatchRecords`; dict-style iteration 은
# cached `to_dict()` materialisation 으로 backed.
batch = await client.batch_read(keys, bins=["name", "age"])
for user_key, bins in batch.items():
    print(user_key, bins)
```

  </TabItem>
</Tabs>

## 팁

- **Batch size**: batch당 100–5,000개 key를 권장합니다. Batch가 너무 크면 timeout이 발생할 수 있습니다.
- **Timeout**: 큰 batch operation에는 더 긴 `total_timeout`을 사용하세요.
- **Error handling**: 각 batch record는 독립적으로 실패할 수 있습니다. 항상 `br.record`가 `None`인지 확인하세요.
