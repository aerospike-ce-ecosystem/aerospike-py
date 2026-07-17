---
title: Prometheus 메트릭
sidebar_label: 메트릭
sidebar_position: 2
description: Aerospike 작업을 모니터링하는 Prometheus 메트릭
---

aerospike-py는 operation-level metric을 Rust에서 기록하고 **Prometheus text format**으로 제공합니다. Metric 이름은 [OpenTelemetry DB Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/)를 따릅니다.

## Quick Start

```python
import aerospike_py

# metric 을 string 으로 받기
text: str = aerospike_py.get_metrics()

# 또는 내장 HTTP server 시작
aerospike_py.start_metrics_server(port=9464)
# Prometheus 가 http://localhost:9464/metrics 를 scrape

# 종료
aerospike_py.stop_metrics_server()
```

## `db_client_operation_duration_seconds`

모든 data operation의 duration을 추적하는 **histogram**입니다.

**Labels:**

| Label | Examples |
|---|---|
| `db_system_name` | `aerospike` |
| `db_namespace` | `test`, `production` |
| `db_collection_name` | `users`, `sessions` |
| `db_operation_name` | `get`, `put`, `delete`, `query` |
| `error_type` | `""` (success), `Timeout`, `KeyNotFoundError` |

**Buckets:** `0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0` (초)

**Instrumented operations:** `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `query`

:::tip
`exists()` 는 `KeyNotFoundError` 를 success 로 취급합니다 — "not found" 가 정상 결과이기 때문.
:::

## Framework 통합

### FastAPI

```python
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, REGISTRY
import aerospike_py

@app.get("/metrics")
def metrics():
    python_metrics = generate_latest(REGISTRY).decode("utf-8")
    aerospike_metrics = aerospike_py.get_metrics()
    return Response(
        python_metrics + "\n" + aerospike_metrics,
        media_type="text/plain; version=0.0.4",
    )
```

### Django

```python
# myproject/apps.py
from django.apps import AppConfig
import aerospike_py

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        aerospike_py.start_metrics_server(port=9464)
```

## Prometheus Config

```yaml
scrape_configs:
  - job_name: "aerospike-py"
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:9464"]
```

## PromQL Examples

```promql
# 평균 latency (5m)
rate(db_client_operation_duration_seconds_sum[5m])
/ rate(db_client_operation_duration_seconds_count[5m])

# P99 latency
histogram_quantile(0.99, rate(db_client_operation_duration_seconds_bucket[5m]))

# error type 별 error rate
sum by (error_type) (rate(db_client_operation_duration_seconds_count{error_type!=""}[5m]))

# namespace 별 ops/sec
sum by (db_namespace, db_operation_name) (rate(db_client_operation_duration_seconds_count[1m]))
```

## Grafana Dashboard

| Panel | PromQL | Type |
|---|---|---|
| Ops/sec | `sum(rate(..._count[1m])) by (db_operation_name)` | Time series |
| P50/P95/P99 | `histogram_quantile(0.5\|0.95\|0.99, rate(..._bucket[5m]))` | Time series |
| Error Rate | `sum(rate(..._count{error_type!=""}[1m])) by (error_type)` | Time series |
| By Namespace | `sum(rate(..._count[1m])) by (db_namespace)` | Pie chart |

## Performance

| Scenario | Overhead |
|---|---|
| operation 당 기록 | ~30-80 ns (atomic increment) |
| 네트워크 round-trip 대비 | 0.001-0.01% |
| `get_metrics()` encoding | ~50-200 μs |

Metric 수집은 항상 활성화되어 있으며 overhead는 무시할 수 있는 수준입니다.
