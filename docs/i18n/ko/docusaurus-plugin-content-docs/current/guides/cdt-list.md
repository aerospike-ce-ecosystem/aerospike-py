---
title: List CDT Operations
sidebar_label: List Operations
sidebar_position: 4
description: List bin에 대한 31가지 원자적 작업 가이드
---

List CDT (Collection Data Type) 작업은 list bin에 대해 31가지 원자적 작업을 제공합니다. 이 작업들은 `client.operate()`의 일부로 서버 측에서 실행되며, list 데이터에 대한 원자적 다중 작업 트랜잭션을 가능하게 합니다.

## Import

```python
from aerospike_py import list_operations as list_ops
import aerospike_py as aerospike
```

## Overview

각 `list_ops.*` 함수는 `client.operate()` 또는 `client.operate_ordered()`에 전달하는 작업 dict를 반환합니다:

```python
ops = [
    list_ops.list_append("scores", 100),
    list_ops.list_size("scores"),
]
_, _, bins = client.operate(key, ops)
```

## Basic Write Operations

### `list_append(bin, val, policy=None)`

리스트 끝에 값을 추가합니다.

```python
ops = [list_ops.list_append("colors", "red")]
client.operate(key, ops)
```

### `list_append_items(bin, values, policy=None)`

리스트에 여러 값을 추가합니다.

```python
ops = [list_ops.list_append_items("colors", ["green", "blue"])]
client.operate(key, ops)
```

### `list_insert(bin, index, val, policy=None)`

지정한 인덱스에 값을 삽입합니다.

```python
ops = [list_ops.list_insert("colors", 0, "yellow")]
client.operate(key, ops)
```

### `list_insert_items(bin, index, values, policy=None)`

지정한 인덱스에 여러 값을 삽입합니다.

```python
ops = [list_ops.list_insert_items("colors", 1, ["cyan", "magenta"])]
client.operate(key, ops)
```

### `list_set(bin, index, val)`

특정 인덱스의 값을 설정합니다.

```python
ops = [list_ops.list_set("colors", 0, "orange")]
client.operate(key, ops)
```

### `list_increment(bin, index, val, policy=None)`

지정한 인덱스의 숫자 값을 증가시킵니다.

```python
ops = [list_ops.list_increment("scores", 0, 10)]
client.operate(key, ops)
```

## Basic Read Operations

### `list_get(bin, index)`

특정 인덱스의 항목을 가져옵니다.

```python
ops = [list_ops.list_get("scores", 0)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first element
```

### `list_get_range(bin, index, count)`

`index`부터 `count`개의 항목을 가져옵니다.

```python
ops = [list_ops.list_get_range("scores", 0, 3)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first 3 elements
```

### `list_size(bin)`

리스트의 항목 수를 반환합니다.

```python
ops = [list_ops.list_size("scores")]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # e.g., 5
```

## Delete Operations

### `list_remove(bin, index)`

지정한 인덱스의 항목을 삭제합니다.

```python
ops = [list_ops.list_remove("colors", 0)]
client.operate(key, ops)
```

### `list_remove_range(bin, index, count)`

`index`부터 `count`개의 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_range("colors", 1, 2)]
client.operate(key, ops)
```

### `list_pop(bin, index)`

지정한 인덱스의 항목을 삭제하고 반환합니다.

```python
ops = [list_ops.list_pop("colors", 0)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # the removed item
```

### `list_pop_range(bin, index, count)`

`index`부터 `count`개의 항목을 삭제하고 반환합니다.

```python
ops = [list_ops.list_pop_range("colors", 0, 2)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # list of removed items
```

### `list_trim(bin, index, count)`

지정한 범위 `[index, index+count)` 밖의 항목을 삭제합니다.

```python
# 인덱스 1..3의 항목만 유지
ops = [list_ops.list_trim("scores", 1, 3)]
client.operate(key, ops)
```

### `list_clear(bin)`

리스트의 모든 항목을 삭제합니다.

```python
ops = [list_ops.list_clear("scores")]
client.operate(key, ops)
```

## Sort Operations

### `list_sort(bin, sort_flags=0)`

리스트를 제자리에서 정렬합니다.

```python
ops = [list_ops.list_sort("scores")]
client.operate(key, ops)

# 정렬 시 중복 제거
ops = [list_ops.list_sort("scores", aerospike.LIST_SORT_DROP_DUPLICATES)]
client.operate(key, ops)
```

### `list_set_order(bin, list_order=0)`

리스트 정렬 타입을 설정합니다.

```python
# 정렬 유지 설정 (이후 쓰기 시 정렬 순서 유지)
ops = [list_ops.list_set_order("scores", aerospike.LIST_ORDERED)]
client.operate(key, ops)
```

## Advanced Read Operations (Value/Index/Rank)

이 작업들은 반환 내용을 제어하는 `return_type` 매개변수가 필요합니다.

### `list_get_by_value(bin, val, return_type)`

지정한 값과 일치하는 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value("tags", "urgent", aerospike.LIST_RETURN_INDEX)]
_, _, bins = client.operate(key, ops)
# 모든 "urgent" 항목의 인덱스를 반환
```

### `list_get_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value_list(
    "tags", ["urgent", "important"], aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value_range(
    "scores", 80, 100, aerospike.LIST_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_index(bin, index, return_type)`

지정한 반환 타입으로 인덱스 기반 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 가져옵니다.

```python
# 인덱스 2부터 3개 항목 가져오기
ops = [list_ops.list_get_by_index_range(
    "scores", 2, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_rank(bin, rank, return_type)`

랭크 기반으로 항목을 가져옵니다 (0 = 최솟값).

```python
# 가장 작은 값 가져오기
ops = [list_ops.list_get_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 가져옵니다.

```python
# 상위 3개 값 가져오기 (가장 높은 랭크)
ops = [list_ops.list_get_by_rank_range(
    "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

## Advanced Delete Operations (Value/Index/Rank)

### `list_remove_by_value(bin, val, return_type)`

지정한 값과 일치하는 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value("tags", "temp", aerospike.LIST_RETURN_COUNT)]
_, _, bins = client.operate(key, ops)
print(f"Removed {bins['tags']} items")
```

### `list_remove_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value_list(
    "tags", ["temp", "debug"], aerospike.LIST_RETURN_NONE
)]
client.operate(key, ops)
```

### `list_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value_range(
    "scores", 0, 50, aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_index(bin, index, return_type)`

인덱스 기반으로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_index_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### `list_remove_by_rank(bin, rank, return_type)`

랭크 기반으로 항목을 삭제합니다.

```python
# 가장 작은 값 삭제
ops = [list_ops.list_remove_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 삭제합니다.

```python
# 가장 작은 값 2개 삭제
ops = [list_ops.list_remove_by_rank_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

## Return Type Constants

`aerospike_py`의 다음 상수를 사용하여 서버가 반환하는 내용을 제어합니다:

| 상수 | 설명 |
|------|------|
| `LIST_RETURN_NONE` | 아무것도 반환하지 않음 |
| `LIST_RETURN_INDEX` | 인덱스 반환 |
| `LIST_RETURN_REVERSE_INDEX` | 역순 인덱스 반환 |
| `LIST_RETURN_RANK` | 랭크 반환 |
| `LIST_RETURN_REVERSE_RANK` | 역순 랭크 반환 |
| `LIST_RETURN_COUNT` | 일치한 항목 수 반환 |
| `LIST_RETURN_VALUE` | 값 반환 |
| `LIST_RETURN_EXISTS` | 존재 여부 불리언 반환 |

## List Order Constants

| 상수 | 설명 |
|------|------|
| `LIST_UNORDERED` | 비정렬 리스트 (기본값) |
| `LIST_ORDERED` | 정렬된 리스트 (정렬 순서 유지) |

## List Sort Flags

| 상수 | 설명 |
|------|------|
| `LIST_SORT_DEFAULT` | 기본 정렬 |
| `LIST_SORT_DROP_DUPLICATES` | 정렬 시 중복 제거 |

## Complete Example

```python
import aerospike_py as aerospike
from aerospike_py import list_operations as list_ops

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "player1")

    # scores 리스트 초기화
    client.put(key, {"scores": [85, 92, 78, 95, 88]})

    # 원자적 작업: 정렬, 상위 3개 가져오기, 크기 확인
    ops = [
        list_ops.list_sort("scores"),
        list_ops.list_get_by_rank_range(
            "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 3 scores: {bins['scores']}")

    # 80점 미만 점수 삭제
    ops = [
        list_ops.list_remove_by_value_range(
            "scores", 0, 80, aerospike.LIST_RETURN_COUNT
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed {bins['scores']} low scores")

    # 새로운 점수 추가 및 업데이트된 크기 확인
    ops = [
        list_ops.list_append("scores", 97),
        list_ops.list_size("scores"),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Total scores: {bins['scores']}")
```
