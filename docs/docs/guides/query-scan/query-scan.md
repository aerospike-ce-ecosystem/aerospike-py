---
title: Query & Scan Guide
sidebar_label: Query & Scan
sidebar_position: 1
slug: /guides/query-scan
description: Learn how to create secondary index queries, full namespace scans, and use predicates.
---

## Secondary Index Queries

Queries require a secondary index on the bin being queried.

### Step 1: Create a Secondary Index

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()

# Integer index
client.index_integer_create("test", "users", "age", "users_age_idx")

# String index
client.index_string_create("test", "users", "city", "users_city_idx")

# Geospatial index
client.index_geo2dsphere_create("test", "locations", "coords", "geo_idx")
```

### Step 2: Insert Data

```python
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
        "city": ["Seoul", "Tokyo", "NYC"][i % 3],
    })
```

### Step 3: Query with Predicates

```python
from aerospike_py import predicates

# Equality query
query = client.query("test", "users")
query.where(predicates.equals("city", "Seoul"))
records = query.results()

# Range query
query = client.query("test", "users")
query.where(predicates.between("age", 25, 35))
records = query.results()
```

### Select Specific Bins

```python
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records = query.results()
```

### Iterate with Callback

```python
query = client.query("test", "users")
query.where(predicates.between("age", 25, 35))

def process(record):
    key, meta, bins = record
    print(f"{bins['name']}: age {bins['age']}")

query.foreach(process)
```

### Stop Early

```python
count = 0

def limited(record):
    global count
    count += 1
    _, _, bins = record
    print(bins)
    if count >= 5:
        return False  # stop iteration

query.foreach(limited)
```

### Cleanup Indexes

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Full Namespace Scan

Scans read all records in a namespace/set without requiring a secondary index.

### Basic Scan

```python
scan = client.scan("test", "users")
records = scan.results()

for key, meta, bins in records:
    print(bins)
```

### Scan with Selected Bins

```python
scan = client.scan("test", "users")
scan.select("name")
records = scan.results()
```

### Scan with Callback

```python
scan = client.scan("test", "users")

total_age = 0
count = 0

def accumulate(record):
    global total_age, count
    _, _, bins = record
    total_age += bins.get("age", 0)
    count += 1

scan.foreach(accumulate)
print(f"Average age: {total_age / count:.1f}")
```

## Async Scan

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

    records = await client.scan("test", "users")
    for _, _, bins in records:
        print(bins)

    await client.close()

asyncio.run(main())
```

## Predicate Reference

| Function | Description | Example |
|----------|-------------|---------|
| `equals(bin, val)` | Equality | `equals("name", "Alice")` |
| `between(bin, min, max)` | Range (inclusive) | `between("age", 20, 30)` |
| `contains(bin, idx_type, val)` | List/map contains | `contains("tags", INDEX_TYPE_LIST, "py")` |
| `geo_within_geojson_region(bin, geojson)` | Points in region | See below |
| `geo_within_radius(bin, lat, lng, radius)` | Points in circle | See below |
| `geo_contains_geojson_point(bin, geojson)` | Regions containing point | See below |

### Geospatial Examples

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
