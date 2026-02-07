---
title: Map CDT Operations
sidebar_label: Map Operations
sidebar_position: 5
description: Map bin에 대한 27가지 원자적 작업 가이드
---

Map CDT (Collection Data Type) 작업은 map bin에 대해 27가지 원자적 작업을 제공합니다. 이 작업들은 `client.operate()`의 일부로 서버 측에서 실행되며, map 데이터에 대한 원자적 다중 작업 트랜잭션을 가능하게 합니다.

## Import

```python
from aerospike_py import map_operations as map_ops
import aerospike_py as aerospike
```

## Overview

각 `map_ops.*` 함수는 `client.operate()` 또는 `client.operate_ordered()`에 전달하는 작업 dict를 반환합니다:

```python
ops = [
    map_ops.map_put("profile", "email", "alice@example.com"),
    map_ops.map_size("profile"),
]
_, _, bins = client.operate(key, ops)
```

## Basic Write Operations

### `map_put(bin, key, val, policy=None)`

map에 키/값 쌍을 추가합니다.

```python
ops = [map_ops.map_put("profile", "name", "Alice")]
client.operate(key, ops)
```

### `map_put_items(bin, items, policy=None)`

map에 여러 키/값 쌍을 추가합니다.

```python
ops = [map_ops.map_put_items("profile", {
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30,
})]
client.operate(key, ops)
```

### `map_increment(bin, key, incr, policy=None)`

map에서 키로 숫자 값을 증가시킵니다.

```python
ops = [map_ops.map_increment("counters", "views", 1)]
client.operate(key, ops)
```

### `map_decrement(bin, key, decr, policy=None)`

map에서 키로 숫자 값을 감소시킵니다.

```python
ops = [map_ops.map_decrement("counters", "stock", 1)]
client.operate(key, ops)
```

## Map Configuration

### `map_set_order(bin, map_order)`

map 정렬 타입을 설정합니다.

```python
# 키 순서로 정렬된 map 설정
ops = [map_ops.map_set_order("profile", aerospike.MAP_KEY_ORDERED)]
client.operate(key, ops)
```

### `map_clear(bin)`

map의 모든 항목을 삭제합니다.

```python
ops = [map_ops.map_clear("profile")]
client.operate(key, ops)
```

## Basic Read Operations

### `map_size(bin)`

map의 항목 수를 반환합니다.

```python
ops = [map_ops.map_size("profile")]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # e.g., 3
```

### `map_get_by_key(bin, key, return_type)`

키로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key("profile", "name", aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # "Alice"
```

## Advanced Read Operations

### `map_get_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 키를 가진 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key_range(
    "profile", "a", "n", aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_key_list(bin, keys, return_type)`

지정한 키 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key_list(
    "profile", ["name", "email"], aerospike.MAP_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_value(bin, val, return_type)`

값으로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value("scores", 100, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
# 값이 100인 항목의 키를 반환
```

### `map_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value_range(
    "scores", 90, 100, aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value_list(
    "scores", [100, 95], aerospike.MAP_RETURN_KEY
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_index(bin, index, return_type)`

인덱스로 항목을 가져옵니다 (키 정렬 순서 기준).

```python
# 첫 번째 항목 가져오기 (키 순서 기준)
ops = [map_ops.map_get_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 가져옵니다.

```python
# 키 순서로 처음 3개 항목 가져오기
ops = [map_ops.map_get_by_index_range(
    "profile", 0, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_rank(bin, rank, return_type)`

랭크로 항목을 가져옵니다 (0 = 최솟값).

```python
# 가장 작은 값을 가진 항목 가져오기
ops = [map_ops.map_get_by_rank("scores", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 가져옵니다.

```python
# 값 기준 상위 3개 항목 가져오기
ops = [map_ops.map_get_by_rank_range(
    "scores", -3, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

## Delete Operations

### `map_remove_by_key(bin, key, return_type)`

키로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key("profile", "temp", aerospike.MAP_RETURN_NONE)]
client.operate(key, ops)
```

### `map_remove_by_key_list(bin, keys, return_type)`

지정한 키 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key_list(
    "profile", ["temp", "debug"], aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 키를 가진 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key_range(
    "cache", "tmp_a", "tmp_z", aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

### `map_remove_by_value(bin, val, return_type)`

값으로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value("scores", 0, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
# 삭제된 항목의 키를 반환
```

### `map_remove_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value_list(
    "tags", ["deprecated", "old"], aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

### `map_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value_range(
    "scores", 0, 50, aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_index(bin, index, return_type)`

인덱스로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_index_range(
    "cache", 0, aerospike.MAP_RETURN_NONE, count=5
)]
client.operate(key, ops)
```

### `map_remove_by_rank(bin, rank, return_type)`

랭크로 항목을 삭제합니다.

```python
# 가장 작은 값을 가진 항목 삭제
ops = [map_ops.map_remove_by_rank("scores", 0, aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 삭제합니다.

```python
# 가장 작은 값 2개 항목 삭제
ops = [map_ops.map_remove_by_rank_range(
    "scores", 0, aerospike.MAP_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

## Return Type Constants

| 상수 | 설명 |
|------|------|
| `MAP_RETURN_NONE` | 아무것도 반환하지 않음 |
| `MAP_RETURN_INDEX` | 인덱스 반환 |
| `MAP_RETURN_REVERSE_INDEX` | 역순 인덱스 반환 |
| `MAP_RETURN_RANK` | 랭크 반환 |
| `MAP_RETURN_REVERSE_RANK` | 역순 랭크 반환 |
| `MAP_RETURN_COUNT` | 일치한 항목 수 반환 |
| `MAP_RETURN_KEY` | 키 반환 |
| `MAP_RETURN_VALUE` | 값 반환 |
| `MAP_RETURN_KEY_VALUE` | 키-값 쌍 반환 |
| `MAP_RETURN_EXISTS` | 존재 여부 불리언 반환 |

## Map Order Constants

| 상수 | 설명 |
|------|------|
| `MAP_UNORDERED` | 비정렬 map (기본값) |
| `MAP_KEY_ORDERED` | 키 순서로 정렬 |
| `MAP_KEY_VALUE_ORDERED` | 키 및 값 순서로 정렬 |

## Map Write Flags

| 상수 | 설명 |
|------|------|
| `MAP_WRITE_FLAGS_DEFAULT` | 기본 동작 |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | 새 항목만 생성 |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | 기존 항목만 업데이트 |
| `MAP_WRITE_FLAGS_NO_FAIL` | policy 위반 시 오류를 발생시키지 않음 |
| `MAP_WRITE_FLAGS_PARTIAL` | 다중 항목 작업에서 부분 성공 허용 |

## Complete Example

```python
import aerospike_py as aerospike
from aerospike_py import map_operations as map_ops

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "player1")

    # scores map 초기화
    client.put(key, {"scores": {"math": 92, "science": 88, "english": 75, "art": 95}})

    # 원자적 작업: 상위 2개 점수 가져오기 및 전체 개수 확인
    ops = [
        map_ops.map_get_by_rank_range(
            "scores", -2, aerospike.MAP_RETURN_KEY_VALUE, count=2
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 2 scores: {bins['scores']}")

    # 80점 미만 점수 삭제
    ops = [
        map_ops.map_remove_by_value_range(
            "scores", 0, 80, aerospike.MAP_RETURN_KEY
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed subjects: {bins['scores']}")

    # 새 점수 추가 및 기존 점수 증가
    ops = [
        map_ops.map_put("scores", "history", 90),
        map_ops.map_increment("scores", "math", 5),
        map_ops.map_size("scores"),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Total subjects: {bins['scores']}")
```
