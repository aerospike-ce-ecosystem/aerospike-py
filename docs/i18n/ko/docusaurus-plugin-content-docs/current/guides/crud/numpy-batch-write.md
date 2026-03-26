---
title: NumPy 배치 쓰기 가이드
sidebar_label: NumPy 배치 쓰기
sidebar_position: 5
slug: /guides/numpy-batch-write
description: batch_write_numpy를 사용하여 numpy 구조화 배열에서 직접 Aerospike로 고성능 대량 적재를 수행하는 방법을 안내합니다.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## 개요

`batch_write_numpy()`는 **numpy 구조화 배열**에서 직접 여러 레코드를 Aerospike에 기록합니다. 각 행이 별도의 쓰기 작업이 되며, dtype 필드가 Aerospike bin에 매핑됩니다.

- **배열에서 레코드로 직접 매핑** -- 중간 Python dict나 루프 불필요
- **키 필드 추출** -- 지정된 dtype 필드(기본값 `_key`)가 레코드의 사용자 키로 사용됨
- **자동 bin 매핑** -- 밑줄(`_`)로 시작하지 않는 모든 필드가 bin이 됨
- **배치 실행** -- 모든 행이 단일 배치 호출로 기록됨

:::tip[사용 시기]

데이터가 이미 numpy 배열에 있을 때(예: ML 피처 스토어, 센서 데이터 파이프라인, 과학 데이터셋) `batch_write_numpy()`를 사용하세요. 일반 Python dict의 경우 `put()` 또는 표준 배치 작업을 대신 사용하세요.

:::

## 설치

```bash
pip install "aerospike-py[numpy]"
```

## 빠른 시작

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()

# 1. 키 필드와 bin 필드로 dtype 정의
dtype = np.dtype([
    ("_key", "i4"),     # 레코드 키 (int32)
    ("score", "f8"),    # bin: float64
    ("count", "i4"),    # bin: int32
])

# 2. 구조화 배열 생성
data = np.array([
    (1, 0.95, 10),
    (2, 0.87, 20),
    (3, 0.72, 15),
], dtype=dtype)

# 3. 배치 쓰기
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

    # 1. 키 필드와 bin 필드로 dtype 정의
    dtype = np.dtype([
        ("_key", "i4"),
        ("score", "f8"),
        ("count", "i4"),
    ])

    # 2. 구조화 배열 생성
    data = np.array([
        (1, 0.95, 10),
        (2, 0.87, 20),
        (3, 0.72, 15),
    ], dtype=dtype)

    # 3. 배치 쓰기
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

## 동작 원리

```
numpy 구조화 배열                  Aerospike
┌──────┬───────┬───────┐
│ _key │ score │ count │
├──────┼───────┼───────┤          ┌──────────────────────┐
│  1   │ 0.95  │  10   │  ──────▶ │ key=1 {score, count} │
│  2   │ 0.87  │  20   │  ──────▶ │ key=2 {score, count} │
│  3   │ 0.72  │  15   │  ──────▶ │ key=3 {score, count} │
└──────┴───────┴───────┘          └──────────────────────┘
        ▲                                  ▲
   key_field="_key"               bins = 밑줄로 시작하지 않는 필드
```

1. `key_field`(기본값 `"_key"`) 컬럼이 각 레코드의 사용자 키로 추출됩니다
2. `_`로 시작하지 **않는** 모든 필드가 Aerospike bin이 됩니다
3. `_`로 시작하는 필드(키 필드 제외)는 무시됩니다

## 키 필드

기본적으로 `"_key"`라는 이름의 dtype 필드가 레코드 키로 사용됩니다. `key_field`로 다른 필드를 지정할 수 있습니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
dtype = np.dtype([
    ("user_id", "i8"),    # 이 필드를 레코드 키로 사용
    ("score", "f8"),
])

data = np.array([(100, 1.5), (101, 2.5)], dtype=dtype)

# "_key" 대신 "user_id"를 키로 사용
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

커스텀 `key_field`를 사용할 때, 해당 필드를 bin으로도 저장하려면 필드 이름이 `_`로 시작하지 **않아야** 합니다. `_`로 시작하는 필드는 키로만 사용되고 bin으로 기록되지 않습니다.

:::

## 지원되는 dtype 종류

`batch_read()`의 `_dtype`에서 지원되는 것과 동일한 dtype 종류가 쓰기에도 지원됩니다:

| numpy 종류 | 코드 | 예시 | Aerospike 값 |
|------------|------|------|--------------|
| 부호 있는 정수 | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` |
| 부호 없는 정수 | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` |
| 부동 소수점 | `f` | `"f4"`, `"f8"` | `Float(f64)` |
| 고정 바이트 | `S` | `"S8"`, `"S16"` | `Blob(bytes)` 또는 `String` |
| Void 바이트 | `V` | `"V4"`, `"V16"` | `Blob(bytes)` |
| 하위 배열 | -- | `("f4", (128,))` | `Blob(bytes)` |

:::tip[지원되지 않는 dtype]

유니코드 문자열(`U`)과 Python 객체(`O`)는 지원되지 않습니다. 문자열 데이터에는 `S`(고정 바이트)를 사용하세요.

:::

## 예제

### 센서 데이터 적재

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

# 1000개의 센서 측정값 생성
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

### 벡터 임베딩

ML 임베딩을 바이트 blob으로 저장합니다:

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

dim = 128
dtype = np.dtype([
    ("_key", "i4"),
    ("embedding", "V" + str(dim * 4)),  # 128 * 4 바이트 = 512바이트 blob
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

### 쓰기와 읽기 왕복

`batch_write_numpy()`와 `batch_read()`의 `_dtype`을 조합하여 완전한 numpy 왕복을 수행합니다:

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

# 쓰기
data = np.array([
    (1, 1.0, 2.0, 0),
    (2, 3.0, 4.0, 1),
    (3, 5.0, 6.0, 0),
], dtype=dtype)
client.batch_write_numpy(data, "test", "points", dtype)

# _dtype으로 읽기
read_dtype = np.dtype([("x", "f8"), ("y", "f8"), ("category", "i4")])
keys = [("test", "points", i) for i in range(1, 4)]
batch = client.batch_read(keys, _dtype=read_dtype, policy={"key": aerospike.POLICY_KEY_SEND})

# 벡터화 분석
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

### Pandas DataFrame에서 Aerospike로

pandas DataFrame을 numpy를 통해 Aerospike에 기록합니다:

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

# 구조화 배열로 변환
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

## 일시적 실패 자동 재시도

`retry > 0`이면 일시적 오류(timeout, device overload, key busy, server memory, partition unavailable)로 실패한 레코드를 지수 백오프로 자동 재시도합니다. 영구 오류(key exists, record too big)는 재시도하지 않습니다.

```python
# 일시적 실패 시 최대 3회 재시도
results = client.batch_write_numpy(data, "test", "demo", dtype, retry=3)

# 재시도 후에도 실패한 레코드 확인
for br in results.batch_records:
    if br.result != 0:
        print(f"Write failed for key {br.key} after retries (code={br.result})")
```

백오프 간격은 10ms, 20ms, 40ms, ... 최대 500ms입니다. 재시도 시에는 실패한 레코드만 다시 전송하며 전체 배치를 재전송하지 않습니다.

:::tip
대량 벌크 적재 시 간헐적 일시 오류가 예상되면 `retry=3`이 적당합니다. 애플리케이션에서 재시도 로직을 직접 제어하려면 `retry=0`(기본값)을 사용하세요.
:::

## 오류 처리

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

## 모범 사례

- **dtype을 데이터에 맞추기** -- 메모리와 네트워크 전송량을 줄이기 위해 최소한의 dtype을 사용하세요 (`"f8"` 대신 `"f4"`, `"i8"` 대신 `"i2"`)
- **배치 크기** -- 최적의 성능을 위해 호출당 100-5,000행을 유지하세요
- **키 필드 규칙** -- 일관성을 위해 기본 키 필드로 `"_key"`를 사용하세요
- **밑줄 접두사** -- `_`로 시작하는 필드는 bin에서 제외됩니다. 메타데이터 필드에 활용하세요
- **batch_read와의 왕복** -- 효율적인 읽기를 위해 동일한 dtype 필드(`_key` 제외)를 `batch_read(_dtype=...)`에 사용하세요
- **대용량 데이터셋** -- 큰 배열을 청크로 분할하여 배치로 기록하세요:

```python
chunk_size = 1000
for i in range(0, len(data), chunk_size):
    chunk = data[i:i + chunk_size]
    client.batch_write_numpy(chunk, "test", "demo", dtype)
```

## API 레퍼런스

```python
# Sync
results: BatchRecords = client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
    retry: int = 0,
)

# Async
results: BatchRecords = await client.batch_write_numpy(
    data: np.ndarray,
    namespace: str,
    set_name: str,
    _dtype: np.dtype,
    key_field: str = "_key",
    policy: dict | None = None,
    retry: int = 0,
)
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `data` | `np.ndarray` | 필수 | 레코드 데이터가 담긴 구조화 numpy 배열 |
| `namespace` | `str` | 필수 | 대상 Aerospike namespace |
| `set_name` | `str` | 필수 | 대상 set 이름 |
| `_dtype` | `np.dtype` | 필수 | 배열 레이아웃을 설명하는 구조화 dtype |
| `key_field` | `str` | `"_key"` | 레코드 사용자 키로 사용할 dtype 필드 이름 |
| `policy` | `dict \| None` | `None` | 선택적 [`BatchPolicy`](/docs/api/types#batchpolicy) 오버라이드 |
| `retry` | `int` | `0` | 일시적 실패(timeout, device overload, key busy) 최대 재시도 횟수. `0` = 재시도 안 함. |

**반환값:** `BatchRecords` -- `batch_records: list[BatchRecord]`를 포함하며, 각 `BatchRecord`는 `key`, `result` (0=성공), `record` (`Record` 또는 `None`)를 가집니다.

**참고:** numpy 배열로 레코드를 읽어오려면 [NumPy 배치 읽기 가이드](./numpy-batch.md)를 참조하세요.
