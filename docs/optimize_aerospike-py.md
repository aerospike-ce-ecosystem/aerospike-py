# aerospike-py: Zero-Conversion Handle 아키텍처로 성능 개선

## Context

aerospike-py(Rust/PyO3)의 `batch_read`가 `asyncio.gather` 환경에서 official C client보다 느린 근본 원인:

```
pyo3-async-runtimes의 future_into_py 흐름:
  Tokio future 완료 → spawn_blocking → Python::attach(GIL 획득) → IntoPyObject 변환 → call_soon_threadsafe

gather(9 × batch_read) 시:
  9개 spawn_blocking thread가 동시에 GIL을 요청
  → 1개만 변환 중, 8개는 GIL 대기
  → 전체 GIL 직렬화 시간: 9 × 5~40ms = 45~360ms
```

**Official C client**은 이 문제가 없음 — `run_in_executor`의 각 thread가 독립적으로 변환 완료 후 event loop에 결과만 전달.

**목표**: `batch_read`의 `IntoPyObject` 비용을 0에 가깝게 만들어 GIL 경합을 제거하고, official C client보다 빠르게 만든다.

현재 벤치마크 (50 QPS, 9 sets, skip_inference):
- aerospike-py (lazy): p50=121ms
- official C client: p50=106ms
- 목표: **aerospike-py p50 < 90ms**

---

## 핵심 전략: Zero-Conversion Handle

`batch_read`가 Python 객체로 변환된 결과 대신 **Rust 데이터를 감싼 경량 handle 객체**를 반환. `IntoPyObject`는 `Arc` 래핑만 수행 (GIL hold < 0.01ms). 실제 변환은 Python에서 handle 메서드 호출 시 발생 → event loop에서 단일 스레드로 실행되므로 GIL 경합 0.

```
Before:  future_into_py → spawn_blocking(GIL: 5~40ms 변환) → call_soon_threadsafe
After:   future_into_py → spawn_blocking(GIL: <0.01ms Arc wrap) → call_soon_threadsafe
                                                                     ↓
                                        Python: handle.as_dict() → 변환 (경합 없음)
```

---

## 변경 파일 및 단계

### Step 1: `rust/src/batch_types.rs` — `PyBatchReadHandle` 추가

```rust
use std::sync::Arc;

#[pyclass(name = "BatchReadHandle")]
pub struct PyBatchReadHandle {
    inner: Arc<Vec<BatchRecord>>,
}

#[pymethods]
impl PyBatchReadHandle {
    fn __len__(&self) -> usize { self.inner.len() }

    fn __getitem__(&self, py: Python, index: isize) -> PyResult<Py<PyBatchRecord>> {
        // 단일 record lazy 변환
    }

    fn __iter__(slf: PyRef<Self>) -> PyResult<PyBatchReadIter> {
        // iterator
    }

    /// dict[key_str, bins_dict] 직접 반환 — 가장 빠른 접근 경로
    fn as_dict(&self, py: Python) -> PyResult<Bound<PyDict>> {
        batch_to_dict_py(py, &self.inner)
    }

    /// 기존 BatchRecords 호환 (lazy conversion)
    #[getter]
    fn batch_records(&self, py: Python) -> PyResult<Py<PyBatchRecords>> {
        batch_to_batch_records_py(py, /* clone inner */)
    }

    /// found records만 필터링 (변환 없이 Rust에서 처리)
    fn filter_found(&self) -> PyBatchReadHandle {
        let filtered = self.inner.iter()
            .filter(|br| br.result_code.is_none() || matches!(br.result_code, Some(Ok)))
            .cloned().collect();
        PyBatchReadHandle { inner: Arc::new(filtered) }
    }

    /// key 목록만 반환 (bins 변환 없음)
    fn keys(&self, py: Python) -> PyResult<Bound<PyList>> { ... }
}
```

#### `PendingBatchReadHandle` — spawn_blocking용 deferred type

```rust
pub struct PendingBatchReadHandle {
    pub results: Vec<BatchRecord>,
}

impl<'py> IntoPyObject<'py> for PendingBatchReadHandle {
    fn into_pyobject(self, py: Python<'py>) -> Result<...> {
        // GIL hold < 0.01ms — Arc wrap + Py::new만 수행
        let handle = PyBatchReadHandle { inner: Arc::new(self.results) };
        Ok(Py::new(py, handle)?.into_bound(py).into_any())
    }
}
```

### Step 2: `rust/src/async_client.rs` — batch_read 반환 타입 변경

`batch_read` 메서드(line ~707-743)의 `future_into_py` 블록에서:

```rust
// Before:
Ok(PendingBatchRead::Standard(results))  // → IntoPyObject가 2600 alloc

// After:
Ok(PendingBatchReadHandle { results })   // → IntoPyObject가 Arc::new + Py::new만
```

`as_dict` 파라미터는 Rust 시그니처에서 제거 — handle의 `.as_dict()` 메서드로 이동.

NumPy path(`_dtype`)는 기존 eager 방식 유지 (numpy buffer write는 이미 빠름).

### Step 3: `rust/src/lib.rs` — pyclass 등록

```rust
m.add_class::<batch_types::PyBatchReadHandle>()?;
```

### Step 4: `src/aerospike_py/__init__.pyi` — 타입 스텁 추가

```python
class BatchReadHandle:
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> BatchRecord: ...
    def __iter__(self) -> Iterator[BatchRecord]: ...
    def as_dict(self) -> dict[str | int, dict[str, Any]]: ...
    def to_batch_records(self) -> BatchRecords: ...
    @property
    def batch_records(self) -> list[BatchRecord]: ...
    def filter_found(self) -> BatchReadHandle: ...
    def keys(self) -> list[str | int]: ...
```

`AsyncClient.batch_read` 반환 타입을 `BatchReadHandle`로 변경.

### Step 5: `src/aerospike_py/__init__.py` — import 추가

`BatchReadHandle`을 `_aerospike` 네이티브 모듈에서 import하여 재export.

### Step 6: 벤치마크 코드 업데이트

`src/serving/aerospike_clients.py`의 `py_async_batch_read_all_sets`:

```python
# as_dict 모드 (최고 성능):
async def _as_dict_read(batch_keys, set_name):
    handle = await client.batch_read(batch_keys)  # BatchReadHandle 반환
    return set_name, handle.as_dict(), len(batch_keys), ...

results = await asyncio.gather(*[_as_dict_read(bk, sn) for sn, bk in set_items])
```

### Step 7: 기존 테스트 업데이트

`tests/integration/test_async.py` 등에서 `batch_read` 반환 타입이 `BatchReadHandle`로 변경됨에 따라:

```python
# Before:
result = await client.batch_read(keys)
for br in result.batch_records:

# After (호환 경로):
handle = await client.batch_read(keys)
for br in handle.batch_records:  # .batch_records getter가 lazy 변환

# After (최고 성능):
handle = await client.batch_read(keys)
bins_dict = handle.as_dict()
```

---

## 성능 예측

| 단계 | GIL hold in spawn_blocking | GIL 경합 (9 concurrent) | 예상 p50 |
|------|---------------------------|------------------------|---------|
| 현재 (lazy) | ~5ms/batch | 9개 thread 직렬 | 121ms |
| Zero-Conversion Handle | **<0.01ms/batch** | **경합 없음** | **~80-90ms** |
| Official C client | N/A | N/A | 106ms |

핵심: **GIL 경합이 0이 되면, Tokio의 non-blocking I/O 이점이 발휘** → official보다 빨라짐.

---

## Breaking Change 영향 및 마이그레이션

| 기존 패턴 | 변경 후 | 마이그레이션 비용 |
|----------|---------|----------------|
| `result.batch_records` | `handle.batch_records` | **동일** (property로 제공) |
| `for br in result.batch_records:` | `for br in handle.batch_records:` | **동일** |
| `br.record`, `br.key`, `br.result` | **동일** | 변경 없음 |
| `batch_read(keys, as_dict=True)` | `handle = batch_read(keys); handle.as_dict()` | 2줄 변경 |
| `isinstance(result, BatchRecords)` | `isinstance(handle, BatchReadHandle)` | 타입 체크 변경 |

`.batch_records` property가 기존과 동일한 `list[BatchRecord]`를 반환하므로, **대부분의 사용자 코드는 변경 없이 작동.**

---

## 검증 방법

```bash
# 1. Rust 컴파일 확인
cd aerospike-py && cargo check --manifest-path rust/Cargo.toml

# 2. 단위 테스트
make test-unit

# 3. 통합 테스트 (Aerospike 서버 필요)
make run-aerospike-ce && make test-integration

# 4. Cross-compile wheel
maturin build --release -i python3.10 --target x86_64-unknown-linux-gnu --zig

# 5. 벤치마크 Docker 빌드 → 배포 → 부하 테스트
cd ../aerospike-py-benchmark
cp aerospike-py/target/wheels/*.whl deploy/
docker buildx build --platform linux/amd64 -f deploy/Dockerfile .
# push → deploy → oha 50 QPS 테스트
```

검증 기준:
- `handle.as_dict()` 반환값이 기존 `as_dict=True`와 동일
- `handle.batch_records`가 기존 `BatchRecords.batch_records`와 동일
- 50 QPS 부하에서 **p50 < 90ms** (official의 106ms보다 빠름)
