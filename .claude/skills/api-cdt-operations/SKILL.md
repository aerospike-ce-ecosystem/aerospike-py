---
name: api-cdt-operations
description: aerospike-py List and Map CDT (Collection Data Type) operations for operate() - list_operations, map_operations
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## List CDT

```python
from aerospike_py import list_operations as lop

client.operate(key, [
    lop.list_append("mylist", "val"),
    lop.list_get("mylist", 0),
    lop.list_size("mylist"),
])

# 주요 함수 (모두 Operation dict를 반환):
# 쓰기: list_append, list_append_items, list_insert, list_insert_items
# 읽기: list_get, list_get_range, list_get_by_value, list_get_by_index,
#        list_get_by_index_range, list_get_by_rank, list_get_by_rank_range,
#        list_get_by_value_list, list_get_by_value_range
# 삭제: list_pop, list_pop_range, list_remove, list_remove_range,
#        list_remove_by_value, list_remove_by_value_list, list_remove_by_value_range,
#        list_remove_by_index, list_remove_by_index_range,
#        list_remove_by_rank, list_remove_by_rank_range
# 수정: list_set, list_trim, list_clear, list_increment, list_sort, list_set_order
# 정보: list_size
#
# return_type: LIST_RETURN_NONE, LIST_RETURN_VALUE, LIST_RETURN_COUNT,
#              LIST_RETURN_INDEX, LIST_RETURN_RANK 등
# policy (선택): {"list_order": LIST_ORDERED, "write_flags": LIST_WRITE_ADD_UNIQUE}
```

### List 상수

```python
# Return Type
LIST_RETURN_NONE = 0          # 반환 없음
LIST_RETURN_VALUE = 7         # 값 반환
LIST_RETURN_COUNT = 5         # 개수 반환
LIST_RETURN_INDEX = 1         # 인덱스 반환
LIST_RETURN_RANK = 3          # 랭크 반환

# Order / Sort / Write Flags
LIST_UNORDERED, LIST_ORDERED
LIST_SORT_DEFAULT, LIST_SORT_DROP_DUPLICATES
LIST_WRITE_DEFAULT, LIST_WRITE_ADD_UNIQUE, LIST_WRITE_INSERT_BOUNDED
LIST_WRITE_NO_FAIL, LIST_WRITE_PARTIAL
```

## Map CDT

```python
from aerospike_py import map_operations as mop

client.operate(key, [
    mop.map_put("mymap", "k1", "v1"),
    mop.map_get_by_key("mymap", "k1", aerospike_py.MAP_RETURN_VALUE),
    mop.map_size("mymap"),
])

# 주요 함수:
# 쓰기: map_put, map_put_items, map_increment, map_decrement
# 읽기: map_get_by_key, map_get_by_key_range, map_get_by_key_list,
#        map_get_by_value, map_get_by_value_range, map_get_by_value_list,
#        map_get_by_index, map_get_by_index_range,
#        map_get_by_rank, map_get_by_rank_range
# 삭제: map_remove_by_key, map_remove_by_key_list, map_remove_by_key_range,
#        map_remove_by_value, map_remove_by_value_list, map_remove_by_value_range,
#        map_remove_by_index, map_remove_by_index_range,
#        map_remove_by_rank, map_remove_by_rank_range
# 기타: map_clear, map_size, map_set_order
#
# return_type: MAP_RETURN_NONE, MAP_RETURN_VALUE, MAP_RETURN_KEY,
#              MAP_RETURN_KEY_VALUE, MAP_RETURN_COUNT 등
# policy (선택): {"map_order": MAP_KEY_ORDERED, "write_flags": MAP_WRITE_FLAGS_CREATE_ONLY}
```

### Map 상수

```python
# Return Type
MAP_RETURN_NONE = 0           # 반환 없음
MAP_RETURN_INDEX = 1          # 인덱스 반환
MAP_RETURN_REVERSE_INDEX = 2  # 역순 인덱스
MAP_RETURN_RANK = 3           # 랭크 반환
MAP_RETURN_REVERSE_RANK = 4   # 역순 랭크
MAP_RETURN_COUNT = 5          # 개수 반환
MAP_RETURN_KEY = 6            # 키 반환
MAP_RETURN_VALUE = 7          # 값 반환
MAP_RETURN_KEY_VALUE = 8      # 키-값 쌍 반환
MAP_RETURN_EXISTS = 9         # 존재 여부

# Order / Write Flags
MAP_UNORDERED, MAP_KEY_ORDERED, MAP_KEY_VALUE_ORDERED
MAP_WRITE_FLAGS_DEFAULT, MAP_WRITE_FLAGS_CREATE_ONLY, MAP_WRITE_FLAGS_UPDATE_ONLY
MAP_WRITE_FLAGS_NO_FAIL, MAP_WRITE_FLAGS_PARTIAL
```
