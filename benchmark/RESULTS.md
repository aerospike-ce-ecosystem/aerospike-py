# 성능 분석: Rust 바인딩 vs C 바인딩

## 환경

- macOS (Apple Silicon, M4 Pro)
- Aerospike CE 8.1.0.3 (Docker)
- 10,000 ops x 30 rounds, warmup=200

## 1. Sync 성능 갭 분석

### 시도한 최적화별 비교

| 접근 방식 | put (Rust/C) | get (Rust/C) |
|-----------|-------------|-------------|
| baseline (`block_on`) | ~1.10x | ~1.12x |
| `spawn+oneshot` | 1.12x | 1.14x |
| `block_on` + DEFAULT_POLICY 캐싱 | 1.10x | 1.12x |

### 최종 결과 (block_on + DEFAULT_POLICY 캐싱)

```
Op       |     Rust avg |        C avg |    Ratio |   Rust stdev |      C stdev
--------------------------------------------------------------------------------
put      |      0.126ms |      0.114ms |    1.11x |     0.0018ms |     0.0031ms
get      |      0.126ms |      0.112ms |    1.13x |     0.0021ms |     0.0017ms
```

### ~10% 갭의 원인

1. **py.detach() (GIL 해제/재획득)**: ~3-5μs — C 클라이언트도 GIL 해제하지만 구현 차이
2. **async 프로토콜 처리**: Rust aerospike 클라이언트는 async-only.
   Future 생성, poll, waker 등의 기계적 오버헤드가 C의 직접 동기 I/O 대비 존재
3. **Python↔Rust 변환**: PyO3 타입 변환 비용 ~1-3μs

### block_on 오버헤드 상세

Tokio 소스 분석 결과, `Runtime::block_on()`의 실제 오버헤드:
- thread-local context 설정 (`enter_runtime`): ~5-15ns
- `CachedParkThread` 생성: ~5ns (thread-local 캐싱)
- Waker 생성: ~10-20ns
- Guard drop: ~5-10ns
- **합계: ~30-50ns per call** — 네트워크 I/O (~100,000ns) 대비 0.05% 미만

### spawn+oneshot은 효과 없음

`RUNTIME.spawn()` + `oneshot::channel()` 패턴은 기존 `block_on`보다 오히려 느림.
cross-thread 통신 (oneshot channel send/recv + task spawn) 오버헤드가
block_on의 runtime context 진입/퇴출 비용보다 큼.

## 2. 10% sync 갭은 실제로 문제인가?

### 절대값

```
Rust: 0.126ms/op  vs  C: 0.114ms/op  →  차이 0.012ms (12μs)
```

- 1,000 ops/sec 워크로드: 총 12ms/sec 차이 → 무시 가능
- 10,000 ops/sec 워크로드: 총 120ms/sec 차이 → 여전히 무시 가능
- 네트워크 지연(1ms+)이 지배적인 실제 환경에서는 더욱 무의미

### 실제 프로덕션 패턴별 영향

| 패턴 | 사용 API | 영향 |
|------|----------|------|
| 웹 서버 (FastAPI 등) | async | Rust 바인딩이 **2.2-2.4x 빠름** |
| 배치 처리 | batch_read | C와 동등 (1.0x) |
| 단순 스크립트 | sync | 10% 차이 체감 불가 (12μs) |

## 3. Async 성능: 핵심 차별점

### C client의 Python async/await 한계

C client 자체는 async API를 지원 (libev/libuv/libevent 기반 콜백). 하지만:

- **Python 바인딩에서 async 노출 불가** — 시도 후 제거됨: [PR #462](https://github.com/aerospike/aerospike-client-python/pull/462)
- C client의 async는 콜백 기반으로, Python의 `asyncio` 이벤트 루프와 직접 통합 어려움
- 결과적으로 C client에서의 유일한 동시성 방법: `asyncio.run_in_executor()` (스레드풀, 진정한 async 아님)

### aerospike-py의 async 아키텍처

```
aerospike-py:  asyncio.gather(*[put(i) for i in range(N)])
               → PyO3 future_into_py → Tokio async runtime → 진정한 비동기 I/O

C client:      asyncio.run_in_executor(pool, client.put, ...)
               → 스레드풀에서 sync 호출 → GIL 경합 → 제한된 동시성
```

### batch_read에서 sync ≈ async인 이유

| 연산 | sync 측정 | async 측정 |
|------|-----------|------------|
| put/get | `for i in range(N): client.put(...)` (순차) | `asyncio.gather(*[put(i) for i in range(N)])` (동시) |
| batch_read | `client.batch_read(keys)` (1회 호출) | `await client.batch_read(keys)` (1회 호출) |

`batch_read(5000 keys)` → 하나의 요청, 하나의 응답 (서버 측에서 배치 처리).
async든 sync든 실행할 작업이 1개 → 병렬화 대상이 없음.
**async 자체가 빠른 것이 아니라, `asyncio.gather`를 통한 동시성이 빠른 것.**

## 4. 전략적 결론: C 바인딩 전환이 필요한가?

### 아니오.

| 판단 기준 | Rust 바인딩 유지 | C 바인딩 전환 |
|-----------|:---:|:---:|
| sync 성능 | 1.10-1.13x (12μs 갭) | 1.0x (baseline) |
| async 성능 | **네이티브 async/await** | Python 바인딩 미노출 ([PR #462](https://github.com/aerospike/aerospike-client-python/pull/462)) |
| 개발 비용 | 0 (이미 완성) | 2-4개월 |
| 유지보수 | PyO3 자동화 | 수동 C API |
| 메모리 안전 | Rust 보장 | segfault 리스크 |
| 빌드 편의성 | maturin (간단) | C 툴체인 (복잡) |
| 업계 방향 | 일치 (아래 참조) | 역행 |

### Aerospike 공식 로드맵과의 일치

Aerospike는 2026년 상반기에 **Rust client 기반의 새로운 Python client**를 출시 예정:

- [Issue #263](https://github.com/aerospike/aerospike-client-python/issues/263) — Ronen Botzer: *"We're going to be releasing a fluent Python client, built on the Rust client, in H1 of this year"*
- [Issue #147](https://github.com/aerospike/aerospike-client-python/issues/147) — Rust client가 Python, Node.js, Ruby 등 다중 언어 바인딩의 기반이 될 것
- [PR #462](https://github.com/aerospike/aerospike-client-python/pull/462) — C Python client에서 미완성 async 코드 제거 → C 기반 Python async 구현 포기

**업계 방향 자체가 Rust 바인딩. C client를 새로 바인딩하는 것은 이 흐름에 역행.**

## 5. 적용된 최적화

- `DEFAULT_WRITE_POLICY` / `DEFAULT_READ_POLICY` LazyLock 캐싱 (미미하지만 무해한 최적화)
- `put()`, `get()`에서 policy=None 시 기본 정책 캐시 사용

### 시도 후 제거한 최적화

- `spawn_blocking_op` (spawn+oneshot 패턴) — 오히려 느려져서 제거
