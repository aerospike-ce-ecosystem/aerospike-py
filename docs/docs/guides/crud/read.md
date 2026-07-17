---
title: Read Operations
sidebar_label: Read
sidebar_position: 1
slug: /guides/read
description: Get, select, exists, and batch read operations.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Keys

Every record is identified by a key tuple: `(namespace, set, primary_key)`.

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

# Read specific bins
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

result: ExistsResult = client.exists(key)  # or: await client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

## Batch Read

Read multiple records with one batch API call. The client routes each key to the
node that owns it, so a multi-node batch may use more than one network request.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
keys: list[tuple] = [("test", "demo", f"user_{i}") for i in range(10)]

# All bins — returns a `LazyBatchRecords`. The dict-style Mapping
# protocol (`items`, `keys`, `values`, `get`, `__getitem__`, `__iter__`,
# `__contains__`, `__len__`) is backed by a single cached `to_dict()`
# materialisation, so iteration works without an explicit conversion. Call
# `batch.to_dict()` when you specifically need a plain mutable dict.
batch = client.batch_read(keys)
for user_key, bins in batch.items():
    print(user_key, bins)

# Specific bins
batch = client.batch_read(keys, bins=["name", "age"])

# Existence check only
batch = client.batch_read(keys, bins=[])
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# Same `LazyBatchRecords` as the sync path; dict-style iteration
# is backed by a cached `to_dict()` materialisation.
batch = await client.batch_read(keys, bins=["name", "age"])
for user_key, bins in batch.items():
    print(user_key, bins)
```

  </TabItem>
</Tabs>

## Tips

- **Batch size**: 100-5,000 keys per batch is optimal. Very large batches may timeout.
- **Timeouts**: Increase `total_timeout` for large batch operations.
- **Error handling**: The mapping view contains successful records that have a
  user key. Compare the requested user keys with `batch.keys()` to find misses.
  Use `batch.iter_records()` and inspect each `br.result` when you need to
  distinguish a missing record from another per-record error.
