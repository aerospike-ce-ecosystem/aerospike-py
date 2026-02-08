---
title: NumPy Batch Read Guide
sidebar_label: NumPy Batch Read
sidebar_position: 8
description: Use batch_read with numpy structured arrays for high-performance columnar analytics directly from Aerospike.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Overview

`batch_read()` supports an optional `_dtype` parameter that returns results as a **numpy structured array** instead of Python objects. This enables:

- **Zero-copy columnar access** — `batch.batch_records["temperature"]` returns a numpy array
- **Vectorized computation** — use numpy/pandas operations directly on query results
- **Memory efficiency** — bin values are written directly into a numpy buffer in Rust, bypassing intermediate Python objects

:::tip[Performance]

With the `_dtype` parameter, Rust writes Aerospike values directly into the numpy buffer via raw pointer operations. For 10K records with 5 bins, this eliminates ~60K intermediate Python objects compared to the standard `BatchRecords` path.

:::

## Installation

```bash
pip install "aerospike-py[numpy]"
```

This installs `numpy>=2.0` as an optional dependency.

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()

# 1. Write some records
for i in range(100):
    client.put(
        ("test", "sensors", f"sensor_{i}"),
        {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
        policy={"key": aerospike.POLICY_KEY_SEND},
    )

# 2. Define dtype matching your bins
dtype = np.dtype([
    ("temperature", "f8"),  # float64
    ("humidity", "i4"),     # int32
    ("status", "u1"),       # uint8
])

# 3. Batch read with _dtype
keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
batch = client.batch_read(keys, _dtype=dtype)

# 4. Access as numpy arrays
print(batch.batch_records["temperature"].mean())  # columnar access
print(batch.batch_records[0])                      # row access
print(batch.get("sensor_42")["temperature"])       # key lookup
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
import numpy as np
import aerospike_py as aerospike
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
    })
    await client.connect()

    # 1. Write some records
    for i in range(100):
        await client.put(
            ("test", "sensors", f"sensor_{i}"),
            {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
            policy={"key": aerospike.POLICY_KEY_SEND},
        )

    # 2. Define dtype matching your bins
    dtype = np.dtype([
        ("temperature", "f8"),
        ("humidity", "i4"),
        ("status", "u1"),
    ])

    # 3. Batch read with _dtype
    keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
    batch = await client.batch_read(keys, _dtype=dtype)

    # 4. Access as numpy arrays
    print(batch.batch_records["temperature"].mean())
    print(batch.batch_records[0])
    print(batch.get("sensor_42")["temperature"])

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## NumpyBatchRecords

When `_dtype` is provided, `batch_read()` returns a `NumpyBatchRecords` object:

| Attribute | Type | Description |
|-----------|------|-------------|
| `batch_records` | `np.ndarray` | Structured array with the user-specified dtype |
| `meta` | `np.ndarray` | Structured array with dtype `[("gen", "u4"), ("ttl", "u4")]` |
| `result_codes` | `np.ndarray` | `int32` array of per-record result codes (0 = success) |
| `_map` | `dict` | `{primary_key: index}` mapping for key-based lookup |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get(primary_key)` | `np.void` | Look up a single record by primary key |

## Supported dtype Kinds

| numpy Kind | Code | Example | Aerospike Value |
|------------|------|---------|-----------------|
| Signed int | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` — truncated to target size |
| Unsigned int | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` — cast to unsigned |
| Float | `f` | `"f2"`, `"f4"`, `"f8"` | `Float(f64)` — cast to target precision |
| Fixed bytes | `S` | `"S8"`, `"S16"` | `Blob(bytes)` or `String` — truncated/zero-padded |
| Void bytes | `V` | `"V4"`, `"V16"` | `Blob(bytes)` — truncated/zero-padded |
| Sub-array | — | `("f4", (128,))` | `Blob(bytes)` — raw copy (e.g., vector embeddings) |

:::tip[Unsupported dtypes]

Unicode strings (`U`) and Python objects (`O`) are rejected with `TypeError`. Use `S` (fixed bytes) for string data.

:::

## Access Patterns

### Columnar Access

```python
temps = batch.batch_records["temperature"]  # float64 array
print(temps.mean(), temps.std(), temps.max())

# Boolean filtering
hot = batch.batch_records[temps > 40.0]
```

### Row Access

```python
record = batch.batch_records[0]
print(record["temperature"], record["humidity"])
```

### Key Lookup

```python
record = batch.get("sensor_42")
print(record["temperature"])
```

### Meta Access

```python
# Generation and TTL per record
print(batch.meta["gen"])  # uint32 array
print(batch.meta["ttl"])  # uint32 array

# Check which records failed
failed = batch.result_codes != 0
print(f"Failed: {failed.sum()} / {len(batch.result_codes)}")
```

## Defining dtype

The dtype field names must match your Aerospike bin names exactly.

### Numeric Bins

```python
dtype = np.dtype([
    ("price", "f8"),       # float64
    ("quantity", "i4"),    # int32
    ("flags", "u1"),       # uint8
])
```

### Bytes / Blob Bins

```python
dtype = np.dtype([
    ("name", "S32"),       # 32-byte fixed string
    ("raw_data", "V64"),   # 64-byte void buffer
])
```

### Vector Embeddings (Sub-array)

Store float32 vectors (e.g., ML embeddings) as byte blobs in Aerospike, then read them back as sub-arrays:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

dim = 128
dtype = np.dtype([
    ("embedding", "f4", (dim,)),  # 128-dim float32 sub-array
    ("score", "f4"),
])

# Write: store embedding as raw bytes
embedding = np.random.randn(dim).astype(np.float32)
client.put(
    ("test", "vectors", "vec_1"),
    {"embedding": embedding.tobytes(), "score": 0.95},
    policy={"key": aerospike.POLICY_KEY_SEND},
)

# Read: sub-array automatically reconstructed from bytes
keys = [("test", "vectors", "vec_1")]
batch = client.batch_read(keys, _dtype=dtype)

recovered = batch.batch_records[0]["embedding"]  # float32[128]
np.testing.assert_array_almost_equal(recovered, embedding)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
import numpy as np
import aerospike_py as aerospike
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()

    dim = 128
    dtype = np.dtype([
        ("embedding", "f4", (dim,)),
        ("score", "f4"),
    ])

    embedding = np.random.randn(dim).astype(np.float32)
    await client.put(
        ("test", "vectors", "vec_1"),
        {"embedding": embedding.tobytes(), "score": 0.95},
        policy={"key": aerospike.POLICY_KEY_SEND},
    )

    keys = [("test", "vectors", "vec_1")]
    batch = await client.batch_read(keys, _dtype=dtype)

    recovered = batch.batch_records[0]["embedding"]
    np.testing.assert_array_almost_equal(recovered, embedding)

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Bin Filtering

Combine `bins` and `_dtype` to read only specific bins from the server:

```python
dtype = np.dtype([("temperature", "f8")])
batch = client.batch_read(keys, bins=["temperature"], _dtype=dtype)
```

Only the `temperature` bin is transferred from the server, reducing network I/O.

## Error Handling

### Missing Records

Records not found (result code 2) are filled with zeros in the structured array:

```python
batch = client.batch_read(keys, _dtype=dtype)

# Check result codes
for i, rc in enumerate(batch.result_codes):
    if rc != 0:
        print(f"Record {i} failed with result code {rc}")

# Filter successful records only
success_mask = batch.result_codes == 0
valid_data = batch.batch_records[success_mask]
```

### Missing Bins

If a record exists but a bin is missing, the field defaults to zero (the numpy zero-value for that dtype):

```python
# Record has "temperature" but not "humidity"
dtype = np.dtype([("temperature", "f8"), ("humidity", "i4")])
batch = client.batch_read(keys, _dtype=dtype)
# humidity will be 0 for records missing that bin
```

### dtype Validation Errors

```python
# TypeError: unicode strings not supported
dtype = np.dtype([("name", "U10")])
batch = client.batch_read(keys, _dtype=dtype)  # raises TypeError

# TypeError: Python objects not supported
dtype = np.dtype([("data", "O")])
batch = client.batch_read(keys, _dtype=dtype)  # raises TypeError
```

## Pandas Integration

Convert `NumpyBatchRecords` to a pandas DataFrame:

```python
import pandas as pd

batch = client.batch_read(keys, _dtype=dtype)

df = pd.DataFrame(batch.batch_records)
df["gen"] = batch.meta["gen"]
df["ttl"] = batch.meta["ttl"]

# Now use pandas operations
hot_sensors = df[df["temperature"] > 35.0]
print(hot_sensors.describe())
```

## Best Practices

- **Match dtype to your bins** — field names in the dtype must match bin names in Aerospike
- **Use `bins` parameter** — combine with `_dtype` to reduce network transfer
- **Check `result_codes`** — filter out failed records before analysis
- **Use smallest sufficient dtype** — `"f4"` instead of `"f8"`, `"i2"` instead of `"i8"` to reduce memory
- **Batch size** — keep batches at 100-5,000 keys for optimal performance
- **Vector data** — store embeddings as `tobytes()` blobs, read with sub-array dtypes

## API Reference

```python
# Sync
batch: NumpyBatchRecords = client.batch_read(
    keys: list[tuple[str, str, str | int | bytes]],
    bins: list[str] | None = None,
    policy: dict | None = None,
    _dtype: np.dtype = ...,
)

# Async
batch: NumpyBatchRecords = await client.batch_read(
    keys: list[tuple[str, str, str | int | bytes]],
    bins: list[str] | None = None,
    policy: dict | None = None,
    _dtype: np.dtype = ...,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keys` | `list[Key]` | required | List of `(namespace, set, primary_key)` tuples |
| `bins` | `list[str] \| None` | `None` | Bin names to read (`None` = all) |
| `policy` | `dict \| None` | `None` | Batch policy overrides |
| `_dtype` | `np.dtype` | required | Structured dtype defining output schema |
