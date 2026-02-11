---
title: Prometheus 메트릭
sidebar_label: Metrics
sidebar_position: 2
description: Aerospike 오퍼레이션 모니터링을 위한 OpenTelemetry 호환 Prometheus 메트릭.
---

# Prometheus 메트릭

aerospike-py는 Rust에서 오퍼레이션 수준의 메트릭을 수집하고 **Prometheus text format**으로 노출합니다. 메트릭 이름과 라벨은 [OpenTelemetry DB Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/)를 따르므로 표준 Observability 스택과 호환됩니다.

## 아키텍처

```
┌────────────────────────────────────────────────────────┐
│  Rust (prometheus-client crate)                        │
│                                                        │
│  client.put() ──▶ OperationTimer ──▶ Histogram.observe │
│  client.get() ──▶ OperationTimer ──▶ Histogram.observe │
│  ...                                                   │
│                                                        │
│  Registry ──▶ encode() ──▶ Prometheus text format       │
└───────────────────────┬────────────────────────────────┘
                        │ PyO3
┌───────────────────────▼────────────────────────────────┐
│  Python                                                │
│                                                        │
│  aerospike_py.get_metrics() → str                      │
│  aerospike_py.start_metrics_server(port=9464)          │
│  aerospike_py.stop_metrics_server()                    │
└────────────────────────────────────────────────────────┘
```

메트릭 기록은 핫 패스에서 **lock-free atomic 오퍼레이션**을 사용합니다. `Mutex`는 스크레이핑 시 텍스트 인코딩할 때만 획득되며, 일반적인 15~30초 스크레이프 간격에서는 영향이 없습니다.

## 제공되는 메트릭

### `db_client_operation_duration_seconds`

모든 데이터 오퍼레이션의 소요 시간을 추적하는 **histogram**입니다.

| 라벨 | 설명 | 예시 |
|---|---|---|
| `db_system_name` | 항상 `"aerospike"` | `aerospike` |
| `db_namespace` | Aerospike namespace | `test`, `production` |
| `db_collection_name` | Aerospike set 이름 | `users`, `sessions` |
| `db_operation_name` | 오퍼레이션 종류 | `get`, `put`, `delete`, `query`, `scan` |
| `error_type` | 성공 시 빈 문자열, 실패 시 에러 분류 | `""`, `Timeout`, `KeyNotFoundError` |

**Histogram 버킷:** `0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0` 초

**계측 대상 오퍼레이션:**

| 오퍼레이션 | `db_operation_name` |
|---|---|
| `put` | `put` |
| `get` | `get` |
| `select` | `select` |
| `exists` | `exists` |
| `remove` / `delete` | `remove` |
| `touch` | `touch` |
| `append` | `append` |
| `prepend` | `prepend` |
| `increment` | `increment` |
| `operate` | `operate` |
| `batch_read` | `batch_read` |
| `batch_operate` | `batch_operate` |
| `batch_remove` | `batch_remove` |
| `Query.results()` | `query` |
| `Scan.results()` / `Scan.foreach()` | `scan` |

**에러 타입:**

| `error_type` | 원인 |
|---|---|
| `""` (빈 문자열) | 성공 |
| `Timeout` | 오퍼레이션 타임아웃 |
| `Connection` | 네트워크 연결 실패 |
| `KeyNotFoundError` | 레코드가 존재하지 않음 |
| `KeyExistsError` | 레코드가 이미 존재 (create-only) |
| `GenerationError` | 낙관적 잠금 충돌 |
| `FilteredOut` | Expression 필터에 의해 제외됨 |
| `InvalidArgument` | 잘못된 파라미터 |

:::tip[exists() 특수 처리]
`exists()`는 `KeyNotFoundError`를 **성공**(빈 `error_type`)으로 처리합니다. 존재 여부 확인에서 "없음"은 정상적인 결과이기 때문입니다.
:::

## 빠른 시작

### 문자열로 메트릭 가져오기

```python
import aerospike_py

text = aerospike_py.get_metrics()
print(text)
```

출력 (오퍼레이션 실행 전에도):

```
# HELP db_client_operation_duration_seconds Duration of database client operations.
# TYPE db_client_operation_duration_seconds histogram
# EOF
```

### 내장 메트릭 서버

백그라운드 스레드에서 경량 HTTP 서버를 시작합니다:

```python
aerospike_py.start_metrics_server(port=9464)
# Prometheus가 http://localhost:9464/metrics 를 스크레이프
```

더 이상 필요하지 않을 때 중지합니다:

```python
aerospike_py.stop_metrics_server()
```

## 프레임워크 연동

### FastAPI

Aerospike 메트릭과 애플리케이션의 Python `prometheus_client` 메트릭을 결합합니다:

```python
from fastapi import FastAPI, Response
from prometheus_client import Counter, generate_latest, REGISTRY
import aerospike_py

app = FastAPI()

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path"]
)

@app.get("/metrics")
def metrics():
    # Python 앱 메트릭
    python_metrics = generate_latest(REGISTRY).decode("utf-8")
    # Aerospike Rust 메트릭
    aerospike_metrics = aerospike_py.get_metrics()
    # 둘을 합쳐서 반환
    combined = python_metrics + "\n" + aerospike_metrics
    return Response(combined, media_type="text/plain; version=0.0.4")
```

```bash
pip install prometheus-client
```

### Django

내장 메트릭 서버를 Django와 함께 사용합니다:

```python
# myproject/apps.py
from django.apps import AppConfig
import aerospike_py

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        aerospike_py.start_metrics_server(port=9464)
```

### 독립 실행 스크립트

배치 작업이나 CLI 도구에서:

```python
import aerospike_py

aerospike_py.start_metrics_server(port=9464)

client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
for i in range(1000):
    client.put(("test", "demo", f"key{i}"), {"value": i})

# 메트릭은 http://localhost:9464/metrics 에서 확인 가능
# 프로세스를 유지하거나 stop_metrics_server()로 정리
input("종료하려면 Enter를 누르세요...")
aerospike_py.stop_metrics_server()
```

## Prometheus 설정

`prometheus.yml`에 스크레이프 대상을 추가합니다:

```yaml
scrape_configs:
  - job_name: "aerospike-py"
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:9464"]
```

또는 FastAPI 통합 엔드포인트를 사용하는 경우:

```yaml
scrape_configs:
  - job_name: "my-app"
    scrape_interval: 15s
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:8000"]
```

## 유용한 PromQL 쿼리

### 평균 오퍼레이션 지연 시간 (최근 5분)

```promql
rate(db_client_operation_duration_seconds_sum[5m])
/
rate(db_client_operation_duration_seconds_count[5m])
```

### 오퍼레이션별 P99 지연 시간

```promql
histogram_quantile(0.99,
  rate(db_client_operation_duration_seconds_bucket[5m])
)
```

### 에러 타입별 에러 비율

```promql
sum by (error_type) (
  rate(db_client_operation_duration_seconds_count{error_type!=""}[5m])
)
```

### namespace별 초당 오퍼레이션 수

```promql
sum by (db_namespace, db_operation_name) (
  rate(db_client_operation_duration_seconds_count[1m])
)
```

## Grafana 대시보드

네 가지 패널로 구성된 기본 대시보드:

| 패널 | PromQL | 시각화 |
|---|---|---|
| Ops/sec | `sum(rate(db_client_operation_duration_seconds_count[1m])) by (db_operation_name)` | Time series |
| P50/P95/P99 지연 시간 | `histogram_quantile(0.5\|0.95\|0.99, rate(..._bucket[5m]))` | Time series |
| 에러 비율 | `sum(rate(..._count{error_type!=""}[1m])) by (error_type)` | Time series |
| Namespace별 Ops | `sum(rate(..._count[1m])) by (db_namespace)` | Pie chart |

## 성능 영향

| 시나리오 | 오버헤드 |
|---|---|
| 오퍼레이션당 기록 | ~30–80 ns (atomic increment) |
| Aerospike round-trip 대비 | 0.001–0.01% |
| `get_metrics()` 인코딩 | ~50–200 us |

메트릭 수집은 항상 활성화되어 있습니다. 네트워크 I/O에 비해 오버헤드는 무시할 수 있는 수준입니다.
