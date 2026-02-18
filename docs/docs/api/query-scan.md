---
title: Query
sidebar_label: Query
sidebar_position: 2
description: API reference for the Query class including predicates and result iteration.
---

## Query

`Query` performs secondary index queries to find records matching specific criteria.

### Creating a Query

```python
query = client.query("test", "demo")
```

### `select(*bins)`

Select specific bins to return.

```python
query.select("name", "age")
```

### `where(predicate)`

Add a filter predicate. Requires a secondary index on the bin.

```python
from aerospike_py import predicates

query.where(predicates.equals("name", "Alice"))
query.where(predicates.between("age", 20, 30))
```

### `results(policy=None)`

Execute the query and return all matching records.

```python
records = query.results()
for key, meta, bins in records:
    print(bins)
```

### `foreach(callback, policy=None)`

Execute the query and call `callback` for each record.

```python
def process(record):
    key, meta, bins = record
    print(bins)

query.foreach(process)
```

Return `False` from the callback to stop iteration:

```python
count = 0
def limited(record):
    nonlocal count
    count += 1
    if count >= 10:
        return False

query.foreach(limited)
```

## Predicates

The `aerospike.predicates` module provides filter functions for queries.

### `equals(bin_name, val)`

Match records where `bin_name == val`.

```python
from aerospike_py import predicates

# String equality
predicates.equals("name", "Alice")

# Integer equality
predicates.equals("age", 30)
```

### `between(bin_name, min_val, max_val)`

Match records where `min_val <= bin_name <= max_val`.

```python
predicates.between("age", 20, 30)
```

### `contains(bin_name, index_type, val)`

Match records where a list/map bin contains `val`.

```python
predicates.contains("tags", aerospike.INDEX_TYPE_LIST, "python")
predicates.contains("props", aerospike.INDEX_TYPE_MAPKEYS, "color")
```

### `geo_within_geojson_region(bin_name, geojson)`

Match records with geo points within a GeoJSON region.

```python
region = '{"type": "Polygon", "coordinates": [[[0,0],[0,1],[1,1],[1,0],[0,0]]]}'
predicates.geo_within_geojson_region("location", region)
```

### `geo_within_radius(bin_name, lat, lng, radius)`

Match records within a radius (meters) of a point.

```python
predicates.geo_within_radius("location", 37.7749, -122.4194, 1000.0)
```

### `geo_contains_geojson_point(bin_name, geojson)`

Match records with geo regions containing a GeoJSON point.

```python
point = '{"type": "Point", "coordinates": [0.5, 0.5]}'
predicates.geo_contains_geojson_point("region", point)
```

## Full Query Example

```python
import aerospike_py as aerospike
from aerospike_py import predicates

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()

# Insert test data
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
    })

# Create secondary index
client.index_integer_create("test", "users", "age", "users_age_idx")

# Query: find users aged 25-35
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records = query.results()

print(f"Found {len(records)} users aged 25-35")
for _, _, bins in records:
    print(f"  {bins['name']}: age {bins['age']}")

# Cleanup
client.index_remove("test", "users_age_idx")
client.close()
```
