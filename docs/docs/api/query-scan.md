---
title: Query API
sidebar_label: Query
sidebar_position: 5
description: Query and AsyncQuery class reference with predicates.
---

## Query / AsyncQuery

Created via `client.query(namespace, set_name)`. Use `where()` to set a predicate, `select()` to choose bins, then `results()` or `foreach()` to execute.

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()  # or: await query.results()
```

### `select(*bins)`

Select specific bins to return.

### `where(predicate)`

Set a predicate filter. Requires a secondary index on the bin.

### `results(policy=None) -> list[Record]`

Execute and return all matching records.

### `foreach(callback, policy=None)`

Execute and invoke `callback(record)` for each result. Return `False` to stop early.

```python
def process(record: Record) -> None:
    print(record.bins)

query.foreach(process)
```

---

## Predicates

```python
from aerospike_py import predicates
```

| Function | Description | Example |
|----------|-------------|---------|
| `equals(bin, val)` | Equality | `equals("name", "Alice")` |
| `between(bin, min, max)` | Inclusive range | `between("age", 20, 30)` |
| `contains(bin, idx_type, val)` | List/map contains | `contains("tags", INDEX_TYPE_LIST, "py")` |
| `geo_within_geojson_region(bin, geojson)` | Points in region | See below |
| `geo_within_radius(bin, lat, lng, radius)` | Points in circle (meters) | See below |
| `geo_contains_geojson_point(bin, geojson)` | Regions containing point | See below |

### Geospatial

```python
# Points within a polygon
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query.where(predicates.geo_within_geojson_region("location", region))

# Points within radius
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# Regions containing a point
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

---

## Full Example

```python
import aerospike_py as aerospike
from aerospike_py import predicates, Record

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# Insert data
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
    })

# Create index
client.index_integer_create("test", "users", "age", "users_age_idx")

# Query
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records: list[Record] = query.results()

for record in records:
    print(f"{record.bins['name']}: age {record.bins['age']}")

# Cleanup
client.index_remove("test", "users_age_idx")
client.close()
```
