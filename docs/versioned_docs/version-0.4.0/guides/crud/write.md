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

# Simple write
client.put(key, {"name": "Alice", "age": 30})

# Supported types: str, int, float, bytes, list, dict, bool, None
client.put(key, {
    "str_bin": "hello",
    "int_bin": 42,
    "float_bin": 3.14,
    "list_bin": [1, 2, 3],
    "map_bin": {"nested": "dict"},
})

# With TTL
client.put(key, {"val": 1}, meta={"ttl": 300})

# Create only (fail if exists)
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

# With generation check
client.remove(key, meta={"gen": 5}, policy={"gen": aerospike.POLICY_GEN_EQ})

# Remove specific bins
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

## Touch (Reset TTL)

```python
client.touch(key, val=600)  # or: await client.touch(key, val=600)
```

## Multi-Operation (Operate)

Execute multiple operations atomically on a single record.

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

# Ordered results
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

Write multiple records with **per-record bins** in a single batch call. This is the batch version of `put()` — each record can have different bin names and values.

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

### Batch Write with TTL

TTL can be set at two levels:

- **Batch-level**: `policy={"ttl": N}` applies to all records in the batch.
- **Per-record**: `(key, bins, {"ttl": N})` overrides the batch-level TTL for that specific record.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# Batch-level TTL — all records expire in 30 days
results = client.batch_write(records, policy={"ttl": 2592000})

# Per-record TTL — each record has its own expiration
records_with_ttl = [
    (("test", "demo", "user1"), {"name": "Alice"}, {"ttl": 3600}),     # 1 hour
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 86400}),      # 1 day
    (("test", "demo", "user3"), {"name": "Charlie"}),                   # namespace default
]
results = client.batch_write(records_with_ttl)

# Mix: batch-level default + per-record override
results = client.batch_write(
    [
        (("test", "demo", "user1"), {"name": "Alice"}),                 # uses batch-level TTL
        (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 3600}),   # overrides to 1 hour
    ],
    policy={"ttl": 86400},  # default: 1 day
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

**Retry with auto-recovery:** Records that fail with transient errors (timeout, device overload, key busy) are automatically retried with exponential backoff:

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
# Retry failed records up to 5 times
results = client.batch_write(records, retry=5)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
# Retry failed records up to 5 times
results = await client.batch_write(records, retry=5)
```

  </TabItem>
</Tabs>

:::tip[in_doubt flag]
When `br.in_doubt` is `True`, the write may have completed on the server despite the error (e.g., timeout after the write was sent). Check `in_doubt` before retrying to avoid duplicate writes on non-idempotent operations.
:::

## Batch Operate / Remove

```python
# Batch operate — returns BatchRecords (same as batch_read)
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

## Tips

- **Batch size**: 100-5,000 keys per batch is optimal. Very large batches may timeout.
- **Timeouts**: Increase `total_timeout` for large batch operations.
- **Error handling**: Individual batch records can fail independently. Always check `br.record` for `None`.
