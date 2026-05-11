---
title: Multi-worker production tuning
sidebar_label: Multi-worker production
sidebar_position: 3
description: Configuration and code patterns for high-load multi-worker servers (uvicorn, gunicorn, BentoML).
---

This guide collects the knobs and code patterns that matter when running
aerospike-py inside a multi-worker server (uvicorn `--workers N`,
gunicorn, BentoML, etc.) under sustained high concurrency. None of the
recommendations below require a non-default build — they're all
runtime-tunable for the standard PyPI wheel.

The recommendations are derived from the analysis of issue
[#347](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/347)
and the optimization work that followed it.

---

## TL;DR

Three changes account for the bulk of the per-request overhead reduction
without touching application logic:

1. **Run on free-threaded Python 3.14t** when your workload tolerates it
   — single biggest win, no Rust changes required.
2. **Pre-compile your `BatchPolicy`** once at startup with
   `aerospike_py.BatchPolicyInstance(...)` and reuse it on every request.
3. **Replace `asyncio.gather(*[client.batch_read(...) for _ in groups])`
   with a single `await client.batch_read_many(groups)`** — collapses
   N round-trips into one and pays the per-call Python↔Rust handoff
   exactly once.

Optional, deployment-dependent:

4. Set `AEROSPIKE_RUNTIME_MODE=current_thread` for multi-process servers.
5. Use `client.batch_read_ordered(keys)` if your downstream code is
   doing `[result.get(user_pk) for ...]` after every batch read.
6. Build with `--features production` if you've finished profiling and
   want to strip the stage-timer instrumentation.

---

## 1. Run on free-threaded Python 3.14t

aerospike-py declares `gil_used = true` on Python 3.14t (the
free-threaded interpreter). All of the result conversion that runs in
the Tokio worker's `spawn_blocking` callback releases the GIL in the
free-threaded build, so several concurrent `batch_read` callers no
longer serialize on a single global lock.

Measured impact on the existing
[`benchmark/`](https://github.com/aerospike-ce-ecosystem/aerospike-py/tree/main/benchmark)
suite (Rust code identical, only the Python interpreter swapped):

| Metric | 3.11 + GIL | 3.14t free-threaded | Delta |
|---|---:|---:|---:|
| FastAPI E2E p95 | 189 ms | 97 ms | **−49 %** |
| Iterations per second | 41.6 | 61.2 | **+47 %** |

The aerospike-py wheels are built for both `cp311` … `cp314` and `cp314t`.
Pin the runtime in your container image:

```dockerfile
FROM python:3.14.0-slim
# Free-threaded Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.14t-full && rm -rf /var/lib/apt/lists/*
RUN python3.14t -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install aerospike-py uvicorn fastapi
```

> The aerospike-py code base has been validated on 3.14t end-to-end
> (`make test-matrix` covers `cp311`, `cp312`, `cp313`, `cp314`, `cp314t`).
> No application code change is required.

---

## 2. Pre-compile `BatchPolicy` once at startup

Every `batch_read(..., policy={...})` call parses the dict — ~10 field
lookups + type extraction. Long-lived services that send the same
policy on every request can build it once and reuse it.

```python
import aerospike_py
from aerospike_py import AsyncClient

# At module load time
BATCH_POLICY = aerospike_py.BatchPolicyInstance(
    socket_timeout=2000,
    total_timeout=5000,
    max_retries=2,
    concurrency=1,
)

async def handler(client: AsyncClient, keys: list) -> dict:
    return await client.batch_read(keys, policy=BATCH_POLICY)
```

The `policy` argument continues to accept dicts (back-compat), so this
is a strictly additive opt-in. Use whichever shape is more convenient
per call site.

---

## 3. Collapse fan-out reads with `batch_read_many`

The classic feature-view fan-out pattern is

```python
results = await asyncio.gather(*[
    client.batch_read(group_keys) for group_keys in feature_view_keys
])
```

For N=9 feature views this pays the per-call PyO3 + Tokio + GIL overhead
**nine times** — one task spawn per gather entry, one limiter
acquisition per call, nine spawn-blocking callbacks that contend for
the GIL when they finish.

`batch_read_many` does the same job in one shot:

```python
results: list[dict] = await client.batch_read_many(feature_view_keys)
```

Internally:

- One Tokio task spawn instead of N
- One limiter acquisition instead of N
- One `client.batch()` network round-trip (Aerospike's batch protocol
  carries mixed-set keys in a single request)
- One GIL hand-off back to the event loop instead of N

The returned `list[dict]` preserves input group order. Per-group
overrides for `bins`/`policy` are intentionally not exposed in this
minimal API — all groups share one `bins` and one `policy`.

---

## 4. (optional) `current_thread` Tokio runtime

Multi-process servers — uvicorn `--workers N`, gunicorn, BentoML —
already supply parallelism via OS processes. Each process gets its own
Tokio runtime, and the multi-thread runtime's work-stealing scheduler
is mostly overhead at that scale (a couple of worker threads contending
for the same in-process GIL).

```bash
export AEROSPIKE_RUNTIME_MODE=current_thread
export AEROSPIKE_RUNTIME_WORKERS=1   # ignored in current_thread mode
```

The default is `multi_thread` to preserve existing behavior; opt in
when you know your deployment is fan-out-by-process. Unknown values
fall back to `multi_thread` with a warn-level log.

---

## 5. (optional) `batch_read_ordered` for positional consumers

If your downstream code is doing

```python
result = await client.batch_read(keys)
materialized = [result.get(user_pk) for _, _, user_pk in keys]
```

— i.e. you don't actually need the dict shape; you want a positional
list in input order — `batch_read_ordered` does the reorder in Rust
inside the same GIL acquisition that materializes the bins:

```python
materialized: list[dict | None] = await client.batch_read_ordered(keys)
```

`None` for missing records, in input order. Duplicate input keys each
get their own slot (server-side dedup does not collapse positions).

---

## 6. (advanced) `--features production` build

Each `batch_read` call passes through ~11 internal stage timers
(`key_parse`, `future_into_py_setup`, `tokio_schedule_delay`, …,
`into_pyobject`). When the runtime toggle
`AEROSPIKE_PY_INTERNAL_METRICS` is **off** (the default), each stage
runs a single `Ordering::Relaxed` atomic load and skips the
`Instant::now()` + histogram observation — already nearly free, but
not zero.

For users who have finished diagnosing performance issues and want the
absolute minimum overhead, build with the `production` Cargo feature
and the stage timer is **compile-stripped** to a direct passthrough of
the wrapped expression:

```bash
maturin develop --release --features production
```

The PyPI wheels do not enable `production` by default — the runtime
toggle is more useful to most users. Only build from source with this
flag if you've validated your config and want to recover the few
hundred nanoseconds per batch.

---

## Recommended baseline for a fresh BentoML / FastAPI service

```bash
# Container image — runtime
FROM python:3.14.0-slim
RUN pip install aerospike-py uvicorn fastapi

# Container runtime — env
ENV AEROSPIKE_RUNTIME_MODE=current_thread
ENV AEROSPIKE_RUNTIME_WORKERS=1
ENV AEROSPIKE_PY_INTERNAL_METRICS=0
```

```python
# app.py
import aerospike_py
from aerospike_py import AsyncClient

BATCH_POLICY = aerospike_py.BatchPolicyInstance(
    socket_timeout=2000, total_timeout=5000, max_retries=2,
)

async def predict(client: AsyncClient, feature_view_keys: list[list]) -> list[dict]:
    return await client.batch_read_many(feature_view_keys, policy=BATCH_POLICY)
```

That covers the three highest-impact knobs (3.14t runtime,
pre-compiled policy, `batch_read_many`) and the recommended env
defaults for a multi-worker setup. Add the remaining knobs only when
profiling shows a hot spot they specifically address.
