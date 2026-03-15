# Goal 2: 성능 (GIL-free, C 클라이언트 대비 우위)

## 설계 원칙

- Tokio worker 기본 2개 (`AEROSPIKE_RUNTIME_WORKERS`): GIL reacquire contention 최소화
- signal driver 비활성화(`enable_io()` + `enable_time()`, not `enable_all()`): Python signal 핸들러 충돌 방지
- ArcSwapOption: async client 상태 lock-free 접근

## 벤치마크 결과 (vs aerospike-client-python C 클라이언트)

| 경로 | put | get | batch_read_numpy |
|------|-----|-----|-----------------|
| Sync (sequential) | ~1.1x 느림 | ~1.1x 느림 | — |
| Async (concurrent) | **2.1x 빠름** | **1.6x 빠름** | **3.4x 빠름** |

## Sync gap 원인 (구조적 한계)

1. `py.detach()` GIL 전환 비용 ~3-5µs
2. async-only crate → `block_on` Future 생성 오버헤드
3. PyO3 타입 변환 ~1-3µs

→ 절대값 ~12µs 차이. async 경로가 핵심 차별화 포인트.

## 주요 파일

- `rust/src/runtime.rs` — 런타임 튜닝 근거
- `benchmark/bench_compare.py` — 비교 벤치마크
- `benchmark/RESULTS.md` — 상세 분석 및 근거
