---
title: Query Guide
sidebar_label: Query
sidebar_position: 1
slug: /guides/query-scan
description: Secondary index queries with predicates.
---

## Secondary Index Query

Query하려는 bin에는 secondary index가 있어야 합니다.

### Index 생성 + 데이터 insert

```python
import aerospike_py as aerospike

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# index 생성
client.index_integer_create("test", "users", "age", "users_age_idx")
client.index_string_create("test", "users", "city", "users_city_idx")

# 데이터 insert
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
        "city": ["Seoul", "Tokyo", "NYC"][i % 3],
    })
```

### Predicate 로 query

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

### Callback 순회

```python
def process(record: Record) -> None:
    print(f"{record.bins['name']}: age {record.bins['age']}")

query = client.query("test", "users")
query.where(predicates.between("age", 25, 35))
query.foreach(process)
```

Callback에서 `False`를 반환하면 순회를 일찍 끝낼 수 있습니다.

```python
count = 0

def limited(record: Record):
    global count
    count += 1
    if count >= 5:
        return False  # 순회 중단

query.foreach(limited)
```

### 정리

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Predicate Reference

| Function | 설명 |
|----------|-------------|
| `equals(bin, val)` | equality 매칭 |
| `between(bin, min, max)` | 범위 (inclusive) |
| `contains(bin, idx_type, val)` | list/map contains |
| `geo_within_geojson_region(bin, geojson)` | 영역 안의 point |
| `geo_within_radius(bin, lat, lng, radius)` | circle 안의 point (m 단위) |
| `geo_contains_geojson_point(bin, geojson)` | point 를 포함하는 region |

### Geospatial

```python
# polygon 안의 point
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query.where(predicates.geo_within_geojson_region("location", region))

# 반경 (m) 안의 point
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# point 를 포함하는 region
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

Secondary index 없이 server-side filtering을 사용하려면 [Expression Filters](./expression-filters.md)를 참고하세요.
