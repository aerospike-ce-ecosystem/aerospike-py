---
title: List & Map CDT Operations
sidebar_label: Operations
sidebar_position: 3
slug: /guides/operations
description: client.operate()를 통한 List (31개) 및 Map (27개) 원자적 CDT 작업 가이드
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

`client.operate()`를 통한 원자적 서버 측 컬렉션 데이터 타입 (CDT) 작업입니다.

```python
from aerospike_py import list_operations as list_ops
from aerospike_py import map_operations as map_ops
import aerospike_py as aerospike
```

<Tabs>
  <TabItem value="list" label="List CDT Operations" default>

## List CDT Operations

각 `list_ops.*` 함수는 `client.operate()` 또는 `client.operate_ordered()`에 전달하는 작업 dict를 반환합니다:

```python
ops = [
    list_ops.list_append("scores", 100),
    list_ops.list_size("scores"),
]
_, _, bins = client.operate(key, ops)
```

### Basic Write Operations

<Tabs>
  <TabItem value="list_append" label="list_append" default>

**`list_append(bin, val, policy=None)`** — 리스트 끝에 값을 추가합니다.

```python
ops = [list_ops.list_append("colors", "red")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_append_items" label="list_append_items">

**`list_append_items(bin, values, policy=None)`** — 리스트에 여러 값을 추가합니다.

```python
ops = [list_ops.list_append_items("colors", ["green", "blue"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_insert" label="list_insert">

**`list_insert(bin, index, val, policy=None)`** — 지정한 인덱스에 값을 삽입합니다.

```python
ops = [list_ops.list_insert("colors", 0, "yellow")]
client.operate(key, ops)
```

**`list_insert_items(bin, index, values, policy=None)`** — 지정한 인덱스에 여러 값을 삽입합니다.

```python
ops = [list_ops.list_insert_items("colors", 1, ["cyan", "magenta"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_set" label="list_set">

**`list_set(bin, index, val)`** — 특정 인덱스의 값을 설정합니다.

```python
ops = [list_ops.list_set("colors", 0, "orange")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_increment" label="list_increment">

**`list_increment(bin, index, val, policy=None)`** — 지정한 인덱스의 숫자 값을 증가시킵니다.

```python
ops = [list_ops.list_increment("scores", 0, 10)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### Basic Read Operations

#### `list_get(bin, index)`

특정 인덱스의 항목을 가져옵니다.

```python
ops = [list_ops.list_get("scores", 0)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first element
```

#### `list_get_range(bin, index, count)`

`index`부터 `count`개의 항목을 가져옵니다.

```python
ops = [list_ops.list_get_range("scores", 0, 3)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first 3 elements
```

#### `list_size(bin)`

리스트의 항목 수를 반환합니다.

```python
ops = [list_ops.list_size("scores")]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # e.g., 5
```

### Remove Operations

#### `list_remove(bin, index)`

지정한 인덱스의 항목을 삭제합니다.

```python
ops = [list_ops.list_remove("colors", 0)]
client.operate(key, ops)
```

#### `list_remove_range(bin, index, count)`

`index`부터 `count`개의 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_range("colors", 1, 2)]
client.operate(key, ops)
```

#### `list_pop(bin, index)`

지정한 인덱스의 항목을 삭제하고 반환합니다.

```python
ops = [list_ops.list_pop("colors", 0)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # the removed item
```

#### `list_pop_range(bin, index, count)`

`index`부터 `count`개의 항목을 삭제하고 반환합니다.

```python
ops = [list_ops.list_pop_range("colors", 0, 2)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # list of removed items
```

#### `list_trim(bin, index, count)`

지정한 범위 `[index, index+count)` 밖의 항목을 삭제합니다.

```python
ops = [list_ops.list_trim("scores", 1, 3)]
client.operate(key, ops)
```

#### `list_clear(bin)`

리스트의 모든 항목을 삭제합니다.

```python
ops = [list_ops.list_clear("scores")]
client.operate(key, ops)
```

### Sort & Order

#### `list_sort(bin, sort_flags=0)`

리스트를 제자리에서 정렬합니다.

```python
ops = [list_ops.list_sort("scores")]
client.operate(key, ops)

# 정렬 시 중복 제거
ops = [list_ops.list_sort("scores", aerospike.LIST_SORT_DROP_DUPLICATES)]
client.operate(key, ops)
```

#### `list_set_order(bin, list_order=0)`

리스트 정렬 타입을 설정합니다.

```python
ops = [list_ops.list_set_order("scores", aerospike.LIST_ORDERED)]
client.operate(key, ops)
```

### Advanced Read Operations (Value/Index/Rank)

이 작업들은 반환 내용을 제어하는 `return_type` 매개변수가 필요합니다.

#### `list_get_by_value(bin, val, return_type)`

지정한 값과 일치하는 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value("tags", "urgent", aerospike.LIST_RETURN_INDEX)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value_list(
    "tags", ["urgent", "important"], aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_value_range(
    "scores", 80, 100, aerospike.LIST_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index(bin, index, return_type)`

지정한 반환 타입으로 인덱스 기반 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_index_range(
    "scores", 2, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank(bin, rank, return_type)`

랭크 기반으로 항목을 가져옵니다 (0 = 최솟값).

```python
ops = [list_ops.list_get_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 가져옵니다.

```python
ops = [list_ops.list_get_by_rank_range(
    "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Delete Operations (Value/Index/Rank)

#### `list_remove_by_value(bin, val, return_type)`

지정한 값과 일치하는 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value("tags", "temp", aerospike.LIST_RETURN_COUNT)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value_list(
    "tags", ["temp", "debug"], aerospike.LIST_RETURN_NONE
)]
client.operate(key, ops)
```

#### `list_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_value_range(
    "scores", 0, 50, aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index(bin, index, return_type)`

인덱스 기반으로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_index_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

#### `list_remove_by_rank(bin, rank, return_type)`

랭크 기반으로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 삭제합니다.

```python
ops = [list_ops.list_remove_by_rank_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### List Constants

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
| `LIST_UNORDERED` | 비정렬 리스트 (기본값) |
| `LIST_ORDERED` | 정렬된 리스트 (정렬 순서 유지) |
| `LIST_SORT_DEFAULT` | 기본 정렬 |
| `LIST_SORT_DROP_DUPLICATES` | 정렬 시 중복 제거 |

### List Complete Example

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

  </TabItem>
  <TabItem value="map" label="Map CDT Operations">

## Map CDT Operations

각 `map_ops.*` 함수는 `client.operate()` 또는 `client.operate_ordered()`에 전달하는 작업 dict를 반환합니다:

```python
ops = [
    map_ops.map_put("profile", "email", "alice@example.com"),
    map_ops.map_size("profile"),
]
_, _, bins = client.operate(key, ops)
```

### Basic Write Operations

<Tabs>
  <TabItem value="map_put" label="map_put" default>

**`map_put(bin, key, val, policy=None)`** — map에 키/값 쌍을 추가합니다.

```python
ops = [map_ops.map_put("profile", "name", "Alice")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_put_items" label="map_put_items">

**`map_put_items(bin, items, policy=None)`** — map에 여러 키/값 쌍을 추가합니다.

```python
ops = [map_ops.map_put_items("profile", {
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30,
})]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_increment" label="map_increment">

**`map_increment(bin, key, incr, policy=None)`** — map에서 키로 숫자 값을 증가시킵니다.

```python
ops = [map_ops.map_increment("counters", "views", 1)]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_decrement" label="map_decrement">

**`map_decrement(bin, key, decr, policy=None)`** — map에서 키로 숫자 값을 감소시킵니다.

```python
ops = [map_ops.map_decrement("counters", "stock", 1)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### Basic Read Operations

#### `map_size(bin)`

map의 항목 수를 반환합니다.

```python
ops = [map_ops.map_size("profile")]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # e.g., 3
```

#### `map_get_by_key(bin, key, return_type)`

키로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key("profile", "name", aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # "Alice"
```

### Map Settings

#### `map_set_order(bin, map_order)`

map 정렬 타입을 설정합니다.

```python
ops = [map_ops.map_set_order("profile", aerospike.MAP_KEY_ORDERED)]
client.operate(key, ops)
```

#### `map_clear(bin)`

map의 모든 항목을 삭제합니다.

```python
ops = [map_ops.map_clear("profile")]
client.operate(key, ops)
```

### Remove Operations

#### `map_remove_by_key(bin, key, return_type)`

키로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key("profile", "temp", aerospike.MAP_RETURN_NONE)]
client.operate(key, ops)
```

#### `map_remove_by_key_list(bin, keys, return_type)`

지정한 키 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key_list(
    "profile", ["temp", "debug"], aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 키를 가진 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_key_range(
    "cache", "tmp_a", "tmp_z", aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value(bin, val, return_type)`

값으로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value("scores", 0, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value_list(
    "tags", ["deprecated", "old"], aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_value_range(
    "scores", 0, 50, aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Read Operations (Key/Value/Index/Rank)

이 작업들은 반환 내용을 제어하는 `return_type` 매개변수가 필요합니다.

#### `map_get_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 키를 가진 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key_range(
    "profile", "a", "n", aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_key_list(bin, keys, return_type)`

지정한 키 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_key_list(
    "profile", ["name", "email"], aerospike.MAP_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value(bin, val, return_type)`

값으로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value("scores", 100, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 값을 가진 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value_range(
    "scores", 90, 100, aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_list(bin, values, return_type)`

지정한 값 중 하나와 일치하는 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_value_list(
    "scores", [100, 95], aerospike.MAP_RETURN_KEY
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index(bin, index, return_type)`

인덱스로 항목을 가져옵니다 (키 정렬 순서 기준).

```python
ops = [map_ops.map_get_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_index_range(
    "profile", 0, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank(bin, rank, return_type)`

랭크로 항목을 가져옵니다 (0 = 최솟값).

```python
ops = [map_ops.map_get_by_rank("scores", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 가져옵니다.

```python
ops = [map_ops.map_get_by_rank_range(
    "scores", -3, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Delete Operations (Index/Rank)

#### `map_remove_by_index(bin, index, return_type)`

인덱스로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_index_range(bin, index, return_type, count=None)`

인덱스 범위로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_index_range(
    "cache", 0, aerospike.MAP_RETURN_NONE, count=5
)]
client.operate(key, ops)
```

#### `map_remove_by_rank(bin, rank, return_type)`

랭크로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_rank("scores", 0, aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_rank_range(bin, rank, return_type, count=None)`

랭크 범위로 항목을 삭제합니다.

```python
ops = [map_ops.map_remove_by_rank_range(
    "scores", 0, aerospike.MAP_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### Map Constants

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
| `MAP_UNORDERED` | 비정렬 map (기본값) |
| `MAP_KEY_ORDERED` | 키 순서로 정렬 |
| `MAP_KEY_VALUE_ORDERED` | 키 및 값 순서로 정렬 |
| `MAP_WRITE_FLAGS_DEFAULT` | 기본 동작 |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | 새 항목만 생성 |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | 기존 항목만 업데이트 |
| `MAP_WRITE_FLAGS_NO_FAIL` | policy 위반 시 오류를 발생시키지 않음 |
| `MAP_WRITE_FLAGS_PARTIAL` | 다중 항목 작업에서 부분 성공 허용 |

### Map Complete Example

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

  </TabItem>
</Tabs>
