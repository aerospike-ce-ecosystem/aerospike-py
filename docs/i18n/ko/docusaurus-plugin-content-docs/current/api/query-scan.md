---
title: Query API
sidebar_label: Query
sidebar_position: 5
description: Query and AsyncQuery class reference with predicates.
---

## Query / AsyncQuery

`client.query(namespace, set_name)` 로 생성. `where()` 로 predicate, `select()` 로 bin 선택 후 `results()` 또는 `foreach()` 로 실행.

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()  # 또는: await query.results()
```

### `select(*bins)`

반환할 특정 bin 선택.

### `where(predicate)`

predicate filter 설정. bin 에 secondary index 가 필요.

### `results(policy=None) -> list[Record]`

실행하고 매칭되는 모든 record 반환.

### `foreach(callback, policy=None)`

실행하고 각 결과에 대해 `callback(record)` 호출. 조기 종료 위해 `False` 반환.

```python
def process(record: Record) -> None:
    print(record.bins)

query.foreach(process)
```

---

## Predicate

```python
from aerospike_py import predicates
```

| Function | 설명 | Example |
|----------|-------------|---------|
| `equals(bin, val)` | equality | `equals("name", "Alice")` |
| `between(bin, min, max)` | 범위 (inclusive) | `between("age", 20, 30)` |
| `contains(bin, idx_type, val)` | list/map contains | `contains("tags", INDEX_TYPE_LIST, "py")` |
| `geo_within_geojson_region(bin, geojson)` | 영역 안의 point | 아래 참조 |
| `geo_within_radius(bin, lat, lng, radius)` | circle 안의 point (m) | 아래 참조 |
| `geo_contains_geojson_point(bin, geojson)` | point 를 포함하는 region | 아래 참조 |

### Geospatial

```python
# polygon 안의 point
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query.where(predicates.geo_within_geojson_region("location", region))

# 반경 안의 point
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# point 를 포함하는 region
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

---

## 전체 예제

```python
import aerospike_py as aerospike
from aerospike_py import predicates, Record

client = aerospike.client({"hosts": [("127.0.0.1", 3000)]}).connect()

# 데이터 insert
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
    })

# index 생성
client.index_integer_create("test", "users", "age", "users_age_idx")

# Query
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records: list[Record] = query.results()

for record in records:
    print(f"{record.bins['name']}: age {record.bins['age']}")

# 정리
client.index_remove("test", "users_age_idx")
client.close()
```
