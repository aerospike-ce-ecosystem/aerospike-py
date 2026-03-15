# Goal 4: NumPy v2 통합

numpy >= 2.0 optional dep (`pip install aerospike-py[numpy]`).

## Read 경로: batch_read → structured array

1. 사용자 제공 dtype 파싱 → `FieldInfo` (offset, kind, itemsize)
2. `np.zeros`로 배열 할당 → `__array_interface__`로 raw 포인터 획득
3. `Vec<BatchRecord>` → `ptr::write_unaligned` 직접 기록 (Python 객체 생성 없음)
4. 반환: `NumpyBatchRecords` (data array + meta array + result_codes + key_map)

```python
dtype = np.dtype([("score", "f4"), ("tags", "S32")])
result = client.batch_read(keys, _dtype=dtype)
scores = result.batch_records["score"]  # zero-copy numpy column access
```

## Write 경로: batch_write_numpy

numpy structured array → `Vec<(Key, Vec<Bin>)>` 변환 후 batch write.
`_key` 필드(기본값)를 Aerospike key로 사용.

## 지원 dtype kinds

`i` (int), `u` (uint), `f` (float, f16 포함), `S` (fixed bytes), `V` (void bytes)
`U` (unicode), `O` (object) — 거부

## 주요 파일

- `rust/src/numpy_support.rs` — Rust 핵심 변환
- `src/aerospike_py/numpy_batch.py` — Python `NumpyBatchRecords` 래퍼
- `tests/unit/test_numpy_batch.py`
- `tests/integration/test_numpy_batch.py`
