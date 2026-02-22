---
title: Read Operations
sidebar_label: Read
sidebar_position: 1
slug: /guides/read
description: get, select, exists, batch read 작업 가이드
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Keys

모든 record는 key 튜플로 식별됩니다: `(namespace, set, primary_key)`.

```python
key = ("test", "demo", "user1")      # string PK
key = ("test", "demo", 12345)         # integer PK
key = ("test", "demo", b"\x01\x02")   # bytes PK
```

## Read (Get)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import Record

record: Record = client.get(("test", "demo", "user1"))
# record.key  → AerospikeKey | None
# record.meta → RecordMetadata | None (meta.gen, meta.ttl)
# record.bins → dict[str, Any] | None

# 튜플 언패킹도 가능 (하위 호환)
key, meta, bins = client.get(("test", "demo", "user1"))
# meta.gen == 1, meta.ttl == 2591998
# bins = {"name": "Alice", "age": 30}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import Record

record: Record = await client.get(("test", "demo", "user1"))
# 또는 튜플 언패킹
key, meta, bins = await client.get(("test", "demo", "user1"))
```

  </TabItem>
</Tabs>

### Read Specific Bins (Select)

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

## Check Existence

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import ExistsResult

result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"Record exists, gen={result.meta.gen}")
else:
    print("Record not found")

# 튜플 언패킹도 가능
_, meta = client.exists(key)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import ExistsResult

result: ExistsResult = await client.exists(key)
if result.meta is not None:
    print(f"Record exists, gen={result.meta.gen}")
else:
    print("Record not found")
```

  </TabItem>
</Tabs>

## Batch Read

단일 네트워크 호출로 여러 record를 읽습니다. `BatchRecords` 객체를 반환합니다.

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
        print(f"{key} → {bins}")

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
        print(f"{key} → {bins}")

# 특정 bin만 읽기
batch = await client.batch_read(keys, bins=["name", "age"])

# 존재 여부만 확인
batch = await client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
</Tabs>

## Best Practices

- **배치 크기**: 배치 크기를 적절하게 유지하세요 (100-5000 keys). 매우 큰 배치는 타임아웃이 발생할 수 있습니다.
- **타임아웃**: 대규모 배치 작업에 대해 policy를 통해 적절한 타임아웃을 설정하세요.
- **오류 처리**: 배치 내의 개별 record는 독립적으로 실패할 수 있습니다. 각 결과의 bin이 `None`인지 확인하세요.
