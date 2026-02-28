---
title: NumPy 배치 읽기 가이드
sidebar_label: NumPy 배치 읽기
sidebar_position: 4
slug: /guides/numpy-batch
description: batch_read에 numpy 구조화 배열을 사용하여 Aerospike에서 직접 고성능 컬럼형 분석을 수행하는 방법을 안내합니다.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

`batch_read()`에 `_dtype`을 전달하면 Python 객체 대신 **numpy 구조화 배열**을 반환합니다:

- **제로 카피 컬럼형 접근** -- `batch.batch_records["temperature"]`로 numpy 배열을 반환
- **벡터화 연산** -- 결과에 대해 numpy/pandas를 직접 사용
- **메모리 효율성** -- Rust가 Python 객체를 거치지 않고 numpy 버퍼에 직접 기록

:::tip[성능]
5개 bin이 있는 10K 레코드의 경우, 표준 `BatchRecords` 경로 대비 약 60K개의 중간 Python 객체를 제거합니다.
:::

## 설치

```bash
pip install "aerospike-py[numpy]"
```

선택적 의존성으로 `numpy>=2.0`이 설치됩니다.

## 빠른 시작

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()

# 1. 레코드 작성
for i in range(100):
    client.put(
        ("test", "sensors", f"sensor_{i}"),
        {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
        policy={"key": aerospike.POLICY_KEY_SEND},
    )

# 2. bin에 맞는 dtype 정의
dtype = np.dtype([
    ("temperature", "f8"),  # float64
    ("humidity", "i4"),     # int32
    ("status", "u1"),       # uint8
])

# 3. _dtype으로 배치 읽기
keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
batch = client.batch_read(keys, _dtype=dtype)

# 4. numpy 배열로 접근
print(batch.batch_records["temperature"].mean())  # 컬럼형 접근
print(batch.batch_records[0])                      # 행 접근
print(batch.get("sensor_42")["temperature"])       # 키 조회
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

    # 1. 레코드 작성
    for i in range(100):
        await client.put(
            ("test", "sensors", f"sensor_{i}"),
            {"temperature": 20.0 + i * 0.5, "humidity": 40 + i, "status": 1},
            policy={"key": aerospike.POLICY_KEY_SEND},
        )

    # 2. bin에 맞는 dtype 정의
    dtype = np.dtype([
        ("temperature", "f8"),
        ("humidity", "i4"),
        ("status", "u1"),
    ])

    # 3. _dtype으로 배치 읽기
    keys = [("test", "sensors", f"sensor_{i}") for i in range(100)]
    batch = await client.batch_read(keys, _dtype=dtype)

    # 4. numpy 배열로 접근
    print(batch.batch_records["temperature"].mean())
    print(batch.batch_records[0])
    print(batch.get("sensor_42")["temperature"])

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## NumpyBatchRecords

`_dtype`을 전달하면 `batch_read()`는 `NumpyBatchRecords` 객체를 반환합니다:

| 속성 | 타입 | 설명 |
|------|------|------|
| `batch_records` | `np.ndarray` | 사용자가 지정한 dtype의 구조화 배열 |
| `meta` | `np.ndarray` | `[("gen", "u4"), ("ttl", "u4")]` dtype의 구조화 배열 |
| `result_codes` | `np.ndarray` | 레코드별 결과 코드의 `int32` 배열 (0 = 성공) |
| `_map` | `dict` | 키 기반 조회를 위한 `{primary_key: index}` 매핑 |

### 메서드

| 메서드 | 반환 타입 | 설명 |
|--------|-----------|------|
| `get(primary_key)` | `np.void` | primary key로 단일 레코드 조회 |

## 지원되는 dtype 종류

| numpy 종류 | 코드 | 예시 | Aerospike 값 |
|------------|------|------|--------------|
| 부호 있는 정수 | `i` | `"i1"`, `"i2"`, `"i4"`, `"i8"` | `Int(i64)` -- 대상 크기로 잘림 |
| 부호 없는 정수 | `u` | `"u1"`, `"u2"`, `"u4"`, `"u8"` | `Int(i64)` -- unsigned로 캐스팅 |
| 부동 소수점 | `f` | `"f2"`, `"f4"`, `"f8"` | `Float(f64)` -- 대상 정밀도로 캐스팅 |
| 고정 바이트 | `S` | `"S8"`, `"S16"` | `Blob(bytes)` 또는 `String` -- 잘림/제로 패딩 |
| Void 바이트 | `V` | `"V4"`, `"V16"` | `Blob(bytes)` -- 잘림/제로 패딩 |
| 하위 배열 | -- | `("f4", (128,))` | `Blob(bytes)` -- 원시 복사 (예: 벡터 임베딩) |

:::tip[지원되지 않는 dtype]

유니코드 문자열(`U`)과 Python 객체(`O`)는 `TypeError`로 거부됩니다. 문자열 데이터에는 `S`(고정 바이트)를 사용하세요.

:::

## 접근 패턴

### 컬럼형 접근

```python
temps = batch.batch_records["temperature"]  # float64 배열
print(temps.mean(), temps.std(), temps.max())

# 불리언 필터링
hot = batch.batch_records[temps > 40.0]
```

### 행 접근

```python
record = batch.batch_records[0]
print(record["temperature"], record["humidity"])
```

### 키 조회

```python
record = batch.get("sensor_42")
print(record["temperature"])
```

### 메타데이터 접근

```python
# 레코드별 generation과 TTL
print(batch.meta["gen"])  # uint32 배열
print(batch.meta["ttl"])  # uint32 배열

# 실패한 레코드 확인
failed = batch.result_codes != 0
print(f"Failed: {failed.sum()} / {len(batch.result_codes)}")
```

## dtype 정의

dtype 필드 이름은 Aerospike bin 이름과 정확히 일치해야 합니다.

### 숫자형 Bin

```python
dtype = np.dtype([
    ("price", "f8"),       # float64
    ("quantity", "i4"),    # int32
    ("flags", "u1"),       # uint8
])
```

### 바이트 / Blob Bin

```python
dtype = np.dtype([
    ("name", "S32"),       # 32바이트 고정 문자열
    ("raw_data", "V64"),   # 64바이트 void 버퍼
])
```

### 벡터 임베딩 (하위 배열)

Aerospike에 float32 벡터(예: ML 임베딩)를 바이트 blob으로 저장한 후, 하위 배열로 읽어올 수 있습니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

dim = 128
dtype = np.dtype([
    ("embedding", "f4", (dim,)),  # 128차원 float32 하위 배열
    ("score", "f4"),
])

# 쓰기: 임베딩을 원시 바이트로 저장
embedding = np.random.randn(dim).astype(np.float32)
client.put(
    ("test", "vectors", "vec_1"),
    {"embedding": embedding.tobytes(), "score": 0.95},
    policy={"key": aerospike.POLICY_KEY_SEND},
)

# 읽기: 바이트에서 하위 배열이 자동 복원됨
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

## Bin 필터링

`bins`와 `_dtype`을 함께 사용하여 서버에서 특정 bin만 읽을 수 있습니다:

```python
dtype = np.dtype([("temperature", "f8")])
batch = client.batch_read(keys, bins=["temperature"], _dtype=dtype)
```

서버에서 `temperature` bin만 전송되므로 네트워크 I/O가 줄어듭니다.

## 오류 처리

### 누락된 레코드

찾을 수 없는 레코드(결과 코드 2)는 구조화 배열에서 0으로 채워집니다:

```python
batch = client.batch_read(keys, _dtype=dtype)

# 결과 코드 확인
for i, rc in enumerate(batch.result_codes):
    if rc != 0:
        print(f"Record {i} failed with result code {rc}")

# 성공한 레코드만 필터링
success_mask = batch.result_codes == 0
valid_data = batch.batch_records[success_mask]
```

### 누락된 Bin

레코드는 존재하지만 bin이 누락된 경우, 해당 필드는 0(해당 dtype의 numpy 기본값)으로 설정됩니다:

```python
# 레코드에 "temperature"는 있지만 "humidity"는 없는 경우
dtype = np.dtype([("temperature", "f8"), ("humidity", "i4")])
batch = client.batch_read(keys, _dtype=dtype)
# 해당 bin이 없는 레코드의 humidity는 0이 됩니다
```

### dtype 유효성 검사 오류

```python
# TypeError: 유니코드 문자열은 지원되지 않음
dtype = np.dtype([("name", "U10")])
batch = client.batch_read(keys, _dtype=dtype)  # TypeError 발생

# TypeError: Python 객체는 지원되지 않음
dtype = np.dtype([("data", "O")])
batch = client.batch_read(keys, _dtype=dtype)  # TypeError 발생
```

## Pandas 연동

`NumpyBatchRecords`를 pandas DataFrame으로 변환합니다:

```python
import pandas as pd

batch = client.batch_read(keys, _dtype=dtype)

df = pd.DataFrame(batch.batch_records)
df["gen"] = batch.meta["gen"]
df["ttl"] = batch.meta["ttl"]

# pandas 연산 사용
hot_sensors = df[df["temperature"] > 35.0]
print(hot_sensors.describe())
```

## 모범 사례

- **dtype을 bin에 맞추기** -- dtype의 필드 이름은 Aerospike의 bin 이름과 일치해야 합니다
- **`bins` 파라미터 사용** -- `_dtype`과 함께 사용하여 네트워크 전송량을 줄이세요
- **`result_codes` 확인** -- 분석 전에 실패한 레코드를 필터링하세요
- **최소한의 dtype 사용** -- 메모리 절약을 위해 `"f8"` 대신 `"f4"`, `"i8"` 대신 `"i2"` 사용
- **배치 크기** -- 최적의 성능을 위해 배치당 100-5,000개 키를 유지하세요
- **벡터 데이터** -- 임베딩을 `tobytes()` blob으로 저장하고 하위 배열 dtype으로 읽기

## API 레퍼런스

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

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `keys` | `list[Key]` | 필수 | `(namespace, set, primary_key)` 튜플의 리스트 |
| `bins` | `list[str] \| None` | `None` | 읽을 bin 이름 (`None` = 전체) |
| `policy` | `dict \| None` | `None` | 배치 policy 오버라이드 |
| `_dtype` | `np.dtype` | 필수 | 출력 스키마를 정의하는 구조화 dtype |
