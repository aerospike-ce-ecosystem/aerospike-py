---
title: Compatibility by version
slug: /guides/version-compatibility
toc_max_heading_level: 2
description: API and storage changes to check when upgrading aerospike-py.
---

## 0.14.x → 0.15 {#v0-15}

The 0.15 release candidate requires **Aerospike Server 6.4 or later**. Of the existing sync and async client methods, only `batch_write_numpy()` changes its parameters. Omit the fourth argument, `_dtype`, to use `data.dtype`. Passing a different dtype raises `ValueError` before the write.

### NumPy vector rollout {#one-element-vectors-are-stored-as-a-blob}

**Upgrade all readers of fields with shape `(1,)` before upgrading writers.** Version 0.14.x writes a scalar and 0.15 writes a blob. Version 0.15 reads both formats. Reading the new blob with `to_numpy()` on 0.14.x raises `TypeError`.

### Results and error handling {#checklist}

| API | What to check in 0.15 |
|---|---|
| `BatchRecord` | The named tuple gains a fifth field, `error_type`. If you unpack four variables, switch to named fields such as `row.result` and `row.in_doubt`. |
| Batch writes | The default `max_retries` drops from 2 to 0. If the exception carries `partial_result`, inspect each row’s result and `in_doubt` before retrying. |
| `batch_read()` | `len(handle)` counts distinct keys in the result mapping. Use `handle.found_count()` to count successful rows, including duplicate requests. |
| Filter policy | An invalid `filter_expression` raises `InvalidArgError`. Build filters with `aerospike_py.exp`. |
| `AsyncQuery.foreach()` | Passing an `async def` callback raises `TypeError`. Use `async for` to await work on each record. |
| Exceptions | Catch `UDFError` for a failing UDF in `apply()` and `InvalidArgError` for an unknown namespace. |

### Order and duplicates in `operate_ordered()` {#operate_ordered-returns-one-entry-per-operation}

Version 0.14.x grouped responses by bin. Version 0.15 returns one entry per operation that answered, in request order. Reading `x` twice when its value is 3 yields `[("x", 3), ("x", 3)]`. For example, when a request includes a write to `x` and a map operation, the value-less write appears as `("x", None)`.

### Memory under concurrent batch load {#memory-under-concurrent-batch-load}

With eight concurrent 720-key batch reads, peak RSS rose from **66–70 MiB** on 0.14.4 to **75–77 MiB** on 0.15. If your service has a memory limit, check peak RSS at its usual batch size and concurrency. [0.15 benchmarks](../performance/overview.mdx)

## 0.13.0 → 0.14.0 {#v0-14}

- Executing a `list_sort` operation with an unknown flag now raises `ValueError`. Use `LIST_SORT_DEFAULT` (0) for the default sort or `LIST_SORT_DROP_DUPLICATES` (2) to remove duplicates.
- Exceptions expose the server code through `result_code`. For example, calling `remove()` on a missing record raises `RecordNotFound` with `result_code == 2`. [0.14.0 release notes](https://github.com/aerospike-ce-ecosystem/aerospike-py/releases/tag/v0.14.0)
