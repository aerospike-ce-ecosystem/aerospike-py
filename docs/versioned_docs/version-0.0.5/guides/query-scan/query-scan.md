---
title: Query Guide
sidebar_label: Query
sidebar_position: 1
slug: /guides/query-scan
description: Secondary index queries with predicates.
---

## Secondary Index Queries

Queries require a secondary index on the bin being queried.

### Create Index and Insert Data

```python
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# Create indexes
client.index_integer_create("test", "users", "age", "users_age_idx")
client.index_string_create("test", "users", "city", "users_city_idx")

# Insert data
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
        "city": ["Seoul", "Tokyo", "NYC"][i % 3],
    })
```

### Query with Predicates

```python
from aerospike_py import predicates, Record

# Equality
query = client.query("test", "users")
query.where(predicates.equals("city", "Seoul"))
records: list[Record] = query.results()

# Range
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records = query.results()
```

### Callback Iteration

```python
def process(record: Record) -> None:
    print(f"{record.bins['name']}: age {record.bins['age']}")

query = client.query("test", "users")
query.where(predicates.between("age", 25, 35))
query.foreach(process)
```

Return `False` from the callback to stop early:

```python
count = 0

def limited(record: Record):
    global count
    count += 1
    if count >= 5:
        return False  # stop iteration

query.foreach(limited)
```

### Cleanup

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Predicate Reference

| Function | Description |
|----------|-------------|
| `equals(bin, val)` | Equality match |
| `between(bin, min, max)` | Range (inclusive) |
| `contains(bin, idx_type, val)` | List/map contains |
| `geo_within_geojson_region(bin, geojson)` | Points in region |
| `geo_within_radius(bin, lat, lng, radius)` | Points in circle (meters) |
| `geo_contains_geojson_point(bin, geojson)` | Regions containing point |

### Geospatial

```python
# Points within a polygon
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query.where(predicates.geo_within_geojson_region("location", region))

# Points within radius (meters)
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# Regions containing a point
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

See [Expression Filters](./expression-filters.md) for server-side filtering without secondary indexes.
