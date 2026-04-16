# `future_into_py` 병목 대안 리서치

> 2026-04-16 | aerospike-py v0.1.0 (PyO3 0.28.2, pyo3-async-runtimes 0.28)

## 1. 현재 상태

| 항목 | 값 |
|------|-----|
| PyO3 | 0.28.2 |
| pyo3-async-runtimes | 0.28 (tokio-runtime) |
| Tokio workers | 2 (GIL contention 최소화 목적) |
| `gil_used` | `true` (`lib.rs:61`) |
| 병목 | `future_into_py` 경유 시 Python ↔ Rust 경계에서 **46ms/51ms (90%)** 소모 |

## 2. `future_into_py` 내부 동작 (비용 발생 지점)

`pyo3-async-runtimes`의 `future_into_py`는 호출마다 다음을 수행:

1. `asyncio.Future` 생성 (GIL held)
2. `oneshot::channel()` 할당 (cancellation 용)
3. Tokio에 **2개 nested task** spawn (outer + inner)
4. Future 완료 시 `call_soon_threadsafe()`로 event loop 깨움 (socket/pipe write)
5. `Python::attach()`로 GIL 획득 → `IntoPyObject` 실행 → `set_result()`

`asyncio.gather(9개)`일 때: 9번의 GIL 순차 획득 + 9번의 event loop wakeup + 9번의 coroutine resume가 직렬화됨.

## 3. 대안 분석

### 3.1 PyO3 Native `async fn` (experimental-async)

PyO3 0.22+에서 사용 가능한 `#[pyfunction]`/`#[pymethods]`의 `async fn` 지원.

```rust
// 현재 (future_into_py)
fn batch_read<'py>(&self, py: Python<'py>, ...) -> PyResult<Bound<'py, PyAny>> {
    future_into_py(py, async move { ... })
}

// 대안 (native async fn)
async fn batch_read(&self, ...) -> PyResult<PendingBatchRead> {
    let result = client_ops::do_batch_read(&client, &args).await?;
    Ok(PendingBatchRead::Handle(result))
}
```

**장점:**
- `asyncio.Future` + `call_soon_threadsafe` + `spawn_blocking` 오버헤드 제거
- Python coroutine protocol을 직접 구현 (`__next__`/`send`/`throw`)
- Tokio task spawn, oneshot channel 불필요

**단점:**
- GIL이 polling 중 계속 held됨 → `AllowThreads<F>` 래퍼로 I/O 중 detach 필요
- 아직 `experimental` 상태이며, 현재 `pyo3-async-runtimes` 아키텍처와 대규모 변경 필요
- `batch_read`의 핵심 병목인 "9개 동시 호출의 GIL 직렬화" 자체는 해결 불가 (GIL은 여전히 한 번에 하나)

**평가: 중장기 관심 대상, 단독으로 근본 해결은 아님**

### 3.2 Free-Threaded Python 3.14t (PEP 703/779)

**가장 근본적인 해결책.** GIL이 제거되므로 9개 `IntoPyObject` 변환이 진짜 병렬 실행됨.

**현재 상태:**
- PEP 779 승인 — Python 3.14에서 free-threaded가 공식 "supported" 상태
- PyO3 0.28은 `gil_used = false`가 기본값 (thread-safe 모듈 가정)
- aerospike-py가 이미 3.14t 빌드 지원
- `PyBatchRecord.record_cell: Mutex<LazyRecordCell>`, `Arc`/`AtomicU8` 패턴이 이미 thread-safe

**필요한 변경:**
```rust
// lib.rs:61 — 현재
#[pymodule(gil_used = true)]

// 변경
#[pymodule(gil_used = false)]  // thread-safety audit 후
```

**예상 효과:**
- GIL 직렬화 ~20ms 완전 제거
- `key_parse` 13ms → 병렬화로 ~2-3ms
- `as_dict` 7ms → 병렬화로 ~1-2ms

**평가: 효과 최대, 단 production 환경에서 3.14t 채택이 전제**

### 3.3 `pyo3_disable_reference_pool` Cargo feature

PyO3의 global reference pool 동기화가 Python-Rust 경계 비용의 상당 부분을 차지함.

```toml
# Cargo.toml
[features]
default = []
# 추가
pyo3_disable_reference_pool = []
```

PyO3 공식 문서:
> "The reference pool synchronization can become a significant part of the cost of crossing the Python-Rust boundary."

**조건:** `Py<T>` 객체가 interpreter에 attached된 상태에서만 drop되어야 함 (현재 코드 패턴상 충족)

**평가: 낮은 노력, 중간 효과 — 즉시 적용 가능**

### 3.4 Bin Name Interning (batch 변환 최적화)

`batch_to_dict_py`에서 동일한 bin name이 record마다 반복 생성됨. 1800 records × 6 bins = 10,800회 중복 `PyString` 할당.

```rust
// 최적화: per-batch HashMap cache
let mut name_cache: HashMap<&str, Bound<'py, PyString>> = HashMap::new();
for (name, value) in &record.bins {
    let py_name = name_cache.entry(name.as_str())
        .or_insert_with(|| PyString::intern(py, name));
    bins.set_item(py_name, value_to_py(py, value)?)?;
}
```

**평가: 중간 노력, 10-15% 개선 — `as_dict()` 구간 단축**

### 3.5 `merge_as_dict` 정적 메서드 (gather 패턴 최적화)

9개 handle의 `as_dict()`를 9번 호출 대신, 1번의 GIL 획득으로 모두 변환:

```rust
#[staticmethod]
fn merge_as_dict(handles: Vec<PyRef<Self>>, py: Python) -> PyResult<Vec<Bound<PyDict>>> {
    handles.iter().map(|h| h.as_dict_inner(py)).collect()
}
```

**평가: 중간 노력, event loop resume 8회 절감**

### 3.6 single batch_read (이미 검증됨)

bottleneck-analysis.md의 `gather(9회) → single(1회)` 전환이 이미 **-33% avg, -43% median** 검증됨.
`future_into_py` 호출 횟수 자체를 9→1로 줄이는 가장 실용적인 해결책.

## 4. 다른 프로젝트 사례

| 프로젝트 | 전략 |
|----------|------|
| **Polars** | 모든 연산에서 `py.detach()`, Arrow 메모리 직접 접근으로 Python 객체 생성 최소화 |
| **pydantic-core** | 입력을 즉시 Rust 타입으로 변환, 모든 처리를 pure Rust에서, 결과만 한 번에 변환 |
| **Ruff** | Python 객체 생성 거의 없음 (입출력이 문자열) |

공통 패턴: **경계 횡단 횟수를 최소화하고, 횡단할 때 최대한 많은 데이터를 한 번에 변환**

## 5. 관련 이슈 및 참고 자료

- [pyo3-asyncio Issue #18](https://github.com/awestlake87/pyo3-asyncio/issues/18) — MongoDB 벤치마크에서 pure Python 대비 27x 느림 (100K items 기준), cross-runtime 통신 오버헤드 원인
- [PyO3 Issue #3827](https://github.com/PyO3/pyo3/issues/3827) — `#[pyfunction]` 호출당 20-40ns 오버헤드
- [PyO3 Issue #1632](https://github.com/PyO3/pyo3/issues/1632) — async/await tracking issue
- [PyO3 Free-Threading Guide](https://pyo3.rs/v0.28.2/free-threading)
- [PyO3 Performance Guide](https://pyo3.rs/main/performance) — `pyo3_disable_reference_pool` 설명
- [PyO3 Async/Await Guide](https://pyo3.rs/v0.28.2/async-await) — native `async fn` 사용법
- [PEP 779](https://peps.python.org/pep-0779/) — Free-threaded Python 공식 supported 상태 기준
- [pyo3-async (wyfo)](https://github.com/wyfo/pyo3-async) — `experimental-async`의 원형, PyO3 core에 merge됨

## 6. 우선순위 종합

| 순위 | 방안 | 노력 | 효과 | 시점 |
|------|------|------|------|------|
| **1** | single batch_read 기본화 (보고서 결론) | 낮음 | **-33% avg** | 즉시 |
| **2** | `pyo3_disable_reference_pool` 활성화 | 낮음 | 중간 | 즉시 |
| **3** | bin name interning (`PyString::intern`) | 중간 | -10~15% | 단기 |
| **4** | `merge_as_dict` 정적 메서드 | 중간 | event loop 오버헤드 절감 | 단기 |
| **5** | Free-threaded 3.14t + `gil_used = false` | 중간 | **GIL 병목 완전 제거** | 중기 |
| **6** | PyO3 native `async fn` 전환 | 높음 | `future_into_py` 오버헤드 제거 | 장기 |

## 7. 결론

`future_into_py`를 직접 대체할 drop-in 라이브러리는 현재 존재하지 않음.

3단계 접근이 가장 현실적:
1. **호출 횟수 줄이기** — single batch_read (검증 완료, -33%)
2. **호출당 비용 줄이기** — reference pool 비활성화, bin name interning
3. **GIL 자체 제거** — Free-threaded Python 3.14t (중기)
