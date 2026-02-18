---
title: Prometheus Metrics
sidebar_label: Metrics
sidebar_position: 2
description: Prometheus metrics for monitoring Aerospike operations.
---

aerospike-py collects operation-level metrics in Rust and exposes them in **Prometheus text format**. Metric names follow [OpenTelemetry DB Client Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/).

## Quick Start

```python
import aerospike_py

# Get metrics as string
text: str = aerospike_py.get_metrics()

# Or start a built-in HTTP server
aerospike_py.start_metrics_server(port=9464)
# Prometheus scrapes http://localhost:9464/metrics

# Stop when done
aerospike_py.stop_metrics_server()
```

## `db_client_operation_duration_seconds`

A **histogram** tracking the duration of every data operation.

**Labels:**

| Label | Examples |
|---|---|
| `db_system_name` | `aerospike` |
| `db_namespace` | `test`, `production` |
| `db_collection_name` | `users`, `sessions` |
| `db_operation_name` | `get`, `put`, `delete`, `query` |
| `error_type` | `""` (success), `Timeout`, `KeyNotFoundError` |

**Buckets:** `0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0` seconds

**Instrumented operations:** `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `query`

:::tip
`exists()` treats `KeyNotFoundError` as success since "not found" is a normal outcome.
:::

## Framework Integration

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
# Average latency (5m)
rate(db_client_operation_duration_seconds_sum[5m])
/ rate(db_client_operation_duration_seconds_count[5m])

# P99 latency
histogram_quantile(0.99, rate(db_client_operation_duration_seconds_bucket[5m]))

# Error rate by type
sum by (error_type) (rate(db_client_operation_duration_seconds_count{error_type!=""}[5m]))

# Ops/sec by namespace
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
| Per-operation recording | ~30-80 ns (atomic increment) |
| Relative to network round-trip | 0.001-0.01% |
| `get_metrics()` encoding | ~50-200 us |

Metrics collection is always enabled with negligible overhead.
