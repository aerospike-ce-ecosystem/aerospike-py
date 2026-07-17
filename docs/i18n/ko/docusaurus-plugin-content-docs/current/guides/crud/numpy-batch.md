---
title: NumPy Batch 읽기 가이드
sidebar_label: NumPy Batch 읽기
sidebar_position: 4
slug: /guides/numpy-batch
description: NumPy 구조화 배열과 batch_read를 사용해 Aerospike 데이터를 고성능 열 기반 분석에 활용하는 방법
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

`batch_read(...).to_numpy(dtype)`는 batch result를 record별 Python object 대신 **NumPy structured array**로 materialize합니다.

- **Zero-copy column access** — `batch.batch_records["temperature"]`는 NumPy array를 반환합니다. `torch.from_numpy(...)`에 전달하면 O(1)로 tensor를 만들 수 있습니다.
- **GIL-free buffer fill** — Client는 GIL을 해제한 상태에서 record별 `Value`를 buffer에 씁니다. 이 동안 다른 asyncio task와 thread가 실행될 수 있습니다.
- **Vectorized 연산** — 결과를 NumPy나 pandas에서 바로 사용할 수 있습니다.
- **낮은 object overhead** — Rust가 NumPy buffer에 직접 쓰므로 value마다 Python object를 만들지 않습니다.

:::tip[Performance]
Record 10,000개와 bin 5개를 읽을 때 `lazy_records.to_dict()`로 materialize하는 방식보다 중간 Python object를 약 60,000개 줄입니다.
:::

## 설치

```bash
pip install "aerospike-py[numpy]"
```

선택적 dependency로 `numpy>=2.0`을 설치합니다.

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

`batch_read()`가 반환한 `LazyBatchRecords`에서 `.to_numpy(dtype)`를 호출하면 `NumpyBatchRecords` 객체를 얻습니다. Client가 GIL을 해제하고 structured array를 채우므로 결과를 복사하지 않고 `torch.from_numpy(...)`에 바로 전달할 수 있습니다.

:::warning[찾지 못한 record는 0으로 채워짐]

`RecordNotFound`를 포함해 `result_codes[i] != 0`인 row는 data와 metadata가 dtype의 0 값으로 남습니다. Buffer만 봐서는 실제 bin 값이 0인 record와 구분할 수 없습니다. 평균이나 합계를 계산하거나 inference에 전달하기 전에 `batch.result_codes == 0`으로 mask하거나 `lazy_records.found_count()`를 확인하세요.

:::

| Attribute | Type | 설명 |
|-----------|------|-------------|
| `batch_records` | `np.ndarray` | 사용자 지정 dtype을 사용하는 structured array |
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

dtype field 이름은 Aerospike bin 이름과 정확히 일치해야 합니다.

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

Record는 있지만 bin이 없으면 해당 field에는 dtype에 맞는 NumPy zero value가 들어갑니다.

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

- **dtype을 bin에 맞추기** — dtype field 이름을 Aerospike bin 이름과 같게 지정하세요.
- **`bins` 파라미터 사용** — `.to_numpy(dtype)` 와 결합해 네트워크 전송 줄이기
- **`result_codes` 확인** — 분석 전 실패한 record 필터링
- **데이터를 표현할 수 있는 가장 작은 dtype 사용** — 메모리를 줄이려면 `"f8"` 대신 `"f4"`, `"i8"` 대신 `"i2"`를 사용하세요.
- **Batch size** — batch 하나에 100~5,000개 key를 넣을 때 성능이 가장 좋습니다.
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

`LazyBatchRecords.to_numpy(dtype)`는 GIL을 해제한 상태에서 structured array를 materialize합니다. Record별 fill loop는 raw `ptr::write_unaligned`를 사용하므로 buffer를 채우는 동안 다른 asyncio task나 PyTorch inference thread가 GIL을 사용할 수 있습니다.

| Parameter | Type | Default | 설명 |
|-----------|------|---------|-------------|
| `keys` | `list[Key]` | required | `(namespace, set, primary_key)` tuple list (`batch_read` argument) |
| `bins` | `list[str] \| None` | `None` | read 할 bin name (`None` = 전체) (`batch_read` argument) |
| `policy` | `dict \| None` | `None` | batch policy override (`batch_read` argument) |
| `dtype` | `np.dtype` | required | 출력 schema 를 정의하는 structured dtype (`LazyBatchRecords.to_numpy` argument) |
