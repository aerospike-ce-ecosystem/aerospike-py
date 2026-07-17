---
title: NumPy Batch Write Guide
sidebar_label: NumPy Batch Write
sidebar_position: 5
slug: /guides/numpy-batch-write
description: Use batch_write_numpy to write records directly from numpy structured arrays for high-performance bulk ingestion into Aerospike.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## 개요

`batch_write_numpy()`는 **NumPy structured array**에서 Aerospike로 record를 직접 씁니다. 각 row는 하나의 write operation이 되고, 각 dtype field는 Aerospike bin에 매핑됩니다.

- **Array-to-record 직접 매핑** — 중간 Python dict나 loop를 만들지 않습니다.
- **Key field 추출** — 지정한 dtype field(기본값 `_key`)를 record의 user key로 사용합니다.
- **자동 bin 매핑** — 이름이 `_`로 시작하지 않는 모든 field가 bin이 됩니다.
- **Batch 실행** — 모든 row를 한 번의 batch call로 씁니다.

:::tip[언제 쓰나]

데이터가 이미 NumPy array에 있다면 `batch_write_numpy()`를 사용하세요. ML feature store, sensor data pipeline, scientific dataset이 대표적인 예입니다. Python dict를 쓸 때는 `put()`이나 표준 batch operation을 사용합니다.

:::

## 설치

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

# 1. key field 와 bin field 로 dtype 정의
dtype = np.dtype([
    ("_key", "i4"),     # record key (int32)
    ("score", "f8"),    # bin: float64
    ("count", "i4"),    # bin: int32
])

# 2. structured array 생성
data = np.array([
    (1, 0.95, 10),
    (2, 0.87, 20),
    (3, 0.72, 15),
], dtype=dtype)

# 3. Batch write
results = client.batch_write_numpy(data, "test", "demo", dtype)

# 4. 결과 확인
for br in results.batch_records:
    if br.result == 0:
        print(f"Key: {br.key}, Gen: {br.record.meta.gen}")
    else:
        print(f"Failed: {br.key}, code={br.result}")
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

    # 1. key field 와 bin field 로 dtype 정의
    dtype = np.dtype([
        ("_key", "i4"),
        ("score", "f8"),
        ("count", "i4"),
    ])

    # 2. structured array 생성
    data = np.array([
        (1, 0.95, 10),
        (2, 0.87, 20),
        (3, 0.72, 15),
    ], dtype=dtype)

    # 3. Batch write
    results = await client.batch_write_numpy(data, "test", "demo", dtype)

    # 4. 결과 확인
    for br in results.batch_records:
        if br.result == 0:
            print(f"Key: {br.key}, Gen: {br.record.meta.gen}")
        else:
            print(f"Failed: {br.key}, code={br.result}")

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## 동작 방식

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
   key_field="_key"               bins = non-underscore field
```

1. `key_field` (default `"_key"`) column 이 각 record 의 user key 로 추출됨
2. `_`로 시작하지 **않은** 나머지 field는 Aerospike bin이 됩니다.
3. `_` 로 prefix 된 field (key field 외) 는 무시됨

## Key Field

기본적으로 `"_key"` 라는 dtype field 가 record key 로 사용. `key_field` 로 다른 field 지정 가능:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
dtype = np.dtype([
    ("user_id", "i8"),    # 이것을 record key 로 사용
    ("score", "f8"),
])

data = np.array([(100, 1.5), (101, 2.5)], dtype=dtype)

# "_key" 대신 "user_id" 를 key 로 사용
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

custom `key_field` 사용 시 그 field 가 bin 으로도 저장되길 원하면 이름이 `_` 로 시작하면 **안 됨**. `_` 로 시작하면 key 로만 사용되고 bin 으로는 write 안 됨.

:::

## 지원되는 dtype kind

`batch_read().to_numpy(dtype)` 가 지원하는 동일 dtype kind 가 write 에도 지원됨:

| numpy Kind | Code | Example | Aerospike Value |
|------------|------|---------|-----------------|
| Signed int | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` |
| Unsigned int | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` |
| Float | `f` | `"f4"`, `"f8"` | `Float(f64)` |
| Fixed bytes | `S` | `"S8"`, `"S16"` | `Blob(bytes)` 또는 `String` |
| Void bytes | `V` | `"V4"`, `"V16"` | `Blob(bytes)` |
| Sub-array | — | `("f4", (128,))` | `Blob(bytes)` |

:::tip[지원 안 되는 dtype]

Unicode string (`U`) 과 Python object (`O`) 는 미지원. string 데이터에는 `S` (fixed bytes) 사용.

:::

## 예제

### Sensor 데이터 ingestion

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

# 1000 개 sensor reading 생성
n = 1000
data = np.zeros(n, dtype=dtype)
data["_key"] = np.arange(n)
data["temperature"] = np.random.normal(25.0, 5.0, n)
data["humidity"] = np.random.uniform(30.0, 90.0, n).astype(np.float32)
data["pressure"] = np.random.normal(1013.25, 10.0, n).astype(np.float32)
data["status"] = 1

results = client.batch_write_numpy(data, "test", "sensors", dtype)
print(f"Wrote {len(results.batch_records)} records")
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
    print(f"Wrote {len(results.batch_records)} records")

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

### Vector Embedding

ML embedding 을 byte blob 으로 저장:

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

### Write 와 Read Roundtrip

`batch_write_numpy()` 와 `batch_read().to_numpy(dtype)` 를 결합한 full numpy roundtrip:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# dtype 정의
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

# to_numpy(dtype) 로 read back — buffer fill 동안 GIL release
read_dtype = np.dtype([("x", "f8"), ("y", "f8"), ("category", "i4")])
keys = [("test", "points", i) for i in range(1, 4)]
batch = client.batch_read(
    keys,
    policy={"key": aerospike.POLICY_KEY_SEND},
).to_numpy(read_dtype)

# Vectorised 분석
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
    lazy_records = await client.batch_read(keys, policy={"key": aerospike.POLICY_KEY_SEND})
    batch = lazy_records.to_numpy(read_dtype)

    print(batch.batch_records["x"].mean())
    print(batch.batch_records["category"].sum())

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

### Pandas DataFrame 을 Aerospike 로

numpy 를 거쳐 pandas DataFrame 을 Aerospike 에 write:

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

# structured array 로 변환
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

## Transient 실패에 대한 Retry

`retry > 0`이면 transient error(timeout, device overload, key busy, server memory, partition unavailable)가 발생한 record를 exponential backoff로 자동 재시도합니다. Key exists나 record too big 같은 영구 error는 재시도하지 않습니다.

```python
# transient 실패 시 최대 3회 retry
results = client.batch_write_numpy(data, "test", "demo", dtype, retry=3)

# retry 후에도 실패한 record 확인
for br in results.batch_records:
    if br.result != 0:
        print(f"Write failed for key {br.key} after retries (code={br.result})")
```

Retry 간격은 10 ms에서 시작해 20 ms, 40 ms 순으로 늘어나며 최대 500 ms입니다. 매 retry에서는 전체 batch가 아니라 실패한 record만 다시 보냅니다.

:::tip
대규모 bulk ingestion에서 간헐적인 transient failure가 예상된다면 `retry=3`부터 시작하세요. Application에서 retry logic을 직접 제어하려면 기본값인 `retry=0`을 사용합니다.
:::

## Error Handling

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_write_numpy(data, "test", "demo", dtype)
    for br in results.batch_records:
        if br.result != 0:
            print(f"Write failed for key {br.key} (code={br.result})")
except AerospikeError as e:
    print(f"Batch write error: {e}")
```

## Best Practice

- **dtype을 데이터에 맞추기** — 메모리 사용량과 네트워크 전송량을 줄이려면 데이터를 표현할 수 있는 가장 작은 dtype을 사용하세요(`"f8"` 대신 `"f4"`, `"i8"` 대신 `"i2"`).
- **Batch size** — 호출 하나에 100~5,000개 row를 넣을 때 성능이 가장 좋습니다.
- **Key field 규칙** — 일관성을 위해 기본 key field인 `"_key"`를 사용하세요.
- **Underscore prefix** — `_` 로 시작하는 field 는 bin 에서 제외, metadata field 에 활용
- **`batch_read`로 다시 읽기** — 같은 dtype에서 `_key`를 제외한 field를 사용해 `batch_read(...).to_numpy(dtype)`를 호출하세요. GIL을 해제한 상태에서 buffer를 채우므로 효율적입니다.
- **대형 dataset** — 큰 array 를 chunk 로 나눠 batch 단위 write:

```python
chunk_size = 1000
for i in range(0, len(data), chunk_size):
    chunk = data[i:i + chunk_size]
    client.batch_write_numpy(chunk, "test", "demo", dtype)
```

## API Reference

```python
# Sync
results: BatchWriteResult = client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
    retry: int = 0,
)

# Async
results: BatchWriteResult = await client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
    retry: int = 0,
)
```

| Parameter | Type | Default | 설명 |
|-----------|------|---------|-------------|
| `data` | `np.ndarray` | required | record 데이터의 structured numpy array |
| `namespace` | `str` | required | target Aerospike namespace |
| `set_name` | `str` | required | target set 이름 |
| `_dtype` | `np.dtype` | required | array 레이아웃을 describing 하는 structured dtype |
| `key_field` | `str` | `"_key"` | record user key 로 사용할 dtype field 이름 |
| `policy` | `dict \| None` | `None` | 선택적 [`BatchPolicy`](/docs/api/types#batchpolicy) override |
| `retry` | `int` | `0` | transient 실패 (timeout, device overload, key busy) 의 최대 retry. `0` = retry 없음. |

**Returns:** `BatchWriteResult` — `batch_records: list[BatchRecord]` 를 가진 NamedTuple. 각 `BatchRecord` 가 `key`, `result` (0=success), `record` (`Record` 또는 `None`), `in_doubt` (transport-ambiguity flag) carry.

**See also:** numpy array 로 record read back 하려면 [NumPy Batch Read Guide](./numpy-batch.md) 참조.
