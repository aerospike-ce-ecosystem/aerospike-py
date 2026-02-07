---
title: Map CDT Operations
sidebar_label: Map Operations
sidebar_position: 5
description: 27 atomic map operations for put, get, remove, and advanced queries on map bins.
---

Map CDT (Collection Data Type) operations provide 27 atomic operations on map bins. These are executed server-side as part of `client.operate()`, enabling atomic multi-operation transactions on map data.

## Import

```python
from aerospike_py import map_operations as map_ops
import aerospike_py as aerospike
```

## Overview

Each `map_ops.*` function returns an operation dict that you pass to `client.operate()` or `client.operate_ordered()`:

```python
ops = [
    map_ops.map_put("profile", "email", "alice@example.com"),
    map_ops.map_size("profile"),
]
_, _, bins = client.operate(key, ops)
```

## Basic Write Operations

### `map_put(bin, key, val, policy=None)`

Put a key/value pair into a map.

```python
ops = [map_ops.map_put("profile", "name", "Alice")]
client.operate(key, ops)
```

### `map_put_items(bin, items, policy=None)`

Put multiple key/value pairs into a map.

```python
ops = [map_ops.map_put_items("profile", {
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30,
})]
client.operate(key, ops)
```

### `map_increment(bin, key, incr, policy=None)`

Increment a numeric value in a map by key.

```python
ops = [map_ops.map_increment("counters", "views", 1)]
client.operate(key, ops)
```

### `map_decrement(bin, key, decr, policy=None)`

Decrement a numeric value in a map by key.

```python
ops = [map_ops.map_decrement("counters", "stock", 1)]
client.operate(key, ops)
```

## Map Settings

### `map_set_order(bin, map_order)`

Set the map ordering type.

```python
# Set map to key-ordered
ops = [map_ops.map_set_order("profile", aerospike.MAP_KEY_ORDERED)]
client.operate(key, ops)
```

### `map_clear(bin)`

Remove all items from a map.

```python
ops = [map_ops.map_clear("profile")]
client.operate(key, ops)
```

## Basic Read Operations

### `map_size(bin)`

Return the number of entries in a map.

```python
ops = [map_ops.map_size("profile")]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # e.g., 3
```

### `map_get_by_key(bin, key, return_type)`

Get an entry by key.

```python
ops = [map_ops.map_get_by_key("profile", "name", aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
print(bins["profile"])  # "Alice"
```

## Advanced Read Operations

### `map_get_by_key_range(bin, begin, end, return_type)`

Get entries with keys in the range `[begin, end)`.

```python
ops = [map_ops.map_get_by_key_range(
    "profile", "a", "n", aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_key_list(bin, keys, return_type)`

Get entries matching any of the given keys.

```python
ops = [map_ops.map_get_by_key_list(
    "profile", ["name", "email"], aerospike.MAP_RETURN_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_value(bin, val, return_type)`

Get entries by value.

```python
ops = [map_ops.map_get_by_value("scores", 100, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
# Returns keys of entries with value 100
```

### `map_get_by_value_range(bin, begin, end, return_type)`

Get entries with values in the range `[begin, end)`.

```python
ops = [map_ops.map_get_by_value_range(
    "scores", 90, 100, aerospike.MAP_RETURN_KEY_VALUE
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_value_list(bin, values, return_type)`

Get entries matching any of the given values.

```python
ops = [map_ops.map_get_by_value_list(
    "scores", [100, 95], aerospike.MAP_RETURN_KEY
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_index(bin, index, return_type)`

Get entry by index (key-ordered position).

```python
# Get first entry (by key order)
ops = [map_ops.map_get_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_index_range(bin, index, return_type, count=None)`

Get entries by index range.

```python
# Get first 3 entries by key order
ops = [map_ops.map_get_by_index_range(
    "profile", 0, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_rank(bin, rank, return_type)`

Get entry by rank (0 = smallest value).

```python
# Get entry with smallest value
ops = [map_ops.map_get_by_rank("scores", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_get_by_rank_range(bin, rank, return_type, count=None)`

Get entries by rank range.

```python
# Get top 3 entries by value
ops = [map_ops.map_get_by_rank_range(
    "scores", -3, aerospike.MAP_RETURN_KEY_VALUE, count=3
)]
_, _, bins = client.operate(key, ops)
```

## Remove Operations

### `map_remove_by_key(bin, key, return_type)`

Remove entry by key.

```python
ops = [map_ops.map_remove_by_key("profile", "temp", aerospike.MAP_RETURN_NONE)]
client.operate(key, ops)
```

### `map_remove_by_key_list(bin, keys, return_type)`

Remove entries matching any of the given keys.

```python
ops = [map_ops.map_remove_by_key_list(
    "profile", ["temp", "debug"], aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_key_range(bin, begin, end, return_type)`

Remove entries with keys in the range `[begin, end)`.

```python
ops = [map_ops.map_remove_by_key_range(
    "cache", "tmp_a", "tmp_z", aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

### `map_remove_by_value(bin, val, return_type)`

Remove entries by value.

```python
ops = [map_ops.map_remove_by_value("scores", 0, aerospike.MAP_RETURN_KEY)]
_, _, bins = client.operate(key, ops)
# Returns keys of removed entries
```

### `map_remove_by_value_list(bin, values, return_type)`

Remove entries matching any of the given values.

```python
ops = [map_ops.map_remove_by_value_list(
    "tags", ["deprecated", "old"], aerospike.MAP_RETURN_NONE
)]
client.operate(key, ops)
```

### `map_remove_by_value_range(bin, begin, end, return_type)`

Remove entries with values in the range `[begin, end)`.

```python
ops = [map_ops.map_remove_by_value_range(
    "scores", 0, 50, aerospike.MAP_RETURN_COUNT
)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_index(bin, index, return_type)`

Remove entry by index.

```python
ops = [map_ops.map_remove_by_index("profile", 0, aerospike.MAP_RETURN_KEY_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_index_range(bin, index, return_type, count=None)`

Remove entries by index range.

```python
ops = [map_ops.map_remove_by_index_range(
    "cache", 0, aerospike.MAP_RETURN_NONE, count=5
)]
client.operate(key, ops)
```

### `map_remove_by_rank(bin, rank, return_type)`

Remove entry by rank.

```python
# Remove entry with smallest value
ops = [map_ops.map_remove_by_rank("scores", 0, aerospike.MAP_RETURN_VALUE)]
_, _, bins = client.operate(key, ops)
```

### `map_remove_by_rank_range(bin, rank, return_type, count=None)`

Remove entries by rank range.

```python
# Remove 2 entries with smallest values
ops = [map_ops.map_remove_by_rank_range(
    "scores", 0, aerospike.MAP_RETURN_NONE, count=2
)]
client.operate(key, ops)
```

## Return Type Constants

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

## Map Order Constants

| Constant | Description |
|----------|-------------|
| `MAP_UNORDERED` | Unordered map (default) |
| `MAP_KEY_ORDERED` | Ordered by key |
| `MAP_KEY_VALUE_ORDERED` | Ordered by key and value |

## Map Write Flag Constants

| Constant | Description |
|----------|-------------|
| `MAP_WRITE_FLAGS_DEFAULT` | Default behavior |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | Only create new entries |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | Only update existing entries |
| `MAP_WRITE_FLAGS_NO_FAIL` | Do not raise error on policy violation |
| `MAP_WRITE_FLAGS_PARTIAL` | Allow partial success for multi-item ops |

## Complete Example

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
