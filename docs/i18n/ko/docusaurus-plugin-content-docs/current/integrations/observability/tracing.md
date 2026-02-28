---
title: 분산 트레이싱
sidebar_label: Tracing
sidebar_position: 3
description: Aerospike 오퍼레이션을 위한 OpenTelemetry 분산 트레이싱.
---

모든 데이터 오퍼레이션에 대한 내장 **OpenTelemetry 트레이싱**을 제공합니다. Span은 [Database Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/)를 따르며 **OTLP gRPC**로 내보냅니다.

## 빠른 시작

```bash
pip install aerospike-py            # 트레이싱 내장
pip install aerospike-py[otel]      # + Python span에서 컨텍스트 전파
```

```python
import aerospike_py

# 1. 초기화
aerospike_py.init_tracing()

# 2. 클라이언트 사용 -- 모든 오퍼레이션이 자동으로 트레이싱됨
client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
client.put(("test", "users", "user1"), {"name": "Alice"})
client.get(("test", "users", "user1"))
client.close()

# 3. 종료 전 대기 중인 span 플러시
aerospike_py.shutdown_tracing()
```

## API

| 함수 | 설명 |
|---|---|
| `init_tracing()` | OTLP 트레이서를 초기화합니다. `OTEL_*` 환경변수를 읽습니다. |
| `shutdown_tracing()` | 플러시 후 종료합니다. 프로세스 종료 전에 호출하세요. |

두 함수 모두 스레드 안전하며 멱등(idempotent)합니다.

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC 엔드포인트 |
| `OTEL_SERVICE_NAME` | `aerospike-py` | 서비스 이름 |
| `OTEL_SDK_DISABLED` | `false` | 트레이싱 완전 비활성화 |
| `OTEL_TRACES_EXPORTER` | `otlp` | `none`으로 설정하면 내보내기 비활성화 |

## Span 속성

| 속성 | 예시 |
|---|---|
| `db.system.name` | `aerospike` |
| `db.namespace` | `test` |
| `db.collection.name` | `users` |
| `db.operation.name` | `PUT`, `GET`, `REMOVE` |

**Span 이름:** `{OPERATION} {namespace}.{set}` (예: `PUT test.users`)

**에러 발생 시:** `error.type`, `db.response.status_code`, `otel.status_code=ERROR`

**계측 대상:** `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `query`

## 컨텍스트 전파

`aerospike-py[otel]`을 설치하면 W3C TraceContext가 Python 활성 span에서 Rust span으로 자동 전파됩니다:

| 설정 | 동작 |
|---|---|
| `aerospike-py[otel]` + 활성 span | Python span이 부모가 됨 |
| `aerospike-py[otel]` + 활성 span 없음 | 루트 span 생성 |
| `aerospike-py` (기본) | 루트 span (전파 없음) |

## 프레임워크 연동

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

HTTP부터 Aerospike까지 엔드투엔드 트레이스를 구성하려면:

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

## Jaeger 설정

```bash
docker run -d --name jaeger \
  -p 4317:4317 -p 16686:16686 \
  jaegertracing/all-in-one:latest

export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=my-aerospike-app
```

`http://localhost:16686`에서 트레이스를 확인할 수 있습니다.

## 트레이싱 비활성화

```bash
export OTEL_SDK_DISABLED=true          # 완전 비활성화
export OTEL_TRACES_EXPORTER=none       # span은 생성되지만 내보내지 않음
```

## 장애 허용 동작

| 시나리오 | 동작 |
|---|---|
| OTLP 엔드포인트 접근 불가 | 경고 로그, 트레이싱 비활성화 |
| `init_tracing()` 미호출 | No-op span |
| `opentelemetry-api` 미설치 | 루트 span (전파 없음) |
| `shutdown_tracing()` 미호출 | 일부 대기 중인 span이 유실될 수 있음 |

## 성능 영향

| 시나리오 | 오버헤드 |
|---|---|
| Span 생성 | ~1-5 us |
| 컨텍스트 전파 | ~10-50 us |
| 네트워크 round-trip 대비 | < 1% |
| `OTEL_SDK_DISABLED=true` | ~30-80 ns (메트릭만) |
