---
title: Query 가이드
sidebar_label: Query
sidebar_position: 1
slug: /guides/query-scan
description: 보조 인덱스 Query에 predicate를 적용하는 방법
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

Query는 `where()` predicate를 하나만 받습니다. 같은 query에 `where()`를 한 번 더 호출하면 query를 실행할 때 `InvalidArgError`가 발생합니다. 결과를 더 좁히려면 나머지 조건을 filter expression(`policy={"filter_expression": ...}`, [Expression Filters](./expression-filters.md) 참고)으로 표현하세요.

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

`foreach()`는 record가 도착하는 대로 callback에 넘깁니다. Client에서 대기하는 record는 최대 `record_queue_size`개(`QueryPolicy` field, 기본값 1024)이므로 결과 크기가 커져도 memory가 늘지 않습니다. Callback이 `False`를 반환하거나 exception을 발생시키면 server의 scan도 멈춥니다. Scan이 실행되는 동안 record를 넘기기 때문에, query가 실패하면(timeout, node 장애) callback이 이미 일부 record를 처리한 뒤에 exception이 발생할 수 있습니다. Record를 모두 받거나 하나도 받지 않아야 한다면 `results()`를 사용하세요.

### 정리

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Async streaming

`AsyncClient`에서는 query를 세 가지 방법으로 읽을 수 있습니다: `await query.results()`, `await query.foreach(callback)`, `async for record in query`. 세 방법 모두 query의 record stream을 await하며 읽습니다.

```python
import aerospike_py
from aerospike_py import predicates

client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
await client.connect()

query = client.query("test", "users")
query.where(predicates.between("age", 25, 35))

async for record in query:
    await handle(record)
```

`query.stream(policy)`는 `async for`가 사용하는 것과 같은 `AsyncRecordStream`을 반환합니다. Policy를 넘길 때 호출하고, 블록을 벗어나는 즉시 query를 멈춰야 할 때는 `async with`와 함께 사용하세요.

```python
async with query.stream({"max_records": 1000}) as records:
    async for record in records:
        if record.bins["status"] == "wanted":
            break
```

- **첫 record를 요청하기 전에는 아무것도 보내지 않습니다.** `stream()`은 policy를 바로 검사하고, query는 첫 읽기에서 시작합니다.
- **Memory 사용량이 제한됩니다.** Client에서 대기하는 record는 최대 `record_queue_size`개(기본값 1024)와 넘겨주는 중인 묶음뿐이고, 대기하는 동안에는 server에서 읽지 않습니다. Consumer가 query의 `socket_timeout`(기본 30초)보다 오래 읽지 않으면 query를 잃습니다. Server는 읽지 않는 client를 포기합니다.

### 일찍 멈추기와 취소

다음 경우 client와 server 양쪽에서 query가 멈춥니다.

- Stream이 끝났을 때
- `close()`(또는 `await aclose()`)를 호출했을 때
- `async with` 블록을 벗어났을 때
- Stream이 garbage collection될 때. CPython에서는 다른 곳에서 stream을 참조하지 않는 상태로 `async for` loop를 `break`나 exception으로 벗어나는 순간입니다. 이 동작이 interpreter에 의존하면 안 되는 곳에서는 `async with`를 사용하세요.
- 다음 record를 기다리는 task, 또는 `results()`·`foreach()`를 await하는 task가 취소되었을 때

멈춤은 node가 다음에 client로 record를 넘길 때 적용됩니다. Record가 흐르고 있는 scan은 수 ms 안에 멈춥니다. 속도가 제한된 scan(`records_per_second`)은 server가 다음 묶음을 보낼 때까지, 최대 query의 `socket_timeout` 동안 connection을 유지합니다. Sync client도 `foreach()`를 일찍 빠져나오면 같은 방식으로 server의 scan을 멈춥니다.

### Async client의 `foreach()`

Callback은 일반 함수입니다. Event loop 밖의 worker thread에서 실행되므로, 다른 task를 멈추지 않고 block할 수 있습니다(파일 쓰기, sync client 호출 등). Callback은 await되지 않습니다. `async def` 함수를 넘기면 `TypeError`가 발생합니다. Record마다 무언가를 await하려면 `async for record in query`를 사용하세요.

`foreach()`를 await하는 task가 취소되면, 이미 실행 중인 callback은 끝까지 실행되고, 새 callback은 시작되지 않으며, 그다음에야 `CancelledError`가 발생합니다.

Sync client와 마찬가지로 `foreach()`는 scan이 실행되는 동안 record를 넘기므로, query가 실패하면 일부 record를 처리한 뒤에 exception이 발생할 수 있습니다. `results()`는 전부 아니면 전무입니다.

실행 중인 query는 `max_concurrent_operations` slot을 차지하지 않으므로, consumer가 record마다 다른 값을 조회할 수 있습니다. 동시에 실행하는 scan 수는 application에서 제한하세요.

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

Query는 `where()` predicate를 하나만 받으므로 예제마다 query를 새로 만듭니다.

```python
# polygon 안의 point
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query = client.query("test", "places")
query.where(predicates.geo_within_geojson_region("location", region))

# 반경 (m) 안의 point
query = client.query("test", "places")
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# point 를 포함하는 region
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query = client.query("test", "areas")
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

Secondary index 없이 server-side filtering을 사용하려면 [Expression Filters](./expression-filters.md)를 참고하세요.
