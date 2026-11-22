---
title: Python client benchmarks
sidebar_label: Client comparison
sidebar_position: 2
slug: /performance/client-comparison
description: Compare server batches, NumPy, scans, and independent point operations in aerospike-py 0.14.4, PR 500, and the official Python SDK.
---

import useBaseUrl from '@docusaurus/useBaseUrl';

With four callers, PR #500 delivered the highest throughput for **NumPy batch reads and writes** in all three trials on both Python builds. The official SDK led on **free-threaded batch writes from Python dictionaries** and on **32 independent async point operations**. The tables compare release wheels from PR commit `4aabf09`, the previous `aerospike-py 0.14.4` release, and the official `aerospike-sdk 1.0.0` with `aerospike-native 1.0.0`. [Measured commit](https://github.com/aerospike-ce-ecosystem/aerospike-py/commit/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c) · [Previous release](https://pypi.org/project/aerospike-py/0.14.4/) · [SDK release](https://github.com/aerospike/aerospike-client-python-sdk/releases/tag/v1.0.0)

## Server batches with 720 keys

Four synchronous threads shared a client. Each thread repeatedly accessed its own 720 existing integer keys, with eight integer bins per key. Every read consumed all eight values. Writes used different values for each key, checked every row's status, and read back the records after timing. Throughput is in **thousands of rows per second**.

| Python build | Input or output | 0.14.4 | PR #500 | Official SDK |
|---|---|---:|---:|---:|
| Standard | Read to dictionaries | 258.1 | 271.8 | 228.1 |
| Standard | Write from dictionaries | 190.4 | 204.7 | 176.8 |
| Standard | Read to a NumPy array | 249.4 | 283.6 | 211.2 |
| Standard | Write from a NumPy array | 188.3 | 222.0 | 187.2 |
| Free-threaded | Read to dictionaries | 252.0 | 260.3 | 250.2 |
| Free-threaded | Write from dictionaries | 167.3 | 163.4 | 195.5 |
| Free-threaded | Read to a NumPy array | 253.1 | 300.7 | 256.3 |
| Free-threaded | Write from a NumPy array | 192.3 | 214.7 | 183.9 |

Both aerospike-py versions used `batch_read().to_list()`, `to_numpy(dtype)`, `batch_write()`, and `batch_write_numpy()`. The SDK used `session.query(*keys).execute()` with `collect()` for reads and `session.upsert(dataset).bins(...).rows(...).execute()` for writes. Dictionary writes include building each client's request from prepared keys and per-row dictionaries. NumPy measurements include building the SDK output array with `numpy.fromiter()` or converting the input array with `tolist()`.

- On free-threaded NumPy reads, PR #500 used **2.26 µs of client CPU per row**, versus 2.43 µs for 0.14.4 and 4.97 µs for the SDK. The SDK had the shortest p99 per batch at **22.6 ms**, followed by the PR at 26.8 ms and 0.14.4 at 29.6 ms.
- Prebuilding the API-specific write inputs brought standard-build throughput to 189.8k / 204.9k / 190.7k rows/s for 0.14.4 / PR / SDK. On the free-threaded build the same sequence was 162.0k / 163.8k / 194.1k rows/s.
- With one caller, standard Python dictionary reads reached 104.2k / 103.8k / 98.5k rows/s for 0.14.4 / PR / SDK. The PR's four-thread gain over 0.14.4 shrank to a difference of less than 1% with one caller.

## Full-set queries

One consumer read 12,000 records, checked the integer ID and 160-byte string in each, and verified that every expected ID appeared exactly once. Times are **milliseconds to consume the entire set**. List collection uses `query.results()` on aerospike-py and `collect()` on the SDK query result. The iterator rows use `async for` directly.

| Python build | How records were consumed | 0.14.4 | PR #500 | Official SDK |
|---|---|---:|---:|---:|
| Standard | Sync list collection | 43.16 | 34.71 | 25.04 |
| Standard | Async list collection | 47.70 | 29.23 | 339.97 |
| Standard | Async iterator | — | 33.75 | 336.53 |
| Free-threaded | Sync list collection | 46.86 | 36.63 | 28.62 |
| Free-threaded | Async list collection | 46.68 | 36.12 | 191.88 |
| Free-threaded | Async iterator | — | 41.80 | 196.64 |

The SDK completed synchronous collection fastest on both builds. For async list collection, upgrading from 0.14.4 to PR #500 reduced elapsed time **38.7%** on standard CPython and **22.6%** on free-threaded CPython. Version 0.14.4 offered an async `foreach()` callback. PR #500 added the public async iterator. The SDK iterator took **9.97×** as long as the PR iterator on standard CPython and **4.70×** as long on free-threaded CPython. [Async stream profile](./async-stream-profile.md)

## Independent point operations

When each key needs its own wire command, aerospike-py can submit concurrent `get()` or `put()` calls with `asyncio.gather()`. The SDK's `get_many()` and `put_many()` submit a window of independent commands in one call. This test issued **one window of 32 keys at a time**. A write applied the same eight-bin payload to every key in the window. Throughput is in **thousands of rows per second**. [SDK window implementation](https://github.com/aerospike/aerospike-client-python-sdk/blob/v1.0.0/aerospike_sdk/aio/session.py#L460-L558)

| Python build | Operation | 0.14.4 | PR #500 | Official SDK |
|---|---|---:|---:|---:|
| Standard | Read | 22.28 | 22.02 | 25.02 |
| Standard | Write | 22.98 | 22.42 | 25.39 |
| Free-threaded | Read | 18.20 | 17.35 | 25.48 |
| Free-threaded | Write | 19.32 | 19.01 | 26.30 |

On free-threaded reads the SDK used **18.55 µs of client CPU per row**. The two aerospike-py versions used 260.19 µs (0.14.4) and 258.19 µs (PR). This distinction matters when choosing between grouping independent operations and issuing a server batch.

## Measurement conditions

The clients and a single Aerospike CE 8.2.0.1 node shared a 12-core Apple M4 Pro with 24 GiB of memory. The server ran in a Podman VM with 5 vCPUs. Tests used CPython 3.14.2 and 3.14.2t, NumPy 2.5.5, and uvloop 0.23.0 for async work. Each process checked the GIL state after importing its client.

Each value is the median of three warmed runs with client order varied between runs. Each batch condition ran for 1.2 seconds per trial. Each point window condition ran for 1.5 seconds. Each query trial timed one complete scan after a warmup scan. CPU per row includes all client process threads. Batch p99 measures latency for one 720-row call. The shared host and short trials limit how well small differences predict a separate production cluster.

<a href={useBaseUrl('/benchmark/4aabf09/client-comparison.zip')}>Download measurements, scripts, and reproduction instructions (ZIP)</a>
