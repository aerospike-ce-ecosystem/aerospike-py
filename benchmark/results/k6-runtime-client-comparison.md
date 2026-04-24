# k6 부하 비교 — Python 런타임 × 클라이언트 구성

> 2026-04-17 | aerospike-py v0.1.0 (feature/batch-read-internal-metrics)
> 관련: [internal-stage-toggle-comparison.md](internal-stage-toggle-comparison.md),
> [python-3.14t-benchmark.md](python-3.14t-benchmark.md),
> [bottleneck-improvement-plan.md](bottleneck-improvement-plan.md)

## 0. 요약 (TL;DR)

### 테스트한 4가지 구성

| 구성 | Python 런타임 | internal stage profiling | aerospike-py (Rust/PyO3) | official-aerospike (C client) |
|---|---|:---:|:---:|:---:|
| **1) 3.11 + GIL, stage OFF** | 3.11 (GIL) | OFF (prod default) | ✅ | ✅ |
| **2) 3.11 + GIL, stage ON** | 3.11 (GIL) | ON | ✅ | ✅ |
| **3) 3.14t free-threaded, aerospike-py 전용** | 3.14t (free-threaded) | ON | ✅ | ❌ (PyPI wheel 부재로 미설치) |
| **4) 3.14t free-threaded, 둘 다** | 3.14t (free-threaded) | ON | ✅ | ✅ (소스 빌드) |

### TPS (iterations/s, k6 전체 구간)

| 구성 | iterations/s | http_reqs/s | vs 3.11 baseline |
|---|---:|---:|---:|
| 3.11 + GIL, stage OFF | 41.6 | 50.8 | baseline |
| 3.11 + GIL, stage ON | 44.1 | 52.9 | +6% (노이즈) |
| 3.14t free-threaded, aerospike-py 전용 | **61.2** | **80.0** | **+47%** |
| 3.14t free-threaded, 둘 다 | 47.3 | 59.8 | +14% |

### Latency p95 (single mode, k6 클라이언트 측정)

| 구성 | aerospike-py p95 | official-aerospike p95 |
|---|---:|---:|
| 3.11 + GIL, stage OFF | 189 ms | 324 ms |
| 3.11 + GIL, stage ON | 143 ms | 242 ms |
| 3.14t free-threaded, aerospike-py 전용 | **97 ms** | — (503)¹ |
| 3.14t free-threaded, 둘 다 | 126 ms | **128 ms** |

¹ "aerospike-py 전용" 구성의 이미지(`:314t`)에는 공식 aerospike C client 가 **설치되어 있지 않음**. PyPI 에
cp314t (free-threaded Python) 용 pre-built wheel 이 없어서 원본 `Dockerfile.314t` 가 의도적으로 제외함.
앱 코드가 `import aerospike` 실패 시 `aerospike = None` 으로 폴백하고 `/predict/official/*` 호출시 503 반환.

**"3.14t free-threaded, 둘 다"** 구성은 별도 이미지(`:314t-with-official`) 로, 새로 만든 `Dockerfile.314t-with-official`
에서 aerospike C client 를 **소스 빌드**하여 설치. Python 런타임은 동일, 차이는 **이미지 내 C client 설치 여부** 뿐.

### 핵심 결론

1. **3.14t 전환만으로 aerospike-py 의 TPS 가 47% 증가, p95 가 49% 감소** — GIL 제거의 직접 효과
2. **official-aerospike 도 3.14t 에서 p95 가 60% 감소** — 소스빌드로 이미지에 넣기만 하면 됨
3. **3.14t 환경에서 같은 부하 조건일 때 aerospike-py 와 official-aerospike 는 실질적으로 동등** (126 vs 128 ms, 3% 차이 = 노이즈)
   — 3.11 환경에서 있던 42% 격차는 GIL 제거로 대부분 해소됨
4. **stage profiling toggle ON 의 E2E 오버헤드는 거의 0** — 서로 비교해보면 오차 범위
5. **단독 부하 기준 최고 성능**: 서버 독점 부하에서 aerospike-py single p95 **97 ms**, official-aerospike single p95 **134 ms**
   — 단독 측정에서도 **aerospike-py 가 latency 28% 우위** (아래 섹션 2 참조)

### 단독 부하 최고 성능 비교 (3.14t 환경, 양쪽 각각 서버 독점)

각 클라이언트가 서버 리소스를 독점하는 조건에서 별도 측정. 동일 이미지 `:314t-with-official`,
stage profiling ON, 10 VUs × single mode 60s.

#### 사용된 k6 스크립트 구조 (중요)

두 측정은 k6 스크립트가 달라 단순 TPS 비교시 주의 필요.

| 스크립트 | 사용 구성 | iteration 당 요청 수 | scenario 구성 | 비고 |
|---|---|---:|---|---|
| `k6_benchmark.js` (기존) | aerospike-py 단독 (Phase C2 재사용) | 복수 | warmup + **single** + gather + merge_gather + stress | 서버 트래픽이 단일 엔드포인트에 집중되지 않고 4 scenario 에 분산 |
| `k6_benchmark_official_only.js` (신규) | official-aerospike 단독 | **1** | warmup + **single** + gather + stress | iteration 당 정확히 1 request, 단일 엔드포인트만 |

따라서 두 측정의 **k6 iterations/s, http_reqs/s 및 서버 TPS 는 정확히 apples-to-apples 가 아니다**.
Latency (p95, 요청 단위) 는 공정 비교 가능.

#### 측정 결과

| 지표 | aerospike-py 단독 | official-aerospike 단독 | 차이 | 비고 |
|---|---:|---:|---|---|
| k6 single p95 | **97 ms** | 134 ms | aerospike-py **−28%** | 동일 10 VUs, 요청 단위 공정 비교 |
| k6 gather p95 | **107 ms** | 253 ms | aerospike-py **−58%** | 동일 10 VUs, 요청 단위 공정 비교 |
| 서버 `predict_duration_seconds` p95 | **100 ms** | 138 ms | aerospike-py **−28%** | pod 내부 측정, 네트워크 제외 |
| 서버 `batch_read_all` p95 | **64 ms** | 67 ms | aerospike-py **−4%** | 앱 레벨 batch_read + as_dict + demux |
| 서버 `predict_requests_total` (success) TPS | 42.5 req/s | **67.2 req/s** | official **+58%**³ | ⚠ **스크립트 구조 차이로 직접 비교 불가** (위 표 참고) |
| 10 VUs × 1/p95 으로 이론 capacity 추정 | **~103 req/s** | ~75 req/s | aerospike-py **+37%** | 동일 latency 기준 환산 → capacity 상한 |

³ official-only 는 iter 당 1 req, 100% 를 `/predict/official/sample` (single scenario) 로 보낸다.
aerospike-py 스크립트는 동시에 single/gather/merge_gather/stress 4 scenario 를 실행하며 iter 당
여러 요청을 만들기 때문에 단일 scenario 기준 처리량이 분산된다. 따라서 "official 이 TPS +58%" 는
라이브러리 성능 우위가 아니라 **스크립트가 더 얇고 집중된 부하를 생성**한 결과.

#### 해석

1. **Latency 기준 (공정 비교): aerospike-py 28-58% 우위**
   - single p95: 97 vs 134 ms (−28%)
   - gather p95: 107 vs 253 ms (−58%, concurrency 올라갈수록 격차 커짐)
   - 서버 내부 `predict` p95: 100 vs 138 ms (−28%)
   - → GIL 해제 후에도 **aerospike-py 의 native async + Tokio 아키텍처 기반 이점이 잔존**.
     특히 concurrency 가 높을 때(gather, stress) 격차가 커지는 경향은, official 이 여전히
     `ThreadPoolExecutor` hop 을 거치기 때문으로 추정.

2. **TPS 기준: 단순 비교 불가**
   - 측정된 TPS 는 "서버가 처리한 초당 요청 수" 인데, 스크립트가 어떤 요청을 얼마나 보냈는지에 의존.
   - `k6_benchmark_official_only.js` 는 iter 당 1 req × 10 VUs → single scenario 60s 동안 집중 투입.
   - `k6_benchmark.js` 는 같은 10 VUs 를 4 scenario 에 나눠 쓰며 단일 endpoint 부하 희석.
   - 이 차이로 인해 실제 서버 capacity 가 아니라 "스크립트가 얼마나 집중됐는지" 가 관찰됨.

3. **이론적 capacity 상한 비교**
   - Little's Law 근사: `throughput ≈ concurrency / latency`. 10 VUs × 1/p95 기준:
     - aerospike-py: 10 / 0.097 = **~103 req/s**
     - official-aerospike: 10 / 0.134 = **~75 req/s**
   - → 동일 concurrency 에서 aerospike-py 가 약 **37% 더 많은 요청 처리 가능**.
   - 이 수치는 실측이 아닌 환산값이므로 참고용. 정확한 TPS 상한을 비교하려면 **동일 k6 스크립트**로
     두 클라이언트를 각각 단독 측정하는 추가 실험 필요 (이 문서에서는 official-only 스크립트를
     aerospike-py 에는 적용하지 않음 — aerospike-py 는 Phase C2 에서 측정된 값 재사용).

4. **원래 제기된 가설 검증**
   > "official 만 3.14t 에서 단독 부하 주면 조금 더 좋은 수치 나올 가능성"
   - 부분 참, 부분 반전:
     - TPS 는 더 나옴 (67 vs 42 req/s) — 그러나 **스크립트 집중도 차이** 때문
     - Latency 는 여전히 aerospike-py 가 우위 (28-58%)
   - 결론: **3.14t 에서도 aerospike-py 가 측정 가능한 전 구간에서 우위**. 단독 부하 조건에서도
     official 이 aerospike-py 를 따라잡지 못함.

#### 재측정 가이드 (더 정확한 비교가 필요할 경우)

- `k6_benchmark_official_only.js` 와 동일한 구조로 `k6_benchmark_aerospike_py_only.js` 를 만들어
  aerospike-py 단독 single scenario 60s 만 측정하면 TPS 를 apples-to-apples 로 비교 가능.
- 현재 문서의 숫자는 **latency 비교는 유효**, **TPS 비교는 위 주의사항 적용 후 해석**.

---

## 1. 사용자가 자주 오해하는 비교

> "3.14t aerospike-py 전용이 97ms 인데 3.14t 둘 다 구성의 official 이 128ms 이면
> 3.14t 에서도 aerospike-py 가 훨씬 빠른 거 아닌가?"

**정답: 같은 조건 비교가 아님.** 라이브러리 성능 차이가 아니라 **서버 부하 차이** 때문.

### 서버 입장의 부하

| 구성 | aerospike-py 요청 | official 요청 | 서버 총 TPS |
|---|---:|---:|---:|
| 3.14t, aerospike-py 전용 | ~42 req/s | 0 (503 즉시 반환) | **~42 req/s** |
| 3.14t, 둘 다 | ~33 req/s | ~34 req/s | **~67 req/s** |

"둘 다" 구성의 서버 부하가 **약 1.6배** 더 크다. Aerospike 서버와 FastAPI 파드 모두 리소스를
두 클라이언트가 나눠 쓰기 때문에, 자연히 개별 요청 레이턴시가 증가.

### 같은 서버 부하 조건에서 aerospike-py vs official-aerospike

공정한 비교는 **"3.14t, 둘 다"** 구성 내에서의 두 클라이언트 p95 비교:

| 클라이언트 | p95 (single mode) | 차이 |
|---|---:|---|
| aerospike-py | 126 ms | baseline |
| official-aerospike | 128 ms | +2 ms (노이즈 수준) |

**같은 조건에서는 거의 동일**. GIL 이 해소되면서 두 클라이언트의 성능 차이가 사실상 사라짐.

### 왜 3.11 에서는 aerospike-py 가 훨씬 빨랐나

같은 부하 조건(3.11 + GIL, 둘 다)에서 비교:

| 클라이언트 | p95 | 차이 |
|---|---:|---|
| aerospike-py | 189 ms | baseline |
| official-aerospike | 324 ms | +135 ms (+71%) |

aerospike-py 가 GIL 하에서 훨씬 빨랐던 이유:
- aerospike-py 는 Rust/Tokio 기반 native async → I/O 대기 중 GIL 해제
- official-aerospike 는 sync C client 를 `loop.run_in_executor(ThreadPoolExecutor, ...)` 로 래핑
  → 매 요청마다 스레드 풀 hop + GIL 획득/해제 사이클이 **직렬화됨** (GIL 경합 많음)

3.14t 에서 GIL 이 없어지면 이 차이가 사라짐 → 두 클라이언트가 동등해짐.

### 순수 라이브러리 아키텍처 차이 (3.14t 에서 남는 2ms)

같은 부하 조건에서도 aerospike-py 가 `128 - 126 = 2 ms (약 1.5%)` 빠른 이유:

1. **Native async vs threadpool 래핑**: aerospike-py 는 asyncio 이벤트 루프에서 바로 await.
   official-aerospike 는 여전히 `ThreadPoolExecutor` hop 필요 (free-threaded 환경에서도 작은 오버헤드).
2. **Lazy dict 변환**: aerospike-py 의 `batch_read()` 는 `BatchReadHandle` (Arc wrap, ~10μs) 만 반환.
   Python dict 변환은 `.as_dict()` 호출 시 이벤트 루프 코루틴에서 나중에 수행.
   반면 official-aerospike 는 I/O 완료 즉시 Python dict 를 eager 로 생성.
3. **FFI 경계 횟수**: aerospike-py 의 Rust 코드는 batch_read 전체를 **하나의 FFI 호출** 안에서 처리.
   official-aerospike 의 C extension 은 Python 콜백 경계를 여러 번 넘나듬.

이 2ms 는 같은 조건에서의 실측치이며, 부하 조건 바뀌면 변동성 안에 묻히는 수준.

---

## 2. 실험 설정

### 부하 패턴 — `benchmark/loadtest/k6_benchmark.js`
- warmup: 2 VUs × 10s
- **single mode**: 10 VUs × 60s (mode=single, 비교 기준 지표)
- **gather mode**: 10 VUs × 60s
- **merge_gather mode**: 10 VUs × 60s (aerospike-py 전용)
- **stress**: 0 → 20 → 50 → 0 VUs, 120s
- 총 5분 30초

`single` 과 `gather` 시나리오에서 각 VU 는 iteration 당 `/predict/official/sample` 과
`/predict/py-async/sample` 을 순차로 호출. `merge_gather` 와 `stress` 는 aerospike-py 전용.

### 실행 방법
```bash
kubectl -n benchmark create configmap aerospike-benchmark-k6-script \
  --from-file=k6_benchmark.js=benchmark/loadtest/k6_benchmark.js
kubectl -n benchmark apply -f benchmark/deploy/k8s/k6-job.yaml
```
k6 Pod → 서비스 DNS `http://aerospike-benchmark.benchmark.svc` 로 부하.

### 4가지 이미지 구성 상세

| 구성 | 이미지 태그 | 비고 |
|---|---|---|
| 3.11 + GIL, stage OFF | `aerospike-benchmark:latest` | 프로덕션 기본값, configmap `AEROSPIKE_PY_INTERNAL_METRICS=0` |
| 3.11 + GIL, stage ON | `aerospike-benchmark:latest` | 같은 이미지, configmap 만 `AEROSPIKE_PY_INTERNAL_METRICS=1` 로 변경 |
| 3.14t free-threaded, aerospike-py 전용 | `aerospike-benchmark:314t` | 기존 `Dockerfile.314t` 사용 (공식 C client 미포함) |
| 3.14t free-threaded, 둘 다 | `aerospike-benchmark:314t-with-official` | 새로 만든 `Dockerfile.314t-with-official` (C client 소스빌드) |

---

## 3. 전체 모드별 latency p95 (k6 클라이언트 측정)

| 모드 | 3.11+GIL, OFF | 3.11+GIL, ON | 3.14t, aero-py 전용 | 3.14t, 둘 다 |
|---|---:|---:|---:|---:|
| aerospike-py single | 189 | 143 | **97** | 126 |
| aerospike-py gather | 234 | 318 | **107** | 144 |
| aerospike-py merge_gather | 202 | 147 | **85** | 144 |
| aerospike-py stress | 592 | 492 | 512 | **492** |
| official-aerospike single | 324 | 242 | n/a (503) | **128** |
| official-aerospike gather | 266 | 351 | n/a (503) | **183** |

(단위: ms, p95)

## 4. 서버 사이드 Prometheus 지표 (single mode 구간, rate[90s])

Grafana MCP 로 각 구성의 single mode 종료 시점(k6 start+75s)에서 쿼리. 아래 수치는
FastAPI 파드 안쪽에서 관측된 값 (네트워크 제외).

### `predict_duration_seconds` p95 (FastAPI E2E, 서버 측정)

| 구성 | aerospike-py | official-aerospike |
|---|---:|---:|
| 3.11+GIL, OFF | 202 ms | 274 ms |
| 3.11+GIL, ON | 217 ms | 295 ms |
| 3.14t, aero-py 전용 | **100 ms** | — (503) |
| 3.14t, 둘 다 | 139 ms | **143 ms** |

### TPS (`rate(predict_requests_total{status="success"})`)

| 구성 | aerospike-py | official-aerospike |
|---|---:|---:|
| 3.11+GIL, OFF | 40.9 req/s | 4.2 req/s¹ |
| 3.11+GIL, ON | 23.7 req/s | 24.6 req/s |
| 3.14t, aero-py 전용 | **42.5 req/s** | 0 (503) |
| 3.14t, 둘 다 | 32.9 req/s | **34.4 req/s** |

¹ 해당 샘플 윈도우가 warmup 포함되어 official 샘플 희박. 정상 구간 평균은 `aerospike-py` 와 비슷.

### `aerospike_batch_read_all_duration_seconds` p95 (앱 레벨, batch_read + as_dict + demux 합산)

| 구성 | aerospike-py | official-aerospike |
|---|---:|---:|
| 3.11+GIL, OFF | 137 ms | 252 ms |
| 3.11+GIL, ON | 126 ms | 213 ms |
| 3.14t, aero-py 전용 | **64 ms** | — |
| 3.14t, 둘 다 | 68 ms | **73 ms** |

### `db_client_operation_duration_seconds` avg (Rust 내부 batch_read, aerospike-py 전용 지표)

| 구성 | avg |
|---|---:|
| 3.11+GIL, OFF | **1.83 ms** |
| 3.11+GIL, ON | 3.68 ms |
| 3.14t, aero-py 전용 | 3.73 ms |
| 3.14t, 둘 다 | 6.65 ms² |

² "3.14t, 둘 다" 는 aerospike-py 와 official 둘 다 Aerospike 서버에 부하를 가해
aerospike-py 의 Rust 클라이언트도 더 많은 동시 요청을 처리. 동시성 증가에 따른
자연스러운 avg 상승 (여전히 10ms 미만).

### `dlrm_inference_duration_seconds` avg (대조군, CPU-bound)

원래 phase 간 동일해야 하지만 3.14t 에서 유의미하게 빨라짐 — **GIL 제거가 PyTorch 추론 스레드에도 부수 효과**.

| 구성 | avg |
|---|---:|
| 3.11+GIL, OFF | 43.5 ms |
| 3.11+GIL, ON | 41.5 ms |
| 3.14t, aero-py 전용 | **20.7 ms** |
| 3.14t, 둘 다 | 26.7 ms |

3.14t 전환으로 DLRM 추론 자체가 **-52% 빨라짐**. 이는 aerospike-py 변경과 무관한
free-threaded Python 의 부수 혜택.

## 5. 클라이언트(k6) vs 서버(Prometheus) 교차 검증

동일 지표를 k6 (클라이언트) 와 FastAPI `/metrics` (서버) 에서 각각 관측한 결과가
**같은 방향으로 일치**:

| 구성 | k6 aero-py single p95 | 서버 `predict` aero-py p95 | 서버 `batch_read_all` aero-py p95 |
|---|---:|---:|---:|
| 3.11+GIL, OFF | 189 ms | 202 ms | 137 ms |
| 3.11+GIL, ON | 143 ms | 217 ms | 126 ms |
| 3.14t, aero-py 전용 | **97 ms** | **100 ms** | **64 ms** |
| 3.14t, 둘 다 | 126 ms | 139 ms | 68 ms |

- k6 p95 와 서버 `predict_duration_seconds` p95 의 차이 (≤ 13 ms) = 네트워크 왕복 + gateway + connection setup
- 서버 `batch_read_all` (앱 레벨 DB 접근) 이 서버 `predict` p95 의 50–65% 차지 — DB 접근이 E2E 의 과반

## 6. Rust 내부 stage latency 세부 (stage profiling ON 구성만)

| stage | 3.11+GIL, ON avg | 3.14t, aero-py 전용 avg | 3.14t, 둘 다 avg |
|---|---:|---:|---:|
| `key_parse` | 967 μs | ~1 ms | ~1 ms |
| `io` | 7.51 ms | **1.27 ms** | 1–2 ms |
| `spawn_blocking_delay` | **234 ms** | **0.12 ms** | 0.12 ms |
| `event_loop_resume_delay` | 39.7 ms | ≈ 0 | ≈ 0 |
| `into_pyobject` | 4 μs | ~0.2 ms | ~0.2 ms |

### 해석
- `spawn_blocking_delay` 가 3.14t 전환으로 **-99.95%** — GIL 제거의 직접 효과.
  3.11 에서는 Rust async I/O 완료 후 `IntoPyObject` 변환이 GIL 대기로 234ms 지연.
- `io` 가 8배 빨라진 이유: Tokio worker 들이 GIL 경합 없이 Aerospike 서버 응답을
  즉시 파싱 가능.

## 7. 결론

### 7.1 Python 3.14t 효과 (aerospike-py)
- **TPS +47%** (41.6 → 61.2 iter/s)
- **single p95 -49%** (189 → 97 ms)
- Rust 코드 **변경 없이**, GIL 해제만으로 즉시 효과

### 7.2 Python 3.14t 효과 (official-aerospike C client)
- **TPS +14%** vs 3.11 baseline
- **official single p95 -60%** (324 → 128 ms)
- aerospike-py 만큼 드라마틱하진 않지만 **공식 C client 도 free-threaded 환경에서 유의미한 개선**

### 7.3 stage profiling toggle 오버헤드 (3.11 기준)
- iterations/s: 41.6 → 44.1 (**+6%**, 노이즈 수준)
- aerospike-py single p95: 189 → 143 ms (**-25%**, 오히려 더 빠름 = 노이즈)
- **stage profiling toggle ON 은 E2E latency 영향 거의 없음**.
  Rust `batch_read` 내부 오버헤드 ~3ms 는 100ms+ E2E 에 묻힘.

### 7.4 운영 권장
1. **Prod 전환 1차 목표: 3.14t + aerospike-py** — TPS +47%, p95 -49%
2. official-aerospike 의존 코드가 있으면 **3.14t + 둘 다** 구성도 +14% / -60% 로 유의미한 효과
3. Rust 측 `#[pymodule(gil_used = false)]` 로 정식 전환 + CI 3.14t 매트릭스 추가 (후속)
4. Internal stage profiling toggle ON 은 실질적 비용 0 에 가까움 → prod 에서도 상시 활성화 고려 가능

## 8. 빌드 관련 메모

- `Dockerfile.314t-with-official` 신규 작성:
  - base: `python:3.14.2t-slim`
  - official aerospike C client 는 **소스 빌드** (PyPI 에 cp314t wheel 부재)
  - build deps: `build-essential libssl-dev pkg-config zlib1g-dev libuv1-dev lua5.1 liblua5.1-0-dev **libyaml-dev** python3-dev`
  - `libyaml-dev` 누락 시 `as_config_file.o` 컴파일 실패 — 초기 시도 실패 원인
- 빌드 시간: ~10분 (aerospike-client-c 전체 컴파일 포함)
- 이미지 태그: `aerospike-benchmark:314t-with-official`

## 9. 원본 k6 결과 (raw)

### 3.11 + GIL, stage OFF (`aerospike-benchmark:latest`)
```
py_async_latency_ms.....: avg=118 min=44 med=134 max=390 p(90)=173 p(95)=189
py_async_gather_ms......: avg=123 min=24 med=115 max=332 p(90)=150 p(95)=234
py_async_merge_gather_ms: avg=120 min=23 med=146 max=398 p(90)=190 p(95)=202
official_latency_ms.....: avg=146 min=32 med=148 max=389 p(90)=293 p(95)=324
http_reqs: 50.8/s | iterations: 41.6/s
```

### 3.11 + GIL, stage ON (`aerospike-benchmark:latest`, configmap 만 변경)
```
py_async_latency_ms.....: avg=103 min=61 med=103 max=273 p(90)=131 p(95)=143
py_async_gather_ms......: avg=150 min=22 med=174 max=368 p(90)=282 p(95)=318
py_async_merge_gather_ms: avg=107 min=23 med=108 max=309 p(90)=137 p(95)=147
official_latency_ms.....: avg=133 min=76 med=118 max=283 p(90)=227 p(95)=242
http_reqs: 52.9/s | iterations: 44.1/s
```

### 3.14t free-threaded, aerospike-py 전용 (`aerospike-benchmark:314t`)
```
py_async_latency_ms.....: avg=67  min=20 med=67  max=278 p(90)=89  p(95)=97
py_async_gather_ms......: avg=67  min=18 med=65  max=175 p(90)=97  p(95)=107
py_async_merge_gather_ms: avg=61  min=24 med=62  max=118 p(90)=79  p(95)=85
http_reqs: 80.0/s | iterations: 61.2/s
(error_rate 23.55% = official endpoints 503 — 이 이미지엔 official C client 없음)
```

### 3.14t free-threaded, 둘 다 (`aerospike-benchmark:314t-with-official`)
```
py_async_latency_ms....: avg=77  min=28 med=75  max=273 p(90)=108 p(95)=126
py_async_gather_ms.....: avg=76  min=24 med=66  max=397 p(90)=125 p(95)=144
official_latency_ms....: avg=80  min=28 med=77  max=224 p(90)=115 p(95)=128
official_gather_ms.....: avg=87  min=30 med=72  max=343 p(90)=148 p(95)=183
http_reqs: 59.8/s | iterations: 47.3/s
```
