---
title: Migration from Official Client
sidebar_label: Migration Guide
sidebar_position: 3
slug: /guides/migration
description: Migrate from aerospike-client-python (C-based) to aerospike-py (Rust-based).
---

## Installation

```bash
pip uninstall aerospike
pip install aerospike-py
```

## Import Changes

```python
# Before
import aerospike
from aerospike import exception as ex

# After -- drop-in alias
import aerospike_py as aerospike
from aerospike_py import exception as ex
```

## Client Creation

```python
# Identical API
config = {"hosts": [("127.0.0.1", 3000)]}
client = aerospike.client(config).connect()

# New: context manager
with aerospike.client(config).connect() as client:
    pass  # close() called automatically
```

## CRUD -- Compatible

```python
key = ("test", "demo", "user1")

# Same signatures
client.put(key, {"name": "Alice", "age": 30})
_, meta, bins = client.get(key)
_, meta = client.exists(key)
client.remove(key)
client.select(key, ["name"])
client.touch(key)
client.append(key, "name", " Smith")
client.increment(key, "counter", 1)
```

## Policies, Constants, Exceptions -- Compatible

```python
# Same policy dicts
policy = {"socket_timeout": 5000, "total_timeout": 10000, "max_retries": 2}

# Same constants
aerospike.POLICY_KEY_SEND       # 1
aerospike.TTL_NEVER_EXPIRE      # -1

# Same exception classes
from aerospike_py.exception import RecordNotFound, RecordExistsError
```

:::note[Exception Renames]
`TimeoutError` → `AerospikeTimeoutError`, `IndexError` → `AerospikeIndexError` to avoid shadowing Python builtins. Old names work as deprecated aliases.
:::

## CDT, Expressions, Query -- Compatible

```python
from aerospike_py import list_operations as lops, map_operations as mops, exp, predicates

# CDT operations
ops = [lops.list_append("tags", "new"), mops.map_put("attrs", "color", "blue")]
client.operate(key, ops)

# Expression filters
expr = exp.ge(exp.int_bin("age"), exp.int_val(18))
client.get(key, policy={"filter_expression": expr})

# Query
query = client.query("test", "demo")
query.where(predicates.between("age", 18, 65))
records = query.results()
```

## Async Client (New)

Not available in the official client:

```python
import asyncio
import aerospike_py as aerospike

async def main():
    client = aerospike.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()
    await client.put(key, {"name": "Alice"})
    _, meta, bins = await client.get(key)
    await client.close()

asyncio.run(main())
```

## Known Differences

| Feature | Official Client | aerospike-py |
|---------|----------------|--------------|
| Runtime | C extension | Rust + PyO3 |
| Async | No | Yes |
| NumPy batch reads | No | Yes |
| Context manager | No | Yes |
| `TimeoutError` | `TimeoutError` | `AerospikeTimeoutError` |
| `IndexError` | `IndexError` | `AerospikeIndexError` |
| `GeoJSON` type | `aerospike.GeoJSON` | Not yet available |
