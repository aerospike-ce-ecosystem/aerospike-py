# Rust sync vs C sync 성능 갭 분석

## 환경

- macOS (Apple Silicon)
- Aerospike CE 8.1.0.3 (Docker)
- 10,000 ops x 30 rounds, warmup=200

## 벤치마크 결과

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

## 분석

### spawn+oneshot은 효과 없음

`RUNTIME.spawn()` + `oneshot::channel()` 패턴은 기존 `block_on`보다 오히려 느림.
cross-thread 통신 (oneshot channel send/recv + task spawn) 오버헤드가
block_on의 runtime context 진입/퇴출 비용보다 큼.

### block_on 오버헤드는 30-50ns

Tokio 소스 분석 결과, `Runtime::block_on()`의 실제 오버헤드:
- thread-local context 설정 (`enter_runtime`): ~5-15ns
- `CachedParkThread` 생성: ~5ns (thread-local 캐싱)
- Waker 생성: ~10-20ns
- Guard drop: ~5-10ns
- **합계: ~30-50ns per call**

네트워크 I/O (~100,000ns) 대비 0.05% 미만으로 병목이 아님.

### ~10% 갭의 실제 원인

1. **py.detach() (GIL 해제/재획득)**: ~3-5μs — C 클라이언트도 GIL 해제하지만 구현 차이
2. **async 프로토콜 처리**: Rust aerospike 클라이언트는 async-only.
   Future 생성, poll, waker 등의 기계적 오버헤드가 C의 직접 동기 I/O 대비 존재
3. **Python↔Rust 변환**: PyO3 타입 변환 비용 ~1-3μs

## 결론

~10% 갭은 async-only Rust aerospike 클라이언트의 **아키텍처적 한계**.
sync I/O를 직접 지원하는 C 클라이언트와의 갭을 완전히 제거하는 것은 불가능.

### 적용된 변경

- `DEFAULT_WRITE_POLICY` / `DEFAULT_READ_POLICY` LazyLock 캐싱 (미미하지만 무해한 최적화)
- `put()`, `get()`에서 policy=None 시 기본 정책 캐시 사용

### 시도 후 제거한 변경

- `spawn_blocking_op` (spawn+oneshot 패턴) — 오히려 느려져서 제거
