---
title: List & Map CDT Operations
sidebar_label: Operations
sidebar_position: 3
slug: /guides/operations
description: Atomic server-side List (31 ops) and Map (27 ops) collection data type operations via client.operate().
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

Atomic server-side collection data type (CDT) operations via `client.operate()`.

```python
from aerospike_py import list_operations as list_ops
from aerospike_py import map_operations as map_ops
import aerospike_py as aerospike
```

---

## List CDT Operations

Each `list_ops.*` function returns an operation dict that you pass to `client.operate()` or `client.operate_ordered()`:

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

**`list_append(bin, val, policy=None)`** — Append a value to the end of a list.

```python
ops = [list_ops.list_append("colors", "red")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_append_items" label="list_append_items">

**`list_append_items(bin, values, policy=None)`** — Append multiple values to a list.

```python
ops = [list_ops.list_append_items("colors", ["green", "blue"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_insert" label="list_insert">

**`list_insert(bin, index, val, policy=None)`** — Insert a value at the given index.

```python
ops = [list_ops.list_insert("colors", 0, "yellow")]
client.operate(key, ops)
```

**`list_insert_items(bin, index, values, policy=None)`** — Insert multiple values at the given index.

```python
ops = [list_ops.list_insert_items("colors", 1, ["cyan", "magenta"])]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_set" label="list_set">

**`list_set(bin, index, val)`** — Set the value at a specific index.

```python
ops = [list_ops.list_set("colors", 0, "orange")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="list_increment" label="list_increment">

**`list_increment(bin, index, val, policy=None)`** — Increment the numeric value at a given index.

```python
ops = [list_ops.list_increment("scores", 0, 10)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### Basic Read Operations

#### `list_get(bin, index)`

Get the item at a specific index.

```python
ops = [list_ops.list_get("scores", 0)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first element
```

#### `list_get_range(bin, index, count)`

Get `count` items starting at `index`.

```python
ops = [list_ops.list_get_range("scores", 0, 3)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first 3 elements
```

#### `list_size(bin)`

Return the number of items in a list.

```python
ops = [list_ops.list_size("scores")]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # e.g., 5
```

### Remove Operations

#### `list_remove(bin, index)`

Remove the item at the given index.

```python
ops = [list_ops.list_remove("colors", 0)]
client.operate(key, ops)
```

#### `list_remove_range(bin, index, count)`

Remove `count` items starting at `index`.

```python
ops = [list_ops.list_remove_range("colors", 1, 2)]
client.operate(key, ops)
```

#### `list_pop(bin, index)`

Remove and return the item at the given index.

```python
ops = [list_ops.list_pop("colors", 0)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # the removed item
```

#### `list_pop_range(bin, index, count)`

Remove and return `count` items starting at `index`.

```python
ops = [list_ops.list_pop_range("colors", 0, 2)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # list of removed items
```

#### `list_trim(bin, index, count)`

Remove items outside the specified range `[index, index+count)`.

```python
ops = [list_ops.list_trim("scores", 1, 3)]
client.operate(key, ops)
```

#### `list_clear(bin)`

Remove all items from a list.

```python
ops = [list_ops.list_clear("scores")]
client.operate(key, ops)
```

### Sort & Order

#### `list_sort(bin, sort_flags=0)`

Sort the list in place.

```python
ops = [list_ops.list_sort("scores")]
client.operate(key, ops)

# Drop duplicates while sorting
ops = [list_ops.list_sort("scores", aerospike.LIST_SORT_DROP_DUPLICATES)]
client.operate(key, ops)
```

#### `list_set_order(bin, list_order=0)`

Set the list ordering type.

```python
ops = [list_ops.list_set_order("scores", aerospike.LIST_ORDERED)]
client.operate(key, ops)
```

### Advanced Read Operations (by Value/Index/Rank)

These operations require a `return_type` parameter that controls what is returned.

#### `list_get_by_value(bin, val, return_type)`

Get items matching the given value.

```python
ops = [list_ops.list_get_by_value("tags", "urgent", aerospike.LIST_RETURN_INDEX)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_list(bin, values, return_type)`

Get items matching any of the given values.

```python
ops = [list_ops.list_get_by_value_list(
    "tags", ["urgent", "important"], aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_value_range(bin, begin, end, return_type)`

Get items with values in the range `[begin, end)`.

```python
ops = [list_ops.list_get_by_value_range(
    "scores", 80, 100, aerospike.LIST_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index(bin, index, return_type)`

Get item by index with specified return type.

```python
ops = [list_ops.list_get_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_index_range(bin, index, return_type, count=None)`

Get items by index range.

```python
ops = [list_ops.list_get_by_index_range(
    "scores", 2, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank(bin, rank, return_type)`

Get item by rank (0 = smallest).

```python
ops = [list_ops.list_get_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_get_by_rank_range(bin, rank, return_type, count=None)`

Get items by rank range.

```python
ops = [list_ops.list_get_by_rank_range(
    "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Remove Operations (by Value/Index/Rank)

#### `list_remove_by_value(bin, val, return_type)`

Remove items matching the given value.

```python
ops = [list_ops.list_remove_by_value("tags", "temp", aerospike.LIST_RETURN_COUNT)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_value_list(bin, values, return_type)`

Remove items matching any of the given values.

```python
ops = [list_ops.list_remove_by_value_list(
    "tags", ["temp", "debug"], aerospike.LIST_RETURN_NONE
)]
client.operate(key, ops)
```

#### `list_remove_by_value_range(bin, begin, end, return_type)`

Remove items with values in the range `[begin, end)`.

```python
ops = [list_ops.list_remove_by_value_range(
    "scores", 0, 50, aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index(bin, index, return_type)`

Remove item by index.

```python
ops = [list_ops.list_remove_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_index_range(bin, index, return_type, count=None)`

Remove items by index range.

```python
ops = [list_ops.list_remove_by_index_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

#### `list_remove_by_rank(bin, rank, return_type)`

Remove item by rank.

```python
ops = [list_ops.list_remove_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `list_remove_by_rank_range(bin, rank, return_type, count=None)`

Remove items by rank range.

```python
ops = [list_ops.list_remove_by_rank_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### List Constants

| Constant | Description |
|----------|-------------|
| `LIST_RETURN_NONE` | Return nothing |
| `LIST_RETURN_INDEX` | Return index(es) |
| `LIST_RETURN_REVERSE_INDEX` | Return reverse index(es) |
| `LIST_RETURN_RANK` | Return rank(s) |
| `LIST_RETURN_REVERSE_RANK` | Return reverse rank(s) |
| `LIST_RETURN_COUNT` | Return count of matched items |
| `LIST_RETURN_VALUE` | Return value(s) |
| `LIST_RETURN_EXISTS` | Return boolean existence |
| `LIST_UNORDERED` | Unordered list (default) |
| `LIST_ORDERED` | Ordered list (maintains sort order) |
| `LIST_SORT_DEFAULT` | Default sort |
| `LIST_SORT_DROP_DUPLICATES` | Drop duplicates during sort |

### List Complete Example

```python
import aerospike_py as aerospike
from aerospike_py import list_operations as list_ops

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "player1")

    # Initialize a scores list
    client.put(key, {"scores": [85, 92, 78, 95, 88]})

    # Atomic: sort, get top 3, and get size
    ops = [
        list_ops.list_sort("scores"),
        list_ops.list_get_by_rank_range(
            "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 3 scores: {bins['scores']}")

    # Remove scores below 80
    ops = [
        list_ops.list_remove_by_value_range(
            "scores", 0, 80, aerospike.LIST_RETURN_COUNT
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed {bins['scores']} low scores")

    # Append a new score and get updated size
    ops = [
        list_ops.list_append("scores", 97),
        list_ops.list_size("scores"),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Total scores: {bins['scores']}")
```

---

## Map CDT Operations

Each `map_ops.*` function returns an operation dict that you pass to `client.operate()` or `client.operate_ordered()`:

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

**`map_put(bin, key, val, policy=None)`** — Put a key/value pair into a map.

```python
ops = [map_ops.map_put("profile", "name", "Alice")]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_put_items" label="map_put_items">

**`map_put_items(bin, items, policy=None)`** — Put multiple key/value pairs into a map.

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

**`map_increment(bin, key, incr, policy=None)`** — Increment a numeric value in a map by key.

```python
ops = [map_ops.map_increment("counters", "views", 1)]
client.operate(key, ops)
```

  </TabItem>
  <TabItem value="map_decrement" label="map_decrement">

**`map_decrement(bin, key, decr, policy=None)`** — Decrement a numeric value in a map by key.

```python
ops = [map_ops.map_decrement("counters", "stock", 1)]
client.operate(key, ops)
```

  </TabItem>
</Tabs>

### Basic Read Operations

#### `map_size(bin)`

Return the number of entries in a map.

```python
ops = [map_ops.map_size("profile")]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # e.g., 3
```

#### `map_get_by_key(bin, key, return_type)`

Get an entry by key.

```python
ops = [map_ops.map_get_by_key("profile", "name", aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # "Alice"
```

### Map Settings

#### `map_set_order(bin, map_order)`

Set the map ordering type.

```python
ops = [map_ops.map_set_order("profile", aerospike.MAP_KEY_ORDERED)]
client.operate(key, ops)
```

#### `map_clear(bin)`

Remove all items from a map.

```python
ops = [map_ops.map_clear("profile")]
client.operate(key, ops)
```

### Remove Operations

#### `map_remove_by_key(bin, key, return_type)`

Remove entry by key.

```python
ops = [map_ops.map_remove_by_key("profile", "temp", aerospike.MAP_RETURN_NONE)]
client.operate(key, ops)
```

#### `map_remove_by_key_list(bin, keys, return_type)`

Remove entries matching any of the given keys.

```python
ops = [map_ops.map_remove_by_key_list(
    "profile", ["temp", "debug"], aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_key_range(bin, begin, end, return_type)`

Remove entries with keys in the range `[begin, end)`.

```python
ops = [map_ops.map_remove_by_key_range(
    "cache", "tmp_a", "tmp_z", aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value(bin, val, return_type)`

Remove entries by value.

```python
ops = [map_ops.map_remove_by_value("scores", 0, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_value_list(bin, values, return_type)`

Remove entries matching any of the given values.

```python
ops = [map_ops.map_remove_by_value_list(
    "tags", ["deprecated", "old"], aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

#### `map_remove_by_value_range(bin, begin, end, return_type)`

Remove entries with values in the range `[begin, end)`.

```python
ops = [map_ops.map_remove_by_value_range(
    "scores", 0, 50, aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Read Operations (by Key/Value/Index/Rank)

These operations require a `return_type` parameter that controls what is returned.

#### `map_get_by_key_range(bin, begin, end, return_type)`

Get entries with keys in the range `[begin, end)`.

```python
ops = [map_ops.map_get_by_key_range(
    "profile", "a", "n", aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_key_list(bin, keys, return_type)`

Get entries matching any of the given keys.

```python
ops = [map_ops.map_get_by_key_list(
    "profile", ["name", "email"], aerospike.MAP_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value(bin, val, return_type)`

Get entries by value.

```python
ops = [map_ops.map_get_by_value("scores", 100, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_range(bin, begin, end, return_type)`

Get entries with values in the range `[begin, end)`.

```python
ops = [map_ops.map_get_by_value_range(
    "scores", 90, 100, aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_value_list(bin, values, return_type)`

Get entries matching any of the given values.

```python
ops = [map_ops.map_get_by_value_list(
    "scores", [100, 95], aerospike.MAP_RETURN_KEY
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index(bin, index, return_type)`

Get entry by index (key-ordered position).

```python
ops = [map_ops.map_get_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_index_range(bin, index, return_type, count=None)`

Get entries by index range.

```python
ops = [map_ops.map_get_by_index_range(
    "profile", 0, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank(bin, rank, return_type)`

Get entry by rank (0 = smallest value).

```python
ops = [map_ops.map_get_by_rank("scores", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_get_by_rank_range(bin, rank, return_type, count=None)`

Get entries by rank range.

```python
ops = [map_ops.map_get_by_rank_range(
    "scores", -3, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### Advanced Remove Operations (by Index/Rank)

#### `map_remove_by_index(bin, index, return_type)`

Remove entry by index.

```python
ops = [map_ops.map_remove_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_index_range(bin, index, return_type, count=None)`

Remove entries by index range.

```python
ops = [map_ops.map_remove_by_index_range(
    "cache", 0, aerospike.MAP_RETURN_NONE, count=5
)]
client.operate(key, ops)
```

#### `map_remove_by_rank(bin, rank, return_type)`

Remove entry by rank.

```python
ops = [map_ops.map_remove_by_rank("scores", 0, aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

#### `map_remove_by_rank_range(bin, rank, return_type, count=None)`

Remove entries by rank range.

```python
ops = [map_ops.map_remove_by_rank_range(
    "scores", 0, aerospike.MAP_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### Map Constants

| Constant | Description |
|----------|-------------|
| `MAP_RETURN_NONE` | Return nothing |
| `MAP_RETURN_INDEX` | Return index(es) |
| `MAP_RETURN_REVERSE_INDEX` | Return reverse index(es) |
| `MAP_RETURN_RANK` | Return rank(s) |
| `MAP_RETURN_REVERSE_RANK` | Return reverse rank(s) |
| `MAP_RETURN_COUNT` | Return count of matched entries |
| `MAP_RETURN_KEY` | Return key(s) |
| `MAP_RETURN_VALUE` | Return value(s) |
| `MAP_RETURN_KEY_VALUE` | Return key-value pair(s) |
| `MAP_RETURN_EXISTS` | Return boolean existence |
| `MAP_UNORDERED` | Unordered map (default) |
| `MAP_KEY_ORDERED` | Ordered by key |
| `MAP_KEY_VALUE_ORDERED` | Ordered by key and value |
| `MAP_WRITE_FLAGS_DEFAULT` | Default behavior |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | Only create new entries |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | Only update existing entries |
| `MAP_WRITE_FLAGS_NO_FAIL` | Do not raise error on policy violation |
| `MAP_WRITE_FLAGS_PARTIAL` | Allow partial success for multi-item ops |

### Map Complete Example

```python
import aerospike_py as aerospike
from aerospike_py import map_operations as map_ops

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "player1")

    # Initialize a scores map
    client.put(key, {"scores": {"math": 92, "science": 88, "english": 75, "art": 95}})

    # Atomic: get top 2 scores and total count
    ops = [
        map_ops.map_get_by_rank_range(
            "scores", -2, aerospike.MAP_RETURN_KEY_VALUE, count=2
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Top 2 scores: {bins['scores']}")

    # Remove scores below 80
    ops = [
        map_ops.map_remove_by_value_range(
            "scores", 0, 80, aerospike.MAP_RETURN_KEY
        ),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Removed subjects: {bins['scores']}")

    # Add a new score and increment an existing one
    ops = [
        map_ops.map_put("scores", "history", 90),
        map_ops.map_increment("scores", "math", 5),
        map_ops.map_size("scores"),
    ]
    _, _, bins = client.operate(key, ops)
    print(f"Total subjects: {bins['scores']}")
```
