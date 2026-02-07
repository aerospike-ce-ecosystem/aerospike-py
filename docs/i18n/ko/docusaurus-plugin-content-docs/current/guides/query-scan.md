# Query & Scan Guide

## Secondary Index Query

쿼리를 수행하려면 조회 대상 bin에 Secondary Index가 필요합니다.

### Step 1: Create Secondary Index

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()

# 정수 인덱스
client.index_integer_create("test", "users", "age", "users_age_idx")

# 문자열 인덱스
client.index_string_create("test", "users", "city", "users_city_idx")

# 지리공간 인덱스
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

### Step 3: Query with Predicate

```python
from aerospike_py import predicates

# 동등 쿼리
query = client.query("test", "users")
query.where(predicates.equals("city", "Seoul"))
records = query.results()

# 범위 쿼리
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

### Early Termination

```python
count = 0

def limited(record):
    global count
    count += 1
    _, _, bins = record
    print(bins)
    if count >= 5:
        return False  # 반복 중단

query.foreach(limited)
```

### Cleanup Indexes

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Full Namespace Scan

스캔은 Secondary Index 없이 namespace/set의 모든 record를 읽습니다.

### 기본 스캔

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

| 함수 | 설명 | 예시 |
|------|------|------|
| `equals(bin, val)` | 동등 조건 | `equals("name", "Alice")` |
| `between(bin, min, max)` | 범위 조건 (양 끝 포함) | `between("age", 20, 30)` |
| `contains(bin, idx_type, val)` | list/map 포함 여부 | `contains("tags", INDEX_TYPE_LIST, "py")` |
| `geo_within_geojson_region(bin, geojson)` | 영역 내 포인트 | 아래 참조 |
| `geo_within_radius(bin, lat, lng, radius)` | 원형 범위 내 포인트 | 아래 참조 |
| `geo_contains_geojson_point(bin, geojson)` | 포인트를 포함하는 영역 | 아래 참조 |

### 지리공간 예시

```python
# 다각형 내의 포인트
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query.where(predicates.geo_within_geojson_region("location", region))

# 반경 내의 포인트 (미터 단위)
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# 포인트를 포함하는 영역
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query.where(predicates.geo_contains_geojson_point("coverage", point))
```
