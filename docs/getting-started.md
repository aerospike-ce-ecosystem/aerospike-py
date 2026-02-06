# Getting Started

## Prerequisites

- **Python 3.10+**
- **Rust toolchain** - Install via [rustup](https://rustup.rs/)
- **Aerospike server** - Local or Docker

## Start Aerospike Server

```bash
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 \
  -e "NAMESPACE=test" \
  -e "CLUSTER_NAME=docker" \
  aerospike/aerospike-server
```

## Install from Source

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv
source .venv/bin/activate
pip install maturin

maturin develop
```

Verify the installation:

```bash
python -c "import aerospike_py as aerospike; print(aerospike.__version__)"
```

## Sync Client Example

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

    # Batch read
    keys = [("test", "demo", f"user{i}") for i in range(1, 4)]
    records = client.get_many(keys)

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

!!! tip "Without context manager"
    You can also use `connect()` / `close()` manually:
    ```python
    client = aerospike.client({...}).connect()
    # ... operations ...
    client.close()
    ```

## Async Client Example

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

    key = ("test", "demo", "user1")
    await client.put(key, {"name": "Bob", "age": 25})

    _, meta, bins = await client.get(key)
    print(bins)

    # Concurrent writes
    keys = [("test", "demo", f"item_{i}") for i in range(10)]
    tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
    await asyncio.gather(*tasks)

    # Batch read
    results = await client.get_many(keys)

    await client.close()

asyncio.run(main())
```

## Configuration

The `config` dictionary supports:

| Key | Type | Description |
|-----|------|-------------|
| `hosts` | `list[tuple[str, int]]` | Seed host addresses |
| `cluster_name` | `str` | Expected cluster name (optional) |
| `timeout` | `int` | Connection timeout in ms (default: 1000) |
| `auth_mode` | `int` | `AUTH_INTERNAL`, `AUTH_EXTERNAL`, or `AUTH_PKI` |

## Policies and Metadata

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

## Next Steps

- [CRUD Guide](guides/crud.md) - Detailed CRUD operations
- [Batch Guide](guides/batch.md) - Batch operations
- [Query & Scan Guide](guides/query-scan.md) - Secondary index queries and scans
- [Expression Filters Guide](guides/expression-filters.md) - Server-side filtering
- [List CDT Operations Guide](guides/cdt-list.md) - Atomic list operations
- [Map CDT Operations Guide](guides/cdt-map.md) - Atomic map operations
- [API Reference](api/client.md) - Full API documentation
