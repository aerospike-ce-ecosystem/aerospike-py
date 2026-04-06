---
title: NumPy Integration Guide
sidebar_label: NumPy Integration
sidebar_position: 6
slug: /guides/numpy-integration
description: High-performance batch operations using NumPy structured arrays.
---

High-performance batch reads and writes using NumPy structured arrays. Data flows directly between Aerospike and NumPy buffers via Rust, bypassing per-element Python object creation.

:::note[Requirement]
Requires `numpy >= 2.0`. Install with: `pip install aerospike-py[numpy]`
:::

## When to Use NumPy Batch

| Scenario | Regular `batch_read` | NumPy `batch_read` |
|----------|---------------------|-------------------|
| Records < 100 | Preferred | Overhead not justified |
| Records 100–10K | OK | **2–5x faster** |
| Records > 10K | Slow (dict allocation) | **5–10x faster** |
| Non-numeric bins (strings, lists) | Required | Not supported |
| Vectorized analytics | Manual conversion | **Native numpy arrays** |

## Batch Read with NumPy

### Define a dtype

Each field in the dtype maps to an Aerospike bin name:

```python
import numpy as np

# Fields must be numeric (int/uint/float) or fixed-length bytes
dtype = np.dtype([
    ("score", "f8"),     # float64
    ("count", "i4"),     # int32
    ("level", "u2"),     # uint16
    ("tag", "S8"),       # 8-byte fixed string
])
```

### Read into NumPy arrays

```python
keys = [("test", "demo", f"user_{i}") for i in range(1000)]

result = client.batch_read(keys, bins=["score", "count", "level", "tag"], _dtype=dtype)
# result is a NumpyBatchRecords instance
```

### Access data

```python
# Vectorized operations on the full array
avg_score = result.batch_records["score"].mean()
high_scorers = result.batch_records[result.batch_records["score"] > 90]

# Individual record by primary key
record = result.get("user_42")
print(record["score"], record["count"])

# Metadata arrays
print(result.meta["gen"])  # generation numbers
print(result.meta["ttl"])  # TTL values

# Result codes (0 = success)
success_mask = result.result_codes == 0
valid_records = result.batch_records[success_mask]
```

### Async batch read

```python
result = await async_client.batch_read(keys, bins=["score", "count"], _dtype=dtype)
```

## Batch Write with NumPy

Write records from a structured array. One designated field serves as the primary key.

```python
import numpy as np

dtype = np.dtype([
    ("_key", "i4"),      # primary key field (prefixed with _)
    ("score", "f8"),
    ("count", "i4"),
])

data = np.array([
    (1, 95.5, 10),
    (2, 87.3, 20),
    (3, 92.1, 15),
], dtype=dtype)

results = client.batch_write_numpy(data, "test", "demo", dtype)
# Returns list of Record NamedTuples
```

### Key field conventions

- Default key field: `"_key"` (configurable via `key_field` parameter)
- Fields prefixed with `_` are excluded from bins (only `_key` is used as the record key)
- All other fields become Aerospike bins

```python
# Custom key field name
dtype = np.dtype([("user_id", "i4"), ("score", "f8")])
data = np.array([(100, 95.5), (200, 87.3)], dtype=dtype)
results = client.batch_write_numpy(data, "test", "demo", dtype, key_field="user_id")
```

### Async batch write

```python
results = await async_client.batch_write_numpy(data, "test", "demo", dtype)
```

## Supported dtype Kinds

| NumPy kind | Code | Examples | Aerospike type |
|-----------|------|---------|---------------|
| Signed int | `i` | `i1`, `i2`, `i4`, `i8` | Integer |
| Unsigned int | `u` | `u1`, `u2`, `u4`, `u8` | Integer |
| Float | `f` | `f2`, `f4`, `f8` | Float |
| Fixed bytes | `S` | `S8`, `S16`, `S32` | String (truncated) |
| Void bytes | `V` | `V8`, `V16` | Blob (truncated) |

:::warning[Unsupported types]
Variable-length strings (`U`), objects (`O`), and datetime (`M`/`m`) are **not supported**. Convert to fixed-length types before writing.
:::

## Pandas Integration

### Read into DataFrame

```python
import pandas as pd

result = client.batch_read(keys, bins=["score", "count"], _dtype=dtype)

# Direct conversion — zero copy for numeric data
df = pd.DataFrame(result.batch_records)
df["success"] = result.result_codes == 0
```

### Write from DataFrame

```python
# Convert DataFrame to structured array
dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
data = np.array(list(df[["id", "score", "count"]].itertuples(index=False)), dtype=dtype)
client.batch_write_numpy(data, "test", "demo", dtype)
```

## Strict Mode

Enable warnings for missing or extra bins:

```python
result = client.batch_read(keys, bins=["score", "count"], _dtype=dtype)
# No warnings — missing bins are zero-filled, extra bins are ignored

# With strict=True (internal API via _batch_records_to_numpy):
# Warns when dtype fields are missing from records
# Warns when record bins are not in dtype
```

## NumpyBatchRecords API

| Method / Attribute | Description |
|-------------------|-------------|
| `batch_records` | Structured numpy array with bin data |
| `meta` | `(gen, ttl)` structured array |
| `result_codes` | `int32` array (0 = success) |
| `get(key)` | Retrieve single record by primary key |
| `len(result)` | Number of records |
| `key in result` | Check if primary key exists |
| `for r in result` | Iterate over records |

## Performance Tips

1. **Pre-allocate dtypes** — Define dtype once and reuse across calls
2. **Match dtype to data** — Use smallest sufficient type (`i4` vs `i8`, `f4` vs `f8`)
3. **Batch size** — Optimal range: 500–5000 records per call
4. **Use fixed-length strings** — `S16` is much faster than variable-length alternatives
5. **Filter server-side** — Combine with expression filters to reduce data transfer
