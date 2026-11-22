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

Set a predicate filter. Requires a secondary index on the bin. A query takes one predicate: a second `where()` raises `InvalidArgError` when the query runs.

### `results(policy=None) -> list[Record]`

Execute and return all matching records. All or nothing: a query that fails raises and returns no records.

### `foreach(callback, policy=None)`

Execute and invoke `callback(record)` for each result as it arrives. Return `False` to stop early; that stops the scan on the server too. At most `record_queue_size` records (default 1024) per query wait in the client, counting those taken out of the queue but not yet handed over; on top of that come the batch being handed to Python and one record for each node whose reader is waiting for room.

```python
def process(record: Record) -> None:
    print(record.bins)

query.foreach(process)
```

On `AsyncQuery`, the callback runs in a worker thread and must be a plain function (an `async def` function raises `TypeError`). Callbacks never overlap, but they do not all run on the same thread, so do not keep state in thread-locals. An exception the callback raises stops the query and is raised from `foreach()` unchanged, except `StopIteration`, which reaches the caller as `RuntimeError` with the `StopIteration` as its `__cause__`, as Python does when one leaves a coroutine. Cancelling the awaiting task stops the query; a running callback finishes first, also when `asyncio.run` cancels every task on Ctrl-C.

### `stream(policy=None) -> AsyncRecordStream` (async only)

Open the query as an async iterator of records. `async for record in query` does the same. Nothing is sent until the first record is asked for. The stream is also an async context manager and has `close()`, `aclose()` and `closed`; leaving it early stops the query on the server.

```python
async with query.stream({"max_records": 1000}) as records:
    async for record in records:
        await handle(record)
```

See [Async streaming](../guides/query-scan/query-scan.md#async-streaming) for when the query stops and how much memory it uses.

### `AsyncRecordStream`

Returned by `AsyncQuery.stream()`; `async for record in query` uses one.

| Member | Description |
|--------|-------------|
| `async for record in stream` | The records, one at a time, as they arrive. |
| `async with stream as records` | Closes the stream when the block is left. |
| `close()` | Stop the query and drop the records not yet handed out. Idempotent. |
| `await aclose()` | Same as `close()`; for `contextlib.aclosing` and similar helpers. |
| `closed` | Whether `close()` has been called. |

The query stops, on the client and on the server, when the stream ends, when `close()` is called, when the `async with` block is left, or when the stream is garbage collected. At most `record_queue_size` records (default 1024) per query wait in the client, plus the batch being handed to Python and one record for each node whose reader is waiting for room. Every record is handed out once, and several tasks may iterate the same stream: each record goes to one of them.

The delivery guarantee covers retries within one query over a stable record set. Concurrent modifications can change its results. A callback that writes externally must handle its own acknowledgements and retries.

Cancelling a task that waits for the next record closes the stream. A later read on that stream raises `RuntimeError` instead of ending the iteration, because the cancelled read may already have taken records. A stream closed with `close()` simply ends. To bound a wait, put the timeout around the whole loop, not around one `anext()`.

Closing the client does not stop a stream that is already running; close streams before the client.

### Leaving a query early

Every way of leaving a query before its end stops the scan on the server at once, on the sync and the async client: a `foreach()` callback returning `False` or raising, `break` out of `async for`, `close()`, cancellation, an error in the stream. Up to 0.14.x the server went on scanning until its socket timeout (30 seconds by default). A rate-limited scan (`records_per_second`) is sent in blocks that are far apart and stays listed on the server until its next block is due (45 seconds at 50 records per second in one measurement); `socket_timeout` does not shorten that.

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

Each example builds its own query: a query takes one `where()` predicate.

```python
# Points within a polygon
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query = client.query("test", "places")
query.where(predicates.geo_within_geojson_region("location", region))

# Points within radius
query = client.query("test", "places")
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# Regions containing a point
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query = client.query("test", "areas")
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
