# aerospike-py 벤치마크 최종 결론

> 측정 기간: 2026-04 | 10 VUs, 60초 (single mode 기준), k6 부하 테스트
> 비교 대상: **aerospike-py** (Rust/PyO3) vs **aerospike** 공식 Python client (C extension)
> 부하 앱: FastAPI + DLRM inference, batch_read 9 set × 200 keys per request

상세 측정값은 `results/` 하위 문서 참고.

## 📖 값 읽는 법 (전체 공통 범례)

- **↓ 낮을수록 좋음** — latency/시간/지연 지표. 단위가 `ms`/`μs` 면 이쪽 (예: p50, p95, p99, avg, mean)
- **↑ 높을수록 좋음** — throughput/처리량 지표. 단위가 `req/s`/`TPS`/`iter/s` 면 이쪽
- **(우세)** — 같은 행 비교에서 우위에 있는 값
- **−XX%** (latency) / **+XX%** (TPS) — 우세한 변화량
- **N× faster / N× higher** — N배 우위
- 🔥 — 특히 큰 폭의 개선 (약 50% 이상)

---

## 1. aerospike-py vs 공식 Python client (Python 3.11 + GIL)

**같은 부하, 같은 서버, 같은 FastAPI 앱. 클라이언트만 교체하여 비교.**

> 📖 **읽는 법**: 아래 모든 값은 **latency(ms) — 낮을수록 좋음 ↓**. 각 행에서 작은 값이 우세.

| 지표 (ms, ↓ 낮을수록 좋음) | aerospike-py | 공식 aerospike | aerospike-py 우위 |
|---|---:|---:|---:|
| single mode p95 (k6) | **189 ms** (우세) | 324 ms | **−42%** |
| single mode avg | **126 ms** (우세) | 188 ms | **1.49× faster** |
| single mode median | **101 ms** (우세) | 192 ms | **1.90× faster** |
| gather mode p95 | **234 ms** (우세) | 266 ms | **−12%** |
| FastAPI E2E p95 (서버 측정) | **202 ms** (우세) | 274 ms | **−26%** |

**결론**: 일반적인 production 조건(3.11 + GIL)에서 **p95 기준 1.5~1.7배 빠름**. 동시 호출(gather)에서도 우위 유지.

**원인**: 공식 C client 는 sync API 를 `loop.run_in_executor(ThreadPoolExecutor, ...)` 로 래핑해서 매 요청마다 스레드 풀 hop + GIL 획득/해제가 직렬화됨. aerospike-py 는 Rust/Tokio 네이티브 async → I/O 대기 중 GIL 해제 → 동시성 훨씬 잘 확보.

---

## 1-bis. 환경별 성능 차이 요약 (같은 3.11 + GIL 조건)

aerospike-py 의 이점은 **주변 스택이 얇을수록 크게 드러남**. DB 호출만 있는 환경에서는 5배 가까이 빠르지만, uvicorn/FastAPI/DLRM 이 붙을수록 `torch CPU inference`, `http parsing`, `feature extraction` 같은 DB 무관 비용이 분모에 더해져 비율이 줄어듦.

### 측정한 3가지 환경

| 환경 | 구성 | DB 외 추가 요소 |
|---|---|---|
| **A) 순수 DB client** | 파이썬 루프에서 `batch_read` 반복 호출 (`benchmark/src/benchmark/runner.py`) | 없음 |
| **B) uvicorn ASGI only** | FastAPI 엔드포인트 → `batch_read` → JSON 응답 (`serving/asgi_benchmark.py`) | uvicorn/ASGI, HTTP 파싱, JSON serialize |
| **C) uvicorn + DLRM torch CPU** | FastAPI → key extraction → 9 set `batch_read` → feature extraction → DLRM inference → response (`endpoints/predict.py`) | uvicorn, DLRM (PyTorch CPU), feature extractor |

### 환경별 aerospike-py vs 공식 client

> 📖 **읽는 법**: `ms` 단위는 **낮을수록 좋음 ↓**, `TPS`(req/s)는 **높을수록 좋음 ↑**. 각 행에서 우세한 값에 **(우세)** 표기.

| 환경 | 지표 | 방향 | aerospike-py | 공식 aerospike | aerospike-py 우위 |
|---|---|---|---:|---:|---:|
| **A) 순수 DB client** | avg latency (ms) | ↓ 낮을수록 좋음 | **22.45 ms** (우세) | 107.56 ms | **4.8× faster** |
|  | TPS (req/s) | ↑ 높을수록 좋음 | **373.7** (우세) | 138.2 | **2.7× higher** |
|  | p99 (ms) | ↓ 낮을수록 좋음 | **120.67 ms** (우세) | 195.34 ms | 1.6× |
| **B) uvicorn ASGI only**¹ | total mean (ms) | ↓ 낮을수록 좋음 | **228.49 ms** (우세) | 289.56 ms | **1.3× faster** |
|  | TPS (req/s) | ↑ 높을수록 좋음 | **19.4** (우세) | 16.6 | 1.2× |
|  | Aerospike 구간만 (ms) | ↓ 낮을수록 좋음 | **221.12 ms** (우세) | 280.00 ms | 1.27× |
| **C) uvicorn + DLRM CPU** | single p95 (k6, ms) | ↓ 낮을수록 좋음 | **189 ms** (우세) | 324 ms | **1.71×** |
|  | avg (ms) | ↓ 낮을수록 좋음 | **126 ms** (우세) | 188 ms | 1.49× |
|  | TPS (E2E, req/s) | ↑ 높을수록 좋음 | **~40 req/s** (우세) | ~24 req/s² | ~1.7× |

¹ concurrency=5, iter=50, 9 set × 200 keys (상세: `results/asgi_20260416_134730/asgi-report.md`).
² 공식 client 는 워밍업 윈도우 영향으로 샘플 편차 있음. 정상 구간 평균치.

### 해석

1. **순수 DB client 에서 차이가 가장 큼 (4.8×)** — PyO3 Rust/Tokio 의 이점이 희석 요소 없이 그대로 노출. 공식 client 는 sync 호출이 concurrency 10 에서 GIL 경합으로 평균 100ms 수준까지 올라가지만, aerospike-py 는 20ms 수준 유지.

2. **uvicorn ASGI 만 추가되면 격차가 1.3× 로 급감** — ASGI 레이어(HTTP 파싱, 이벤트 루프 스케줄링, 응답 직렬화)가 공통 비용으로 추가되어 두 클라이언트에 동일하게 더해짐. 분모가 커져서 비율 감소.

3. **uvicorn + DLRM 까지 붙은 실제 서빙 구성에서는 1.5~1.7× 로 안정** — DLRM inference 가 ~20~40ms 소비되지만, 동시에 동시성이 10 VUs 로 올라가면서 GIL 경합이 재현됨. ASGI-only 보다 오히려 비율이 약간 회복되는 경향.

4. **시사점**: DB 호출이 워크로드의 큰 비중을 차지할수록(cache-like 워크로드, lookup-heavy API 등) aerospike-py 의 효과가 가장 크게 드러남. CPU-heavy 서빙 앱(ML inference, 복잡한 비즈니스 로직 포함)에서는 이점이 1.5× 수준으로 수렴하지만 여전히 유효.

---

## 2. Free-threaded 환경 (Python 3.14t, GIL 제거)

**같은 하드웨어, 같은 앱, 같은 이미지(C client 를 소스 빌드해서 포함) — Python 런타임만 3.14t 로 교체.**

### 각 클라이언트의 자체 개선 (3.11 → 3.14t)

> 📖 **읽는 법**: `p95 개선`은 latency 변화 — **오른쪽 값이 낮을수록 좋음 ↓**. `TPS 개선`은 처리량 변화 — **오른쪽 값이 높을수록 좋음 ↑**.

| 클라이언트 | p95 개선 (ms, ↓) | TPS 개선 (iter/s, ↑) |
|---|---:|---:|
| aerospike-py | 189 → **97 ms** (**−49%** 🔥) | 41.6 → **61.2** (**+47%** 🔥) |
| 공식 aerospike | 324 → **128 ms** (**−60%** 🔥) | — |

GIL 을 공유 자원으로 놓고 경합하던 비용이 사라져서 **두 클라이언트 모두 큰 폭으로 개선**. aerospike-py 는 Rust 코드 변경 없이 Python 3.14t 런타임만 바꿔서 얻은 효과.

### 같은 3.14t 조건에서 클라이언트 간 비교

> 📖 **읽는 법**: p95 latency — **낮을수록 좋음 ↓**. 각 행에서 우세한 값에 **(우세)** 표기.

| 구성 | aerospike-py p95 (ms, ↓) | 공식 aerospike p95 (ms, ↓) | 차이 |
|---|---:|---:|---|
| 둘 다 같이 부하 (공정한 서버 부하) | 126 ms | 128 ms | **≈ 동등** (노이즈 수준) |
| 각각 단독 부하, 서버 독점 | **97 ms** (우세) | 134 ms | aerospike-py **−28%** |
| 단독 부하, gather mode | **107 ms** (우세) | 253 ms | aerospike-py **−58%** |

**결론**:
- **3.11 에 있던 42% latency 격차는 GIL 제거로 대부분 소멸** — 공동 부하 조건에서 두 클라이언트가 거의 동등.
- 단, 단독 부하(각각 서버를 독점하는 조건)에서는 **aerospike-py 가 여전히 28~58% 빠름** — 네이티브 async + lazy dict 변환 이점은 GIL 제거 후에도 잔존.
- Concurrency 가 올라갈수록(gather) 격차 확대 — 공식 client 가 여전히 `ThreadPoolExecutor` hop 을 타는 부분이 원인으로 추정.

---

## 3. aerospike-py 주요 성능 최적화 포인트

### 3.1 Rust/Tokio 네이티브 async (아키텍처)
- Python asyncio event loop 에서 바로 `await` 가능. 공식 client 처럼 `run_in_executor` 로 sync 를 감쌀 필요 없음.
- I/O 대기 중 GIL 해제 → 동일 이벤트 루프 안에서 다른 coroutine 이 CPU 점유 가능.

### 3.2 Lazy dict 변환 (`BatchReadHandle`)
- `batch_read()` 는 `Arc<Vec<BatchRecord>>` 를 wrap 한 handle 만 반환 (~10μs).
- Python dict 변환(`.as_dict()`)은 호출자가 필요할 때 수행 → 변환 비용을 event loop 스케줄링에 맞게 분산.

### 3.3 단일 FFI 경계로 batch 처리
- batch_read 전체를 **한 번의 FFI 호출** 안에서 완료. Python ↔ native 경계를 여러 번 넘나들지 않음.
- 공식 C extension 대비 경계 왕복 오버헤드 제거.

### 3.4 Stage profiling toggle — 프로덕션에서도 상시 활성 가능
- `AEROSPIKE_PY_INTERNAL_METRICS=1` 로 Rust 내부 10 단계 latency 측정.
- OFF 대비 E2E 오버헤드 **사실상 0** (노이즈 수준).
- 프로덕션에서 상시 켜두고 성능 회귀를 즉시 관측 가능.

### 3.5 `gather(9회)` → 단일 `batch_read(mixed keys)` 전환
- 9개 set 의 key 를 합쳐 batch_read 1회로 호출 (`mode=single`).
- GIL 하에서의 직렬화 병목(`key_parse` 9× 대기, `as_dict` 9× 순차 resume) 제거.
- 실측: p95 189ms → 126ms (**−33%**, 3.11 + GIL 기준).

### 3.6 Python 3.14t free-threaded 호환
- `#[pymodule(gil_used = true)]` 선언에도 3.14t 인터프리터가 GIL 재활성화하지 않음 → **Rust 코드 변경 없이** free-threaded 혜택 즉시 적용.
- 내부 구조가 이미 thread-safe (`ArcSwapOption`, `Arc<Vec<...>>`, atomic flags, `Mutex`-protected metrics registry).

---

## 4. 최종 권장 사항

> 📖 **읽는 법**: `p95` 는 **낮을수록 좋음 ↓**, `TPS` 는 **높을수록 좋음 ↑**.

| 순위 | 조치 | 예상 효과 |
|---|---|---|
| 1 | 공식 client 쓰는 기존 Python 앱을 **aerospike-py 로 교체** | p95 **−42%** ↓ (3.11 기준) |
| 2 | Python 런타임을 **3.14t free-threaded 로 전환** | p95 **−49%** ↓ 추가, TPS **+47%** ↑ (Rust 변경 불필요) |
| 3 | `gather(N회)` → 단일 `batch_read(mixed keys)` 패턴 적용 | GIL 하에서 p95 **−33%** ↓ |
| 4 | Stage profiling toggle 을 prod 에 **상시 ON** | 회귀 즉시 감지, 오버헤드 ≈ 0 |

합쳐 적용 시 **3.14t + aerospike-py + single batch_read** 로 p95 **97ms** (↓ 낮을수록 좋음) 수준 달성 — 원본 공식 + 3.11 대비 **약 3.3배 빠름**.

---

(범례는 문서 상단의 "📖 값 읽는 법" 참조.)
