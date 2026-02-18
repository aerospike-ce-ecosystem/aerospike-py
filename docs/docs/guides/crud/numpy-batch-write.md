---
title: NumPy Batch Write Guide
sidebar_label: NumPy Batch Write
sidebar_position: 5
slug: /guides/numpy-batch-write
description: Use batch_write_numpy to write records directly from numpy structured arrays for high-performance bulk ingestion into Aerospike.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Overview

`batch_write_numpy()` writes multiple records to Aerospike directly from a **numpy structured array**. Each row becomes a separate write operation, with dtype fields mapped to Aerospike bins.

- **Direct array-to-record mapping** — no intermediate Python dicts or loops
- **Key field extraction** — a designated dtype field (default `_key`) is used as the record's user key
- **Automatic bin mapping** — all non-underscore-prefixed fields become bins
- **Batch execution** — all rows are written in a single batch call

:::tip[When to use]

Use `batch_write_numpy()` when your data is already in numpy arrays (e.g., ML feature stores, sensor data pipelines, scientific datasets). For regular Python dicts, use `put()` or standard batch operations instead.

:::

## Installation

```bash
pip install "aerospike-py[numpy]"
```

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()

# 1. Define dtype with key field and bin fields
dtype = np.dtype([
    ("_key", "i4"),     # record key (int32)
    ("score", "f8"),    # bin: float64
    ("count", "i4"),    # bin: int32
])

# 2. Create structured array
data = np.array([
    (1, 0.95, 10),
    (2, 0.87, 20),
    (3, 0.72, 15),
], dtype=dtype)

# 3. Batch write
results = client.batch_write_numpy(data, "test", "demo", dtype)

# 4. Check results
for record in results:
    key, meta, bins = record
    print(f"Key: {key}, Gen: {meta['gen']}")
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

    # 1. Define dtype with key field and bin fields
    dtype = np.dtype([
        ("_key", "i4"),
        ("score", "f8"),
        ("count", "i4"),
    ])

    # 2. Create structured array
    data = np.array([
        (1, 0.95, 10),
        (2, 0.87, 20),
        (3, 0.72, 15),
    ], dtype=dtype)

    # 3. Batch write
    results = await client.batch_write_numpy(data, "test", "demo", dtype)

    # 4. Check results
    for record in results:
        key, meta, bins = record
        print(f"Key: {key}, Gen: {meta['gen']}")

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## How It Works

```
numpy structured array             Aerospike
┌──────┬───────┬───────┐
│ _key │ score │ count │
├──────┼───────┼───────┤          ┌──────────────────────┐
│  1   │ 0.95  │  10   │  ──────▶ │ key=1 {score, count} │
│  2   │ 0.87  │  20   │  ──────▶ │ key=2 {score, count} │
│  3   │ 0.72  │  15   │  ──────▶ │ key=3 {score, count} │
└──────┴───────┴───────┘          └──────────────────────┘
        ▲                                  ▲
   key_field="_key"               bins = non-underscore fields
```

1. The `key_field` (default `"_key"`) column is extracted as the user key for each record
2. All fields **not** prefixed with `_` become Aerospike bins
3. Fields prefixed with `_` (other than the key field) are ignored

## Key Field

By default, the dtype field named `"_key"` is used as the record key. You can specify a different field with `key_field`:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
dtype = np.dtype([
    ("user_id", "i8"),    # use this as the record key
    ("score", "f8"),
])

data = np.array([(100, 1.5), (101, 2.5)], dtype=dtype)

# Use "user_id" as key instead of "_key"
results = client.batch_write_numpy(
    data, "test", "demo", dtype, key_field="user_id"
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
dtype = np.dtype([
    ("user_id", "i8"),
    ("score", "f8"),
])

data = np.array([(100, 1.5), (101, 2.5)], dtype=dtype)

results = await client.batch_write_numpy(
    data, "test", "demo", dtype, key_field="user_id"
)
```

  </TabItem>
</Tabs>

:::note

When using a custom `key_field`, the field name should **not** start with `_` if you want it to also be stored as a bin. If the field starts with `_`, it is used only as the key and not written as a bin.

:::

## Supported dtype Kinds

The same dtype kinds supported by `batch_read()` with `_dtype` are supported for writes:

| numpy Kind | Code | Example | Aerospike Value |
|------------|------|---------|-----------------|
| Signed int | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` |
| Unsigned int | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` |
| Float | `f` | `"f4"`, `"f8"` | `Float(f64)` |
| Fixed bytes | `S` | `"S8"`, `"S16"` | `Blob(bytes)` or `String` |
| Void bytes | `V` | `"V4"`, `"V16"` | `Blob(bytes)` |
| Sub-array | — | `("f4", (128,))` | `Blob(bytes)` |

:::tip[Unsupported dtypes]

Unicode strings (`U`) and Python objects (`O`) are not supported. Use `S` (fixed bytes) for string data.

:::

## Examples

### Sensor Data Ingestion

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

dtype = np.dtype([
    ("_key", "i4"),
    ("temperature", "f8"),
    ("humidity", "f4"),
    ("pressure", "f4"),
    ("status", "u1"),
])

# Generate 1000 sensor readings
n = 1000
data = np.zeros(n, dtype=dtype)
data["_key"] = np.arange(n)
data["temperature"] = np.random.normal(25.0, 5.0, n)
data["humidity"] = np.random.uniform(30.0, 90.0, n).astype(np.float32)
data["pressure"] = np.random.normal(1013.25, 10.0, n).astype(np.float32)
data["status"] = 1

results = client.batch_write_numpy(data, "test", "sensors", dtype)
print(f"Wrote {len(results)} records")
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

    dtype = np.dtype([
        ("_key", "i4"),
        ("temperature", "f8"),
        ("humidity", "f4"),
        ("pressure", "f4"),
        ("status", "u1"),
    ])

    n = 1000
    data = np.zeros(n, dtype=dtype)
    data["_key"] = np.arange(n)
    data["temperature"] = np.random.normal(25.0, 5.0, n)
    data["humidity"] = np.random.uniform(30.0, 90.0, n).astype(np.float32)
    data["pressure"] = np.random.normal(1013.25, 10.0, n).astype(np.float32)
    data["status"] = 1

    results = await client.batch_write_numpy(data, "test", "sensors", dtype)
    print(f"Wrote {len(results)} records")

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

### Vector Embeddings

Store ML embeddings as byte blobs:

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

dim = 128
dtype = np.dtype([
    ("_key", "i4"),
    ("embedding", "V" + str(dim * 4)),  # 128 * 4 bytes = 512-byte blob
    ("label", "i4"),
])

n = 100
embeddings = np.random.randn(n, dim).astype(np.float32)

data = np.zeros(n, dtype=dtype)
data["_key"] = np.arange(n)
for i in range(n):
    data["embedding"][i] = embeddings[i].tobytes()
data["label"] = np.random.randint(0, 10, n)

results = client.batch_write_numpy(data, "test", "vectors", dtype)
```

### Write and Read Roundtrip

Combine `batch_write_numpy()` and `batch_read()` with `_dtype` for a full numpy roundtrip:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# Define dtype
dtype = np.dtype([
    ("_key", "i4"),
    ("x", "f8"),
    ("y", "f8"),
    ("category", "i4"),
])

# Write
data = np.array([
    (1, 1.0, 2.0, 0),
    (2, 3.0, 4.0, 1),
    (3, 5.0, 6.0, 0),
], dtype=dtype)
client.batch_write_numpy(data, "test", "points", dtype)

# Read back with _dtype
read_dtype = np.dtype([("x", "f8"), ("y", "f8"), ("category", "i4")])
keys = [("test", "points", i) for i in range(1, 4)]
batch = client.batch_read(keys, _dtype=read_dtype, policy={"key": aerospike.POLICY_KEY_SEND})

# Vectorized analysis
print(batch.batch_records["x"].mean())       # 3.0
print(batch.batch_records["category"].sum())  # 1
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

    dtype = np.dtype([
        ("_key", "i4"),
        ("x", "f8"),
        ("y", "f8"),
        ("category", "i4"),
    ])

    data = np.array([
        (1, 1.0, 2.0, 0),
        (2, 3.0, 4.0, 1),
        (3, 5.0, 6.0, 0),
    ], dtype=dtype)
    await client.batch_write_numpy(data, "test", "points", dtype)

    read_dtype = np.dtype([("x", "f8"), ("y", "f8"), ("category", "i4")])
    keys = [("test", "points", i) for i in range(1, 4)]
    batch = await client.batch_read(keys, _dtype=read_dtype, policy={"key": aerospike.POLICY_KEY_SEND})

    print(batch.batch_records["x"].mean())
    print(batch.batch_records["category"].sum())

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

### Pandas DataFrame to Aerospike

Write a pandas DataFrame to Aerospike via numpy:

```python
import numpy as np
import pandas as pd
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# DataFrame
df = pd.DataFrame({
    "user_id": [1, 2, 3],
    "score": [0.95, 0.87, 0.72],
    "level": [10, 20, 15],
})

# Convert to structured array
dtype = np.dtype([
    ("_key", "i4"),
    ("score", "f8"),
    ("level", "i4"),
])

data = np.zeros(len(df), dtype=dtype)
data["_key"] = df["user_id"].values
data["score"] = df["score"].values
data["level"] = df["level"].values

results = client.batch_write_numpy(data, "test", "users", dtype)
```

## Error Handling

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_write_numpy(data, "test", "demo", dtype)
    for record in results:
        key, meta, bins = record
        if meta is None:
            print(f"Write failed for key {key}")
except AerospikeError as e:
    print(f"Batch write error: {e}")
```

## Best Practices

- **Match dtype to your data** — use the smallest sufficient dtype (`"f4"` vs `"f8"`, `"i2"` vs `"i8"`) to reduce memory and network transfer
- **Batch size** — keep arrays at 100-5,000 rows per call for optimal performance
- **Key field convention** — use `"_key"` as the default key field to keep the convention consistent
- **Underscore prefix** — fields starting with `_` are excluded from bins, use this for metadata fields
- **Roundtrip with batch_read** — use the same dtype fields (minus `_key`) with `batch_read(_dtype=...)` for efficient read-back
- **Large datasets** — split large arrays into chunks and write in batches:

```python
chunk_size = 1000
for i in range(0, len(data), chunk_size):
    chunk = data[i:i + chunk_size]
    client.batch_write_numpy(chunk, "test", "demo", dtype)
```

## API Reference

```python
# Sync
results: list[Record] = client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
)

# Async
results: list[Record] = await client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `np.ndarray` | required | Structured numpy array with record data |
| `namespace` | `str` | required | Target Aerospike namespace |
| `set_name` | `str` | required | Target set name |
| `_dtype` | `np.dtype` | required | Structured dtype describing the array layout |
| `key_field` | `str` | `"_key"` | Name of the dtype field to use as the record user key |
| `policy` | `dict \| None` | `None` | Optional [`BatchPolicy`](../../api/types.md#batchpolicy) overrides |

**Returns:** `list[Record]` — a list of `Record` NamedTuples `(key, meta, bins)` with write results.

**See also:** [NumPy Batch Read Guide](./numpy-batch.md) for reading records back into numpy arrays.
