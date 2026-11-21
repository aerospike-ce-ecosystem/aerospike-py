---
title: Query API 레퍼런스
sidebar_label: Query
sidebar_position: 5
description: predicate를 사용하는 Query 및 AsyncQuery 클래스 레퍼런스
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

predicate filter 설정. bin 에 secondary index 가 필요. Query는 predicate를 하나만 받습니다. `where()`를 두 번 호출하면 query를 실행할 때 `InvalidArgError`가 발생합니다.

### `results(policy=None) -> list[Record]`

실행하고 매칭되는 모든 record 반환. 전부 아니면 전무: 실패한 query는 exception을 발생시키고 record를 반환하지 않습니다.

### `foreach(callback, policy=None)`

실행하고 결과가 도착하는 대로 `callback(record)` 호출. 조기 종료 위해 `False` 반환. 이때 server의 scan도 멈춥니다. Client에서 대기하는 record는 query마다 최대 `record_queue_size`개(기본값 1024)이며, queue에서 꺼냈지만 아직 넘겨주지 않은 record도 함께 셉니다. 여기에 Python으로 넘겨주는 중인 묶음과, 자리가 나기를 기다리는 reader가 있는 node마다 record 하나가 더해집니다.

```python
def process(record: Record) -> None:
    print(record.bins)

query.foreach(process)
```

`AsyncQuery`에서는 callback이 worker thread에서 실행되며 일반 함수여야 합니다(`async def` 함수는 `TypeError`). Callback은 서로 겹쳐 실행되지 않지만 모두 같은 thread에서 실행되지는 않으므로, thread-local에 상태를 두지 마세요. Callback이 발생시킨 exception은 query를 멈추고 `foreach()`에서 그대로 다시 발생합니다. 단, `StopIteration`은 coroutine을 빠져나갈 때 Python이 하듯 `StopIteration`을 `__cause__`로 가진 `RuntimeError`로 전달됩니다. Await하는 task를 취소하면 query가 멈추고, 실행 중인 callback은 먼저 끝납니다. Ctrl-C에서 `asyncio.run`이 모든 task를 취소할 때도 같습니다.

### `stream(policy=None) -> AsyncRecordStream` (async 전용)

Query를 record의 async iterator로 엽니다. `async for record in query`도 같습니다. 첫 record를 요청하기 전에는 아무것도 보내지 않습니다. Stream은 async context manager이기도 하고 `close()`, `aclose()`, `closed`를 갖습니다. 일찍 빠져나오면 server의 query도 멈춥니다.

```python
async with query.stream({"max_records": 1000}) as records:
    async for record in records:
        await handle(record)
```

Query가 멈추는 시점과 memory 사용량은 [Async streaming](../guides/query-scan/query-scan.md#async-streaming)을 참고하세요.

### `AsyncRecordStream`

`AsyncQuery.stream()`이 반환하며, `async for record in query`도 이것을 사용합니다.

| Member | 설명 |
|--------|------|
| `async for record in stream` | Record가 도착하는 대로 하나씩 받습니다. |
| `async with stream as records` | 블록을 벗어나면 stream을 닫습니다. |
| `close()` | Query를 멈추고 아직 넘겨주지 않은 record를 버립니다. 여러 번 호출해도 됩니다. |
| `await aclose()` | `close()`와 같습니다. `contextlib.aclosing` 같은 helper용입니다. |
| `closed` | `close()`가 호출되었는지 여부. |

Stream이 끝났을 때, `close()`를 호출했을 때, `async with` 블록을 벗어났을 때, stream이 garbage collection될 때 client와 server 양쪽에서 query가 멈춥니다. Client에서 대기하는 record는 query마다 최대 `record_queue_size`개(기본값 1024)이고, 여기에 Python으로 넘겨주는 중인 묶음과 자리가 나기를 기다리는 reader가 있는 node마다 record 하나가 더해집니다. 모든 record는 한 번씩만 넘겨주며, 여러 task가 같은 stream을 순회해도 됩니다. 각 record는 그중 한 task에만 전달됩니다.

다음 record를 기다리는 task를 취소하면 stream이 닫힙니다. 취소된 읽기가 이미 record를 가져갔을 수 있으므로, 그 뒤 같은 stream을 읽으면 순회가 끝나는 대신 `RuntimeError`가 발생합니다. `close()`로 닫은 stream은 그냥 끝납니다. 기다리는 시간을 제한하려면 `anext()` 하나가 아니라 loop 전체에 timeout을 거세요.

Client를 닫아도 이미 실행 중인 stream은 멈추지 않습니다. Stream을 client보다 먼저 닫으세요.

### Query를 일찍 끝낼 때

Query를 끝까지 읽지 않고 빠져나오는 모든 방법은 sync·async client 모두에서 server의 scan을 즉시 멈춥니다: `foreach()` callback이 `False`를 반환하거나 exception을 발생시킴, `async for`에서 `break`, `close()`, 취소, stream 오류. 0.14.x까지는 server가 socket timeout(기본 30초)까지 scan을 계속했습니다. 속도가 제한된 scan(`records_per_second`)은 server가 묶음을 멀리 떨어진 간격으로 보내며, 다음 묶음을 보낼 때가 될 때까지 server의 목록에 남아 있습니다(한 측정에서 초당 50 record일 때 45초). `socket_timeout`으로는 이 시간을 줄일 수 없습니다.

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

Query는 `where()` predicate를 하나만 받으므로 예제마다 query를 새로 만듭니다.

```python
# polygon 안의 point
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query = client.query("test", "places")
query.where(predicates.geo_within_geojson_region("location", region))

# 반경 안의 point
query = client.query("test", "places")
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# point 를 포함하는 region
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query = client.query("test", "areas")
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
