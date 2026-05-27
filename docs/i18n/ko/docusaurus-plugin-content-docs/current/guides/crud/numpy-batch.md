---
title: NumPy Batch Read Guide
sidebar_label: NumPy Batch Read
sidebar_position: 4
slug: /guides/numpy-batch
description: Use batch_read with numpy structured arrays for high-performance columnar analytics directly from Aerospike.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

`batch_read(...).to_numpy(dtype)` 는 Python object 대신 **numpy structured array** 를 반환:

- **Zero-copy columnar access** — `batch.batch_records["temperature"]` 가 numpy array 반환; `torch.from_numpy(...)` 와 결합해 O(1) tensor hand-off
- **Fill 동안 GIL release** — per-record `Value → buffer` write 가 GIL 해제된 상태로 발생, 다른 asyncio task / thread 가 동시 실행 가능
- **Vectorised 연산** — 결과에 numpy/pandas 직접 사용
- **메모리 효율** — Rust 가 numpy buffer 에 직접 write, Python object 우회

:::tip[Performance]
record 10K + bin 5개에서 `lazy_records.to_dict()` materialisation 대비 ~60K 개 중간 Python object 제거.
:::

## 설치

```bash
pip install "aerospike-py[numpy]"
```

선택적 dependency 로 `numpy>=2.0` 설치됨.

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()

# 1. record write
for i in range(100):
    client.put(
        ("test", "sensors", f"sensor_{i}"),
        {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
        policy={"key": aerospike.POLICY_KEY_SEND},
    )

# 2. bin 에 맞는 dtype 정의
dtype = np.dtype([
    ("temperature", "f8"),  # float64
    ("humidity", "i4"),     # int32
    ("status", "u1"),       # uint8
])

# 3. Batch read + to_numpy(dtype)
keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
batch = client.batch_read(keys).to_numpy(dtype)

# 4. numpy array 로 접근
print(batch.batch_records["temperature"].mean())  # columnar 접근
print(batch.batch_records[0])                      # row 접근
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

    # 1. record write
    for i in range(100):
        await client.put(
            ("test", "sensors", f"sensor_{i}"),
            {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
            policy={"key": aerospike.POLICY_KEY_SEND},
        )

    # 2. bin 에 맞는 dtype 정의
    dtype = np.dtype([
        ("temperature", "f8"),
        ("humidity", "i4"),
        ("status", "u1"),
    ])

    # 3. Batch read + to_numpy(dtype)
    keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
    lazy_records = await client.batch_read(keys)
    batch = lazy_records.to_numpy(dtype)

    # 4. numpy array 로 접근
    print(batch.batch_records["temperature"].mean())
    print(batch.batch_records[0])
    print(batch.get("sensor_42")["temperature"])

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## NumpyBatchRecords

`batch_read()` 가 반환하는 `LazyBatchRecords` 에 `.to_numpy(dtype)` 를 호출하면 `NumpyBatchRecords` 객체를 얻음. structured-array fill 이 GIL release 된 상태로 실행되어 결과를 `torch.from_numpy(...)` 에 zero-copy 로 바로 넘길 수 있음:

:::warning[Missing read 는 silently zero-fill]

`result_codes[i] != 0` 인 row (`RecordNotFound` 포함) 는 data 와 meta entry 가 dtype 의 zero 값으로 남음 — buffer 만으로는 실제로 bin 이 zero 인 record 와 구분 불가. averaging, summing, inference 전에 항상 `batch.result_codes == 0` 으로 mask (또는 `lazy_records.found_count()` 확인).

:::

| Attribute | Type | 설명 |
|-----------|------|-------------|
| `batch_records` | `np.ndarray` | 사용자 지정 dtype 의 structured array |
| `meta` | `np.ndarray` | dtype `[("gen", "u4"), ("ttl", "u4")]` 의 structured array |
| `result_codes` | `np.ndarray` | per-record result code 의 `int32` array (0 = success) |
| `_map` | `dict` | key 기반 lookup 을 위한 `{primary_key: index}` 매핑 |

### Method

| Method | Returns | 설명 |
|--------|---------|-------------|
| `get(primary_key)` | `np.void` | primary key 로 단일 record lookup |

## 지원되는 dtype kind

| numpy Kind | Code | Example | Aerospike Value |
|------------|------|---------|-----------------|
| Signed int | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` — target size 로 truncate |
| Unsigned int | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` — unsigned 로 cast |
| Float | `f` | `"f2"`, `"f4"`, `"f8"` | `Float(f64)` — target precision 으로 cast |
| Fixed bytes | `S` | `"S8"`, `"S16"` | `Blob(bytes)` 또는 `String` — truncate/zero-pad |
| Void bytes | `V` | `"V4"`, `"V16"` | `Blob(bytes)` — truncate/zero-pad |
| Sub-array | — | `("f4", (128,))` | `Blob(bytes)` — raw copy (예: vector embedding) |

:::tip[지원 안 되는 dtype]

Unicode string (`U`) 과 Python object (`O`) 는 `TypeError` 로 reject. string 데이터에는 `S` (fixed bytes) 사용.

:::

## 접근 패턴

### Columnar 접근

```python
temps = batch.batch_records["temperature"]  # float64 array
print(temps.mean(), temps.std(), temps.max())

# boolean filtering
hot = batch.batch_records[temps > 40.0]
```

### Row 접근

```python
record = batch.batch_records[0]
print(record["temperature"], record["humidity"])
```

### Key Lookup

```python
record = batch.get("sensor_42")
print(record["temperature"])
```

### Meta 접근

```python
# per-record generation 과 TTL
print(batch.meta["gen"])  # uint32 array
print(batch.meta["ttl"])  # uint32 array

# 실패한 record 확인
failed = batch.result_codes != 0
print(f"Failed: {failed.sum()} / {len(batch.result_codes)}")
```

## dtype 정의

dtype field 이름이 Aerospike bin 이름과 정확히 일치해야 함.

### Numeric bin

```python
dtype = np.dtype([
    ("price", "f8"),       # float64
    ("quantity", "i4"),    # int32
    ("flags", "u1"),       # uint8
])
```

### Bytes / Blob bin

```python
dtype = np.dtype([
    ("name", "S32"),       # 32-byte fixed string
    ("raw_data", "V64"),   # 64-byte void buffer
])
```

### Vector Embedding (Sub-array)

float32 vector (예: ML embedding) 를 Aerospike 에 byte blob 으로 저장한 뒤 sub-array 로 read:

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

# Write: raw bytes 로 embedding 저장
embedding = np.random.randn(dim).astype(np.float32)
client.put(
    ("test", "vectors", "vec_1"),
    {"embedding": embedding.tobytes(), "score": 0.95},
    policy={"key": aerospike.POLICY_KEY_SEND},
)

# Read: sub-array 가 자동으로 bytes 에서 재구성
keys = [("test", "vectors", "vec_1")]
batch = client.batch_read(keys).to_numpy(dtype)

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
    lazy_records = await client.batch_read(keys)
    batch = lazy_records.to_numpy(dtype)

    recovered = batch.batch_records[0]["embedding"]
    np.testing.assert_array_almost_equal(recovered, embedding)

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Bin Filtering

서버에서 특정 bin 만 read 하려면 `bins` 와 `.to_numpy(dtype)` 결합:

```python
dtype = np.dtype([("temperature", "f8")])
batch = client.batch_read(keys, bins=["temperature"]).to_numpy(dtype)
```

서버에서 `temperature` bin 만 전송되어 네트워크 I/O 감소.

## Error Handling

### Missing Record

찾을 수 없는 record (result code 2) 는 structured array 에서 zero 로 채워짐:

```python
batch = client.batch_read(keys).to_numpy(dtype)

# result code 확인
for i, rc in enumerate(batch.result_codes):
    if rc != 0:
        print(f"Record {i} failed with result code {rc}")

# 성공한 record 만 필터
success_mask = batch.result_codes == 0
valid_data = batch.batch_records[success_mask]
```

### Missing Bin

record 가 존재하지만 bin 이 missing 이면 field 가 zero 로 default (해당 dtype 의 numpy zero-value):

```python
# record 가 "temperature" 는 있지만 "humidity" 가 없음
dtype = np.dtype([("temperature", "f8"), ("humidity", "i4")])
batch = client.batch_read(keys).to_numpy(dtype)
# humidity 는 해당 bin 이 missing 인 record 에서 0
```

### dtype 검증 오류

```python
# TypeError: unicode string 미지원
dtype = np.dtype([("name", "U10")])
batch = client.batch_read(keys).to_numpy(dtype)  # TypeError raise

# TypeError: Python object 미지원
dtype = np.dtype([("data", "O")])
batch = client.batch_read(keys).to_numpy(dtype)  # TypeError raise
```

## Pandas 통합

`NumpyBatchRecords` 를 pandas DataFrame 으로 변환:

```python
import pandas as pd

batch = client.batch_read(keys).to_numpy(dtype)

df = pd.DataFrame(batch.batch_records)
df["gen"] = batch.meta["gen"]
df["ttl"] = batch.meta["ttl"]

# 이제 pandas 연산 사용
hot_sensors = df[df["temperature"] > 35.0]
print(hot_sensors.describe())
```

## Best Practice

- **dtype 을 bin 에 맞춤** — dtype field 이름이 Aerospike bin 이름과 일치
- **`bins` 파라미터 사용** — `.to_numpy(dtype)` 와 결합해 네트워크 전송 줄이기
- **`result_codes` 확인** — 분석 전 실패한 record 필터링
- **충분한 최소 dtype 사용** — 메모리 절감 위해 `"f8"` 대신 `"f4"`, `"i8"` 대신 `"i2"`
- **Batch size** — 최적 성능을 위해 batch 를 100-5,000 key 로 유지
- **Vector 데이터** — embedding 을 `tobytes()` blob 으로 저장하고 sub-array dtype 으로 read

## API Reference

```python
# Sync
lazy_records: LazyBatchRecords = client.batch_read(
    keys: list[tuple[str, str, str | int | bytes]],
    bins: list[str] | None = None,
    policy: dict | None = None,
)
batch: NumpyBatchRecords = lazy_records.to_numpy(dtype)

# Async
lazy_records: LazyBatchRecords = await client.batch_read(
    keys: list[tuple[str, str, str | int | bytes]],
    bins: list[str] | None = None,
    policy: dict | None = None,
)
batch: NumpyBatchRecords = lazy_records.to_numpy(dtype)
```

`LazyBatchRecords.to_numpy(dtype)` 호출은 GIL 해제된 상태로 structured-array materialisation 을 수행 — per-record fill loop 가 raw `ptr::write_unaligned` write 시퀀스라, sibling Python 작업 (다른 asyncio task, torch inference thread) 이 buffer fill 중 GIL 보유 가능.

| Parameter | Type | Default | 설명 |
|-----------|------|---------|-------------|
| `keys` | `list[Key]` | required | `(namespace, set, primary_key)` tuple list (`batch_read` argument) |
| `bins` | `list[str] \| None` | `None` | read 할 bin name (`None` = 전체) (`batch_read` argument) |
| `policy` | `dict \| None` | `None` | batch policy override (`batch_read` argument) |
| `dtype` | `np.dtype` | required | 출력 schema 를 정의하는 structured dtype (`LazyBatchRecords.to_numpy` argument) |
