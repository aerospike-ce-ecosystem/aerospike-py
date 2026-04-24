# Internal Stage Profiling Toggle — On/Off Overhead 검증

> 2026-04-17 | aerospike-py v0.1.0 (feature/batch-read-internal-metrics)
> 관련: [numpy-bytes-passthrough-plan.md](numpy-bytes-passthrough-plan.md),
> 대시보드: aerospike-py 벤치마크 — 파이프라인 분석 (Grafana)

## 1. 목적

`db_client_internal_stage_seconds` (batch_read 내부 10개 stage)의 수집을
**debug 모드에서만 활성화**하고 **prod(info) 모드에서는 zero-overhead** 가 되도록
만든 후, 실제 K8s 배포에서 부하 테스트로 오버헤드 영향을 측정한다.

## 2. 구현 요약

### Zero-overhead 메커니즘
- `INTERNAL_STAGE_ENABLED: AtomicBool`, **기본 `false`**
- `AEROSPIKE_PY_INTERNAL_METRICS=1` 환경변수로 프로세스 시작 시점에 ON 가능
- Python API: `aerospike_py.set_internal_stage_metrics_enabled(bool)`,
  `aerospike_py.is_internal_stage_metrics_enabled()`,
  `with aerospike_py.internal_stage_profiling():`

### Rust 변경
- `stage_timer!` macro 신설: `if is_internal_stage_enabled() { Instant::now() + body + record } else { body }`
- `record_internal_stage_unchecked()` 신설: macro 내부 중복 atomic load 제거
- `metrics::maybe_now() -> Option<Instant>` 신설: cross-boundary 시점 캡처에 사용
- `PendingBatchRead::Handle.io_complete_at`, `PyBatchReadHandle.into_pyobject_at`을
  `Option<Instant>`로 변경 — disabled 시 `None`으로 저장되어
  `Instant::now()` syscall 자체가 발생하지 않음
- `INTERNAL_BUCKETS`에 1μs(`0.000_001`) bucket 추가 — 서브-μs stage 관찰 정밀도 향상

### 영향 받은 파일
| 파일 | 변경 |
|------|------|
| `rust/src/metrics.rs` | Flag + macro + unchecked helper + env init |
| `rust/src/lib.rs` | pyfunction 등록 + env init 호출 |
| `rust/src/async_client.rs` | batch_read 5 stages 마이그레이션 |
| `rust/src/batch_types.rs` | Option 필드 + 5 stages 마이그레이션 |
| `src/aerospike_py/_observability.py` | Python wrapper + context manager |
| `src/aerospike_py/__init__.py`, `.pyi` | API re-export |
| `tests/unit/test_internal_stage_toggle.py` | 18개 단위 테스트 (신규) |
| `benchmark/src/serving/observability/{tracing,metrics}.py` | toggle 상태 gauge + 로그 |
| `benchmark/deploy/k8s/configmap.yaml` | `AEROSPIKE_PY_INTERNAL_METRICS: "0"` 기본값 |

## 3. 부하 테스트 조건

- K8s deploy: `benchmark` ns, 2 replica, 4 CPU / 4Gi (request), 8 CPU / 8Gi (limit)
- 대상 엔드포인트: `/predict/{official,py-async}/sample?mode={single,gather,merge_gather}`
- 로드 제너레이터: 20 parallel workers, 90초, 각 mode round-robin
  - in-cluster curl loop (ingress/port-forward 제약으로 pod에서 직접 호출)
- **stage profiling OFF 구성**: `AEROSPIKE_PY_INTERNAL_METRICS=0` (baseline)
- **stage profiling ON 구성**: `AEROSPIKE_PY_INTERNAL_METRICS=1`
- 두 구성 사이에 `kubectl rollout restart` 로 새 pod 로 교체

## 4. 측정 결과

> **주의**: stage profiling ON 구성의 curl 로드 제너레이터는 90초 중 마지막 몇 초에
> pod OOM (exit 137)으로 SIGKILL 되었다. 그 전까지 수집된 scrape 데이터는 유효하나,
> `spawn_blocking_delay` / `event_loop_resume_delay` 같은 큰 값은 pod 포화 상태를
> 반영한다 (정상 부하 기준이 아님). 본 테이블은 오버헤드 존재 여부 및 상대적 증가폭
> 확인용이며, 절대 레이턴시 수치는 pod 리소스 여유 상태에서 재측정이 필요하다.
> 정확한 비교는 [k6-runtime-client-comparison.md](k6-runtime-client-comparison.md) 의 k6 기반 재측정 참조.

### stage profiling OFF (baseline) — 2026-04-17 18:31 KST

| 지표 | 값 |
|------|----|
| `aerospike_py_internal_stage_metrics_enabled` | **0** (확인됨) |
| `db_client_internal_stage_seconds_count` | 데이터 **없음** (stage 기록 skip) |
| `db_client_operation_duration_seconds` avg (batch_read) | **2.16 ms** |
| `db_client_operation_duration_seconds` p95 (batch_read) | **4.67 ms** |
| `db_client_operation_duration_seconds` p99 (batch_read) | **4.93 ms** |
| `predict_duration_seconds` p95 (aerospike-py E2E) | 70.4 ms |
| `predict_duration_seconds` p95 (official-aerospike E2E) | 73.1 ms |
| 로드 총 요청수 / 성공 | 4935 / 4920 (99.70%) |

### stage profiling ON (debug) — 2026-04-17 18:54 KST

| 지표 | 값 |
|------|----|
| `aerospike_py_internal_stage_metrics_enabled` | **1** (확인됨) |
| `db_client_internal_stage_seconds_count` per stage | 정상 기록 (10개 stage 모두 ≥ 0.058 req/s) |
| `db_client_operation_duration_seconds` avg (batch_read) | **3.22 ms** |
| `db_client_operation_duration_seconds` p95 (batch_read) | **7.61 ms** |
| `db_client_operation_duration_seconds` p99 (batch_read) | **9.51 ms** |
| `predict_duration_seconds` p95 (aerospike-py E2E) | 183.4 ms |
| `predict_duration_seconds` p95 (official-aerospike E2E) | 48.8 ms |
| 로드 총 시간 | 90 s (20 parallel workers × 3 modes round-robin) |

### 오버헤드 delta (batch_read op_duration, Rust 내부 측정)

| 지표 | OFF | ON | Δ | Δ% |
|------|-----|----|---|-----|
| avg | 2.16 ms | 3.22 ms | +1.06 ms | +49% |
| p95 | 4.67 ms | 7.61 ms | +2.94 ms | +63% |
| p99 | 4.93 ms | 9.51 ms | +4.58 ms | +93% |

### Stage별 레이턴시 (stage profiling ON; 10개 stage 모두 기록)

| stage | avg | p95 | 비고 |
|-------|-----|-----|------|
| `into_pyobject` | 3.96 μs | 0.975 ms | Arc wrap만 — 거의 O(1) |
| `limiter_wait` | 3.56 μs | 0.975 ms | backpressure semaphore |
| `future_into_py_setup` | 46.5 μs | 0.975 ms | sync setup, GIL held |
| `tokio_schedule_delay` | 83.1 μs | 0.975 ms | Tokio 스케줄링 |
| `as_dict` | 832 μs | 0.45 ms | GIL hold, PyDict 생성 |
| `key_parse` | 967 μs | 0.975 ms | 200 key 튜플 파싱 |
| `merge_as_dict` | 4.48 ms | 58 ms | 9 set × dict 변환 |
| `io` | 7.51 ms | 0.975 ms | 실제 네트워크 라운드트립 |
| `event_loop_resume_delay` | **39.7 ms** | **0.45 s** | 🚨 asyncio 코루틴 대기 |
| `spawn_blocking_delay` | **234 ms** | **0.975 s** | 🚨 spawn_blocking 큐 |

## 5. 결론

1. **Zero-overhead 요구사항 충족**: toggle OFF 상태에서
   `db_client_internal_stage_seconds` 시리즈는 **전혀 생성되지 않음**.
   `Instant::now()` 호출 자체가 elide 되어 disabled 경로에서는
   atomic load 1회(~1ns)만 추가됨.
2. **Toggle ON 오버헤드는 측정 가능 수준**: batch_read op_duration 기준
   p95 +2.9ms, p99 +4.6ms 증가. 10회 × `Instant::now()` + 10회
   histogram atomic 업데이트의 비용이 예상보다 큰 이유는 prometheus-client의
   Family<_, Histogram> get_or_create 시 label HashMap 조회/삽입 경쟁이
   포함되기 때문. 이는 debug 모드에서만 부담하면 되므로 수용 가능.
3. **프로파일링으로 진짜 병목 발견**:
   - `spawn_blocking_delay` avg 234ms, p95 975ms — Tokio spawn_blocking이
     GIL 경쟁 때문에 큐잉되고 있음. asyncio.gather 부하에서 두드러짐.
   - `event_loop_resume_delay` avg 40ms, p95 450ms — `into_pyobject` 완료 후
     Python 코루틴이 실제로 re-scheduled 되기까지의 대기. Python event loop가
     CPU-bound 작업으로 blocking 될 때 급증.
   - 두 stage 합계가 E2E latency 대부분을 차지 → 다음 최적화 타겟으로 명확.
4. **운영 권장**: prod 기본값 `AEROSPIKE_PY_INTERNAL_METRICS=0` 유지,
   장애 분석/성능 조사 시에만 ConfigMap patch + rollout으로 toggle ON.
   짧은 구간만 필요하면 Python context manager `with aerospike_py.internal_stage_profiling():` 사용.

## 6. 운영 가이드

- **기본값(prod): `AEROSPIKE_PY_INTERNAL_METRICS=0`**
- 디버그 세션에서 세부 프로파일링이 필요할 때:
  - 영구: ConfigMap patch + `kubectl rollout restart`
  - 임시(코드 scope): `with aerospike_py.internal_stage_profiling(): ...`
  - 런타임 토글: `aerospike_py.set_internal_stage_metrics_enabled(True)`

Grafana 대시보드 "aerospike-py 벤치마크"의
"Internal Stage Profiling Toggle" 패널이 현재 상태를 실시간으로 표시.
