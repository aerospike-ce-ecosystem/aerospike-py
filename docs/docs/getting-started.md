---
title: Getting Started
sidebar_label: Getting Started
sidebar_position: 1
description: Install aerospike-py and connect to an Aerospike cluster in minutes.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Installation

```bash
pip install aerospike-py
```

**Requirements:** Python 3.10+ (CPython) | Linux (x86_64, aarch64) | macOS (x86_64, arm64) | Windows (x64)

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
import aerospike_py as aerospike
from aerospike_py import Record

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect() as client:
    key: tuple[str, str, str] = ("test", "demo", "user1")

    # Write
    client.put(key, {"name": "Alice", "age": 30})

    # Read
    record: Record = client.get(key)
    print(record.bins)       # {"name": "Alice", "age": 30}
    print(record.meta.gen)   # 1

    # Update
    client.increment(key, "age", 1)

    # Delete
    client.remove(key)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
import asyncio
import aerospike_py as aerospike
from aerospike_py import AsyncClient, Record

async def main() -> None:
    async with AsyncClient({"hosts": [("127.0.0.1", 3000)]}) as client:
        await client.connect()
        key: tuple[str, str, str] = ("test", "demo", "user1")

        await client.put(key, {"name": "Bob", "age": 25})

        record: Record = await client.get(key)
        print(record.bins)  # {"name": "Bob", "age": 25}

        # Concurrent writes
        keys = [("test", "demo", f"item_{i}") for i in range(10)]
        await asyncio.gather(*(client.put(k, {"idx": i}) for i, k in enumerate(keys)))

        await client.remove(key)

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Policies & Metadata

```python
import aerospike_py as aerospike

key = ("test", "demo", "user1")

# TTL (seconds)
client.put(key, {"val": 1}, meta={"ttl": 300})

# Create only (fail if exists)
client.put(key, {"val": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# Optimistic locking
record = client.get(key)
client.put(
    key,
    {"val": record.bins["val"] + 1},
    meta={"gen": record.meta.gen},
    policy={"gen": aerospike.POLICY_GEN_EQ},
)
```

## Next Steps

| Topic | Description |
|-------|-------------|
| [CRUD & Batch](guides/crud/crud.md) | Put, get, batch operations, optimistic locking |
| [List CDT](guides/crud/cdt-list.md) | Atomic list operations |
| [Map CDT](guides/crud/cdt-map.md) | Atomic map operations |
| [NumPy Batch](guides/crud/numpy-batch.md) | Zero-copy columnar batch reads |
| [Query](guides/query-scan/query-scan.md) | Secondary index queries |
| [Expression Filters](guides/query-scan/expression-filters.md) | Server-side filtering |
| [Configuration](guides/config/client-config.md) | Connection, pool, timeouts |
| [API Reference](api/client.md) | Full method signatures |
| [Types](api/types.md) | NamedTuple / TypedDict definitions |
