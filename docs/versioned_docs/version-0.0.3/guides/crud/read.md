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

Read multiple records in a single network call.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
keys: list[tuple] = [("test", "demo", f"user_{i}") for i in range(10)]

# All bins
batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        print(br.record.bins)

# Specific bins
batch = client.batch_read(keys, bins=["name", "age"])

# Existence check only
batch = client.batch_read(keys, bins=[])
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
batch = await client.batch_read(keys, bins=["name", "age"])
for br in batch.batch_records:
    if br.record:
        print(br.record.bins)
```

  </TabItem>
</Tabs>

## Tips

- **Batch size**: 100-5,000 keys per batch is optimal. Very large batches may timeout.
- **Timeouts**: Increase `total_timeout` for large batch operations.
- **Error handling**: Individual batch records can fail independently. Always check `br.record` for `None`.
