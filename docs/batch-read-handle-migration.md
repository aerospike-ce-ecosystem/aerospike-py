# BatchReadHandle: 성능 개선 및 마이그레이션 가이드

> **대상 버전**: 0.3.0 이후 (Zero-Conversion Handle)
> **이전 버전**: 0.3.0 (`BatchRecords` 반환)

---

## 성능 개선 요약

### 문제

`asyncio.gather`로 여러 `batch_read`를 동시 실행할 때, `pyo3-async-runtimes`의 `future_into_py`가 결과를 Python 객체로 변환하는 과정에서 **GIL 경합**이 발생했다.

```
gather(9 × batch_read) 시:
  9개 spawn_blocking thread가 동시에 GIL을 요청
  → 1개만 변환 중, 8개는 GIL 대기
  → 전체 직렬화: 9 × 5~40ms = 45~360ms 오버헤드
```

### 해결: Zero-Conversion Handle

`AsyncClient.batch_read()`가 더 이상 `BatchRecords`를 직접 반환하지 않는다. 대신 **`BatchReadHandle`** — Rust 데이터를 `Arc`로 감싼 경량 핸들 — 을 반환한다. `IntoPyObject`(GIL 안에서 실행되는 변환)는 `Arc::new` + `Py::new`만 수행하여 GIL 점유 시간을 < 0.01ms로 줄인다.

실제 Python 객체 변환은 사용자가 핸들 메서드를 호출할 때 event loop 스레드에서 실행되므로, 여러 `batch_read`가 동시에 완료되더라도 GIL 경합이 없다.

```
Before:  future 완료 → spawn_blocking(GIL: ~5ms 변환) → call_soon_threadsafe
After:   future 완료 → spawn_blocking(GIL: <0.01ms Arc wrap) → call_soon_threadsafe
                                                                  ↓
                          Python: handle.as_dict() → 변환 (경합 없음)
```

### 벤치마크 (50 QPS, 9 sets, 1800 records/batch)

| 클라이언트 | p50 |
|-----------|-----|
| aerospike-py 0.3.0 (lazy conversion) | 121ms |
| official C client | 106ms |
| **aerospike-py + BatchReadHandle** | **~80-90ms (예상)** |

> 실제 수치는 배포 후 부하 테스트로 확인 필요.

### 변경 범위

| 항목 | 변경 여부 |
|------|----------|
| `AsyncClient.batch_read()` | **변경** — `BatchReadHandle` 반환 |
| `Client.batch_read()` (sync) | 변경 없음 — `BatchRecords` 유지 |
| `AsyncClient.batch_operate/write/remove()` | 변경 없음 |
| NumPy path (`_dtype` 사용 시) | 변경 없음 — `NumpyBatchRecords` 유지 |

---

## API Breaking Changes

### 1. `AsyncClient.batch_read()` 반환 타입 변경

```python
# Before (0.3.0)
result: BatchRecords = await client.batch_read(keys)

# After
handle: BatchReadHandle = await client.batch_read(keys)
```

### 2. `as_dict` 파라미터 제거

```python
# Before (0.3.0) — Rust 시그니처에 as_dict 파라미터 존재
result = await client._inner.batch_read(keys, as_dict=True)

# After — handle 메서드로 이동
handle = await client.batch_read(keys)
data = handle.as_dict()
```

### 3. `isinstance` 체크

```python
# Before
isinstance(result, BatchRecords)  # True

# After
isinstance(handle, BatchReadHandle)  # True
isinstance(handle, BatchRecords)     # False
```

---

## BatchReadHandle API

```python
class BatchReadHandle:
    """async batch_read 결과 핸들. 변환은 메서드 호출 시 수행."""

    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[BatchRecord]: ...

    def as_dict(self) -> dict[str | int, dict[str, Any]]:
        """최고 성능 경로. dict[key, bins_dict] 직접 반환.
        중간 객체(BatchRecord, key tuple, meta dict) 없이 bins dict만 생성."""

    @property
    def batch_records(self) -> list[BatchRecord]:
        """하위 호환 경로. list[BatchRecord] NamedTuple 반환.
        lazy 변환 + 캐싱. 두 번째 접근부터는 캐시된 결과 반환."""

    def found_count(self) -> int:
        """성공(result_code == 0) record 수. Python 변환 없이 Rust에서 카운트."""

    def keys(self) -> list[str | int]:
        """user key 목록만 추출. record 데이터 변환 없음."""
```

---

## 마이그레이션 가이드

### 변경 불필요 (하위 호환)

`.batch_records` property가 기존과 동일한 `list[BatchRecord]` NamedTuple을 반환하므로, **대부분의 사용자 코드는 변경 없이 작동한다**.

```python
# 이 패턴들은 그대로 작동:
handle = await client.batch_read(keys)

# ✅ batch_records 접근
for br in handle.batch_records:
    ...

# ✅ NamedTuple 속성 접근
br.record.bins["name"]
br.record.meta.gen

# ✅ tuple unpacking
_, meta, bins = br.record

# ✅ result code 확인
if br.result == 0 and br.record is not None:
    ...

# ✅ len()
assert len(handle) == 10

# ✅ iteration (batch_records 경유)
for br in handle:
    ...
```

### 변경 필요

```python
# ❌ isinstance 체크
# Before:
if isinstance(result, BatchRecords): ...
# After:
if isinstance(handle, BatchReadHandle): ...

# ❌ 변수명/타입 힌트
# Before:
result: BatchRecords = await client.batch_read(keys)
# After:
handle: BatchReadHandle = await client.batch_read(keys)
```

### 성능 최적화 (권장)

key→bins 매핑만 필요한 경우, `as_dict()`가 `batch_records`보다 훨씬 빠르다:

```python
# 🚀 최고 성능 — as_dict()
handle = await client.batch_read(keys, bins=["name", "score"])
data = handle.as_dict()
# data = {"user_1": {"name": "Alice", "score": 95}, ...}

# ⚡ 호환 경로 — batch_records (NamedTuple 변환 발생)
for br in handle.batch_records:
    if br.result == 0:
        print(br.record.bins)
```

`as_dict()` vs `batch_records` 할당 비교 (N records, B bins/record):

| 경로 | 할당 수 |
|------|---------|
| `batch_records` | N × (9 + B) |
| `as_dict()` | N × (1 + B) + 1 |
| **절감** | **N × 8** (예: 1800 × 8 = 14,400) |

### 동시 실행 패턴

```python
# gather에서 as_dict() 사용 (최적)
async def read_set(keys, set_name):
    handle = await client.batch_read(keys)
    return set_name, handle.as_dict()

results = await asyncio.gather(
    *(read_set(keys, name) for name, keys in set_items)
)
```

---

## Sync Client (변경 없음)

`Client.batch_read()` (sync)는 기존대로 `BatchRecords`를 반환한다.
sync 클라이언트는 `py.detach()` 패턴을 사용하므로 GIL 경합 문제가 없어 Handle 도입이 불필요하다.

```python
# Sync — 변경 없음
result: BatchRecords = client.batch_read(keys)
for br in result.batch_records:
    ...
```
