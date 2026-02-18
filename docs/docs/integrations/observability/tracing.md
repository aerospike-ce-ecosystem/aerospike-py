---
title: Distributed Tracing
sidebar_label: Tracing
sidebar_position: 3
description: OpenTelemetry distributed tracing for Aerospike operations.
---

Built-in **OpenTelemetry tracing** for every data operation. Spans follow [Database Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/) and export via **OTLP gRPC**.

## Quick Start

```bash
pip install aerospike-py            # tracing built-in
pip install aerospike-py[otel]      # + context propagation from Python spans
```

```python
import aerospike_py

# 1. Initialize
aerospike_py.init_tracing()

# 2. Use client -- all operations are traced automatically
client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
client.put(("test", "users", "user1"), {"name": "Alice"})
client.get(("test", "users", "user1"))
client.close()

# 3. Flush pending spans before exit
aerospike_py.shutdown_tracing()
```

## API

| Function | Description |
|---|---|
| `init_tracing()` | Initialize OTLP tracer. Reads `OTEL_*` env vars. |
| `shutdown_tracing()` | Flush and shut down. Call before process exit. |

Both are thread-safe and idempotent.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_SERVICE_NAME` | `aerospike-py` | Service name |
| `OTEL_SDK_DISABLED` | `false` | Disable tracing entirely |
| `OTEL_TRACES_EXPORTER` | `otlp` | Set to `none` to disable export |

## Span Attributes

| Attribute | Example |
|---|---|
| `db.system.name` | `aerospike` |
| `db.namespace` | `test` |
| `db.collection.name` | `users` |
| `db.operation.name` | `PUT`, `GET`, `REMOVE` |

**Span name:** `{OPERATION} {namespace}.{set}` (e.g., `PUT test.users`)

**On error:** `error.type`, `db.response.status_code`, `otel.status_code=ERROR`

**Instrumented:** `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `query`

## Context Propagation

With `aerospike-py[otel]` installed, W3C TraceContext is automatically propagated from Python active spans to Rust spans:

| Setup | Behavior |
|---|---|
| `aerospike-py[otel]` + active span | Python span becomes parent |
| `aerospike-py[otel]` + no active span | Root span created |
| `aerospike-py` (base) | Root span (no propagation) |

## Framework Integration

### FastAPI

```python
from contextlib import asynccontextmanager
import aerospike_py
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    aerospike_py.init_tracing()
    client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()
    aerospike_py.shutdown_tracing()

app = FastAPI(lifespan=lifespan)
```

For end-to-end HTTP-to-Aerospike traces:

```bash
pip install opentelemetry-instrumentation-fastapi
```

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

### Django

```python
# apps.py
from django.apps import AppConfig
import aerospike_py

class MyAppConfig(AppConfig):
    name = "myapp"
    def ready(self):
        aerospike_py.init_tracing()

# settings.py
import atexit, aerospike_py
atexit.register(aerospike_py.shutdown_tracing)
```

## Jaeger Setup

```bash
docker run -d --name jaeger \
  -p 4317:4317 -p 16686:16686 \
  jaegertracing/all-in-one:latest

export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=my-aerospike-app
```

Visit `http://localhost:16686` to view traces.

## Disabling Tracing

```bash
export OTEL_SDK_DISABLED=true          # disable entirely
export OTEL_TRACES_EXPORTER=none       # spans created but not exported
```

## Graceful Degradation

| Scenario | Behavior |
|---|---|
| OTLP endpoint unreachable | Warning log, tracing disabled |
| `init_tracing()` not called | No-op spans |
| `opentelemetry-api` not installed | Root spans (no propagation) |
| `shutdown_tracing()` not called | Some pending spans may be lost |

## Performance

| Scenario | Overhead |
|---|---|
| Span creation | ~1-5 us |
| Context propagation | ~10-50 us |
| vs network round-trip | < 1% |
| `OTEL_SDK_DISABLED=true` | ~30-80 ns (metrics only) |
