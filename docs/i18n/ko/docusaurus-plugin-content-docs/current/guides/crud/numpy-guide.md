---
title: NumPy Integration Guide
sidebar_label: NumPy Integration
sidebar_position: 6
slug: /guides/numpy-integration
description: High-performance batch operations using NumPy structured arrays.
---

NumPy structured array 를 사용한 고성능 batch read/write. 데이터가 Rust 를 통해 Aerospike 와 NumPy buffer 사이를 직접 흘러, per-element Python object 생성을 우회.

:::note[Requirement]
`numpy >= 2.0` 필요. 설치: `pip install aerospike-py[numpy]`
:::

## NumPy batch 를 언제 쓰나

| Scenario | 일반 `batch_read` | NumPy `batch_read` |
|----------|---------------------|-------------------|
| record < 100 | 권장 | 오버헤드 정당화 안 됨 |
| record 100–10K | OK | **2–5x 빠름** |
| record > 10K | 느림 (dict 할당) | **5–10x 빠름** |
| non-numeric bin (string, list) | 필수 | 미지원 |
| vectorised analytics | 수동 변환 | **native numpy array** |

## NumPy 로 Batch Read

### dtype 정의

dtype 의 각 field 가 Aerospike bin name 으로 매핑:

```python
import numpy as np

# field 는 numeric (int/uint/float) 또는 고정 길이 bytes 여야 함
dtype = np.dtype([
    ("score", "f8"),     # float64
    ("count", "i4"),     # int32
    ("level", "u2"),     # uint16
    ("tag", "S8"),       # 8-byte fixed string
])
```

### NumPy array 로 read

```python
keys = [("test", "demo", f"user_{i}") for i in range(1000)]

result = client.batch_read(keys, bins=["score", "count", "level", "tag"]).to_numpy(dtype)
# result 는 NumpyBatchRecords instance
```

### 데이터 접근

```python
# 전체 array 위의 vectorised operation
avg_score = result.batch_records["score"].mean()
high_scorers = result.batch_records[result.batch_records["score"] > 90]

# primary key 로 개별 record
record = result.get("user_42")
print(record["score"], record["count"])

# Metadata array
print(result.meta["gen"])  # generation 번호
print(result.meta["ttl"])  # TTL 값

# Result code (0 = success)
success_mask = result.result_codes == 0
valid_records = result.batch_records[success_mask]
```

### Async batch read

```python
lazy_records = await async_client.batch_read(keys, bins=["score", "count"])
result = lazy_records.to_numpy(dtype)
```

## NumPy 로 Batch Write

structured array 로부터 record write. 지정된 field 하나가 primary key 역할.

```python
import numpy as np

dtype = np.dtype([
    ("_key", "i4"),      # primary key field (_ 로 prefix)
    ("score", "f8"),
    ("count", "i4"),
])

data = np.array([
    (1, 95.5, 10),
    (2, 87.3, 20),
    (3, 92.1, 15),
], dtype=dtype)

results = client.batch_write_numpy(data, "test", "demo", dtype)
# Record NamedTuple list 반환
```

### Key field 규약

- 기본 key field: `"_key"` (`key_field` 파라미터로 설정 가능)
- `_` 로 prefix 된 field 는 bin 에서 제외 (record key 로는 `_key` 만 사용)
- 다른 모든 field 가 Aerospike bin 이 됨

```python
# 사용자 정의 key field 이름
dtype = np.dtype([("user_id", "i4"), ("score", "f8")])
data = np.array([(100, 95.5), (200, 87.3)], dtype=dtype)
results = client.batch_write_numpy(data, "test", "demo", dtype, key_field="user_id")
```

### Async batch write

```python
results = await async_client.batch_write_numpy(data, "test", "demo", dtype)
```

## 지원되는 dtype kind

| NumPy kind | Code | Examples | Aerospike type |
|-----------|------|---------|---------------|
| Signed int | `i` | `i1`, `i2`, `i4`, `i8` | Integer |
| Unsigned int | `u` | `u1`, `u2`, `u4`, `u8` | Integer |
| Float | `f` | `f2`, `f4`, `f8` | Float |
| Fixed bytes | `S` | `S8`, `S16`, `S32` | String (truncated) |
| Void bytes | `V` | `V8`, `V16` | Blob (truncated) |

:::warning[지원 안 되는 타입]
가변 길이 string (`U`), object (`O`), datetime (`M`/`m`) 은 **미지원**. write 전에 fixed-length 타입으로 변환.
:::

## Pandas 통합

### DataFrame 으로 read

```python
import pandas as pd

result = client.batch_read(keys, bins=["score", "count"]).to_numpy(dtype)

# 직접 변환 — numeric 데이터에 대해 zero copy
df = pd.DataFrame(result.batch_records)
df["success"] = result.result_codes == 0
```

### DataFrame 에서 write

```python
# DataFrame 을 structured array 로 변환
dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
data = np.array(list(df[["id", "score", "count"]].itertuples(index=False)), dtype=dtype)
client.batch_write_numpy(data, "test", "demo", dtype)
```

## Strict Mode

missing 또는 extra bin 에 대해 경고 활성화:

```python
result = client.batch_read(keys, bins=["score", "count"]).to_numpy(dtype)
# 경고 없음 — missing bin 은 zero-fill, extra bin 은 무시

# strict=True (_batch_records_to_numpy 통한 internal API) 사용 시:
# dtype field 가 record 에서 missing 일 때 경고
# record bin 이 dtype 에 없을 때 경고
```

## NumpyBatchRecords API

| Method / Attribute | 설명 |
|-------------------|-------------|
| `batch_records` | bin 데이터의 structured numpy array |
| `meta` | `(gen, ttl)` structured array |
| `result_codes` | `int32` array (0 = success) |
| `get(key)` | primary key 로 단일 record 가져오기 |
| `len(result)` | record 수 |
| `key in result` | primary key 존재 여부 |
| `for r in result` | record 순회 |

## Performance 팁

1. **dtype 사전 할당** — dtype 을 한 번 정의하고 호출 간 재사용
2. **dtype 을 데이터에 맞춤** — 충분한 최소 타입 사용 (`i4` vs `i8`, `f4` vs `f8`)
3. **Batch size** — 최적 범위: 호출당 500–5000 record
4. **fixed-length string 사용** — `S16` 이 가변 길이 대안보다 훨씬 빠름
5. **server-side filter** — expression filter 와 결합해 데이터 전송 줄이기
