# batch_read() dict 반환: 성능 개선 및 마이그레이션 가이드

> **대상 버전**: 0.4.0
> **이전 버전**: 0.3.0 (`BatchRecords` NamedTuple 반환)

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

### 해결: Zero-Conversion + Direct Dict Return

내부적으로 Rust `future_into_py` 콜백에서는 `Arc::new` + `Py::new`만 수행하여 GIL 점유 시간을 < 0.01ms로 줄인다. dict 변환은 Python 코루틴 컨텍스트에서 실행되므로, 여러 `batch_read`가 동시에 완료되더라도 GIL 경합이 없다.

```
Async: future 완료 → callback(GIL: <0.01ms Arc wrap) → call_soon_threadsafe
                                                          ↓
       Python 코루틴: as_dict() → dict 변환 → dict 반환 (경합 없음)

Sync:  py.detach(I/O) → batch_to_dict_py() → dict 반환 (중간 객체 생략으로 더 빠름)
```

---

## API Breaking Changes

### 1. 반환 타입: dict

```python
# Before (0.3.0)
result: BatchRecords = await client.batch_read(keys)
for br in result.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)

# After (0.4.0) — sync와 async 모두 동일
result: BatchRecords = await client.batch_read(keys)
# result = {"user_key_1": {"name": "Alice", "score": 95}, ...}
for user_key, bins in result.items():
    print(user_key, bins)
```

### 2. 타입 정의

```python
from aerospike_py import BatchRecords, UserKey, AerospikeRecord

# BatchRecords = dict[UserKey, AerospikeRecord]
# UserKey = str | int
# AerospikeRecord = dict[str, Any]
```

### 3. `isinstance` 체크

```python
# Before
isinstance(result, BatchRecords)  # True (NamedTuple)

# After
isinstance(result, dict)  # True
```

### 4. Write 계열은 `BatchWriteResult`

```python
from aerospike_py import BatchWriteResult

# batch_write, batch_operate, batch_remove → BatchWriteResult
result = client.batch_write(records)
for br in result.batch_records:
    if br.result != 0:
        print(f"Failed: {br.key}")
```

---

## 변경 범위

| 항목 | 변경 |
|------|------|
| `AsyncClient.batch_read()` | **변경** — `dict[UserKey, AerospikeRecord]` 반환 |
| `Client.batch_read()` (sync) | **변경** — `dict[UserKey, AerospikeRecord]` 반환 |
| `batch_write/operate/remove()` | **변경** — `BatchWriteResult` 반환 (기존 `BatchRecords` NamedTuple과 동일 구조) |
| NumPy path (`_dtype` 사용 시) | 변경 없음 — `NumpyBatchRecords` 유지 |

---

## 마이그레이션 가이드

### 변경 필요

```python
# ❌ batch_records 접근
for br in result.batch_records:
    print(br.record.bins)

# ✅ dict 접근
for user_key, bins in result.items():
    print(bins)

# ❌ result code 확인
if br.result == 0: ...

# ✅ dict에는 성공한 레코드만 포함
# missing records는 dict에 포함되지 않음
if "my_key" in result: ...

# ❌ isinstance
isinstance(result, BatchRecords)  # False (BatchRecords는 이제 TypeAlias)

# ✅
isinstance(result, dict)  # True
```

### 동시 실행 패턴

```python
# asyncio.gather — 직접 dict 반환 (가장 간결)
async def read_set(keys, set_name):
    data = await client.batch_read(keys)
    return set_name, data

results = await asyncio.gather(
    *(read_set(keys, name) for name, keys in set_items)
)
```

---

## 성능 참고

dict 반환은 내부적으로 `batch_to_dict_py()`를 사용하며, 중간 객체(BatchRecord wrapper, key tuple, meta dict)를 생략하여 할당을 최소화한다.

| 경로 | 할당 수 (N records, B bins) |
|------|-----------------------------|
| 기존 `batch_records` NamedTuple | N × (9 + B) |
| **dict 반환** | N × (1 + B) + 1 |
| **절감** | **N × 8** (예: 1800 × 8 = 14,400) |
