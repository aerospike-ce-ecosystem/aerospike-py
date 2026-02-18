---
title: List CDT Operations
sidebar_label: List Operations
sidebar_position: 2
slug: /guides/cdt-list
description: 31 atomic list operations for append, insert, remove, sort, and advanced queries on list bins.
---

Atomic server-side list operations via `client.operate()`.

## Import

```python
from aerospike_py import list_operations as list_ops
import aerospike_py as aerospike
```

## Overview

Each `list_ops.*` function returns an operation dict that you pass to `client.operate()` or `client.operate_ordered()`:

```python
ops = [
    list_ops.list_append("scores", 100),
    list_ops.list_size("scores"),
]
_, _, bins = client.operate(key, ops)
```

## Basic Write Operations

### `list_append(bin, val, policy=None)`

Append a value to the end of a list.

```python
ops = [list_ops.list_append("colors", "red")]
client.operate(key, ops)
```

### `list_append_items(bin, values, policy=None)`

Append multiple values to a list.

```python
ops = [list_ops.list_append_items("colors", ["green", "blue"])]
client.operate(key, ops)
```

### `list_insert(bin, index, val, policy=None)`

Insert a value at the given index.

```python
ops = [list_ops.list_insert("colors", 0, "yellow")]
client.operate(key, ops)
```

### `list_insert_items(bin, index, values, policy=None)`

Insert multiple values at the given index.

```python
ops = [list_ops.list_insert_items("colors", 1, ["cyan", "magenta"])]
client.operate(key, ops)
```

### `list_set(bin, index, val)`

Set the value at a specific index.

```python
ops = [list_ops.list_set("colors", 0, "orange")]
client.operate(key, ops)
```

### `list_increment(bin, index, val, policy=None)`

Increment the numeric value at a given index.

```python
ops = [list_ops.list_increment("scores", 0, 10)]
client.operate(key, ops)
```

## Basic Read Operations

### `list_get(bin, index)`

Get the item at a specific index.

```python
ops = [list_ops.list_get("scores", 0)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first element
```

### `list_get_range(bin, index, count)`

Get `count` items starting at `index`.

```python
ops = [list_ops.list_get_range("scores", 0, 3)]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # first 3 elements
```

### `list_size(bin)`

Return the number of items in a list.

```python
ops = [list_ops.list_size("scores")]
_, _, bins = client.operate(key, ops)
print(bins["scores"])  # e.g., 5
```

## Remove Operations

### `list_remove(bin, index)`

Remove the item at the given index.

```python
ops = [list_ops.list_remove("colors", 0)]
client.operate(key, ops)
```

### `list_remove_range(bin, index, count)`

Remove `count` items starting at `index`.

```python
ops = [list_ops.list_remove_range("colors", 1, 2)]
client.operate(key, ops)
```

### `list_pop(bin, index)`

Remove and return the item at the given index.

```python
ops = [list_ops.list_pop("colors", 0)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # the removed item
```

### `list_pop_range(bin, index, count)`

Remove and return `count` items starting at `index`.

```python
ops = [list_ops.list_pop_range("colors", 0, 2)]
_, _, bins = client.operate(key, ops)
print(bins["colors"])  # list of removed items
```

### `list_trim(bin, index, count)`

Remove items outside the specified range `[index, index+count)`.

```python
# Keep only items at index 1..3
ops = [list_ops.list_trim("scores", 1, 3)]
client.operate(key, ops)
```

### `list_clear(bin)`

Remove all items from a list.

```python
ops = [list_ops.list_clear("scores")]
client.operate(key, ops)
```

## Sort Operations

### `list_sort(bin, sort_flags=0)`

Sort the list in place.

```python
ops = [list_ops.list_sort("scores")]
client.operate(key, ops)

# Drop duplicates while sorting
ops = [list_ops.list_sort("scores", aerospike.LIST_SORT_DROP_DUPLICATES)]
client.operate(key, ops)
```

### `list_set_order(bin, list_order=0)`

Set the list ordering type.

```python
# Set to ordered (maintains sort order on future writes)
ops = [list_ops.list_set_order("scores", aerospike.LIST_ORDERED)]
client.operate(key, ops)
```

## Advanced Read Operations (by Value/Index/Rank)

These operations require a `return_type` parameter that controls what is returned.

### `list_get_by_value(bin, val, return_type)`

Get items matching the given value.

```python
ops = [list_ops.list_get_by_value("tags", "urgent", aerospike.LIST_RETURN_INDEX)]
_, _, bins = client.operate(key, ops)
# Returns indices of all "urgent" items
```

### `list_get_by_value_list(bin, values, return_type)`

Get items matching any of the given values.

```python
ops = [list_ops.list_get_by_value_list(
    "tags", ["urgent", "important"], aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_value_range(bin, begin, end, return_type)`

Get items with values in the range `[begin, end)`.

```python
ops = [list_ops.list_get_by_value_range(
    "scores", 80, 100, aerospike.LIST_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_index(bin, index, return_type)`

Get item by index with specified return type.

```python
ops = [list_ops.list_get_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_index_range(bin, index, return_type, count=None)`

Get items by index range.

```python
# Get 3 items starting at index 2
ops = [list_ops.list_get_by_index_range(
    "scores", 2, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_rank(bin, rank, return_type)`

Get item by rank (0 = smallest).

```python
# Get the smallest value
ops = [list_ops.list_get_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_get_by_rank_range(bin, rank, return_type, count=None)`

Get items by rank range.

```python
# Get top 3 values (highest rank)
ops = [list_ops.list_get_by_rank_range(
    "scores", -3, aerospike.LIST_RETURN_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

## Advanced Remove Operations (by Value/Index/Rank)

### `list_remove_by_value(bin, val, return_type)`

Remove items matching the given value.

```python
ops = [list_ops.list_remove_by_value("tags", "temp", aerospike.LIST_RETURN_COUNT)]
_, _, bins = client.operate(key, ops)
print(f"Removed {bins['tags']} items")
```

### `list_remove_by_value_list(bin, values, return_type)`

Remove items matching any of the given values.

```python
ops = [list_ops.list_remove_by_value_list(
    "tags", ["temp", "debug"], aerospike.LIST_RETURN_NONE
)]
client.operate(key, ops)
```

### `list_remove_by_value_range(bin, begin, end, return_type)`

Remove items with values in the range `[begin, end)`.

```python
ops = [list_ops.list_remove_by_value_range(
    "scores", 0, 50, aerospike.LIST_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_index(bin, index, return_type)`

Remove item by index.

```python
ops = [list_ops.list_remove_by_index("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_index_range(bin, index, return_type, count=None)`

Remove items by index range.

```python
ops = [list_ops.list_remove_by_index_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

### `list_remove_by_rank(bin, rank, return_type)`

Remove item by rank.

```python
# Remove smallest value
ops = [list_ops.list_remove_by_rank("scores", 0, aerospike.LIST_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `list_remove_by_rank_range(bin, rank, return_type, count=None)`

Remove items by rank range.

```python
# Remove 2 smallest values
ops = [list_ops.list_remove_by_rank_range(
    "scores", 0, aerospike.LIST_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

## Return Type Constants

Use these constants from `aerospike_py` to control what the server returns:

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

## List Order Constants

| Constant | Description |
|----------|-------------|
| `LIST_UNORDERED` | Unordered list (default) |
| `LIST_ORDERED` | Ordered list (maintains sort order) |

## List Sort Flags

| Constant | Description |
|----------|-------------|
| `LIST_SORT_DEFAULT` | Default sort |
| `LIST_SORT_DROP_DUPLICATES` | Drop duplicates during sort |

## Complete Example

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
