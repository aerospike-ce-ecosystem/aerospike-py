---
title: Getting Started
sidebar_label: Getting Started
sidebar_position: 1
description: Install aerospike-py and connect to an Aerospike cluster in minutes with sync or async Python clients.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Prerequisites

- **Python 3.10+**

### Supported Platforms

| OS | Architecture |
|---|---|
| Linux | x86_64, aarch64 |
| macOS | x86_64, aarch64 (Apple Silicon) |
| Windows | x64 |

## Installation

```bash
pip install aerospike-py
```

Verify the installation:

```bash
python -c "import aerospike_py as aerospike; print(aerospike.__version__)"
```

:::tip[Install from Source]

For contributors or development builds, see the [Contributing Guide](contributing.md).

:::

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

# Create and connect (with context manager)
with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    # Write a record
    key = ("test", "demo", "user1")
    client.put(key, {"name": "Alice", "age": 30})

    # Read a record
    _, meta, bins = client.get(key)
    print(f"bins={bins}, gen={meta['gen']}, ttl={meta['ttl']}")

    # Update with increment
    client.increment(key, "age", 1)

    # Atomic multi-operation
    ops = [
        {"op": aerospike.OPERATOR_INCR, "bin": "age", "val": 1},
        {"op": aerospike.OPERATOR_READ, "bin": "age", "val": None},
    ]
    _, _, bins = client.operate(key, ops)

    # Delete
    client.remove(key)
# client.close() is called automatically
```

:::tip[Without context manager]

You can also use `connect()` / `close()` manually:

```python
client = aerospike.client({...}).connect()
# ... operations ...
client.close()
```

:::

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
import aerospike_py as aerospike
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

    # Write a record
    key = ("test", "demo", "user1")
    await client.put(key, {"name": "Bob", "age": 25})

    # Read a record
    _, meta, bins = await client.get(key)
    print(f"bins={bins}, gen={meta['gen']}, ttl={meta['ttl']}")

    # Update with increment
    await client.increment(key, "age", 1)

    # Atomic multi-operation
    ops = [
        {"op": aerospike.OPERATOR_INCR, "bin": "age", "val": 1},
        {"op": aerospike.OPERATOR_READ, "bin": "age", "val": None},
    ]
    _, _, bins = await client.operate(key, ops)

    # Concurrent writes with asyncio.gather
    keys = [("test", "demo", f"item_{i}") for i in range(10)]
    tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
    await asyncio.gather(*tasks)

    # Delete
    await client.remove(key)

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Configuration

The `config` dictionary supports:

| Key | Type | Description |
|-----|------|-------------|
| `hosts` | `list[tuple[str, int]]` | Seed host addresses |
| `cluster_name` | `str` | Expected cluster name (optional) |
| `timeout` | `int` | Connection timeout in ms (default: 1000) |
| `auth_mode` | `int` | `AUTH_INTERNAL`, `AUTH_EXTERNAL`, or `AUTH_PKI` |

## Policies and Metadata

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# Write with TTL (seconds)
client.put(key, {"val": 1}, meta={"ttl": 300})

# Write with key send policy
client.put(key, {"val": 1}, policy={"key": aerospike.POLICY_KEY_SEND})

# Create only (fail if exists)
client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# Optimistic locking with generation check
_, meta, bins = client.get(key)
client.put(key, {"val": bins["val"] + 1},
           meta={"gen": meta["gen"]},
           policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
# Write with TTL (seconds)
await client.put(key, {"val": 1}, meta={"ttl": 300})

# Write with key send policy
await client.put(key, {"val": 1}, policy={"key": aerospike.POLICY_KEY_SEND})

# Create only (fail if exists)
await client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# Optimistic locking with generation check
_, meta, bins = await client.get(key)
await client.put(key, {"val": bins["val"] + 1},
                 meta={"gen": meta["gen"]},
                 policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
</Tabs>

## Next Steps

- [CRUD & Batch Guide](guides/crud.md) - CRUD and batch operations
- [Query & Scan Guide](guides/query-scan.md) - Secondary index queries and scans
- [Expression Filters Guide](guides/expression-filters.md) - Server-side filtering
- [List CDT Operations Guide](guides/cdt-list.md) - Atomic list operations
- [Map CDT Operations Guide](guides/cdt-map.md) - Atomic map operations
- [API Reference](api/client.md) - Full API documentation
