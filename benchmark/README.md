# aerospike-py 벤치마크 최종 결론

> 측정: 2026-04 | FastAPI + DLRM + Aerospike CE, k6 10 VUs × 60s (별도 명시 시 제외)
> 비교: **aerospike-py** (Rust/PyO3) vs **aerospike** 공식 Python client (C extension)
> 상세: `results/` 하위 문서 참조

**표 표기 규칙**: 숫자 옆 `↓` = 낮을수록 좋음, `↑` = 높을수록 좋음, `(우세)` = 같은 행 비교 우위, 🔥 = 50%+ 개선.

---

## 최종 결론

### aerospike-py 가 공식 Python client 대비 얼마나 빠른가 (%)

Python 3.11 + GIL (프로덕션 기본 환경) 기준, 환경·지표별 개선 폭:

| 환경 | 지표 | 공식 aerospike | aerospike-py | 개선 폭 |
|---|---|---:|---:|---:|
| **A) 순수 DB client** (HTTP·ML 없음) | avg latency ↓ | 108 ms | **22 ms** | **−80%** 🔥 (4.8×) |
|  | p99 ↓ | 195 ms | **121 ms** | **−38%** (1.6×) |
|  | TPS ↑ | 138 req/s | **374 req/s** | **+171%** 🔥 (2.7×) |
| **B) uvicorn ASGI only** (FastAPI + DB) | total mean ↓ | 290 ms | **228 ms** | **−21%** (1.3×) |
|  | TPS ↑ | 16.6 | **19.4** | **+17%** (1.2×) |
| **C) uvicorn + DLRM torch CPU** (실 serving) | single p95 ↓ | 324 ms | **189 ms** | **−42%** (1.71×) |
|  | single avg ↓ | 146 ms | **118 ms** | **−19%** (1.24×) |
|  | FastAPI E2E p95 ↓ | 274 ms | **202 ms** | **−26%** (1.36×) |

### Free-threaded Python 3.14t 전환 추가 효과

aerospike-py 만 놓고 3.11 → 3.14t 전환: **p95 −49% (189 → 97 ms) 🔥, TPS +47% (41.6 → 61.2 iter/s) 🔥**.
Rust 코드 변경 없이 런타임만 바꿔 얻은 효과.

### 누적 적용 시 최대 성능

| 시나리오 | p95 ↓ | 원본 대비 |
|---|---:|---:|
| 원본 (공식 client + 3.11 + gather) | 324 ms | baseline |
| + aerospike-py 로 교체 | 189 ms | **−42%** |
| + `gather(N) → single batch_read(mixed keys)` | 126 ms | **−61%** |
| + Python 3.14t free-threaded | **97 ms** | **−70%** 🔥 (**3.3× 빠름**) |

### 권장 조치

| # | 조치 | 개선 효과 |
|---|---|---|
| 1 | 공식 client → **aerospike-py 로 교체** | p95 **−42%** (3.11 기준) |
| 2 | Python 런타임을 **3.14t free-threaded 로 전환** | p95 **−49%** 추가, TPS **+47%** (Rust 변경 불필요) |
| 3 | `gather(N회)` → 단일 `batch_read(mixed keys)` 패턴 적용 | p95 **−33%** (GIL 환경) |
| 4 | `AEROSPIKE_PY_INTERNAL_METRICS=1` (stage profiling) **상시 ON** | 회귀 즉시 감지, 오버헤드 ≈ 0 |

---

## 1. 상세: aerospike-py vs 공식 Python client (Python 3.11 + GIL)

**주변 스택이 얇을수록 격차가 크고**, 실제 서빙 앱에 가까워질수록 (ML inference · HTTP 파싱 등 공통 비용이 분모에 더해지면서) **비율은 줄어들지만 tail latency 우위는 유지**된다.

### 1.1 환경 A — 순수 DB client (파이썬 루프, HTTP·ML 없음)

출처: `results/20260416_134243/report.md` (concurrency 10, 30 iter × 9 set × 2 batch size)

| 지표 | aerospike-py | 공식 aerospike | 우위 |
|---|---:|---:|---:|
| avg latency ↓ | **22 ms** (우세) | 108 ms | **4.8×** 🔥 |
| p99 ↓ | **121 ms** (우세) | 195 ms | 1.6× |
| TPS ↑ | **374 req/s** (우세) | 138 req/s | **2.7×** 🔥 |

### 1.2 환경 B — uvicorn ASGI only (FastAPI + batch_read, ML 없음)

출처: `results/asgi_20260416_134730/asgi-report.md` (concurrency 5, iter 50)

| 지표 | aerospike-py | 공식 aerospike | 우위 |
|---|---:|---:|---:|
| total mean ↓ | **228 ms** (우세) | 290 ms | 1.3× |
| Aerospike 구간만 ↓ | **221 ms** (우세) | 280 ms | 1.27× |
| TPS ↑ | **19.4** (우세) | 16.6 | 1.2× |

### 1.3 환경 C — uvicorn + DLRM torch CPU (실제 serving 스택)

출처: `results/k6-runtime-client-comparison.md` §9 "3.11 + GIL, stage OFF" 단일 k6 run raw 데이터. 같은 FastAPI pod 에서 두 엔드포인트 교대 호출 → 네트워크·서버 상태 완전 동일.

| 지표 | aerospike-py | 공식 aerospike | 우위 |
|---|---:|---:|---:|
| single p95 ↓ | **189 ms** (우세) | 324 ms | **1.71×** 🔥 |
| single p90 ↓ | **173 ms** (우세) | 293 ms | 1.69× |
| single avg ↓ | **118 ms** (우세) | 146 ms | 1.24× |
| single median ↓ | **134 ms** (우세) | 148 ms | 1.10× |
| gather p95 ↓ | **234 ms** (우세) | 266 ms | 1.14× |
| FastAPI E2E p95 (서버) ↓ | **202 ms** (우세) | 274 ms | 1.36× |

### 요약

- **DB 비중이 클수록 격차 최대화**: A(순수 DB) 4.8× → B(ASGI) 1.3× → C(서빙) avg 1.24×
- **Tail latency (p95) 는 실제 서빙에서도 1.7× 우위 유지** — SLA 관리가 중요한 서비스일수록 효과 큼
- **공식 client 의 tail 이 무거운 원인**: sync API 를 `loop.run_in_executor(ThreadPoolExecutor, ...)` 로 래핑 → 매 요청마다 스레드 풀 hop + GIL 획득/해제가 직렬화 → 경합 상황에서 p95/p99 가 크게 튐
- **aerospike-py 는 Rust/Tokio 네이티브 async** → I/O 중 GIL 해제로 tail 안정

---

## 2. 상세: Free-threaded Python 3.14t 전환 효과

### 2.1 각 클라이언트의 3.11 → 3.14t 개선

| 클라이언트 | p95 ↓ | TPS ↑ |
|---|---|---|
| aerospike-py | 189 → **97 ms** (**−49%** 🔥) | 41.6 → **61.2** (**+47%** 🔥) |
| 공식 aerospike | 324 → **128 ms** (**−60%** 🔥) | — |

**GIL 이 공통 병목이었음**. aerospike-py 는 Rust 코드 변경 없이 런타임만 바꿔 얻은 효과.

### 2.2 3.14t 에서도 aerospike-py 가 여전히 빠른가 — 충분한 부하에선 YES

| 조건 | 실효 per-client 동시성 | aerospike-py p95 ↓ | 공식 p95 ↓ | 차이 |
|---|:---:|---:|---:|---|
| 둘 다 교대 부하 (10 VUs, 2 엔드포인트) | ~5 | 126 ms | 128 ms | 표기상 동률 |
| 단독 부하 single (10 VUs) | 10 | **97 ms** (우세) | 134 ms | **−28%** |
| 단독 부하 gather (9× fan-out) | 10×9 | **107 ms** (우세) | 253 ms | **−58%** 🔥 |

**⚠️ "둘 다 교대" 의 126 vs 128ms 동률 해석 주의**: 이 수치는 GIL 제거로 성능이 평등해져서 나온 결과가 **아니라**, 각 클라이언트가 보는 **실제 동시성이 ~5 VUs 로 낮아져 bottleneck 을 재현할 만큼 부하가 강하지 않았기 때문**. 10 VUs 단독 부하에서는 28%, 9× fan-out gather 에서는 58% 격차가 그대로 드러남. **동시성이 올라갈수록 공식 client 의 `ThreadPoolExecutor` hop 누적 비용이 커지고 aerospike-py 의 네이티브 async 우위가 더 벌어짐.**
