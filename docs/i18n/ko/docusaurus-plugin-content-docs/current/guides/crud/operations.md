---
title: List & Map CDT Operations
sidebar_label: Operations
sidebar_position: 3
slug: /guides/operations
description: Atomic server-side List (31 ops) and Map (27 ops) collection data type operations via client.operate().
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

`client.operate()` 를 통한 atomic server-side collection data type (CDT) operation.

```python
from aerospike_py import list_operations as list_ops
from aerospike_py import map_operations as map_ops
import aerospike_py as aerospike
```

<Tabs>
  <TabItem value="list" label="List CDT Operations" default>

## List CDT Operations

각 `list_ops.*` function 은 `client.operate()` 또는 `client.operate_ordered()` 에 전달할 operation dict 를 반환:

```python
ops = [
    list_ops.list_append("scores", 100),
    list_ops.list_size("scores"),
]
_, _, bins = client.operate(key, ops)
```

### 기본 Write Operation

<Tabs>
  <TabItem value="list_append" label="list_append" default>

**`list_append(bin, val, policy=None)`** — list 끝에 value append.

```python
ops = [list_ops.list_append("colors", "red")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_append_items" label="list_append_items">

**`list_append_items(bin, values, policy=None)`** — list 에 다수 value append.

```python
ops = [list_ops.list_append_items("colors", ["green", "blue"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_insert" label="list_insert">

**`list_insert(bin, index, val, policy=None)`** — 주어진 index 에 value insert.

```python
ops = [list_ops.list_insert("colors", 0, "yellow")]
client.operate(key, ops)
```

**`list_insert_items(bin, index, values, policy=None)`** — 주어진 index 에 다수 value insert.

```python
ops = [list_ops.list_insert_items("colors", 1, ["cyan", "magenta"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_set" label="list_set">

**`list_set(bin, index, val)`** — 특정 index 의 value set.

```python
ops = [list_ops.list_set("colors", 0, "orange")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_increment" label="list_increment">

**`list_increment(bin, index, val, policy=None)`** — 주어진 index 의 numeric value increment.

```python
ops = [list_ops.list_increment("scores", 0, 10)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### 기본 Read Operation

#### `list_get(bin, index)`

특정 index 의 item 가져오기.

```python
ops = [list_ops.list_get("scores", 0)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # 첫 element
```

#### `list_get_range(bin, index, count)`

`index` 부터 `count` 개 item 가져오기.

```python
ops = [list_ops.list_get_range("scores", 0, 3)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # 첫 3개 element
```

#### `list_size(bin)`

list 의 item 수 반환.

```python
ops = [list_ops.list_size("scores")]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # 예: 5
```

### Remove Operation

#### `list_remove(bin, index)`

주어진 index 의 item 제거.

```python
ops = [list_ops.list_remove("colors", 0)]
client.operate(key, ops)
```

#### `list_remove_range(bin, index, count)`

`index` 부터 `count` 개 item 제거.

```python
ops = [list_ops.list_remove_range("colors", 1, 2)]
client.operate(key, ops)
```

#### `list_pop(bin, index)`

주어진 index 의 item 을 제거하고 반환.

```python
ops = [list_ops.list_pop("colors", 0)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # 제거된 item
```

#### `list_pop_range(bin, index, count)`

`index` 부터 `count` 개 item 을 제거하고 반환.

```python
ops = [list_ops.list_pop_range("colors", 0, 2)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # 제거된 item 의 list
```

#### `list_trim(bin, index, count)`

지정된 범위 `[index, index+count)` 밖의 item 제거.

```python
ops = [list_ops.list_trim("scores", 1, 3)]
client.operate(key, ops)
```

#### `list_clear(bin)`

list 의 모든 item 제거.

```python
ops = [list_ops.list_clear("scores")]
client.operate(key, ops)
```

### Sort & Order

#### `list_sort(bin, sort_flags=0)`

list 를 in place 로 sort.

```python
ops = [list_ops.list_sort("scores")]
client.operate(key, ops)

# sort 중 중복 제거
ops = [list_ops.list_sort("scores", aerospike.LIST_SORT_DROP_DUPLICATES)]
client.operate(key, ops)
```

#### `list_set_order(bin, list_order=0)`

list ordering 타입 설정.

```python
ops = [list_ops.list_set_order("scores", aerospike.LIST_ORDERED)]
client.operate(key, ops)
```

### Advanced Read Operation (Value/Index/Rank 기반)

이 operation 들은 반환되는 내용을 제어하는 `return_type` 파라미터 필요.

#### `list_get_by_value(bin, val, return_type)`

주어진 value 와 매칭되는 item 가져오기.

```python
ops = [list_ops.list_get_by_value("tags", "urgent", aerospike.LIST_RETURN_INDEX)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_list(bin, values, return_type)`

주어진 value 중 어느 하나와 매칭되는 item 가져오기.

```python
ops = [list_ops.list_get_by_value_list(
    "tags", ["urgent", "important"], aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 value 를 가진 item 가져오기.

```python
ops = [list_ops.list_get_by_value_range(
    "scores", 80, 100, aerospike.LIST_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index(bin, index, return_type)`

지정된 return type 으로 index 기반 item 가져오기.

```python
ops = [list_ops.list_get_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index_range(bin, index, return_type, count=None)`

index range 로 item 가져오기.

```python
ops = [list_ops.list_get_by_index_range(
    "scores", 2, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank(bin, rank, return_type)`

rank 기반 item 가져오기 (0 = 최소).

```python
ops = [list_ops.list_get_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank_range(bin, rank, return_type, count=None)`

rank range 로 item 가져오기.

```python
ops = [list_ops.list_get_by_rank_range(
    "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Remove Operation (Value/Index/Rank 기반)

#### `list_remove_by_value(bin, val, return_type)`

주어진 value 와 매칭되는 item 제거.

```python
ops = [list_ops.list_remove_by_value("tags", "temp", aerospike.LIST_RETURN_COUNT)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_value_list(bin, values, return_type)`

주어진 value 중 어느 하나와 매칭되는 item 제거.

```python
ops = [list_ops.list_remove_by_value_list(
    "tags", ["temp", "debug"], aerospike.LIST_RETURN_NONE
)]
client.operate(key, ops)
```

#### `list_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 value 를 가진 item 제거.

```python
ops = [list_ops.list_remove_by_value_range(
    "scores", 0, 50, aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index(bin, index, return_type)`

index 기반 item 제거.

```python
ops = [list_ops.list_remove_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index_range(bin, index, return_type, count=None)`

index range 로 item 제거.

```python
ops = [list_ops.list_remove_by_index_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

#### `list_remove_by_rank(bin, rank, return_type)`

rank 기반 item 제거.

```python
ops = [list_ops.list_remove_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_rank_range(bin, rank, return_type, count=None)`

rank range 로 item 제거.

```python
ops = [list_ops.list_remove_by_rank_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### List Constant

| Constant | 설명 |
|----------|-------------|
| `LIST_RETURN_NONE` | 아무것도 반환 안 함 |
| `LIST_RETURN_INDEX` | index 반환 |
| `LIST_RETURN_REVERSE_INDEX` | reverse index 반환 |
| `LIST_RETURN_RANK` | rank 반환 |
| `LIST_RETURN_REVERSE_RANK` | reverse rank 반환 |
| `LIST_RETURN_COUNT` | 매칭된 item 수 반환 |
| `LIST_RETURN_VALUE` | value 반환 |
| `LIST_RETURN_EXISTS` | boolean 존재 여부 반환 |
| `LIST_UNORDERED` | unordered list (default) |
| `LIST_ORDERED` | ordered list (sort order 유지) |
| `LIST_SORT_DEFAULT` | default sort |
| `LIST_SORT_DROP_DUPLICATES` | sort 시 중복 제거 |

### List 전체 예제

```python
import aerospike_py as aerospike
from aerospike_py import list_operations as list_ops

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "player1")

    # scores list 초기화
    client.put(key, {"scores": [85, 92, 78, 95, 88]})

    # Atomic: sort + top 3 가져오기 + size
    ops = [
        list_ops.list_sort("scores"),
        list_ops.list_get_by_rank_range(
            "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 3 scores: {bins['scores']}")

    # 80 미만 score 제거
    ops = [
        list_ops.list_remove_by_value_range(
            "scores", 0, 80, aerospike.LIST_RETURN_COUNT
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed {bins['scores']} low scores")

    # 새 score append + 업데이트된 size 가져오기
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

각 `map_ops.*` function 은 `client.operate()` 또는 `client.operate_ordered()` 에 전달할 operation dict 를 반환:

```python
ops = [
    map_ops.map_put("profile", "email", "alice@example.com"),
    map_ops.map_size("profile"),
]
_, _, bins = client.operate(key, ops)
```

### 기본 Write Operation

<Tabs>
  <TabItem value="map_put" label="map_put" default>

**`map_put(bin, key, val, policy=None)`** — map 에 key/value 쌍 put.

```python
ops = [map_ops.map_put("profile", "name", "Alice")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_put_items" label="map_put_items">

**`map_put_items(bin, items, policy=None)`** — map 에 다수 key/value 쌍 put.

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

**`map_increment(bin, key, incr, policy=None)`** — key 기준 map 의 numeric value increment.

```python
ops = [map_ops.map_increment("counters", "views", 1)]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_decrement" label="map_decrement">

**`map_decrement(bin, key, decr, policy=None)`** — key 기준 map 의 numeric value decrement.

```python
ops = [map_ops.map_decrement("counters", "stock", 1)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### 기본 Read Operation

#### `map_size(bin)`

map 의 entry 수 반환.

```python
ops = [map_ops.map_size("profile")]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # 예: 3
```

#### `map_get_by_key(bin, key, return_type)`

key 기반 entry 가져오기.

```python
ops = [map_ops.map_get_by_key("profile", "name", aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # "Alice"
```

### Map 설정

#### `map_set_order(bin, map_order)`

map ordering 타입 설정.

```python
ops = [map_ops.map_set_order("profile", aerospike.MAP_KEY_ORDERED)]
client.operate(key, ops)
```

#### `map_clear(bin)`

map 의 모든 item 제거.

```python
ops = [map_ops.map_clear("profile")]
client.operate(key, ops)
```

### Remove Operation

#### `map_remove_by_key(bin, key, return_type)`

key 기반 entry 제거.

```python
ops = [map_ops.map_remove_by_key("profile", "temp", aerospike.MAP_RETURN_NONE)]
client.operate(key, ops)
```

#### `map_remove_by_key_list(bin, keys, return_type)`

주어진 key 중 어느 하나와 매칭되는 entry 제거.

```python
ops = [map_ops.map_remove_by_key_list(
    "profile", ["temp", "debug"], aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 key 를 가진 entry 제거.

```python
ops = [map_ops.map_remove_by_key_range(
    "cache", "tmp_a", "tmp_z", aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value(bin, val, return_type)`

value 기반 entry 제거.

```python
ops = [map_ops.map_remove_by_value("scores", 0, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_value_list(bin, values, return_type)`

주어진 value 중 어느 하나와 매칭되는 entry 제거.

```python
ops = [map_ops.map_remove_by_value_list(
    "tags", ["deprecated", "old"], aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 value 를 가진 entry 제거.

```python
ops = [map_ops.map_remove_by_value_range(
    "scores", 0, 50, aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Read Operation (Key/Value/Index/Rank 기반)

이 operation 들은 반환되는 내용을 제어하는 `return_type` 파라미터 필요.

#### `map_get_by_key_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 key 를 가진 entry 가져오기.

```python
ops = [map_ops.map_get_by_key_range(
    "profile", "a", "n", aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_key_list(bin, keys, return_type)`

주어진 key 중 어느 하나와 매칭되는 entry 가져오기.

```python
ops = [map_ops.map_get_by_key_list(
    "profile", ["name", "email"], aerospike.MAP_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value(bin, val, return_type)`

value 기반 entry 가져오기.

```python
ops = [map_ops.map_get_by_value("scores", 100, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_range(bin, begin, end, return_type)`

`[begin, end)` 범위의 value 를 가진 entry 가져오기.

```python
ops = [map_ops.map_get_by_value_range(
    "scores", 90, 100, aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_list(bin, values, return_type)`

주어진 value 중 어느 하나와 매칭되는 entry 가져오기.

```python
ops = [map_ops.map_get_by_value_list(
    "scores", [100, 95], aerospike.MAP_RETURN_KEY
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index(bin, index, return_type)`

index (key-ordered 위치) 기반 entry 가져오기.

```python
ops = [map_ops.map_get_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index_range(bin, index, return_type, count=None)`

index range 로 entry 가져오기.

```python
ops = [map_ops.map_get_by_index_range(
    "profile", 0, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank(bin, rank, return_type)`

rank 기반 entry 가져오기 (0 = 최소 value).

```python
ops = [map_ops.map_get_by_rank("scores", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank_range(bin, rank, return_type, count=None)`

rank range 로 entry 가져오기.

```python
ops = [map_ops.map_get_by_rank_range(
    "scores", -3, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Remove Operation (Index/Rank 기반)

#### `map_remove_by_index(bin, index, return_type)`

index 기반 entry 제거.

```python
ops = [map_ops.map_remove_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_index_range(bin, index, return_type, count=None)`

index range 로 entry 제거.

```python
ops = [map_ops.map_remove_by_index_range(
    "cache", 0, aerospike.MAP_RETURN_NONE, count=5
)]
client.operate(key, ops)
```

#### `map_remove_by_rank(bin, rank, return_type)`

rank 기반 entry 제거.

```python
ops = [map_ops.map_remove_by_rank("scores", 0, aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_rank_range(bin, rank, return_type, count=None)`

rank range 로 entry 제거.

```python
ops = [map_ops.map_remove_by_rank_range(
    "scores", 0, aerospike.MAP_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### Map Constant

| Constant | 설명 |
|----------|-------------|
| `MAP_RETURN_NONE` | 아무것도 반환 안 함 |
| `MAP_RETURN_INDEX` | index 반환 |
| `MAP_RETURN_REVERSE_INDEX` | reverse index 반환 |
| `MAP_RETURN_RANK` | rank 반환 |
| `MAP_RETURN_REVERSE_RANK` | reverse rank 반환 |
| `MAP_RETURN_COUNT` | 매칭된 entry 수 반환 |
| `MAP_RETURN_KEY` | key 반환 |
| `MAP_RETURN_VALUE` | value 반환 |
| `MAP_RETURN_KEY_VALUE` | key-value 쌍 반환 |
| `MAP_RETURN_EXISTS` | boolean 존재 여부 반환 |
| `MAP_UNORDERED` | unordered map (default) |
| `MAP_KEY_ORDERED` | key 로 ordered |
| `MAP_KEY_VALUE_ORDERED` | key 와 value 로 ordered |
| `MAP_WRITE_FLAGS_DEFAULT` | default 동작 |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | 새 entry 만 생성 |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | 기존 entry 만 update |
| `MAP_WRITE_FLAGS_NO_FAIL` | policy 위반 시 error raise 안 함 |
| `MAP_WRITE_FLAGS_PARTIAL` | multi-item op 의 부분 성공 허용 |

### Map 전체 예제

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

    # Atomic: top 2 score 와 총 개수 가져오기
    ops = [
        map_ops.map_get_by_rank_range(
            "scores", -2, aerospike.MAP_RETURN_KEY_VALUE, count=2
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 2 scores: {bins['scores']}")

    # 80 미만 score 제거
    ops = [
        map_ops.map_remove_by_value_range(
            "scores", 0, 80, aerospike.MAP_RETURN_KEY
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed subjects: {bins['scores']}")

    # 새 score 추가 + 기존 score increment
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
