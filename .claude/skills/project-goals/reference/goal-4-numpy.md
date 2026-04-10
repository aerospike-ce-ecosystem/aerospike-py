# Goal 4: NumPy v2 Integration

numpy >= 2.0 optional dep (`pip install aerospike-py[numpy]`).

## Read Path: batch_read → structured array

1. Parse user-provided dtype → `FieldInfo` (offset, kind, itemsize)
2. Allocate array with `np.zeros` → obtain raw pointer via `__array_interface__`
3. `Vec<BatchRecord>` → write directly with `ptr::write_unaligned` (no Python object creation)
4. Return: `NumpyBatchRecords` (data array + meta array + result_codes + key_map)

```python
dtype = np.dtype([("score", "f4"), ("tags", "S32")])
result = client.batch_read(keys, _dtype=dtype)
scores = result.batch_records["score"]  # zero-copy numpy column access
```

## Write Path: batch_write_numpy

numpy structured array → `Vec<(Key, Vec<Bin>)>` conversion then batch write.
Uses `_key` field (default) as the Aerospike key.

## Supported dtype kinds

`i` (int), `u` (uint), `f` (float, including f16), `S` (fixed bytes), `V` (void bytes)
`U` (unicode), `O` (object) — rejected

## Key Files

- `rust/src/numpy_support.rs` — core Rust conversion
- `src/aerospike_py/numpy_batch.py` — Python `NumpyBatchRecords` wrapper
- `tests/unit/test_numpy_batch.py`
- `tests/integration/test_numpy_batch.py`
