---
title: CRUD & Batch Operations Guide
sidebar_label: CRUD & Batch
sidebar_position: 1
slug: /guides/crud
description: Step-by-step guide covering put, get, remove, batch operations, and optimistic locking.
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

## Write (Put)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

key = ("test", "demo", "user1")

# Simple write
client.put(key, {"name": "Alice", "age": 30})

# Supported bin value types
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

    # Simple write
    await client.put(key, {"name": "Alice", "age": 30})

    # Supported bin value types
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
# TTL in seconds
client.put(key, {"val": 1}, meta={"ttl": 300})

# Never expire
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

# Create only (fails if record exists)
policy: WritePolicy = {"exists": aerospike.POLICY_EXISTS_CREATE_ONLY}
client.put(key, bins, policy=policy)

# Replace only (fails if record doesn't exist)
client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_REPLACE_ONLY})

# Send key to server (stored with record)
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

## Read (Get)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import Record

record: Record = client.get(("test", "demo", "user1"))
# record.key  → AerospikeKey | None
# record.meta → RecordMetadata | None (meta.gen, meta.ttl)
# record.bins → dict[str, Any] | None

# Tuple unpacking also works (backward compat)
key, meta, bins = client.get(("test", "demo", "user1"))
# meta.gen == 1, meta.ttl == 2591998
# bins = {"name": "Alice", "age": 30}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import Record

record: Record = await client.get(("test", "demo", "user1"))
# or tuple unpacking
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

# Tuple unpacking also works
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

## Update (Increment, Append, Prepend)

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# Increment integer bin
client.increment(key, "age", 1)

# Increment float bin
client.increment(key, "score", 0.5)

# Append to string
client.append(key, "name", " Smith")

# Prepend to string
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
# Simple delete
client.remove(key)

# Delete with generation check
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
client.touch(key, val=600)  # reset TTL to 600 seconds
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.touch(key, val=600)
```

  </TabItem>
</Tabs>

## Multi-Operation (Operate)

Execute multiple operations atomically on a single record:

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

## Batch Read

Read multiple records in a single network call. Returns a `BatchRecords` object.

- `bins=None` - Read all bins
- `bins=["a", "b"]` - Read specific bins
- `bins=[]` - Existence check only

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# Read all bins
batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(f"{key} → {bins}")

# Read specific bins
batch = client.batch_read(keys, bins=["name", "age"])

# Existence check
batch = client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# Read all bins
batch = await client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(f"{key} → {bins}")

# Read specific bins
batch = await client.batch_read(keys, bins=["name", "age"])

# Existence check
batch = await client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
</Tabs>

## Batch Operate

Execute operations on multiple records:

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

Use generation-based conflict resolution:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py.exception import RecordGenerationError

# Read current state
_, meta, bins = client.get(key)

try:
    # Update only if generation matches
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

- **Batch size**: Keep batch sizes reasonable (100-5000 keys). Very large batches may timeout.
- **Timeouts**: Set appropriate timeouts for large batch operations via policy.
- **Error handling**: Individual records in a batch can fail independently. Check each result for `None` bins.
