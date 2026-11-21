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

A query takes one `where()` predicate. A second `where()` on the same query raises `InvalidArgError` when the query runs. To narrow the result further, put the other conditions in a filter expression (`policy={"filter_expression": ...}`, see [Expression Filters](./expression-filters.md)).

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

`foreach()` hands records to the callback as they arrive. At most `record_queue_size` records (a `QueryPolicy` field, default 1024) wait in the client, so memory does not grow with the result set. Returning `False`, or raising from the callback, stops the scan on the server as well. Because records are delivered while the scan runs, a query that fails (a timeout, a node going away) can raise after the callback has already processed part of the records. Use `results()` when you need all records or none.

### Cleanup

```python
client.index_remove("test", "users_age_idx")
client.index_remove("test", "users_city_idx")
```

## Async streaming

With `AsyncClient` a query can be read in three ways: `await query.results()`, `await query.foreach(callback)` and `async for record in query`. All three read the query's record stream by awaiting it.

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

`query.stream(policy)` returns the same `AsyncRecordStream` that `async for` uses. Call it to pass a policy, and use it with `async with` when the query must stop as soon as the block is left:

```python
async with query.stream({"max_records": 1000}) as records:
    async for record in records:
        if record.bins["status"] == "wanted":
            break
```

- **Nothing is sent before the first record is asked for.** `stream()` checks the policy right away; the query starts with the first read.
- **Memory stays bounded.** At most `record_queue_size` records (default 1024) wait in the client, plus the batch being handed out, and the server is not read from while they wait. A consumer that stops reading for longer than the query's `socket_timeout` (30 seconds by default) loses the query: the server gives up on a client that does not read.

### Stopping early and cancelling

The query stops, on the client and on the server, when:

- the stream ends;
- `close()` (or `await aclose()`) is called;
- the `async with` block is left;
- the stream is garbage collected. In CPython that is the moment an `async for` loop is left with `break` or by an exception while nothing else refers to the stream. Use `async with` where this must not depend on the interpreter;
- the task that waits for the next record, or that awaits `results()` or `foreach()`, is cancelled.

Stopping takes effect when a node next hands records to the client. A scan whose records are flowing stops within milliseconds. A rate-limited scan (`records_per_second`) keeps its connection until the server sends its next block, at most the query's `socket_timeout`. The sync client stops the scan on the server the same way when `foreach()` is left early.

### `foreach()` on the async client

The callback is a plain function. It runs in a worker thread, off the event loop, so it may block (write to a file, call a sync client) without stalling other tasks. It cannot be awaited: passing an `async def` function raises `TypeError`. To await something for each record, use `async for record in query`.

When the task that awaits `foreach()` is cancelled, a callback that is already running finishes, no further callback starts, and only then is `CancelledError` raised.

As with the sync client, `foreach()` hands records over while the scan runs, so a failing query can raise after part of the records were processed. `results()` is all or nothing.

A running query does not take one of the `max_concurrent_operations` slots, so a consumer can look things up for each record. Bound the number of scans that run at once in your application.

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

Each example builds its own query: a query takes one `where()` predicate.

```python
# Points within a polygon
region = '{"type":"Polygon","coordinates":[[[126.9,37.5],[126.9,37.6],[127.0,37.6],[127.0,37.5],[126.9,37.5]]]}'
query = client.query("test", "places")
query.where(predicates.geo_within_geojson_region("location", region))

# Points within radius (meters)
query = client.query("test", "places")
query.where(predicates.geo_within_radius("location", 37.5665, 126.978, 5000.0))

# Regions containing a point
point = '{"type":"Point","coordinates":[126.978, 37.5665]}'
query = client.query("test", "areas")
query.where(predicates.geo_contains_geojson_point("coverage", point))
```

See [Expression Filters](./expression-filters.md) for server-side filtering without secondary indexes.
