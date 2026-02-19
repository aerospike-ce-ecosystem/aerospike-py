---
name: api-batch-operate
description: aerospike-py batch operations (batch_read, batch_operate, batch_remove, NumPy batch) and operate/operate_ordered multi-op
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## Batch

```python
keys: list[tuple[str, str, str | int | bytes]] = [
    ("test", "demo", f"user_{i}") for i in range(10)
]

# batch_read -> BatchRecords (raw 튜플, NamedTuple 아님)
batch: BatchRecords = client.batch_read(keys)
for br in batch.batch_records:
    if br.result == 0 and br.record is not None:
        key_tuple, meta_dict, bins = br.record
        print(bins)

# 특정 bin만 읽기
batch = client.batch_read(keys, bins=["name", "age"])

# batch_operate -> list[Record] (NamedTuple)
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results: list[Record] = client.batch_operate(keys, ops)
for record in results:
    print(record.bins)

# batch_remove -> list[Record]
results: list[Record] = client.batch_remove(keys)

# Async: 동일하게 await
batch = await client.batch_read(keys, bins=["name", "age"])
results = await client.batch_operate(keys, ops)
results = await client.batch_remove(keys)
```

### NumPy Batch

```python
import numpy as np

# dtype 정의 (int, float, fixed-length bytes만 가능)
dtype = np.dtype([("age", "i4"), ("score", "f8"), ("name", "S32")])

# batch_read + NumPy -> NumpyBatchRecords
result: NumpyBatchRecords = client.batch_read(keys, bins=["age", "score", "name"], _dtype=dtype)

# 결과 접근
result.batch_records   # np.ndarray (structured array)
result.meta            # np.ndarray, dtype=[("gen", "u4"), ("ttl", "u4")]
result.result_codes    # np.ndarray (int32), 0 = 성공

# 단일 레코드 조회 (primary key로)
row = result.get("user_0")  # np.void (scalar record)
row["age"]   # 30
row["score"] # 95.5

# 벡터 연산
ages = result.batch_records["age"]
mean_age = ages[result.result_codes == 0].mean()
```

## Operate (Multi-op)

```python
# 단일 레코드에 대한 원자적 다중 연산
ops: list[dict[str, Any]] = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record: Record = client.operate(key, ops)

# 순서 보존 결과
from aerospike_py.types import OperateOrderedResult, BinTuple
result: OperateOrderedResult = client.operate_ordered(key, ops)
for bt in result.ordered_bins:
    print(f"{bt.name} = {bt.value}")
```

### 반환 타입

```python
from aerospike_py.types import Record, OperateOrderedResult, BinTuple

Record(key: AerospikeKey | None, meta: RecordMetadata | None, bins: dict[str, Any] | None)
OperateOrderedResult(key: AerospikeKey | None, meta: RecordMetadata | None, ordered_bins: list[BinTuple])
BinTuple(name: str, value: Any)
```

### Operator 상수

```python
OPERATOR_READ = 1       # bin 읽기
OPERATOR_WRITE = 2      # bin 쓰기
OPERATOR_INCR = 5       # 숫자 증가
OPERATOR_APPEND = 9     # 문자열 뒤에 추가
OPERATOR_PREPEND = 10   # 문자열 앞에 추가
OPERATOR_TOUCH = 11     # TTL 리셋
OPERATOR_DELETE = 12    # 레코드 삭제
```
