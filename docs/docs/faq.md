---
sidebar_position: 99
title: FAQ
description: Frequently asked questions about aerospike-py.
---

## Why is aerospike-py written in Rust?

aerospike-py uses [PyO3](https://pyo3.rs/) to expose the [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust) to Python. This design offers several advantages over a pure-Python client or a C extension:

- **Performance** -- Rust compiles to native code. Benchmarks show throughput on par with (or better than) the official C-based client, especially for batch and async workloads.
- **Memory safety** -- Rust's ownership model eliminates whole classes of bugs (use-after-free, buffer overflows, data races) without a garbage collector.
- **Native async** -- The underlying client runs on Tokio. `AsyncClient` therefore uses native async I/O instead of wrapping synchronous calls.
- **Zero Python dependencies** -- The base install (`pip install aerospike-py`) has no external Python dependencies. NumPy and OpenTelemetry are optional extras.

## How does GIL handling work?

aerospike-py releases the Python Global Interpreter Lock (GIL) during all database I/O so that other Python threads can make progress while a request is in flight.

| Client | Mechanism |
|--------|-----------|
| **Sync `Client`** | `py.detach()` releases the GIL, then `RUNTIME.block_on()` runs the async Rust operation on the internal Tokio runtime. The GIL is re-acquired when the result is returned. |
| **Async `AsyncClient`** | `future_into_py()` returns a Python awaitable. The actual work runs on the Tokio runtime without holding the GIL. When the future completes, `Python::attach()` re-acquires the GIL to hand the result back. |

In both cases, the request travels to the Aerospike cluster without holding the GIL. Other Python threads or async tasks can run concurrently.

## Is aerospike-py thread-safe?

Yes. A single `Client` instance can be shared safely across multiple threads. Internally the Rust client manages a connection pool, and all shared state is protected by lock-free or mutex-guarded structures.

```python
import threading
import aerospike_py

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment

def worker(thread_id: int) -> None:
    key = ("test", "demo", f"thread_{thread_id}")
    client.put(key, {"tid": thread_id})
    record = client.get(key)
    assert record.bins["tid"] == thread_id

threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
client.close()
```

## Does it support Python free-threaded mode (3.14t)?

Yes. aerospike-py builds and runs on the experimental free-threaded CPython (PEP 703). CI runs unit tests **and** concurrency stress tests on Python 3.14t to verify correctness without the GIL.

The core logic runs in Rust and relies on Rust's memory-safety guarantees. It remains safe when Python removes the GIL entirely.

## Is NumPy required?

No. NumPy is an **optional** dependency.

```bash
# Base install -- no NumPy needed
pip install aerospike-py

# With NumPy support
pip install aerospike-py[numpy]
```

With NumPy installed, call `LazyBatchRecords.to_numpy(dtype)` on the value returned by `batch_read()`. It produces `NumpyBatchRecords` backed by a NumPy structured array. The client fills the buffer with the GIL released, and you can pass the result directly to `torch.from_numpy(...)` without copying it. Use `batch_write_numpy()` for bulk writes from structured arrays. All other features work without NumPy.

## Can I migrate from the official C client?

Yes. aerospike-py is designed as a near-drop-in replacement. Start by changing the import:

```python
# Before
import aerospike

# After
import aerospike_py as aerospike
```

Most API signatures, constants, exception classes, and policy dicts are compatible. See the [Migration Guide](/docs/guides/migration) for a step-by-step walkthrough and the [API Comparison](/docs/guides/api-comparison) for a detailed side-by-side table.

## How do I enable OpenTelemetry tracing?

Tracing support is compiled into every build. To enable it:

```bash
pip install aerospike-py[otel]   # adds opentelemetry-api for context propagation
```

```python
import aerospike_py

# Initialize before creating the client
aerospike_py.init_tracing()

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment
# ... all operations are traced automatically ...
client.close()

# Flush pending spans before exit
aerospike_py.shutdown_tracing()
```

Spans are exported via OTLP gRPC (default endpoint `http://localhost:4317`). Configure with standard `OTEL_*` environment variables. See the [Tracing guide](/docs/integrations/observability/tracing) for details.

## How do I enable Prometheus metrics?

aerospike-py ships a built-in Prometheus metrics HTTP server:

```python
import aerospike_py

# Start metrics server on port 9464
aerospike_py.start_metrics_server(9464)

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment
# ... operations are metered automatically ...
client.close()

aerospike_py.stop_metrics_server()
```

Scrape `http://localhost:9464/metrics` from Prometheus. Operation latency histograms are recorded per operation type. See the [Metrics guide](/docs/integrations/observability/metrics) for details.

## What Aerospike server versions are supported?

aerospike-py is tested against **Aerospike Server 6.x and 7.x** (Community and Enterprise). It is built on the Aerospike Rust Client v2.0.0-alpha.9.

## How do I report a bug or request a feature?

Open an issue on the GitHub repository:

- **Bug reports:** [github.com/aerospike-ce-ecosystem/aerospike-py/issues/new](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/new)
- **Feature requests:** Same link -- use the "Feature Request" template if available.

For a bug report, include your Python version, operating system, aerospike-py version (`aerospike_py.__version__`), and a minimal reproduction.
