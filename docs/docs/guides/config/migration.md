---
title: Migration from Official Client
sidebar_label: Migration Guide
sidebar_position: 3
slug: /guides/migration
description: Migrate from the official aerospike-client-python (C-based) to aerospike-py (Rust-based).
---

# Migration Guide

This guide helps you migrate from the
[official aerospike-client-python](https://github.com/aerospike/aerospike-client-python)
(C extension) to **aerospike-py** (Rust + PyO3).

## Installation

```bash
# Remove old client
pip uninstall aerospike

# Install new client
pip install aerospike-py
```

## Import Changes

```python
# Before (official client)
import aerospike
from aerospike import exception as ex

# After (aerospike-py) — designed to be a drop-in alias
import aerospike_py as aerospike
from aerospike_py import exception as ex
```

## Client Creation

```python
# Before
config = {"hosts": [("127.0.0.1", 3000)]}
client = aerospike.client(config).connect()

# After — identical API
config = {"hosts": [("127.0.0.1", 3000)]}
client = aerospike.client(config).connect()

# After — with context manager (new)
with aerospike.client(config).connect() as client:
    # client.close() called automatically
    pass
```

## CRUD Operations

The core CRUD API is compatible:

```python
key = ("test", "demo", "user1")

# put / get / exists / remove — same signature
client.put(key, {"name": "Alice", "age": 30})
_, meta, bins = client.get(key)
_, meta = client.exists(key)
client.remove(key)

# select — same signature
_, meta, bins = client.select(key, ["name"])

# touch / append / prepend / increment — same signature
client.touch(key)
client.append(key, "name", " Smith")
client.prepend(key, "name", "Ms. ")
client.increment(key, "counter", 1)
```

## Policy Dicts

Policy dicts use the same keys:

```python
policy = {
    "socket_timeout": 5000,
    "total_timeout": 10000,
    "max_retries": 2,
}
client.get(key, policy=policy)

write_policy = {
    "key": aerospike.POLICY_KEY_SEND,
    "exists": aerospike.POLICY_EXISTS_CREATE_ONLY,
    "gen": aerospike.POLICY_GEN_EQ,
}
client.put(key, bins, meta={"gen": 5}, policy=write_policy)
```

## Exception Handling

Exception classes are compatible:

```python
from aerospike_py.exception import (
    AerospikeError,
    RecordNotFound,
    RecordExistsError,
    AerospikeTimeoutError,  # was TimeoutError in official client
)

try:
    client.get(key)
except RecordNotFound:
    pass
```

:::note Exception Renames
`TimeoutError` and `IndexError` are renamed to `AerospikeTimeoutError` and
`AerospikeIndexError` to avoid shadowing Python builtins. The old names still
work as deprecated aliases.
:::

## Constants

All constants use the same names and values:

```python
aerospike.POLICY_KEY_DIGEST      # 0
aerospike.POLICY_KEY_SEND        # 1
aerospike.POLICY_EXISTS_IGNORE   # 0
aerospike.POLICY_GEN_EQ          # 1
aerospike.TTL_NEVER_EXPIRE       # -1
aerospike.OPERATOR_READ          # 1
aerospike.OPERATOR_WRITE         # 2
```

## List / Map CDT Operations

```python
from aerospike_py import list_operations as lops
from aerospike_py import map_operations as mops

ops = [
    lops.list_append("tags", "new_tag"),
    mops.map_put("attrs", "color", "blue"),
]
_, _, result = client.operate(key, ops)
```

## Expression Filters

```python
from aerospike_py import exp

# Build expression
expr = exp.and_(
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.string_bin("status"), exp.string_val("active")),
)

# Pass to policy
policy = {"filter_expression": expr}
client.get(key, policy=policy)
```

## Query / Scan

```python
query = client.query("test", "demo")
query.select("name", "age")
query.where(aerospike.predicates.between("age", 18, 65))
records = query.results()
```

## Async Client (New)

aerospike-py adds an async client not available in the official client:

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
| Async support | No | Yes |
| NumPy batch reads | No | Yes |
| Context manager | No | Yes (`with` / `async with`) |
| `TimeoutError` name | `TimeoutError` | `AerospikeTimeoutError` (alias available) |
| `IndexError` name | `IndexError` | `AerospikeIndexError` (alias available) |
| Predicate helpers | `aerospike.predicates` | `aerospike.predicates` |
| GeoJSON type | `aerospike.GeoJSON` | Not yet available |
| `operate_ordered()` | Returns ordered list | Same |
