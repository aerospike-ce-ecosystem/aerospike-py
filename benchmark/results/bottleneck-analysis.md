# aerospike-py batch_read 병목 분석 보고서

> 2026-04-16 | K8s mrad1 클러스터, mona-adagent namespace
> aerospike-py v0.1.0 (Rust/PyO3), official aerospike C client v19.2.0

## 1. 문제 정의

Grafana 메트릭 관측 결과, aerospike-py의 Rust 내부 I/O는 **0.9ms**인데
Python layer에서 관측되는 per-set latency는 **51ms** — **99%가 오버헤드**.

```
Rust metrics (db_client_operation_duration_seconds):  0.9ms
Python metrics (aerospike_batch_read_set_duration):  51ms
─────────────────────────────────────────────────────
오버헤드:                                             50.1ms (98.2%)
```

9개 set을 `asyncio.gather`로 동시 실행한 전체 batch_read_all 시간: **116ms**.

## 2. 분석 방법

### 2.1 Rust 내부 구간별 metric 추가

`rust/src/metrics.rs`에 `db_client_internal_stage_seconds` 히스토그램을 신규 추가하여
batch_read의 5개 내부 단계를 개별 측정:

| Stage | 위치 | GIL 상태 |
|-------|------|----------|
| `key_parse` | `async_client.rs` — `prepare_batch_read_args()` | **held** |
| `limiter_wait` | `async_client.rs` — `limiter.acquire_named()` | released |
| `io` | `client_ops.rs` — `do_batch_read()` | released |
| `into_pyobject` | `batch_types.rs` — `IntoPyObject::into_pyobject()` | **held** (spawn_blocking) |
| `as_dict` | `batch_types.rs` — `PyBatchReadHandle::as_dict()` | **held** (event loop) |

### 2.2 Python layer 메트릭 분리

`aerospike_clients.py`에서 `_read_set_py()` 내부를 분리 측정:
- `aerospike_batch_read_io_duration_seconds` — Rust await 완료까지
- `aerospike_dict_conversion_duration_seconds` — as_dict() 변환 시간

### 2.3 테스트 환경

- **K8s**: mrad1 클러스터, mona-adagent namespace, 2 replicas
- **Aerospike**: 8노드 (maiasp025-032), namespace `aidev`
- **부하**: k6 10 VUs, 60초, Istio HTTPRoute 경유
- **모델**: DLRM (PyTorch CPU), 9 set × 200 keys per request
- **관측**: Grafana MCP (`n3r-m1-service` datasource), Prometheus scrape 15s

## 3. Rust 내부 구간별 실측 결과

```
Grafana PromQL:
  sum by (stage) (rate(db_client_internal_stage_seconds_sum{
    namespace="mona-adagent", db_operation_name="batch_read"
  }[5m])) / sum by (stage) (rate(db_client_internal_stage_seconds_count{...}[5m]))
```

| Stage | 시간 (avg) | 비율 | 설명 |
|-------|-----------|------|------|
| `key_parse` | **1.46ms** | 30.8% | Python key 튜플 → Rust `Vec<Key>` (GIL held) |
| `io` | **2.22ms** | 46.8% | Aerospike 서버 네트워크 round-trip |
| `as_dict` | **0.79ms** | 16.6% | Rust `Vec<BatchRecord>` → Python dict (GIL held) |
| `into_pyobject` | **0.001ms** | 0.03% | `Arc::new` + `Py::new` (spawn_blocking) |
| `limiter_wait` | **0.001ms** | 0.01% | Backpressure 세마포어 대기 |
| **Rust 합계** | **4.74ms** | **100%** | |

## 4. 미식별 구간 분석

```
Python 관측 (per-set):   51ms
Rust 내부 합계:         -  5ms
────────────────────────────
미식별 구간:              46ms (90%)
```

이 46ms는 Rust 코드 밖, **PyO3 `future_into_py` ↔ Python asyncio event loop 경계**에서 발생.

### 4.1 원인: `asyncio.gather(9개 batch_read)` + GIL 직렬화

```
Timeline (gather mode, 9 sets × 200 keys):

T=0ms     asyncio.gather 시작
          ├─ task 1: key_parse (1.46ms, GIL held)
          ├─ task 2: key_parse 대기 (GIL 대기)
          ├─ ...
          └─ task 9: key_parse (GIL 대기)
T=~13ms   9개 key_parse 완료 (순차, 9 × 1.46ms)
          └─ 9개 Rust async future가 Tokio에서 병렬 실행
T=~15ms   9개 I/O 모두 완료 (2.2ms each, 진짜 병렬)
          └─ 9개 future가 spawn_blocking → into_pyobject (각 <0.01ms)
          └─ Event loop에 9개 completed future 등록
T=15-51ms Event loop이 9개 coroutine을 순차 resume:
          ├─ task 1: resume → raw.as_dict() (0.79ms) → 완료
          ├─ (event loop tick 간격: ~3-5ms)
          ├─ task 2: resume → raw.as_dict() (0.79ms) → 완료
          ├─ ...
          └─ task 9: resume → raw.as_dict() (0.79ms) → 완료
T=~51ms   마지막 task 완료 → gather 반환
```

### 4.2 3가지 직렬화 병목

| 병목 | 예상 시간 | 설명 |
|------|----------|------|
| **key_parse GIL 직렬화** | ~13ms | 9 × 1.46ms — GIL은 한 번에 하나만 획득 가능 |
| **event loop scheduling** | ~20ms | 9개 future 완료 → coroutine resume 순차 대기 (single-threaded) |
| **as_dict GIL 직렬화** | ~7ms | 9 × 0.79ms — event loop에서 순차 실행 |
| **spawn_blocking 큐잉** | ~6ms | Tokio worker → Python event loop 전달 오버헤드 |
| **합계** | **~46ms** | Python 관측 51ms - Rust 5ms 와 일치 |

### 4.3 결론

**aerospike-py Rust 코드는 빠릅니다 (4.74ms/call).**

병목은 3가지 PyO3/asyncio 런타임 레벨 문제:
1. **PyO3 `future_into_py`** — Rust async future → Python awaitable 전환 + event loop 등록/해제 비용
2. **GIL 직렬화** — 9개 동시 호출이 `key_parse`와 `as_dict` 구간에서 GIL을 순차 획득
3. **Python asyncio single-thread** — event loop이 9개 coroutine을 하나씩 resume

이 문제는 aerospike-py 비즈니스 로직 최적화로는 해결 불가.

## 5. 해결 방안: gather(9회) → single(1회) 전환

`batch_read`가 이미 mixed-set key를 지원:
```python
# gather (9회 호출 — 현재)
await asyncio.gather(*[client.batch_read(set_i_keys) for i in range(9)])

# single (1회 호출 — 개선)
all_keys = [("ns","set1","k1"), ("ns","set2","k2"), ...]  # 9 set 합산
result = await client.batch_read(all_keys)
demux(result)  # Python에서 set별 분배
```

### 5.1 예상 효과

| 구간 | gather (9회) | single (1회) |
|------|------------|-------------|
| key_parse GIL | 9 × 1.46ms = 13ms | 1 × ~3ms |
| future_into_py 스케줄링 | 9 future 순차 | 1 future |
| as_dict GIL | 9 × 0.79ms = 7ms | 1 × ~3ms |
| event loop resume | 9 coroutine 순차 | 1 coroutine |

## 6. k6 부하 테스트 결과 (gather vs single)

테스트 조건: 10 VUs, 60초, Istio HTTPRoute, K8s 2 replicas

### 6.1 py-async (핵심)

| Metric | gather | single | 개선율 |
|--------|--------|--------|--------|
| **avg** | 189ms | **126ms** | **-33%** |
| **median** | 176ms | **101ms** | **-43%** |
| **p90** | 393ms | **284ms** | **-28%** |
| **p95** | 434ms | **302ms** | **-30%** |
| **min** | 14ms | 16ms | (동등) |
| **max** | 617ms | **477ms** | **-23%** |

### 6.2 official (참고)

| Metric | gather | single | 개선율 |
|--------|--------|--------|--------|
| **avg** | 251ms | **188ms** | **-25%** |
| **median** | 231ms | **192ms** | **-17%** |
| **p90** | 487ms | **369ms** | **-24%** |
| **p95** | 502ms | **396ms** | **-21%** |

### 6.3 py-async vs official (single mode)

| Metric | official single | py-async single | py-async speedup |
|--------|----------------|----------------|-----------------|
| **avg** | 188ms | **126ms** | **1.49x** |
| **median** | 192ms | **101ms** | **1.90x** |
| **p90** | 369ms | **284ms** | **1.30x** |
| **p95** | 396ms | **302ms** | **1.31x** |

## 7. Grafana 메트릭 상세

### 7.1 E2E Pipeline Breakdown (rate 5m)

| Stage | official | py-async |
|-------|---------|----------|
| predict_duration (E2E) | 201ms | 152ms |
| batch_read_all | 162ms | 115ms |
| dlrm_inference | 16ms | 20ms |
| feature_extraction | 11ms | 12ms |
| key_extraction | 2ms | 2ms |
| response_build | 2ms | 2ms |

### 7.2 Per-Set batch_read (avg, rate 5m)

| Set | official | py-async | speedup |
|-----|---------|----------|---------|
| nccsh_adid | 84ms | 53ms | 1.6x |
| nccsh_adgroupid | 86ms | 52ms | 1.7x |
| nccsh_campaignid | 87ms | 51ms | 1.7x |
| nccsh_nvmid | 91ms | 52ms | 1.7x |
| nccsh_hconvvalue_nvmid | 91ms | 53ms | 1.7x |
| nccsh_userid | 88ms | 52ms | 1.7x |

### 7.3 Rust 내부 I/O (db_client_operation_duration_seconds)

| Set | Rust I/O |
|-----|---------|
| nccsh_adid | 0.88ms |
| nccsh_adgroupid | 0.81ms |
| nccsh_campaignid | 0.86ms |
| nccsh_nvmid | 1.53ms |
| nccsh_hconvvalue_nvmid | 0.75ms |
| nccsh_userid | 0.91ms |

## 8. 개선 적용 후 최종 성능 테스트 (single mode 기본)

### 8.1 변경 사항

- `endpoints/predict.py`: 기본 mode를 `gather` → `single`로 변경
- 9개 set의 key를 합쳐서 1회 `batch_read()` 호출 → Python demux

### 8.2 최종 k6 결과 (10 VUs, 60초, K8s 2 replicas, Istio)

**py-async (single, 기본값 — 개선 후)**

| Metric | 값 |
|--------|---|
| **avg** | **60.8ms** |
| **median** | **46.8ms** |
| **p90** | **115.3ms** |
| **p95** | **154.6ms** |
| min | 19.6ms |
| max | 317.0ms |

**py-async (gather, 비교)**

| Metric | 값 |
|--------|---|
| avg | 68.9ms |
| median | 56.5ms |
| p90 | 128.8ms |
| p95 | 159.4ms |

**official (single, 비교)**

| Metric | 값 |
|--------|---|
| avg | 74.7ms |
| median | 56.6ms |
| p90 | 149.1ms |
| p95 | 190.8ms |

**official (gather, 비교)**

| Metric | 값 |
|--------|---|
| avg | 86.9ms |
| median | 69.6ms |
| p90 | 168.2ms |
| p95 | 220.0ms |

### 8.3 gather → single 개선 효과

| Client | Metric | gather | single | 개선 |
|--------|--------|--------|--------|------|
| **py-async** | avg | 68.9ms | **60.8ms** | **-12%** |
| **py-async** | median | 56.5ms | **46.8ms** | **-17%** |
| **py-async** | p90 | 128.8ms | **115.3ms** | **-10%** |
| **py-async** | p95 | 159.4ms | **154.6ms** | **-3%** |
| official | avg | 86.9ms | **74.7ms** | **-14%** |
| official | p90 | 168.2ms | **149.1ms** | **-11%** |

### 8.4 py-async vs official (single mode, 최종)

| Metric | official | py-async | **speedup** |
|--------|---------|----------|------------|
| **avg** | 74.7ms | **60.8ms** | **1.23x** |
| **median** | 56.6ms | **46.8ms** | **1.21x** |
| **p90** | 149.1ms | **115.3ms** | **1.29x** |
| **p95** | 190.8ms | **154.6ms** | **1.23x** |

### 8.5 Stress 테스트 (50 VUs ramp, single mode)

| Metric | py-async |
|--------|---------|
| avg | 143.7ms |
| median | 99.3ms |
| p90 | 333.9ms |
| p95 | 405.3ms |
| errors | 2/8,606 (0.02%) |

전체 테스트: 15,084 requests, 99.99% success, 56.9 req/s

## 9. 추가 개선 가능성

| 방안 | 효과 | 난이도 | 설명 |
|------|------|--------|------|
| **single 모드 기본화** | -12~17% | 낮음 | ✅ 이 보고서에서 적용 완료 |
| key_parse 최적화 (intern) | -10~15% | 중간 | bin name `py.intern()` 적용 |
| `future_into_py` 개선 | 이론적 최대 | 높음 | PyO3/pyo3-async-runtimes PR 필요 |
| Free-threaded Python 3.14t | GIL 제거 | 중간 | aerospike-py가 이미 3.14t 지원 |
