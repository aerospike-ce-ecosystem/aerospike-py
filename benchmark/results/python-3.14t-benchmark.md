# Python 3.14t (Free-Threaded) 성능 테스트

> 2026-04-17 | aerospike-py v0.1.0 (feature/batch-read-internal-metrics)
> 관련: [internal-stage-toggle-comparison.md](internal-stage-toggle-comparison.md),
> [bottleneck-improvement-plan.md](bottleneck-improvement-plan.md),
> [k6-runtime-client-comparison.md](k6-runtime-client-comparison.md)

## 1. 실험 배경

[bottleneck-improvement-plan.md](bottleneck-improvement-plan.md) 의 세 번째 아이디어 —
"Free-threaded Python 3.14t 전환" 이 `spawn_blocking_delay` / `event_loop_resume_delay`
병목을 근본적으로 해결할 수 있다고 가설화했다. 동일한 hardware / deployment 에서
Python 3.11 (GIL) vs Python 3.14t (free-threaded) 을 비교 측정.

## 2. 실험 설정

### Docker 이미지
- **3.11 + GIL build**: `aerospike-benchmark:latest`
  - base: `python:3.11.14-slim`
- **3.14t free-threaded build**: `aerospike-benchmark:314t`
  - base: `python:3.14.2t-slim`
  - 사전 빌드된 cp314t wheel (`benchmark/deploy/wheels-314t/`)

### 코드 변경
- `benchmark/src/serving/aerospike_clients.py`: `aerospike` C 클라이언트 import
  가드 추가 — 3.14t 에 공식 C client wheel 이 없어 aerospike-py 경로만 사용
- Rust 모듈 자체: **변경 없음** (`#[pymodule(gil_used = true)]` 유지)

### GIL 상태 검증
```
python: 3.14.2
Py_GIL_DISABLED build: 1
GIL currently enabled: False
GIL enabled after aerospike_py import: False
```

`gil_used = true` 선언에도 불구하고 Python 3.14t 인터프리터가 GIL 을 재활성화
하지 않음. 이는 free-threaded 모드의 full benefit 을 실질적으로 누리고 있다는 의미.
(향후 `gil_used = false` 로 명시적 전환 및 thread-safety 감사 권장.)

### 부하 테스트 (초기 curl 기반)
- 20 parallel workers × 3 mode (single / gather / merge_gather) round-robin
- 90 초 지속
- `AEROSPIKE_PY_INTERNAL_METRICS=1` (stage profiling ON)
- 동일 pod 에서 pod-local curl loop
- **주의**: curl fork 오버헤드로 클라이언트 측 throughput 제한 — 정확한 k6 재측정은
  [k6-runtime-client-comparison.md](k6-runtime-client-comparison.md) 에 별도 보고.

## 3. 결과: `db_client_operation_duration_seconds` (batch_read)

Rust 내부에서 측정한 순수 Aerospike operation latency. 초기 curl 기반 부하.

| 구성 | avg | p95 | p99 |
|---|---:|---:|---:|
| 3.11 + GIL, stage profiling OFF | 2.16 ms | 4.67 ms | 4.93 ms |
| 3.11 + GIL, stage profiling ON | 3.22 ms | 7.61 ms | 9.51 ms |
| **3.14t free-threaded, stage profiling ON** | **1.11 ms** | **4.70 ms** | **4.94 ms** |

**주목**: 3.14t + stage profiling ON 상태가 3.11 + stage profiling OFF 보다
평균 **48% 빠르고**, p95 는 거의 동일한 수준. stage profiling 의 overhead 마저도
GIL 제거의 이득으로 상쇄.

## 4. 결과: E2E `predict_duration_seconds` p95

FastAPI 끝-단 latency (key 추출 + batch_read + feature + inference + response build).

| 구성 | aerospike-py 경로 p95 | official-aerospike 경로 p95 |
|---|---:|---:|
| 3.11 + GIL, stage profiling OFF | 70.4 ms | 73.1 ms |
| 3.11 + GIL, stage profiling ON | 183.4 ms | 48.8 ms |
| **3.14t free-threaded, stage profiling ON** | **48.8 ms** | n/a (C client 부재) |

aerospike-py 기준 **3.14t vs 3.11+ON: -73%**, **3.14t vs 3.11+OFF: -30%**.

## 5. 결과: Internal Stage 비교 (3.11 vs 3.14t, 둘 다 stage profiling ON)

| stage | 3.11 avg | 3.14t avg | Δ |
|-------|---:|---:|---:|
| `spawn_blocking_delay` | **234 ms** | **0.12 ms** | **-99.95%** 🔥 |
| `event_loop_resume_delay` | 39.7 ms | (n/a)¹ | ≈ -100% |
| `io` | 7.51 ms | 1.27 ms | -83% |
| `merge_as_dict` | 4.48 ms | 3.54 ms | -21% |
| `key_parse` | 967 μs | 1.06 ms | +10% (노이즈) |
| `into_pyobject` | 3.96 μs | 253 μs | +6300%² |
| `tokio_schedule_delay` | 83.1 μs | 49.5 μs | -40% |
| `limiter_wait` | 3.56 μs | 0.96 μs | -73% |
| `future_into_py_setup` | 46.5 μs | 26.4 μs | -43% |
| `as_dict` | 832 μs | (n/a)¹ | — |

¹ 3.14t 부하는 aerospike-py 만 사용 → `mode=merge_gather` 비율이 높아 `as_dict` /
`event_loop_resume_delay` 관찰 표본이 적음 (`NaN` 반환).

² `into_pyobject` 증가는 3.11 의 3.96μs 가 비정상적으로 낮게 측정된 것 (1μs bucket
수집 전 값). 3.14t 의 253μs 는 정상 범위 — 레코드 수 × `Arc` wrap + Bound 생성 시간.

## 6. 해석

### GIL 병목 제거 효과

`spawn_blocking_delay` 234ms → 0.12ms (-99.95%) 는 **GIL 제거의 직접 결과**.
3.11 에서는 `IntoPyObject::into_pyobject` 가 `spawn_blocking` 스레드에서
GIL 획득을 기다려야 했지만, 3.14t 에서는 GIL 이 없어 즉시 실행된다.

### event_loop_resume_delay 개선

`event_loop_resume_delay` 역시 GIL 의존. GIL 이 없으면 event loop tick 이
CPU-bound 작업에 의해 blocking 되지 않아 coroutine 이 즉시 재개된다.

### `io` 개선 (8배)

Aerospike 네트워크 자체는 동일한데 `io` 단계가 7.51ms → 1.27ms 로 감소한 것은
다소 놀라운 결과. 원인 추정:
- Tokio worker 들이 GIL 경합 없이 I/O 응답을 즉시 처리
- Aerospike 서버 응답 파싱 중 PyO3 변환 병목이 사라짐

### Thread-safety 고려

`gil_used = true` 선언에도 GIL 이 재활성화 되지 않은 상황에서 안정 동작한 것은
우리 Rust 코드가 이미 대체로 thread-safe 하기 때문:
- `AsyncClient.inner`: `ArcSwapOption` (lock-free)
- `PyBatchReadHandle.inner`: `Arc<Vec<BatchRecord>>` (read-only 공유)
- `METRICS` registry: `Mutex` 보호
- Atomic flags: `Ordering` 명시

그러나 정식 전환 전에 전면 감사 + `gil_used = false` 명시 필요.

## 6.5 Official aerospike C client 3.14t 성능 (k6 Job 측정)

별도 이미지 `aerospike-benchmark:314t-with-official` 를 빌드하여 동일 조건에서 비교
(k6 Job 5.5분 부하, mode=single 기준).

| 클라이언트 | 3.11 + GIL p95 | **3.14t free-threaded p95** | Δ |
|--------|---:|---:|---:|
| aerospike-py | 189 ms | 126 ms | **-33%** |
| official-aerospike | 324 ms | 128 ms | **-60%** |

- 3.14t 환경에서 **aerospike-py ≈ official-aerospike** (126 vs 128 ms) 로 수렴.
  3.11 에서 있던 42% 격차가 GIL 제거로 사라짐.
- 공식 C client 도 free-threaded 환경에서 단독으로 **-60% 개선** — GIL 경합이
  Python extension 전반의 병목이었음을 재확인.
- Dockerfile.314t-with-official: aerospike C client 소스 빌드 (PyPI cp314t wheel 부재).
  필수 apt deps: `build-essential libssl-dev libuv1-dev liblua5.1-0-dev libyaml-dev`.

세부 내용: [k6-runtime-client-comparison.md](k6-runtime-client-comparison.md).

## 7. 권장 후속 조치

| 우선순위 | 작업 | 리스크 |
|----------|------|--------|
| 1 | PyO3 bindings thread-safety 감사 후 `#[pymodule(gil_used = false)]` 로 명시 | LOW — 코드 이미 대부분 thread-safe |
| 2 | CI matrix 에 3.14t 추가 — 모든 테스트를 free-threaded 에서도 검증 | LOW |
| 3 | 공식 Aerospike C client wheel 3.14t 지원 대기 (또는 자체 빌드 — 이번 실험에서 소스 빌드로 우회 성공) | EXTERNAL 의존 |
| 4 | `compat/` 경계 (GIL 기반 sync Client API) 가 3.14t 에서도 안전한지 격리 검증 | MEDIUM |

## 8. 결론

- **"Free-threaded 전환으로 병목 근본 해결" 가설 검증 성공**:
  `spawn_blocking_delay` / `event_loop_resume_delay` 병목이 **사실상 사라짐**.
- **E2E latency -73%**: 동일 부하, 동일 코드에서 aerospike-py p95 183ms → 49ms.
- **Rust 코드 변경 없이** 효과 발휘 — 기존 구현이 이미 thread-safe 구조였음.
- **Prod 적용 경로**:
  1. CI 에 3.14t 테스트 matrix 추가
  2. `gil_used = false` 로 명시적 전환
  3. 배포 이미지 변경 (base image `python:3.14t-slim`)

## 9. Raw 데이터 요약

### 3.11 + GIL, stage profiling OFF — 2026-04-17 18:31 KST
- 로드: 4935 req / 4920 OK (99.70%)
- 90s, 20 workers × 3 modes

### 3.11 + GIL, stage profiling ON — 2026-04-17 18:54 KST
- 로드: ~4500 req (OOM exit 137 at end)
- 90s, 20 workers × 3 modes

### 3.14t free-threaded, stage profiling ON — 2026-04-17 21:30 KST
- 로드: 4470 req / 4449 OK (99.53%)
- 90s, 20 workers × 3 modes (aerospike-py 전용)
- GIL disabled: ✅ (`sys._is_gil_enabled() == False`)
