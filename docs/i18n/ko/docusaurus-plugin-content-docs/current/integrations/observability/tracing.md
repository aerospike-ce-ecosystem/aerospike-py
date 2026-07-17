---
title: 분산 추적
sidebar_label: 추적
sidebar_position: 3
description: Aerospike 작업을 위한 OpenTelemetry 분산 추적
---

aerospike-py는 모든 data operation을 위한 **OpenTelemetry tracing**을 제공합니다. Span은 [Database Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/)를 따르며 **OTLP gRPC**로 export됩니다.

## Quick Start

```bash
pip install aerospike-py            # tracing built-in
pip install aerospike-py[otel]      # + Python span 으로부터의 context propagation
```

```python
import aerospike_py

# 1. 초기화
aerospike_py.init_tracing()

# 2. client 사용 — 모든 operation 이 자동으로 traced
client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
client.put(("test", "users", "user1"), {"name": "Alice"})
client.get(("test", "users", "user1"))
client.close()

# 3. exit 전 pending span flush
aerospike_py.shutdown_tracing()
```

## API

| Function | 설명 |
|---|---|
| `init_tracing()` | OTLP tracer 초기화. `OTEL_*` 환경변수 사용. |
| `shutdown_tracing()` | Flush 후 shutdown. process exit 전 호출. |

두 function은 모두 thread-safe하고 idempotent합니다.

## 환경변수

| Variable | Default | 설명 |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_SERVICE_NAME` | `aerospike-py` | service name |
| `OTEL_SDK_DISABLED` | `false` | tracing 전체 비활성화 |
| `OTEL_TRACES_EXPORTER` | `otlp` | `none` 으로 설정 시 export 비활성 |

## Span 속성

| Attribute | Example |
|---|---|
| `db.system.name` | `aerospike` |
| `db.namespace` | `test` |
| `db.collection.name` | `users` |
| `db.operation.name` | `PUT`, `GET`, `REMOVE` |

**Span name:** `{OPERATION} {namespace}.{set}` (예: `PUT test.users`)

**오류 시:** `error.type`, `db.response.status_code`, `otel.status_code=ERROR`

**Instrumented operations:** `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `query`

## Context Propagation

`aerospike-py[otel]`을 설치하면 W3C TraceContext가 활성 Python span에서 Rust span으로 자동 전파됩니다.

| Setup | 동작 |
|---|---|
| `aerospike-py[otel]` + active span | Python span 이 parent 가 됨 |
| `aerospike-py[otel]` + no active span | root span 생성 |
| `aerospike-py` (base) | root span (propagation 없음) |

## Framework 통합

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

End-to-end HTTP-to-Aerospike trace 를 위해:

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

## Jaeger 셋업

```bash
docker run -d --name jaeger \
  -p 4317:4317 -p 16686:16686 \
  jaegertracing/all-in-one:latest

export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=my-aerospike-app
```

Trace는 `http://localhost:16686`에서 확인할 수 있습니다.

## Tracing 비활성화

```bash
export OTEL_SDK_DISABLED=true          # 전체 비활성
export OTEL_TRACES_EXPORTER=none       # span 은 생성되나 export 안 됨
```

## Graceful Degradation

| Scenario | 동작 |
|---|---|
| OTLP endpoint 도달 불가 | 경고 log, tracing 비활성 |
| `init_tracing()` 호출 안 함 | no-op span |
| `opentelemetry-api` 미설치 | root span (propagation 없음) |
| `shutdown_tracing()` 호출 안 함 | 일부 pending span 유실 가능 |

## Performance

| Scenario | Overhead |
|---|---|
| Span 생성 | ~1-5 μs |
| Context propagation | ~10-50 μs |
| 네트워크 round-trip 대비 | < 1% |
| `OTEL_SDK_DISABLED=true` | ~30-80 ns (metric 만) |
