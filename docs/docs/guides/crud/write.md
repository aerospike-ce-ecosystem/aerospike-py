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

## Batch Operate / Remove

```python
# Batch operate
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results: list[Record] = client.batch_operate(keys, ops)

# Batch remove
results = client.batch_remove(keys)
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
