---
title: Query
sidebar_label: Query
sidebar_position: 2
description: Query 클래스 API 레퍼런스
---

## Query

`Query`는 Secondary Index 쿼리를 수행하여 특정 기준에 맞는 레코드를 찾습니다.

### Creating a Query

```python
query = client.query("test", "demo")
```

### `select(*bins)`

반환할 특정 빈을 선택합니다.

```python
query.select("name", "age")
```

### `where(predicate)`

필터 조건을 추가합니다. 해당 빈에 Secondary Index가 필요합니다.

```python
from aerospike_py import predicates

query.where(predicates.equals("name", "Alice"))
query.where(predicates.between("age", 20, 30))
```

### `results(policy=None)`

쿼리를 실행하고 일치하는 모든 레코드를 반환합니다.

```python
records = query.results()
for key, meta, bins in records:
    print(bins)
```

### `foreach(callback, policy=None)`

쿼리를 실행하고 각 레코드에 대해 `callback`을 호출합니다.

```python
def process(record):
    key, meta, bins = record
    print(bins)

query.foreach(process)
```

콜백에서 `False`를 반환하면 반복을 중지합니다:

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

`aerospike.predicates` 모듈은 쿼리를 위한 필터 함수를 제공합니다.

### `equals(bin_name, val)`

`bin_name == val`인 레코드를 매칭합니다.

```python
from aerospike_py import predicates

# 문자열 동등 비교
predicates.equals("name", "Alice")

# 정수 동등 비교
predicates.equals("age", 30)
```

### `between(bin_name, min_val, max_val)`

`min_val <= bin_name <= max_val`인 레코드를 매칭합니다.

```python
predicates.between("age", 20, 30)
```

### `contains(bin_name, index_type, val)`

리스트/맵 빈에 `val`이 포함된 레코드를 매칭합니다.

```python
predicates.contains("tags", aerospike.INDEX_TYPE_LIST, "python")
predicates.contains("props", aerospike.INDEX_TYPE_MAPKEYS, "color")
```

### `geo_within_geojson_region(bin_name, geojson)`

GeoJSON 영역 내에 지리 좌표가 포함된 레코드를 매칭합니다.

```python
region = '{"type": "Polygon", "coordinates": [[[0,0],[0,1],[1,1],[1,0],[0,0]]]}'
predicates.geo_within_geojson_region("location", region)
```

### `geo_within_radius(bin_name, lat, lng, radius)`

특정 좌표로부터 반경(미터) 내의 레코드를 매칭합니다.

```python
predicates.geo_within_radius("location", 37.7749, -122.4194, 1000.0)
```

### `geo_contains_geojson_point(bin_name, geojson)`

GeoJSON 포인트를 포함하는 지리 영역이 있는 레코드를 매칭합니다.

```python
point = '{"type": "Point", "coordinates": [0.5, 0.5]}'
predicates.geo_contains_geojson_point("region", point)
```

## Complete Query Example

```python
import aerospike_py as aerospike
from aerospike_py import predicates

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()

# 테스트 데이터 삽입
for i in range(100):
    client.put(("test", "users", f"user_{i}"), {
        "name": f"User {i}",
        "age": 20 + (i % 40),
    })

# Secondary Index 생성
client.index_integer_create("test", "users", "age", "users_age_idx")

# 쿼리: 25-35세 사용자 찾기
query = client.query("test", "users")
query.select("name", "age")
query.where(predicates.between("age", 25, 35))
records = query.results()

print(f"Found {len(records)} users aged 25-35")
for _, _, bins in records:
    print(f"  {bins['name']}: age {bins['age']}")

# 정리
client.index_remove("test", "users_age_idx")
client.close()
```
