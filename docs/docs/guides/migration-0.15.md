---
title: Upgrading to 0.15
sidebar_label: Upgrading to 0.15
sidebar_position: 4
slug: /guides/migration-0.15
description: What changes between aerospike-py 0.14.x and 0.15, with a before/after example for each change and what to do about it.
---

aerospike-py 0.15 moves the native core from Aerospike Rust client 2.2 to 3.0. Most code keeps working unchanged. This page lists every change that can break code written for 0.14.x, or change what it observes, with an example and what to do.

Every example on this page was run with 0.14.x and with 0.15 against a single-node Aerospike CE 8.2 server. The output shown is what each version printed; long messages are shortened with `...`. Unless an example says otherwise, `client` is a connected sync `Client` and `aerospike_py` is imported.

## Checklist

One line per breaking change. Follow the link for the details.

| If your code... | then read |
|---|---|
| runs against an Aerospike server older than 6.4 | [Minimum server version](#minimum-server-version) |
| reads `operate_ordered()` results by position, by bin name, or expects a list for a bin answered twice | [`operate_ordered()`](#operate_ordered-returns-one-entry-per-operation) |
| unpacks a `BatchRecord` into four names, or interprets `BatchRecord.result` codes | [Batch results](#batch-results) |
| catches a failed batch call and assumes nothing was written | [A batch call that fails as a whole](#a-batch-call-that-fails-as-a-whole-keeps-its-rows) |
| relies on `batch_operate`, `batch_remove`, `batch_apply`, `batch_write` or `batch_write_numpy` re-sending by themselves | [Write batches no longer retry](#write-batches-no-longer-retry-automatically) |
| passes `retry=N` to `batch_write` together with `policy["max_retries"]` | [The `retry` argument](#the-retry-argument-of-batch_write) |
| catches `ClientError` for a failing UDF, or `ClusterError` / `AerospikeTimeoutError` for an unknown namespace | [Exceptions](#exceptions) |
| passes policy values that are not one of the `POLICY_*` constants | [Policy values are checked](#policy-values-are-checked) |
| passes a `filter_expression` that is not built with `aerospike_py.exp` (a string, a dict, ...) | [A filter that is not an expression](#a-filter_expression-that-is-not-an-expression-is-refused) |
| reads records that old clients wrote with a language-specific blob (`PYTHON_BLOB`, `JAVA_BLOB`, ...), or catches `RustPanicError` to skip them | [Language-specific blobs](#records-with-a-language-specific-blob-are-readable) |
| uses `batch_write_numpy()` or `to_numpy()` | [NumPy batch reads and writes](#numpy-batch-reads-and-writes) |
| declares the `batch_write_numpy()` key field as a sub-array, such as `("_key", "i8", (1,))` | [The key field is one value](#the-key-field-is-one-value) |
| writes NumPy fields of shape `(1,)` | [One-element vectors](#one-element-vectors-are-stored-as-a-blob) (deployment order matters) |
| passes an `async def` callback to `AsyncQuery.foreach()`, keeps thread-local state in its callback, or cancels it | [Async queries](#async-queries) |
| sets `max_concurrent_operations` and calls `apply()` | [`apply()` and backpressure](#apply-counts-against-max_concurrent_operations) |
| restarts Aerospike containers under a long-lived client | [Node restarts](#node-restarts-with-a-new-node-id) |
| runs with a memory limit sized closely for 0.14.x | [Memory](#memory-under-concurrent-batch-load) |

A query with more than one `where()` predicate raises `InvalidArgError`, as 0.14.x already did; see [Queries](#queries-take-one-where-predicate).

## Minimum server version

0.15 is built on Aerospike Rust client 3.0 (0.14.x used 2.2). With Rust client 3.0 the minimum supported server is **6.4**.

**What to do:** upgrade any server older than 6.4 before you upgrade the client. The [FAQ](/docs/faq#what-aerospike-server-versions-are-supported) lists the server versions the integration tests run against.

## `operate_ordered()` returns one entry per operation

In 0.14.x `operate_ordered()` returned one entry per **bin**. A bin that two operations answered appeared once, with a list of both values, and the entries did not follow the order of the operations (their order changed from run to run). 0.15 returns what the official Python client returns: one `(bin, value)` entry per **operation** that answered, in request order. A bin answered twice appears twice.

```python
from aerospike_py import list_operations as lop
from aerospike_py import map_operations as mop

READ, INCR = aerospike_py.OPERATOR_READ, aerospike_py.OPERATOR_INCR
key = ("test", "demo", "ordered")


def ordered(initial, ops):
    client.put(key, initial, policy={"exists": aerospike_py.POLICY_EXISTS_REPLACE})
    return [tuple(b) for b in client.operate_ordered(key, ops).ordered_bins]


# The same bin read twice
print(ordered({"a": 1, "b": 2, "c": 3},
              [{"op": READ, "bin": "c"}, {"op": READ, "bin": "a"},
               {"op": READ, "bin": "c"}, {"op": READ, "bin": "b"}]))
# A write followed by a read of the same bin
print(ordered({"x": 2}, [{"op": INCR, "bin": "x", "val": 1}, {"op": READ, "bin": "x"}]))
print(ordered({"l": [1]}, [lop.list_append("l", 3), {"op": READ, "bin": "l"}]))
# The same, with a map operation in the request
print(ordered({"x": 2, "m": {"k": 1}},
              [{"op": INCR, "bin": "x", "val": 1}, {"op": READ, "bin": "x"}, mop.map_size("m")]))
```

```text
# 0.14.x
[('c', [3, 3]), ('a', 1), ('b', 2)]
[('x', 3)]
[('l', [2, [1, 3]])]
[('x', 3), ('m', 1)]

# 0.15
[('c', 3), ('a', 1), ('c', 3), ('b', 2)]
[('x', 3)]
[('l', 2), ('l', [1, 3])]
[('x', None), ('x', 3), ('m', 1)]
```

**When an operation without a value appears.** An increment, a write or a read of a missing bin returns no value. Whether it gets an entry depends on the whole request:

- If the request contains a **map, bit or HLL operation**, every operation that names a bin gets an entry, and one that returned no value appears as `(bin, None)`. An operation that names no bin, such as `touch`, never appears.
- Otherwise only the operations that returned a value appear. List operations do not change this.

| Request (initial record) | 0.15 `ordered_bins` |
|---|---|
| `increment(x, 1)`, `read(x)` (`x=2`) | `[("x", 3)]` |
| `write(x, 7)` | `[]` |
| `read(missing)`, `read(b)` (`b=2`) | `[("b", 2)]` |
| `list_get(l, 0)`, `list_get(l, 1)` (`l=[None, 5]`) | `[("l", 5)]` |
| `write(x, 7)`, `map_size(m)` (`m` has one entry) | `[("x", None), ("m", 1)]` |
| `read(missing)`, `map_size(m)` | `[("missing", None), ("m", 1)]` |
| `touch()`, `map_size(m)` | `[("m", 1)]` |
| `write(x, 7)`, `bit_count(b, 0, 8)` (`b=0x0f`) | `[("x", None), ("b", 4)]` |

The binding's results are compared with the official client's for these and more cases in `tests/compatibility/test_operate_ordered_contract.py`.

**Known differences from the official client.** These remain in 0.15:

- An operation that names no bin (`touch`, `delete`) never appears in the result. The official client emits `("", None)` for `delete` when the request also contains a map, bit or HLL operation.
- In a request that writes but contains no map, bit or HLL operation, a list read that finds a nil element is left out. The official client reports `("l", None)` for it.
- `MAP_RETURN_KEY_VALUE` results are a list of `(key, value)` tuples (`[("j", 2), ("k", 1)]`); the official client returns a flat list (`["j", 2, "k", 1]`). This applies to `operate()` as well.

**`operate()` is unchanged.** It still returns a dict with one key per bin, a list when several operations answered the same bin, and no `None` for a write:

```python
record = client.operate(key, [{"op": READ, "bin": "c"}, {"op": READ, "bin": "a"},
                              {"op": READ, "bin": "c"}, {"op": READ, "bin": "b"}])
print(record.bins)
```

```text
# 0.14.x
{'b': 2, 'c': [3, 3], 'a': 1}
# 0.15
{'c': [3, 3], 'a': 1, 'b': 2}
```

**What to do:**

- If you want one value per bin, call `operate()` instead.
- If you index `ordered_bins` by position, count the positions again with the rule above.
- If you expected a list for a bin answered twice, collect the entries yourself: `[b.value for b in result.ordered_bins if b.name == "c"]`.
- If your request contains a map, bit or HLL operation and you do not want the `(bin, None)` entries, drop them: `[b for b in result.ordered_bins if b.value is not None]`.

## Queries take one `where()` predicate

A query runs with one secondary-index predicate. Calling `where()` a second time on the same query raises `InvalidArgError` when the query runs (`results()`, `foreach()` or iteration). 0.14.x raised `InvalidArgError` at the same point, so working code is not affected; only the message changed:

```text
# 0.14.x
InvalidArgError: Invalid argument: Too many filter expressions
# 0.15
InvalidArgError: Invalid argument: a query takes at most one where() predicate, got 2
```

Rust client 3.0 would silently keep only the last predicate, so 0.15 checks this itself. To narrow a query further, keep one predicate and put the other conditions in a filter expression (`policy={"filter_expression": ...}`).

## Batch results

### What `BatchRecord.result` means

`BatchRecord.result` is now:

- `0` only when a server reported success for that record,
- the server's result code when a server reported a failure (`2` not found, `27` filtered out, ...),
- `-1` when no server answered for that record.

In 0.14.x a row without a result code counted as success (`0`), so a record that no node answered could look written. `BatchRecord` also has a new field, `error_type`, which names the failure and tells the `-1` cases apart.

```python
from aerospike_py import exp

client.put(("test", "demo", "kept"), {"v": 1})
client.put(("test", "demo", "dropped"), {"v": 2})
keys = [
    ("test", "demo", "kept"),
    ("test", "demo", "dropped"),           # excluded by the filter below
    ("test", "demo", "missing"),           # never written
    ("no_such_namespace", "demo", "k"),    # a namespace the cluster does not have
]
only_v1 = {"filter_expression": exp.eq(exp.int_bin("v"), exp.int_val(1))}
for br in client.batch_read(keys, policy=only_v1).batch_records:
    print(br.result, getattr(br, "error_type", "(no field)"), br.in_doubt)
```

```text
# 0.14.x
0 (no field) False
27 (no field) False
2 (no field) False
11 (no field) False

# 0.15
0 None False
27 FilteredOut False
2 KeyNotFoundError False
20 InvalidNamespace False
```

How to tell the outcomes of a row apart:

| Outcome | `result` | `error_type` | `in_doubt` |
|---|---|---|---|
| Success | `0` | `None` | `False` |
| Record not found | `2` | `"KeyNotFoundError"` | `False` |
| Excluded by `filter_expression` | `27` | `"FilteredOut"` | `False` |
| Other failure the server reported | its code | named after the code, for example `"KeyExistsError"`, `"GenerationError"`, `"DeviceOverload"` | `False` |
| Server reported a timeout | `9` | `"ServerTimeout"` | `True` for a write: the master may have applied it |
| Request sent, the client stopped waiting | `-1` | `"Timeout"` | `True` for a write |
| Transport failure | `-1` | `"Connection"`, `"InvalidNode"`, ... | `True` for a write that had been sent |
| No node answered for the record | `-1` | `"NoResponse"` | `False` when nothing was sent for it (the key could not be routed). `True` for a write when the call gave up without its rows after it may have sent them |

`in_doubt` means the record failed but the write may have been applied: the request was sent and the answer never came back. Read the record before you write it again.

A write the server refused with a code worth a retry, `KEY_BUSY` (14), `DEVICE_OVERLOAD` (18) or `PARTITION_UNAVAILABLE` (11), is an answer: the row carries that code with `in_doubt == False`, and the call returns normally, also for a batch of one key. This is the same as in 0.14.x. When a write batch is sent with `max_retries > 0`, three more outcomes are reported in doubt; see [Rows a second send may have answered](#rows-a-second-send-may-have-answered).

### A fifth field: `error_type`

`BatchRecord` is a named tuple with five fields now: `key`, `result`, `record`, `in_doubt`, `error_type`. Code that unpacks it into exactly four names breaks:

```python
br = client.batch_write([(("test", "demo", "kept"), {"v": 1})]).batch_records[0]
key, result, record, in_doubt = br
```

```text
# 0.14.x
(no error)
# 0.15
ValueError: too many values to unpack (expected 4)
```

**What to do:** use the attributes (`br.result`, `br.in_doubt`, `br.error_type`), or unpack five names.

### A batch call that fails as a whole keeps its rows

A batch call that fails as a whole still raises an exception, and the exception now carries the rows: `exc.partial_result` is a `BatchWriteResult` with one `BatchRecord` per requested record, in request order. Records that other nodes answered keep their results; the others say why they have none. This holds for every batch method: `batch_read`, `batch_write`, `batch_write_numpy`, `batch_operate`, `batch_remove` and `batch_apply`. For every other failure `partial_result` is `None`.

```python
keys = [("no_such_namespace", "demo", f"k{i}") for i in range(3)]
try:
    client.batch_write([(k, {"v": 1}) for k in keys])
except aerospike_py.AerospikeError as exc:
    print(type(exc).__name__)
    partial = getattr(exc, "partial_result", None)
    if partial is not None:
        for br in partial.batch_records:
            print(br.key.user_key, br.result, br.error_type, br.in_doubt)
```

```text
# 0.14.x
ClusterError

# 0.15
InvalidArgError
k0 -1 NoResponse False
k1 -1 NoResponse False
k2 -1 NoResponse False
```

The exception class for this case changed too, see [An unknown namespace](#an-unknown-namespace-raises-invalidargerror). When `batch_write(retry=N)` raises, `exc.partial_result.retry` holds the retry counters of the call.

**What to do:** where you catch a failed batch call, look at `exc.partial_result` before you decide what to send again. Rows with `result == 0` were written; rows with `in_doubt` may have been.

```python
try:
    client.batch_write(records)
except aerospike_py.AerospikeError as exc:
    if exc.partial_result is None:
        raise
    done = [br.key for br in exc.partial_result.batch_records if br.result == 0]
    unsure = [br.key for br in exc.partial_result.batch_records if br.in_doubt]
```

## Write batches no longer retry automatically

In 0.14.x every batch call started from a policy with `max_retries = 2`. When the answer to a batch was lost, the Rust client sent it again, up to twice, also for increments and UDF calls, and the server applied each copy. In 0.15 the default depends on what the batch does:

| Batch | Default `max_retries` |
|---|---|
| `batch_read`, and `batch_operate` whose operations all read | `2` (unchanged) |
| `batch_write`, `batch_write_numpy`, `batch_remove`, `batch_apply`, and `batch_operate` with a write | `0` |

An explicit `policy["max_retries"]` still wins.

The example uses a UDF that counts its own runs and takes longer than the socket timeout, so the client stops waiting while the server is still running it:

```lua
-- slow_count.lua
function run(rec, rounds)
    local total = 0
    for i = 1, rounds do
        total = total + (i % 7)
    end
    if rec['runs'] == nil then
        rec['runs'] = 1
    else
        rec['runs'] = rec['runs'] + 1
    end
    aerospike:update(rec)
    return rec['runs']
end
```

```python
import time

client.udf_put("slow_count.lua")
key = ("test", "demo", "counter")
client.put(key, {"v": 1})
policy = {"total_timeout": 0, "socket_timeout": 50}
try:
    client.batch_apply([key], "slow_count", "run", [10_000_000], policy=policy)
except aerospike_py.AerospikeError as exc:
    print(type(exc).__name__)
time.sleep(4)  # let the server finish every run it was sent
print("runs:", client.get(key).bins["runs"])
```

```text
# 0.14.x
ClientError
runs: 3

# 0.15
AerospikeTimeoutError
runs: 1
```

**What to do:** if a write batch must be re-sent by the client, ask for it: `policy={"max_retries": 2}`. With that policy the same example prints `runs: 3` on 0.15. Do this only when applying the batch twice gives the same result as applying it once: full-record `batch_write` without `CREATE_ONLY` or a generation check, `batch_remove`, reads. Do not do it for increments, appends, list or map changes that add elements, most UDFs, `CREATE_ONLY` writes (the second copy fails with "record exists" for a write that went through) or generation-checked writes. For `batch_write` and `batch_write_numpy`, prefer `retry=N`, described below.

### Rows a second send may have answered

With `max_retries > 0` on a write, the Rust client sends a node's share of a batch again when its answer is lost. If the first send was applied, the second one meets its own work: a re-sent delete finds no record, a re-sent filtered write no longer matches, a re-sent UDF fails on what the first run left behind. The Rust client does not say whether a row was sent twice, so a row of `batch_write`, `batch_operate` (with a write), `batch_remove` or `batch_apply` that ends in `KEY_NOT_FOUND` (2), `FILTERED_OUT` (27) or `UDF_BAD_RESPONSE` (100) is reported with `in_doubt == True`: the call does not know whether it changed the record. `remove()` that raises `RecordNotFound` under such a policy carries `in_doubt == True` too.

With the default policy (`max_retries` is `0` for every write) nothing changes, and reads (`batch_read`) are never in doubt. See [Error Handling](/docs/guides/error-handling#re-sent-writes-and-in_doubt) for an example.

### The `retry` argument of `batch_write`

`batch_write(records, retry=N)` and `batch_write_numpy(..., retry=N)` run the binding's own retry loop. In 0.15 it:

- makes up to `N + 1` attempts, with exponential backoff (full jitter, at most 500 ms between attempts);
- re-sends only the records that failed with a transient error: a timeout, device overload, key busy, a lost connection, a node that is down;
- never re-sends a record that already succeeded;
- never re-sends a `CREATE_ONLY` or generation-checked record whose earlier send may have been applied (`in_doubt`); the row keeps `in_doubt = True`;
- does not try again when the failure would repeat (an unknown namespace, an invalid argument);
- stops when `total_timeout` (default 1000 ms) runs out. To really get `N + 1` attempts, raise it, for example `policy={"total_timeout": 30000}`.

`result.retry` (a `BatchRetryInfo`) reports `attempts`, `max_attempts`, `truncated_by_timeout` and `unresolved`. When the call raises, the same counters are in `exc.partial_result.retry`.

`retry=N` and `policy["max_retries"]` are two loops, one inside the other: each of the `N + 1` attempts would be re-sent `max_retries` times underneath, whether its records had succeeded or not. Giving both now raises `InvalidArgError`. An explicit `max_retries` of `0` is accepted.

```python
records = [(("test", "demo", f"r{i}"), {"v": i}) for i in range(3)]
try:
    result = client.batch_write(records, policy={"max_retries": 1}, retry=2)
    print([br.result for br in result.batch_records])
except aerospike_py.InvalidArgError as exc:
    print(exc)
```

```text
# 0.14.x
[0, 0, 0]

# 0.15
retry=2 and policy['max_retries']=1 were both given; they would multiply into up to 6 sends per record. Use retry= alone: it re-sends only the records that failed.
```

**What to do:** remove `max_retries` from `batch_write` and `batch_write_numpy` calls that pass `retry=N`.

## Exceptions

### Every exception says what happened

Every `AerospikeError` carries four attributes. 0.14.x had only `result_code`.

| Attribute | Meaning |
|---|---|
| `result_code` | The server's result code when a server answered; `-1` when no server answered. |
| `error_type` | The kind of failure, by name. A server code is named after the code (`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, `"DeviceOverload"`, ...; `"ServerTimeout"` for a timeout the server reported). A failure on the client side is `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"` or `"Client"`. |
| `in_doubt` | `True` when a write was sent and no definite answer came back, so the server may have applied it. `False` when the server answered with a failure (record exists, a failed UDF, ...), and always for reads. A write sent with `max_retries > 0` is the exception, see [Rows a second send may have answered](#rows-a-second-send-may-have-answered). |
| `partial_result` | The rows of a batch call that failed as a whole, `None` otherwise. See [above](#a-batch-call-that-fails-as-a-whole-keeps-its-rows). |

`result_code == -1` covers several failures; `error_type` tells them apart. The exception class and `error_type` changed for two failures:

```python
def describe(call):
    try:
        call()
    except aerospike_py.AerospikeError as exc:
        print(type(exc).__name__, exc.result_code, getattr(exc, "error_type", "(no attribute)"))


describe(lambda: client.get(("test", "demo", "never_written")))
describe(lambda: client.apply(key, "no_such_module", "no_such_function", []))
describe(lambda: client.get(("no_such_namespace", "demo", "k")))
```

```text
# 0.14.x
RecordNotFound 2 (no attribute)
ClientError -1 (no attribute)
AerospikeTimeoutError -1 (no attribute)

# 0.15
RecordNotFound 2 KeyNotFoundError
UDFError 100 UdfBadResponse
InvalidArgError -1 InvalidArgument
```

### A failing UDF raises `UDFError`

A UDF the server could not run raised a plain `ClientError` with `result_code == -1` in 0.14.x, and was logged as a possible bug in aerospike-py. In 0.15 it raises `UDFError` (a `ServerError`) with `result_code == 100` (`AEROSPIKE_ERR_UDF`), the code a failed `batch_apply` row has always reported.

A UDF failure is an answer from the server, not a lost answer: the server could not find the function, or ran it, rolled the record back and said so. `exc.in_doubt` is therefore `False`, for `apply()` and for a `batch_apply` row alike (unless the batch was sent with `max_retries > 0`, see [Rows a second send may have answered](#rows-a-second-send-may-have-answered)). A UDF call the client stopped waiting for is a timeout, and that one is in doubt.

**What to do:** catch `aerospike_py.UDFError` (or `ServerError`) around `apply()`. An `except ClientError` no longer catches a UDF failure.

### An unknown namespace raises `InvalidArgError`

A key whose namespace the cluster does not have raised `AerospikeTimeoutError` for a single-record command and `ClusterError` for a batch call in 0.14.x. Both now raise `InvalidArgError` (`result_code == -1`, `error_type == "InvalidArgument"`). When the batch call does return because other keys could be sent, the row for such a key carries `result == 20` and `error_type == "InvalidNamespace"` (0.14.x: `11`).

**What to do:** if you caught `ClusterError` or `AerospikeTimeoutError` to handle a mistyped or missing namespace, catch `InvalidArgError`.

### Metrics use the same names

The Prometheus `error_type` label of `db_client_operation_duration_seconds` and the OpenTelemetry `error.type` attribute come from the same classification as `exc.error_type`, so a dashboard and an `except` clause name a failure the same way:

```text
db_client_operation_duration_seconds_count{...,db_operation_name="get",error_type="KeyNotFoundError"} 1
```

### Messages changed

Many exception messages read differently, for example `AEROSPIKE_ERR (2): Key not found [node=...]` where 0.14.x said `AEROSPIKE_ERR (2): Server error: KeyNotFoundError, In Doubt: false, Node: ...`. Do not match on message text; use the exception class, `result_code` and `error_type`.

## Policy values are checked

An `exists`, `gen`, `commit_level`, `replica`, `read_mode_ap` or `expected_duration` value that is not one of the `POLICY_*` / `QUERY_DURATION_*` constants now raises `InvalidArgError` before anything is sent. In 0.14.x an unknown value fell back to the default: `exists=9` became a plain update and `gen=9` turned the generation check off.

```python
try:
    client.put(key, {"v": 2}, policy={"exists": 9})
    print("written:", client.get(key).bins)
except aerospike_py.InvalidArgError as exc:
    print(exc)
```

```text
# 0.14.x
written: {'v': 2}

# 0.15
invalid exists value: 9 (valid: POLICY_EXISTS_IGNORE=0, POLICY_EXISTS_UPDATE_ONLY=1, POLICY_EXISTS_REPLACE=2, POLICY_EXISTS_REPLACE_ONLY=3, POLICY_EXISTS_CREATE_ONLY=4)
```

**What to do:** use the constants, for example `aerospike_py.POLICY_EXISTS_CREATE_ONLY`.

### A `filter_expression` that is not an expression is refused

A `filter_expression` that is not an expression built with `aerospike_py.exp` (a string, a number, a list, a dict) now raises `InvalidArgError` before anything is sent: `filter_expression must be an expression built with aerospike_py.exp, got str`. Up to 0.14.x such a value was dropped without a word and the call ran **unfiltered**: `client.put(key, bins, policy={"filter_expression": "v == 1"})` wrote the record unconditionally. `None` still means "no filter".

**What to do:** build the filter with `aerospike_py.exp`, for example `exp.eq(exp.int_bin("v"), exp.int_val(1))`. A call that raises here ran without its filter on 0.14.x; check what it wrote or returned.

### Other values refused before anything is sent

- `max_retries = 2**64 - 1` raises `InvalidArgError` (`max_retries is too large: ...`). Rust client 3.0 would make no attempt at all with that value, so the call would fail with "Timeout after 0 tries" without being sent.
- An integer that does not fit its field (`retry=-1`, `total_timeout=-1`, `ttl=2**70`) raises `OverflowError`. It is not logged as a possible bug in aerospike-py.
- A `batch_write()` record without bins, `(key, {})`, raises `InvalidArgError` (`record 1 has no bins: ...`) and nothing is written. On 0.14.x the call raised `ClientError` ("Batch write operations do not contain a write") and logged it as a possible bug in aerospike-py. A bin set to `None` is still a write, it removes the bin. `batch_write_numpy()` refuses a dtype without bin fields with `ValueError` for the same reason.

`batch_write(retry=2**32 - 1)` reports `retry.max_attempts == 2**32 - 1`: the count saturates instead of wrapping to `0`.

## Records with a language-specific blob are readable

Old clients stored a value that has no Aerospike type with their own language's serializer, under a particle type of its own: `JAVA_BLOB` (7), `CSHARP_BLOB` (8), `PYTHON_BLOB` (9, a pickle), `RUBY_BLOB` (10), `PHP_BLOB` (11), `ERLANG_BLOB` (12). Clusters that have been running long enough still hold such records. With 0.14.x, any read of a record with such a bin raised `RustPanicError`, so the whole record was unreadable. In 0.15 the bin is returned as `bytes` holding the raw payload, the other bins are read normally, and the first such value of each type is logged as a warning (later ones at debug level, so a scan over old data does not flood the log). `get()`, `batch_read()` and scans all behave this way (issue #280).

```python
import logging
import pickle

logging.basicConfig(level=logging.WARNING)
key = ("test", "demo", "legacy")  # written by an old client: plain=7, legacy=PYTHON_BLOB
try:
    record = client.get(key)
    print(record.bins["plain"], type(record.bins["legacy"]).__name__)
    print(pickle.loads(record.bins["legacy"]))  # only for data you trust
except aerospike_py.RustPanicError as exc:
    print(f"{type(exc).__name__}: {exc}")
```

```text
# 0.14.x (after an error log that calls it a possible bug in aerospike-py)
RustPanicError: Rust panic in `Client.get`: internal error: entered unreachable code

# 0.15
WARNING:_aerospike::types::value:bin value has particle type 9, which this client does not interpret; returning its 26 raw bytes (further values of this type are logged at debug level)
7 bytes
{'answer': 42}
```

Writing the bytes back with `put()` stores an ordinary blob; reading that bin afterwards logs no warning.

**What to do:** code that caught `RustPanicError` to skip such records now receives them. If you need the value, decode the bytes yourself. For `PYTHON_BLOB` that is `pickle.loads(...)`, and only for data you trust: unpickling can run code.

## NumPy batch reads and writes

The rules below hold for the sync and the async client alike.

### `batch_write_numpy()` reads the layout from the array

The signature is now `batch_write_numpy(data, namespace, set_name, _dtype=None, key_field="_key", policy=None, retry=0)`. The layout comes from `data.dtype`. In 0.14.x `_dtype` was required, and the array's bytes were read through it even when it did not match the array. In 0.15 a `_dtype` that differs from `data.dtype` raises `ValueError` before the first row is sent.

```python
import numpy as np

dtype = np.dtype([("_key", "i8"), ("score", "f8"), ("count", "i4")])
data = np.array([(101, 0.5, 1), (102, 1.5, 2)], dtype=dtype)
wrong = np.dtype([("_key", "i8"), ("score", "f4"), ("count", "i4")])  # f4, not f8
try:
    result = client.batch_write_numpy(data, "test", "demo", wrong)
    print([(br.key.user_key, br.result) for br in result.batch_records])
except ValueError as exc:
    print(exc)
```

```text
# 0.14.x (the second row was written under a key made of misread bytes)
[(101, 0), (438086664193, 0)]

# 0.15
_dtype does not match the array: data.dtype is [('_key', '<i8'), ('score', '<f8'), ('count', '<i4')], _dtype is [('_key', '<i8'), ('score', '<f4'), ('count', '<i4')]. Omit _dtype to use data.dtype, or convert the array first with data.astype(_dtype).
```

The rows are read from `numpy.asarray(data)`: an array subclass such as `numpy.recarray` is written as the plain array it is, and the mask of a masked array is ignored.

**What to do:** nothing, if the dtype you pass is `data.dtype`. Otherwise drop the argument, or convert the array with `data.astype(...)` first.

### dtypes are checked in both directions

`batch_write_numpy()` and `to_numpy()` check the dtype with the same rules before anything is written or filled. `to_numpy(dtype)` accepts whatever `numpy.dtype(...)` accepts and lays the rows out by the dtype NumPy makes of it. They reject:

- an array or dtype without named fields (`TypeError`);
- NumPy's variable-length `StringDType` (`TypeError`);
- `U` and `O` fields, and an object member nested inside a structured field (`TypeError`);
- a field in non-native byte order (`ValueError`, as in 0.14.x);
- unsupported element widths.

In 0.14.x an object member nested in a structured field was written to the server as the raw bytes of the object pointers:

```text
# 0.14.x: stored bins after batch_write_numpy with ("s", [("x", "i4"), ("o", "O")])
{'s': b'\x00\x00\x00\x00H\xf7\xf8\x02\x01\x00\x00\x00'}
# 0.15
TypeError: dtype field 's' holds Python objects ([('x', '<i4'), ('o', 'O')]): an object member nested inside a structured ...
```

### The key field is one value

The key field of `batch_write_numpy()` (`_key`, or the field named by `key_field`) must be one value: a scalar integer or a fixed-width bytes field. A sub-array, including a one-element `("_key", "i8", (1,))`, or a nested structured field raises `TypeError` before anything is written: `the key field '_key' must be a scalar integer or bytes field, not a sub-array or a nested structure; ...`. 0.14.x accepted `("_key", "i8", (1,))` and wrote the integer key.

**What to do:** declare the key as `("_key", "i8")`. Sub-array **bin** fields are not affected: they are vectors, stored as blobs (see [One-element vectors](#one-element-vectors-are-stored-as-a-blob)).

### Vector length and float range

A numeric sub-array field is a vector. On read it takes a blob of exactly the field's size in bytes; any other length is an error. A scalar fills only a one-element field. A finite value too large for an `f2` or `f4` field raises `OverflowError`; NaN and infinities are kept. In 0.14.x a shorter blob was padded with zeros, a longer one was cut off, a scalar filled the first element of a longer vector, and an overflowing value became `inf`, all without an error. Fixed-width bytes fields (`S<N>`) keep their padding and truncation rules.

```python
client.put(("test", "demo", 121), {"short": b"\x00" * 8, "scalar": 1.5, "big": 70000.0})
handle = client.batch_read([("test", "demo", 121)])
for field in [("short", "f8", (4,)), ("scalar", "f8", (4,)), ("big", "f2")]:
    try:
        print(handle.to_numpy(np.dtype([field])).batch_records.tolist())
    except (ValueError, OverflowError) as exc:
        print(f"{type(exc).__name__}: {exc}")
```

```text
# 0.14.x
[(array([0., 0., 0., 0.]),)]
[(array([1.5, 0. , 0. , 0. ]),)]
[(inf,)]

# 0.15
ValueError: vector length mismatch for field 'short': the stored blob has 8 bytes, the dtype expects 32 (4 elements of 8 bytes)
ValueError: vector length mismatch for field 'scalar': the stored value is a scalar, the dtype expects 4 elements
OverflowError: float overflow: value 70000 does not fit in f16 for field 'big'
```

**What to do:** make the read dtype match what is stored. If a bin really holds values of different lengths, read it without `to_numpy()`.

### One-element vectors are stored as a blob

:::danger[Fields of shape `(1,)`: upgrade readers first; once writers switch, there is no way back to 0.14.x]

0.15 writes a sub-array field of shape `(1,)` (for example `("score", "f4", (1,))`) as a **blob** of the field's size, like every other vector. 0.14.x wrote it as a **scalar**. The type stored on the server changes.

- 0.15 reads both: a scalar written by 0.14.x loads into a `(1,)` field as a vector of length 1.
- 0.14.x cannot read the blob: `to_numpy()` raises `TypeError` for the whole batch.

So, for every bin written through a `(1,)` field:

1. Upgrade **every reader** of the bin to 0.15 first.
2. Then upgrade the **writers**.
3. Once a 0.15 writer has written such a bin, you **cannot roll back to 0.14.x**: a 0.14.x reader rejects the blob.

If you cannot upgrade all readers first, declare the field as a scalar in the writer (`("score", "f4")` instead of `("score", "f4", (1,))`). 0.15 stores that as a scalar, and both versions read it into a `(1,)` field.

:::

```python
dtype = np.dtype([("_key", "i8"), ("score", "f4", (1,))])
client.batch_write_numpy(np.array([(401, [1.5])], dtype=dtype), "test", "demo", dtype)
print(client.get(("test", "demo", 401)).bins)
```

```text
# written by 0.14.x
{'score': 1.5}
# written by 0.15
{'score': b'\x00\x00\xc0?'}
```

```python
rows = client.batch_read([("test", "demo", 401)]).to_numpy(np.dtype([("score", "f4", (1,))]))
print(rows.batch_records.tolist())
```

```text
# 0.14.x reading the record 0.15 wrote
TypeError: cannot write bytes to numeric field 'score'
# 0.15 reading either record
[(array([1.5], dtype=float32),)]
```

### Rows and keys of `NumpyBatchRecords`

Row `i` of the result is request `i`, hit or miss, as before. Only real user keys go into the key index used by `get()` and `in`. In 0.14.x a row requested by digest only was indexed under an invented key (`"__no_user_key_<i>__"` in the native conversion, the row number `i` in the pure-Python one, which could hide a real integer key equal to that number). Such a row is now reachable by position only. A user key requested twice points at its last row, as before.

```python
client.put(("test", "demo", 0), {"v": 1000})
client.put(("test", "demo", 611), {"v": 1611})
digest = client.batch_read([("test", "demo", 611)]).batch_records[0].key[3]
result = client.batch_read([("test", "demo", None, digest), ("test", "demo", 0)]).to_numpy(
    np.dtype([("v", "i8")])
)
print(result.batch_records["v"].tolist(), "__no_user_key_0__" in result, result.get(0)["v"])
```

```text
# 0.14.x
[1611, 1000] True 1000
# 0.15
[1611, 1000] False 1000
```

### Length of the `batch_read()` handle

`len(handle)` on the `LazyBatchRecords` that `batch_read()` returns is now the number of distinct keys in its mapping, so it always equals `len(handle.to_dict())`. In 0.14.x it counted successful rows with a user key, which was too high when a key was requested twice or from two sets. `found_count()` counts successful rows, and `to_list()` has one slot per request, as before.

```python
client.put(("test", "demo", "a"), {"v": 1})
client.put(("test", "demo", "b"), {"v": 2})
handle = client.batch_read([("test", "demo", "a"), ("test", "demo", "a"), ("test", "demo", "b")])
print(len(handle), len(handle.to_dict()), handle.found_count(), len(handle.to_list()))
```

```text
# 0.14.x
3 2 3 3
# 0.15
2 2 3 3
```

`to_dict()` returns a shallow copy: the outer dict is new, but the bins dicts inside it are shared with the handle. Copy a bins dict before you change it, or use `to_list()`, which builds new dicts on every call.

**What to do:** use `found_count()` for "how many records came back" and `len(handle)` for "how many keys the mapping has".

## Async queries

### Cancelling a query stops it

`AsyncQuery.results()` and `AsyncQuery.foreach()` used to run the query in a worker thread. Cancelling the task raised `CancelledError` at once while the thread went on reading records and calling the callback to the end of the scan. In 0.15 both read the query's record stream by awaiting it, so cancelling the task stops the query on the client and on the server.

`foreach()` still calls its callback from a worker thread, so the callback may block. Callbacks never overlap, but they do not all run on the same thread: the event loop's default executor picks one for each batch of records, so do not keep state in thread-locals. An exception the callback raises stops the query and is raised from `foreach()` unchanged, `StopIteration` included. When the task is cancelled, a callback that is running finishes, no new one starts, and only then is `CancelledError` raised. That holds when every task is cancelled at once too, as `asyncio.run` does on Ctrl-C.

```python
async def cancel_after_100(client):
    calls = 0

    def callback(record):
        nonlocal calls
        calls += 1
        time.sleep(0.001)

    task = asyncio.ensure_future(client.query("test", "demo").foreach(callback))
    while calls < 100:
        await asyncio.sleep(0.001)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    at_cancel = calls
    await asyncio.sleep(0.5)
    print(f"callbacks when CancelledError was raised: {at_cancel}, half a second later: {calls}")
```

```text
# 0.14.x
callbacks when CancelledError was raised: 100, half a second later: 468
# 0.15
callbacks when CancelledError was raised: 100, half a second later: 100
```

(`client` is an `AsyncClient` here; the set holds 5,000 records.)

### `async for` and `query.stream()`

An `AsyncQuery` can now be iterated: `async for record in query`. `query.stream(policy)` returns the same thing, an `AsyncRecordStream`, which is also an async context manager and has `close()`. Nothing is sent before the first record is asked for. At most `record_queue_size` records (default 1024) wait in the client, whatever the pace of the consumer, and a consumer may pause for longer than `socket_timeout`: the client fetches the rest again when reading resumes, without repeating a record. Several tasks may iterate the same stream; each record goes to one of them. See the [Query guide](/docs/guides/query-scan#async-streaming).

Two points to know when you move code to streams:

- Cancelling a task that waits for the next record closes the stream, and a later read on it raises `RuntimeError` instead of ending the iteration, because the cancelled read may already have taken records. `asyncio.wait_for(anext(stream), t)` cancels the read when it times out; to bound a wait, put the timeout around the whole loop.
- Closing the client does not stop a stream that is already running: it reads on to its end with the connections it holds, and a stream that has not been read from yet fails on its first read. Close streams before the client.

```python
async for record in client.query("test", "demo"):
    ...
```

```text
# 0.14.x
TypeError: 'async for' requires an object with __aiter__ method, got AsyncQuery
# 0.15
(iterates)
```

### `foreach()` refuses a coroutine function

`AsyncQuery.foreach()` calls its callback from a worker thread and cannot await it. In 0.14.x an `async def` callback created one coroutine per record that nobody awaited (and, since a coroutine is not `False`, never stopped the scan). 0.15 raises `TypeError`:

```python
async def handle(record):
    return False

await client.query("test", "demo").foreach(handle)
```

```text
# 0.14.x (returned after the whole scan, one warning per record)
RuntimeWarning: coroutine 'main.<locals>.handle' was never awaited
# 0.15
TypeError: foreach() calls its callback from a worker thread and cannot await it; to await something for each record, use 'async for record in query'
```

**What to do:** to await something per record, use `async for record in query`.

### Leaving a scan early stops it on the server

This applies to the sync client too. In 0.14.x, when you stopped reading a query early, the client dropped it, but the server went on with the scan and held its connection until the socket timeout (30 s by default). In 0.15 every way out closes the query on the server: a `foreach()` callback returning `False` or raising, `break` out of `async for`, `close()`, leaving `async with`, cancellation, an error in the stream, and garbage collection of the stream.

Measured on the server's own job list (`query-show`), 100,000 records:

| Stop | 0.14.x: scan still running for | 0.15 |
|---|---|---|
| sync `foreach()` callback returns `False` | 30.3 s | gone at once |
| `break` out of `async for` | (not available) | 0.1 s |

One case is different: a rate-limited scan (`records_per_second`) is sent in blocks that are far apart, and it stays listed on the server until its next block is due. Measured at 50 records per second: 45 seconds, the same with a `socket_timeout` of 2000, 30000 (the default) or 0. `socket_timeout` does not bound it.

## `apply()` counts against `max_concurrent_operations`

With `max_concurrent_operations` set, `batch_apply()` took one of the slots, but the single-record `apply()` did not, so UDF calls passed the limit. In 0.15 `apply()` waits for a slot like every other record command and raises `BackpressureError` when `operation_queue_timeout_ms` runs out.

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "max_concurrent_operations": 1,
    "operation_queue_timeout_ms": 100,
}
client = aerospike_py.AsyncClient(config)
await client.connect()
keys = [("test", "demo", "udf_0"), ("test", "demo", "udf_1")]
for key in keys:
    await client.put(key, {"v": 1})

# Two UDF calls of a few hundred milliseconds each, one slot.
outcomes = await asyncio.gather(
    *(client.apply(key, "slow_count", "run", [30_000_000]) for key in keys),
    return_exceptions=True,
)
for outcome in outcomes:
    print(type(outcome).__name__)
```

```text
# 0.14.x
int
int
# 0.15
int
BackpressureError
```

The limit counts single-record commands (including `apply()`) and batch commands (including `batch_apply()`). It does not count query or scan streams, info, truncate, UDF registration, index or admin commands. A stream takes no slot on purpose: it stays open for as long as its consumer reads, and a consumer that looks something up for each record would otherwise wait for a slot its own stream holds.

**What to do:** if you set `max_concurrent_operations`, size it with UDF calls included, and handle `BackpressureError` around `apply()`.

## Node restarts with a new node id

After a node restarts **with a new node id on the same address**, for example when its container is restarted, a long-lived client needs about one cluster tend interval (about 1 second by default) before it routes to that node again. During that time a command can raise `ClusterError`. With 0.14.x this took a few milliseconds. Rust client 3.0 drops a node whose name no longer matches and learns the new one on the next tend. A node that keeps its id across the restart is served at once, as before.

**What to do:** if you restart nodes in place (rolling container restarts, tests that restart the server), give fixed node ids to the nodes, or retry `ClusterError` for about a second after a restart.

## Memory under concurrent batch load

A client process uses more memory under concurrent batch load with 0.15. Process memory (RSS) for the same workload on both versions:

| Workload | 0.14.4 | 0.15 |
|---|---|---|
| `batch_read` of 720 existing records × 8 bins, 8 calls in flight, with a CPU-bound competitor thread | peak 67–68 MiB | peak 78–84 MiB |
| The same batch, 32 calls in flight, 192,000 batches (about three minutes) | moves between 134 and 190 MiB (peak 192 MiB) | settles at 243–246 MiB and stays flat for the last 96,000 batches (peak 253 MiB) |
| One `batch_read` of 50,000 keys | 2.2 KiB peak memory per key | 2.7 KiB per key (about +20%) |

Neither version keeps growing: this is buffer memory the client keeps, not a leak. At 32 calls in flight the difference is about 55–60 MiB, and 0.15 does not hand that memory back while the load continues. It comes from Rust client 3.0: a batch row takes about 20% more memory, every connection keeps a 64 KiB read buffer (4 KiB before), and the client keeps a bounded pool of large buffers for reuse instead of freeing them after each command (up to 4 MiB per size class; unused buffers are released about a minute after they stop being used).

**What to do:** if a memory limit was sized closely for 0.14.x, leave headroom. The extra memory grows with the number of batch calls in flight: about 10–15 MiB at 8, about 55–60 MiB at 32 in this measurement. These buffer settings cannot be configured from Python in 0.15.

For context: throughput and latency were equal or better in every scenario measured for this release (an HTTP load test of six scenarios: requests per second +0.1% to +12%, p50 latency −0.7% to −11%; a NumPy microbenchmark: `to_numpy` −10%, read −0.3%, write −2.7% time). Measure your own workload; these numbers are not a guarantee.

## Logging

aerospike-py logs an error with "This error may be a bug in aerospike-py" and a command for filing an issue when it meets an error it does not expect. 0.14.x also did this for ordinary failures: an argument the library refuses (`TypeError`, `ValueError`), an exception raised by your own `foreach` callback, a failing UDF, a node going down, a client timeout. 0.15 raises these to the caller without that log line. Anything else that is not an `AerospikeError` is still logged.

```python
import logging

logging.basicConfig(level=logging.WARNING)
try:
    client.get(("test", "demo", None))  # None is not a key the server can store
except ValueError as exc:
    print("raised:", exc)
```

```text
# 0.14.x
ERROR:aerospike_py:Unexpected internal error in aerospike-py (Client.get): ValueError: Invalid key: ...
This error may be a bug in aerospike-py. Please report it by running:
gh issue create ...
raised: Invalid key: Invalid argument: Data type is not supported as Key value.

# 0.15
raised: Invalid key: Error 4: Invalid argument: Data type is not supported as Key value.
```

## Other changes

- The client `timeout` and `idle_timeout` keep their 30-second defaults. Rust client 3.0 lowered its own defaults; aerospike-py sets the old values explicitly.
- A map bin is read back with its keys in the order the server returns them, the same on every read (on server 8.2: sorted by key, integers before strings). 0.14.x returned the keys of the same map in a different order on each read. Code that compares dicts is not affected; code that relied on iteration order was already unreliable.
- `meta.ttl` is computed in whole seconds, as the official Python client does. A record read right after it was written with `ttl=1000` reports `1000`; 0.14.x reported `999` nearly every time (398 of 400 reads in a measurement, and 0.15 reported `1000` in 398 of 400). When the client's clock is behind the server's, even by milliseconds, the value can be one second more than was set. Do not assert `meta.ttl <= ttl` exactly; allow a second.
