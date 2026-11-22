---
title: Async query stream profile
sidebar_label: Async query streams
sidebar_position: 3
slug: /performance/async-stream-profile
description: How aerospike-py and the official SDK deliver query records to Python, and how free threading changes elapsed time.
---

import useBaseUrl from '@docusaurus/useBaseUrl';

One `async for` consumer read the same 12,000 records with **48 native Future completions** in the aerospike-py 0.15 candidate at `4aabf09` and **12,001** in the official `aerospike-sdk` 1.0.0 with `aerospike-native` 1.0.0. Both clients use Aerospike Rust core 3.0.0. Their Python bindings choose how many records to return on each wake-up.

| Wall time to consume 12,000 records | aerospike-py 0.15 | Official SDK | SDK time / aerospike-py time |
|---|---:|---:|---:|
| CPython 3.14.2 | 33.75 ms | 336.53 ms | 9.97× |
| Free-threaded CPython 3.14.2t, GIL off | 41.80 ms | 196.64 ms | 4.70× |

These are medians of three runs with uvloop 0.23.0 on an Apple M4 Pro and a single CE 8.2.0.1 node in a local Podman VM. Each run read an integer and a 160-byte string from every record and checked the values, duplicates and missing rows. Timing began after connection and warm-up. An independent run of 15 scans per condition with profilers disabled gave ratios of **10.61×** and **5.06×**. The [client comparison](./client-comparison.md) covers synchronous queries, list collection and batch operations as separate workloads.

## From the server to the Python loop

- **aerospike-py** uses core's `query_foreach` callback to put Rust records in a bounded queue. When the Python iterator exhausts its local list, `next_batch(256)` waits for the first record and takes up to 255 more that are already available. Rust converts the keys, metadata and bins to Python objects and completes one Future with the list. Each subsequent `__anext__` can wrap a local row as a `Record` and return it immediately. [Rust queue and refill](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/query_stream.rs#L596-L634) · [List conversion](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/query_stream.rs#L879-L893) · [Python iterator](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/src/aerospike_py/_async_client.py#L131-L175)
- **The official SDK** uses core's `query` and a buffered `Recordset`. Each native `__anext__` creates a Python Future and schedules a Tokio task to take **one record**. The event loop completes the Future, the SDK wraps the record in `RecordResult`, and the first access to `row.record.bins` constructs and caches a Python dict. With one sequential consumer, the next row is requested after the previous one arrives. The Future count measures completions inside the client process. Both core query entry points use the same underlying query executor. [Core query entry points](https://github.com/aerospike/aerospike-client-rust/blob/2ed9456106daa8431860aa5afa0068d074508da6/aerospike-core/src/client.rs#L1608-L1695) · [Native iterator](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/filter.rs#L873-L917) · [SDK adapter](https://github.com/aerospike/aerospike-client-python-sdk/blob/bd159b32edbc0d7502a726842890b43659b7b72b/aerospike_sdk/record_stream.py#L195-L217) · [Bins getter](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/record.rs#L74-L87)

## Changing only the refill size

The same aerospike-py wheel read the same data with four limits on records per refill. Timings are five-run medians. Separate instrumented runs counted Future waits, including the final end-of-stream read.

| Maximum records per refill | Future waits | CPython 3.14.2 | CPython 3.14.2t |
|---:|---:|---:|---:|
| 1 | 12,001 | 446.51 ms | 563.25 ms |
| 16 | 751 | 62.63 ms | 76.83 ms |
| 64 | 189 | 41.52 ms | 48.68 ms |
| 256 (default) | 48 | 31.99 ms | 37.69 ms |

At the default limit the consumer received 46 full lists, one list of 224 records, then the end-of-stream signal. With a slower producer, a refill can return as little as one record. At a limit of one, the same aerospike-py binary took longer than the official SDK on both builds. Bypassing just the SDK's Python `RecordResult` adapter while reading all bins from the same native recordset reduced its regular-build time from 336.44 to 320.21 ms. The largest measured difference came from how often execution crossed the async boundary.

## Why the gap narrows on the free-threaded build

On Unix with uvloop, the official native client defaults to `loop.call_soon_threadsafe()` on the regular wheel and to a socket pair on the free-threaded wheel. In the socket path, the waker thread writes a byte and an event-loop reader drains the completion queue. The choice follows the wheel's build flags, so turning the GIL back on in a free-threaded wheel still selects the socket pair by default. [Transport selection](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/completion.rs#L196-L229) · [Waker thread](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/waker.rs#L118-L179)

We forced each transport using `AEROSPIKE_PIPE_WAKE=0` and `=1`, and checked the GIL state after importing the extension. Each cell is the median elapsed time across five fresh processes.

| Official SDK runtime | `call_soon_threadsafe` | Socket pair |
|---|---:|---:|
| Regular wheel, GIL on | 336.31 ms | 202.89 ms |
| Free-threaded wheel, GIL on | 343.09 ms | 199.28 ms |
| Free-threaded wheel, GIL off | 336.61 ms | 199.56 ms |

Changing only the wake-up transport on the regular wheel saved **133 ms**. Holding the socket transport fixed on the free-threaded wheel put both GIL states at about **199 ms**. In the independent profiling run the SDK used similar total client CPU on the two builds (247.84 and 242.30 ms per scan), even as elapsed time fell. The result applies to this Unix/uvloop workload.

The denominator of the ratio also changed. A separate timing probe split each aerospike-py scan around its 48 refill calls. Over seven runs, mean time inside the refills rose from **25.07 to 28.61 ms** on the free-threaded build. Mean time outside refills rose from **8.46 to 15.59 ms**, including Python iteration, record wrapping, validation and object release. The probe timed these operations together.

### Per-record logging in a diagnostic build

The profiled revision forwards a Rust `trace!` call into Python logging on each record conversion, even with the Python root logger at `WARNING`. In a separate diagnostic build, bypassing that single call reduced the median Rust-to-Python conversion time for 12,000 rows from **9.52 to 1.80 ms** on regular CPython and **10.36 to 2.06 ms** on free-threaded CPython. The release-wheel comparisons above include the original logging path. [Record conversion](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/types/record.rs#L41-L71) · [Logging bridge](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/logging.rs#L75-L104)

<a href={useBaseUrl('/benchmark/4aabf09/async-stream-profile.zip')}>Download the measurements, profiling scripts and reproduction instructions (ZIP)</a>.
