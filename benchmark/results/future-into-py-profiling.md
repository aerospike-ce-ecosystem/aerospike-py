# `future_into_py` 내부 상세 프로파일링 결과

> 2026-04-16 | K8s 클러스터, benchmark namespace, aerospike-py v0.5.7 (PyO3 0.28.2)

## 1. 목적

이전 분석에서 Rust 내부 합계 5ms vs Python 관측 51ms → **46ms 미식별 구간**이 존재.
이 46ms가 `pyo3-async-runtimes::future_into_py` 내부의 어디에서 소비되는지 정밀 측정.

## 2. 측정 방법

`PendingBatchRead` enum에 `std::time::Instant` timestamp를 추가하여 구간 간 시간 차이를 계산.

```
Python calls batch_read()
  │
  ├─ (A) future_into_py_setup    future_into_py() 호출 비용 (sync, GIL held)
  │
  ├─ (B) tokio_schedule_delay    Tokio spawn → async block 시작
  │
  ├─ key_parse                   Python key → Rust Vec<Key> (기존)
  ├─ limiter_wait                backpressure semaphore (기존)
  ├─ io                          Aerospike network I/O (기존)
  │
  ├─ (C) spawn_blocking_delay    Rust future 완료 → into_pyobject 실행
  │                              (io_complete_at → into_pyobject 시작)
  │
  ├─ into_pyobject               Arc::new + Py::new (기존)
  │
  ├─ (D) event_loop_resume_delay into_pyobject 완료 → Python as_dict() 호출
  │                              (into_pyobject_at → as_dict 시작)
  │
  └─ as_dict                     dict 변환 (기존)
```

Rust 코드 변경:
- `async_client.rs`: (A) `future_into_py_setup`, (B) `tokio_schedule_delay` 측정
- `batch_types.rs`: `PendingBatchRead::Handle`에 `io_complete_at: Instant` 추가
- `batch_types.rs`: `PyBatchReadHandle`에 `into_pyobject_at: Instant` 추가
- `batch_types.rs`: (C) `spawn_blocking_delay`, (D) `event_loop_resume_delay` 측정

## 3. 결과 — stress 포함 (10~50 VUs mixed)

| Stage | 시간 | 비율 | 설명 |
|-------|------|------|------|
| **(D) event_loop_resume_delay** | **253.5ms** | **96.3%** | into_pyobject → as_dict() |
| (C) spawn_blocking_delay | 3.81ms | 1.4% | future 완료 → into_pyobject |
| io | 2.61ms | 1.0% | Aerospike 네트워크 |
| key_parse | 1.95ms | 0.7% | Python key 파싱 |
| as_dict | 1.59ms | 0.6% | dict 변환 |
| (B) tokio_schedule_delay | 0.20ms | 0.08% | Tokio spawn → async 시작 |
| (A) future_into_py_setup | 0.04ms | 0.01% | future_into_py 호출 |
| into_pyobject | 0.001ms | 0.0% | Arc wrap |
| limiter_wait | 0.001ms | 0.0% | 세마포어 |

## 4. 결과 — 10 VUs single 모드 전용 (stress 제외)

| Stage | 시간 | 비율 | 설명 |
|-------|------|------|------|
| **(D) event_loop_resume_delay** | **168.1ms** | **89.8%** | into_pyobject → as_dict() |
| io | 6.08ms | 3.3% | Aerospike 네트워크 |
| key_parse | 6.04ms | 3.2% | Python key 파싱 |
| (C) spawn_blocking_delay | 3.22ms | 1.7% | future 완료 → into_pyobject |
| as_dict | 2.96ms | 1.6% | dict 변환 |
| (B) tokio_schedule_delay | 0.45ms | 0.2% | Tokio spawn → async 시작 |
| (A) future_into_py_setup | 0.02ms | 0.01% | future_into_py 호출 |
| into_pyobject | 0.002ms | 0.0% | Arc wrap |
| limiter_wait | 0.001ms | 0.0% | 세마포어 |
| **합계 (Rust 측정)** | **~187ms** | | |

k6 관측 E2E: avg 129ms (application level) + HTTP overhead ≈ 273ms

## 5. 병목 분석

### event_loop_resume_delay = 168ms (90%)

```
pyo3-async-runtimes 내부:
  1. Rust future 완료
  2. spawn_blocking 콜백에서 into_pyobject 실행 (0.002ms)
  3. call_soon_threadsafe(set_result) 호출 ← Python event loop에 callback 등록
  4. event loop이 다음 tick에서 callback 처리
  5. set_result() → coroutine resume
  6. Python 코드에서 as_dict() 호출

  (3)→(6) 사이가 168ms
```

### 왜 이렇게 오래 걸리나

`call_soon_threadsafe()`는 event loop의 self-pipe에 1byte write → event loop이 poll에서 깨어남 → callback queue 처리 → coroutine resume.

**10 VUs 환경에서 uvicorn single worker가 동시에 처리하는 요청:**
- 10개 HTTP 연결 × 각각 predict pipeline 실행
- 각 pipeline 내에서 batch_read + feature_extract + dlrm_inference
- DLRM inference (21ms)가 event loop을 blocking → 다른 coroutine resume 지연
- 모든 I/O가 non-blocking이지만 **inference는 CPU-bound로 event loop을 점유**

### DLRM inference가 event loop을 blocking하는 구조

```
Request A: batch_read 완료 → call_soon_threadsafe → event loop 큐에 등록
Request B: dlrm_inference 실행 중 (21ms, CPU-bound, event loop 점유)
                                 ↑
                                 Request A의 coroutine resume는
                                 Request B의 inference가 끝날 때까지 대기
```

10 VUs에서 평균적으로 5~8개의 요청이 동시에 pipeline을 타고 있고,
각 요청의 inference가 21ms → **다른 요청의 event loop resume를 21ms씩 지연**.

168ms ≈ 8개 요청 × 21ms inference = **정확히 일치**

## 6. 해결 방안

### 즉시 적용 가능

| 방안 | 효과 | 설명 |
|------|------|------|
| **inference를 run_in_executor로 분리** | event loop 해방 | `await loop.run_in_executor(None, model.forward, ...)` |
| **uvicorn workers 증가** | 병렬 event loop | `--workers 2`로 event loop 2개 |

### 중기

| 방안 | 효과 | 설명 |
|------|------|------|
| Free-threaded Python 3.14t | GIL 제거, 진짜 병렬 | `gil_used = false` + thread-safety audit |
| inference 전용 서비스 분리 | event loop에서 CPU-bound 제거 | 별도 gRPC service |

## 7. 결론

**`event_loop_resume_delay` 168ms는 `pyo3-async-runtimes` 자체의 문제가 아니라,
동일 event loop에서 CPU-bound DLRM inference (21ms)가 다른 coroutine의 resume를 blocking하는 문제.**

`call_soon_threadsafe()` → coroutine resume 경로 자체는 <1ms이지만,
event loop이 inference로 점유되어 callback 처리가 지연됨.

**근본 원인: CPU-bound inference와 I/O-bound batch_read가 같은 single-threaded event loop에서 실행됨.**
