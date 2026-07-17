---
title: 내부 단계 프로파일링
sidebar_label: 내부 단계 프로파일링
sidebar_position: 4
description: aerospike-py 지연 시간을 디버깅하는 단계별 정밀 시간 측정. 비활성화하면 운영 오버헤드가 없습니다.
---

`db_client_operation_duration_seconds`와 함께 더 세밀한 timing을 제공하는 두 번째 histogram도 사용할 수 있습니다.

**`db_client_internal_stage_seconds`** — 단일 `batch_read` 를 내부 stage 별로 쪼개는 histogram (key parsing, Tokio scheduling, I/O, `to_dict` / `to_numpy` 변환, event-loop resume 등).

운영 metric은 항상 활성화되지만 internal stage profiling은 **기본적으로 꺼져 있습니다**. 비활성 path에서는 각 timer가 `Instant::now()`를 건너뛰고 atomic load 한 번만 실행합니다. Batch당 비용은 약 1 ns입니다.

## Quick Start

```python
import aerospike_py

# 기본 off
assert aerospike_py.is_internal_stage_metrics_enabled() is False

# 디버그 세션 동안 켜기
aerospike_py.set_internal_stage_metrics_enabled(True)
lazy_records = await client.batch_read(keys)
print(aerospike_py.get_metrics())   # db_client_internal_stage_seconds 가 이제 채워짐

# 또는 단일 block 범위로
with aerospike_py.internal_stage_profiling():
    lazy_records = await client.batch_read(keys)
# block exit 시 flag 자동 복원, exception 발생해도 동일
```

## 활성화 방법

| Method | 사용 시점 |
|---|---|
| `AEROSPIKE_PY_INTERNAL_METRICS=1` env var | 프로세스 시작 시 전역 기본값 (K8s `ConfigMap`, `docker run -e`, CI). Truthy: `1`, `true`, `True`, `TRUE`, `yes`, `on`. |
| `aerospike_py.set_internal_stage_metrics_enabled(True)` | 애플리케이션 코드에서 런타임 토글. |
| `with aerospike_py.internal_stage_profiling(): ...` | 일시적 — exit 시 이전 상태 복원. |

Native module은 초기화할 때 env var를 한 번 읽습니다. 이후 runtime call을 사용하면 env var 값을 덮어씁니다.

## `db_client_internal_stage_seconds`

단일 데이터베이스 operation 내 stage 별 duration 을 추적하는 **histogram**.

**Labels:**

| Label | Examples |
|---|---|
| `stage` | `key_parse`, `tokio_schedule_delay`, `limiter_wait`, `io`, `spawn_blocking_delay`, `into_pyobject`, `event_loop_resume_delay`, `to_dict`, `to_numpy`, `merge_to_dict`, `future_into_py_setup` |
| `db_operation_name` | `batch_read` (추후 다른 operation 도 instrumented 될 수 있음) |

**Buckets (sub-microsecond 정밀도):**
`1μs, 5μs, 10μs, 50μs, 100μs, 500μs, 1ms, 2ms, 5ms, 10ms, 20ms, 50ms, 100ms, 500ms, 1s`

## Stage Reference (`batch_read`)

| Stage | 측정 대상 |
|---|---|
| `key_parse` | Python keys → Rust tuple (GIL held) |
| `future_into_py_setup` | `future_into_py` sync setup (GIL held) |
| `tokio_schedule_delay` | `future_into_py` setup *직전* 부터 Tokio worker 위 async body 시작까지의 gap. **참고:** synchronous `future_into_py_setup` window 와 순수 scheduling delay 를 모두 포함 — `future_into_py_setup` 을 빼면 격리된 scheduling 비용에 가깝게 근사 (작은 `stage_timer!` macro overhead 도 이 window 안에 포함). |
| `limiter_wait` | backpressure semaphore 대기 시간 |
| `io` | Aerospike network round-trip |
| `spawn_blocking_delay` | I/O 완료와 spawn-blocking thread 위 `IntoPyObject::into_pyobject` 시작 사이의 gap (GIL-bound) |
| `into_pyobject` | `Arc` wrap + `LazyBatchRecords` 생성 |
| `event_loop_resume_delay` | `into_pyobject` 반환과 event loop 에서 Python coroutine 실제 resume 사이의 gap |
| `to_dict` | `batch_to_dict_py` 변환 (GIL held). |
| `to_numpy` | `batch_to_numpy_py` structured-array fill. hot `Value → buffer` loop 는 `Python::detach` 하에서 실행되므로 **timer 가 감싸는 것은 GIL-held framing 만** (allocation, dtype parse, `key_map` build) — GIL-released fill 자체는 아님. |
| `merge_to_dict` | static `LazyBatchRecords.merge_to_dict` — 여러 handle 의 single-GIL merge. |

## 왜 opt-in 인가

Stage profiling 은 측정 가능한 latency 를 추가합니다: 각 `batch_read` 가 `Instant::now()` ~10회 + histogram observation 10회 비용 지불. concurrent worker 20개 벤치마크 에서 `batch_read` 의 `db_client_operation_duration_seconds`:

| | OFF | ON | Δ |
|---|---|---|---|
| avg | 2.16 ms | 3.22 ms | +1.06 ms |
| p95 | 4.67 ms | 7.61 ms | +2.94 ms |
| p99 | 4.93 ms | 9.51 ms | +4.58 ms |

Production에서는 **꺼 둡니다**. Latency regression을 조사할 때만 활성화하세요.

## Scraping 과 Visualization

이 histogram 은 운영 histogram 과 동일한 `get_metrics()` / `start_metrics_server()` 표면으로 노출 — 별도 endpoint 없음. Grafana panel 에서 예를 들어 `to_dict` 의 p95 를 query:

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(
    db_client_internal_stage_seconds_bucket{stage="to_dict"}[5m]
  ))
)
```

모든 stage를 stacked time series로 표시하면 `batch_read`가 어느 단계에서 시간을 쓰는지 바로 확인할 수 있습니다.

```promql
sum by (stage, db_operation_name) (
  rate(db_client_internal_stage_seconds_sum[1m])
) / sum by (stage, db_operation_name) (
  rate(db_client_internal_stage_seconds_count[1m])
)
```

## Toggle 상태 확인

프로세스 시작 시 aerospike-py 가 effective 상태를 log:

```
[aerospike-py] internal_stage_metrics_enabled=False (AEROSPIKE_PY_INTERNAL_METRICS=None)
```

Dashboard에서 확인하려면 애플리케이션이 이 값을 Prometheus gauge로 내보내도록 구성할 수도 있습니다.

```python
from prometheus_client import Gauge
import aerospike_py

g = Gauge("aerospike_py_internal_stage_metrics_enabled",
          "1 if stage profiling is ON, 0 otherwise")
g.set(1 if aerospike_py.is_internal_stage_metrics_enabled() else 0)
```

## Troubleshooting

**`db_client_internal_stage_seconds` 가 `/metrics` 에는 보이는데 sample 이 없음**
`# HELP`와 `# TYPE` header는 항상 등록됩니다. Sample은 toggle을 켠 상태에서 `batch_read`가 한 번 이상 끝난 뒤에 나타납니다.

**context-manager block 에서 exception 발생 — flag 가 아직 ON?**
아니요. `internal_stage_profiling()` 이 `finally` 로 이전 상태 복원, `contextlib.contextmanager` 의미와 동일.

**이게 `db_client_operation_duration_seconds` 에 영향?**
없음. 운영 metric (`db_client_operation_duration_seconds`) 은 `set_metrics_enabled` / `is_metrics_enabled` 로 제어되며 stage toggle 과 무관.
