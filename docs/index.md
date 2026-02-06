# aerospike-py

Aerospike Python Client built with **PyO3 + Rust**. Drop-in replacement for [aerospike-client-python](https://github.com/aerospike/aerospike-client-python) powered by the [Aerospike Rust Client v2](https://github.com/aerospike/aerospike-client-rust).

## Features

- **Sync & Async API** - `Client` for synchronous, `AsyncClient` for asyncio
- **Full CRUD** - put, get, select, exists, remove, touch, increment, append, prepend
- **Batch Operations** - get_many, exists_many, select_many, batch_operate, batch_remove
- **Query & Scan** - Secondary index queries with predicates, full namespace scans
- **Expression Filters** - Server-side filtering with 50+ expression builders (Server 5.2+)
- **List CDT Operations** - 31 atomic list operations (append, insert, get/remove by value/index/rank, sort, etc.)
- **Map CDT Operations** - 27 atomic map operations (put, get/remove by key/value/index/rank, etc.)
- **Context Manager** - `with` statement support for both `Client` and `AsyncClient`
- **UDF** - Register, execute, and remove Lua User Defined Functions
- **Admin** - User/role CRUD, privileges, whitelist, quotas
- **Index Management** - Create/remove integer, string, geo2dsphere indexes
- **Truncate** - Namespace/set truncation
- **130+ Constants** - Policy, operator, index, CDT, status code constants
- **18 Exception Classes** - Full exception hierarchy matching the original client
- **Type Stubs** - Complete `.pyi` files for IDE autocompletion

## Installation

### From Source

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv
source .venv/bin/activate
pip install maturin

maturin develop
```

### Requirements

- Python 3.10+
- Rust toolchain (install via [rustup](https://rustup.rs/))
- Running Aerospike server for integration use

## Quick Example

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()

key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})
_, meta, bins = client.get(key)
print(bins)  # {'name': 'Alice', 'age': 30}

client.close()
```

## Architecture

```
aerospike-py/
├── rust/src/              # PyO3 Rust bindings
│   ├── client.rs          # Sync Client
│   ├── async_client.rs    # Async Client
│   ├── query.rs           # Query / Scan
│   ├── operations.rs      # Operation mapping (incl. CDT list/map)
│   ├── expressions.rs     # Expression filter compilation
│   ├── errors.rs          # Error → Exception mapping
│   ├── constants.rs       # 130+ constants
│   ├── types/             # Type converters
│   └── policy/            # Policy parsers
├── src/aerospike_py/      # Python package
│   ├── __init__.py        # Re-exports, Client wrapper
│   ├── exp.py             # Expression filter builder
│   ├── list_operations.py # List CDT operation helpers
│   ├── map_operations.py  # Map CDT operation helpers
│   ├── exception.py       # Exception hierarchy
│   └── predicates.py      # Query predicates
└── tests/                 # Unit + Integration tests
```

## License

Apache License 2.0
