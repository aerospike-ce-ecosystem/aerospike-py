# `merge_as_dict` 정적 메서드 테스트 결과

> 2026-04-16 | K8s 클러스터, benchmark namespace, 10 VUs, 60초

## 구현

`batch_types.rs`에 `BatchReadHandle::merge_as_dict(handles)` 정적 메서드 추가.
9개 handle의 `as_dict()`를 9번 호출 대신, 1번의 GIL 획득으로 모두 변환.

```rust
#[staticmethod]
fn merge_as_dict(handles: Vec<PyRef<Self>>, py: Python) -> PyResult<Vec<Bound<PyDict>>> {
    handles.iter().map(|h| batch_to_dict_py(py, &h.inner)).collect()
}
```

## 가설

as_dict() 9회 × 0.79ms = 7ms (직렬) → merge_as_dict 1회 ≈ 7ms (동일, GIL 획득 8회 절감)
+ event loop resume 8회 절감 → 전체 15-20ms 개선 예상

## k6 결과 (aerospike-py, 10 VUs, 60초)

| Metric | single | gather | merge_gather | 결론 |
|--------|--------|--------|-------------|------|
| **avg** | **134.6ms** | 154.5ms | 170.7ms | single 최적 |
| **median** | **106.2ms** | 125.4ms | 151.2ms | single 최적 |
| **p90** | **282.7ms** | 296.9ms | 312.5ms | single 최적 |
| **p95** | **295.9ms** | 323.3ms | 394.0ms | single 최적 |

## 분석

**merge_gather가 gather보다 오히려 +10% 느림.**

원인:
1. handle을 받기 위해 `client._inner.batch_read()`를 **9번 호출** → key_parse GIL 직렬화 (~13ms) 여전히 발생
2. `merge_as_dict` 자체 절감 (as_dict GIL 8회 → 1회, ~6ms)이 key_parse 직렬화에 묻힘
3. 추가 Python 코드 (handle list 관리, demux 루프)로 약간의 오버헤드 추가

**핵심**: 병목이 `as_dict()` (0.79ms × 9 = 7ms)가 아니라 `key_parse` (1.46ms × 9 = 13ms) + `future_into_py` 스케줄링 (~20ms)이므로, as_dict 최적화만으로는 효과 없음.

## 결론

**`merge_as_dict`는 적용하지 않음.** `single` 모드가 여전히 최적.

`single`은 key_parse + io + as_dict 모두 1회만 실행하므로, 호출 횟수 자체를 줄이는 것이 gather 내부 최적화보다 효과적.
