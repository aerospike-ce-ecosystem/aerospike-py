---
sidebar_position: 1
title: Architecture
description: How aerospike-py works under the hood — layers, GIL handling, data flow, and batch operations.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Architecture

aerospike-py is a Python client for [Aerospike](https://aerospike.com) built on the [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust) via [PyO3](https://pyo3.rs). The Rust core compiles into a native Python extension module, giving Python applications near-native I/O performance while keeping a Pythonic API with full type annotations.

**Key properties:**

- **GIL-free I/O** — the GIL is released during every database call, so other Python threads and coroutines run concurrently.
- **Type-safe** — ships with `.pyi` stubs for IDE autocompletion and type-checker support.
- **Zero dependencies** — the base install has no external Python dependencies. NumPy and OpenTelemetry are optional extras.

## Layers

```
┌─────────────────────────────────────────────┐
│  Your Python Application                    │
├─────────────────────────────────────────────┤
│  Python Wrapper Layer                       │
│  _client.py / _async_client.py              │
│  NamedTuple wrapping, error decoration      │
├─────────────────────────────────────────────┤
│  PyO3 Binding Layer                         │
│  client.rs / async_client.rs                │
│  GIL management, Python ↔ Rust conversion   │
├─────────────────────────────────────────────┤
│  Aerospike Rust Client                      │
│  aerospike-core crate (fully async)         │
│  Aerospike wire protocol, connection pool   │
├─────────────────────────────────────────────┤
│  Aerospike Server                           │
└─────────────────────────────────────────────┘
```

| Layer | Role |
|-------|------|
| **Python Wrapper** | Thin layer that converts raw tuples from Rust into `Record`, `ExistsResult`, and other NamedTuples. Adds context-manager support and the `@catch_unexpected` decorator. |
| **PyO3 Binding** | `#[pyclass]` structs that bridge Python calls to the async Rust client. Handles GIL release/reacquire and type conversion between Python objects and Rust types. |
| **Aerospike Rust Client** | The `aerospike-core` crate — a fully async client that speaks the Aerospike binary wire protocol over TCP. Manages connection pooling, cluster discovery, and partition maps. |
| **Aerospike Server** | The Aerospike database (Community or Enterprise). |

## Sync vs Async

Both clients expose the same API surface. The difference is how they schedule I/O on the internal Tokio runtime.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
import aerospike_py

client = aerospike_py.client({"hosts": [("localhost", 3000)]}).connect()
client.put(("test", "demo", "user1"), {"name": "Alice"})
record = client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice"}
client.close()
```

Under the hood, each call releases the GIL, runs the Rust future on a Tokio runtime via `block_on()`, then re-acquires the GIL to return the result. Other Python threads can execute freely during the I/O wait.

  </TabItem>
  <TabItem value="async" label="Async">

```python
import aerospike_py

client = aerospike_py.AsyncClient({"hosts": [("localhost", 3000)]})
await client.connect()
await client.put(("test", "demo", "user1"), {"name": "Alice"})
record = await client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice"}
await client.close()
```

Each call returns a Python awaitable backed by a Tokio future. The GIL is not held during I/O, so concurrent `await` calls overlap naturally with `asyncio.gather()` or task groups.

  </TabItem>
</Tabs>

### Performance comparison (vs official C client)

| Path | put | get | batch_read (NumPy) |
|------|-----|-----|--------------------|
| Sync (sequential) | ~1.1x slower | ~1.1x slower | — |
| Async (concurrent) | **2.1x faster** | **1.6x faster** | **3.4x faster** |

The sync gap (~10%) comes from the `block_on()` overhead per call. Async is where aerospike-py shines — concurrent I/O eliminates per-call overhead entirely.

## Data Flow

### Write path (`put`)

1. Python dict `{"name": "Alice"}` is converted to Rust `Vec<Bin>`.
2. Key tuple `("test", "demo", "user1")` becomes an Aerospike `Key` (with RIPEMD-160 digest).
3. The GIL is released. The Rust client serializes bins into the Aerospike wire protocol and sends them over TCP.
4. The server acknowledges. The GIL is re-acquired and `None` is returned to Python.

### Read path (`get`)

1. The GIL is released. The Rust client sends a read request and receives the response.
2. The Rust `Record` (bins + generation + TTL) is converted to a Python tuple `(key, meta, bins)`.
3. The Python wrapper layer wraps this into a `Record` NamedTuple:

```python
record = client.get(("test", "demo", "user1"))
record.bins          # {"name": "Alice"}
record.meta.gen      # 1 (generation counter)
record.meta.ttl      # 0 (seconds until expiration)
record.key.user_key  # "user1"
```

### Type conversion

| Python | Aerospike | Notes |
|--------|-----------|-------|
| `int` | Integer | 64-bit signed |
| `float` | Double | 64-bit IEEE 754 |
| `str` | String | UTF-8 |
| `bytes` | Blob | Raw bytes |
| `list` | List | Nested types supported |
| `dict` | Map | Nested types supported |
| `bool` | Bool | |
| `None` | Nil | Removes the bin on write |

## Batch Operations

### batch_read

Returns a `dict[UserKey, dict]` mapping each user key to its bins. Only successful reads are included — missing or failed keys are absent from the dict.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(1000)]
batch = client.batch_read(keys, bins=["name", "age"])

for user_key, bins in batch.items():
    print(user_key, bins["name"])

# Check which keys are missing
requested = {k[2] for k in keys}
missing = requested - set(batch.keys())
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
batch = await client.batch_read(keys, bins=["name", "age"])
for user_key, bins in batch.items():
    print(user_key, bins["name"])
```

  </TabItem>
</Tabs>

For high-throughput pipelines, pass a NumPy dtype to get a structured array with zero-copy columnar access. See the [NumPy Batch Read guide](./crud/numpy-batch.md) for details.

```python
import numpy as np

dtype = np.dtype([("score", "f8"), ("count", "i4")])
result = client.batch_read(keys, _dtype=dtype)
print(result.batch_records["score"].mean())  # columnar access
```

### batch_write

Each record is a `(key, bins)` tuple. Optionally add a third element for per-record metadata like TTL:

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 3600}),  # expires in 1 hour
]
results = client.batch_write(records, policy={"ttl": 86400})  # default: 1 day
```

**TTL priority:** per-record `{"ttl": N}` > batch-level `policy={"ttl": N}` > namespace default.

**Retry:** Failed records (timeout, device overload, key busy) are automatically retried with exponential backoff. Retries stop early if the elapsed time approaches `total_timeout`.

```python
results = client.batch_write(records, retry=3)
for br in results.batch_records:
    if br.result != 0:
        if br.in_doubt:
            print(f"Key {br.key} may have succeeded — verify before retrying")
        else:
            print(f"Key {br.key} failed (code={br.result})")
```

## Error Handling

Errors from the server are mapped to a Python exception hierarchy rooted at `AerospikeError`. Each exception carries the original error message and result code.

```python
from aerospike_py.exception import RecordNotFound, AerospikeError

try:
    record = client.get(("test", "demo", "missing"))
except RecordNotFound:
    print("Record does not exist")
except AerospikeError as e:
    print(f"Unexpected error: {e}")
```

For batch operations, individual failures do not raise exceptions — check `br.result` on each `BatchRecord` instead. See the [Error Handling guide](./admin/error-handling.md) for the full exception hierarchy and batch error patterns.

## Observability

aerospike-py has built-in support for tracing, metrics, and logging. All three are optional and have near-zero overhead when disabled.

### OpenTelemetry Tracing

Every database operation emits an OTel span with `db.system.name`, `db.namespace`, `db.operation.name`, and other semantic attributes. Install `aerospike-py[otel]` and initialize:

```python
from aerospike_py import init_tracing, shutdown_tracing

init_tracing()   # uses OTEL_* env vars for exporter config
# ... use client ...
shutdown_tracing()
```

### Prometheus Metrics

Operation durations are recorded as histograms. Expose them via the built-in HTTP server or read programmatically:

```python
from aerospike_py import start_metrics_server, get_metrics

start_metrics_server(9090)  # GET http://localhost:9090/metrics
print(get_metrics())        # text format
```

### Logging

Rust internal logs are bridged to Python's `logging` module:

```python
from aerospike_py import set_log_level, LOG_LEVEL_DEBUG
set_log_level(LOG_LEVEL_DEBUG)
```

See the [Observability guides](../integrations/observability/tracing.md) for detailed configuration.

## Design Principles

1. **Rust-first** — Core logic lives in Rust. Python is a thin wrapper for ergonomics (NamedTuples, context managers, factory functions).
2. **Zero Python dependencies** — Base install has no external Python deps. NumPy and OpenTelemetry are optional extras (`pip install aerospike-py[numpy,otel]`).
3. **Type-safe** — `.pyi` stubs provide full IDE support. All return types are NamedTuples with named fields, not raw dicts or tuples.
4. **API compatibility** — Method names, constants, and exceptions align with the [official Aerospike Python client](https://github.com/aerospike/aerospike-client-python) where practical.
5. **GIL-free I/O** — Every database operation releases the GIL during the network call. Sync uses `py.detach()` + Tokio `block_on()`; async uses `future_into_py()`. See [Performance Tuning](./config/performance-tuning.md) for runtime worker configuration.
