---
title: Internal Stage Profiling
sidebar_label: Internal Stage Profiling
sidebar_position: 4
description: Fine-grained per-stage timing for debugging aerospike-py latency, with zero production overhead when disabled.
---

aerospike-py exposes a second, more granular histogram alongside `db_client_operation_duration_seconds`:

**`db_client_internal_stage_seconds`** — a histogram that breaks a single `batch_read` down into its internal stages (key parsing, Tokio scheduling, I/O, `as_dict` conversion, event-loop resume, etc.).

Unlike operational metrics which are always on, internal stage profiling is **off by default**. When disabled, every stage timer call site skips `Instant::now()` entirely — the disabled path costs a single atomic load (~1ns per batch).

## Quick Start

```python
import aerospike_py

# Off by default
assert aerospike_py.is_internal_stage_metrics_enabled() is False

# Turn it on for a debug session
aerospike_py.set_internal_stage_metrics_enabled(True)
handle = await client.batch_read(keys)
print(aerospike_py.get_metrics())   # db_client_internal_stage_seconds now populated

# Or scope it to a single block
with aerospike_py.internal_stage_profiling():
    handle = await client.batch_read(keys)
# Flag automatically restored on exit, even if the block raised
```

## How to Enable

| Method | When to use |
|---|---|
| `AEROSPIKE_PY_INTERNAL_METRICS=1` env var | Whole-process default at startup (K8s `ConfigMap`, `docker run -e`, CI). Truthy: `1`, `true`, `True`, `TRUE`, `yes`, `on`. |
| `aerospike_py.set_internal_stage_metrics_enabled(True)` | Runtime toggle from application code. |
| `with aerospike_py.internal_stage_profiling(): ...` | Temporary — restores the previous state on exit. |

The env var is read once during native module init. Runtime calls win over the env var.

## `db_client_internal_stage_seconds`

A **histogram** tracking per-stage durations inside a single database operation.

**Labels:**

| Label | Examples |
|---|---|
| `stage` | `key_parse`, `tokio_schedule_delay`, `limiter_wait`, `io`, `spawn_blocking_delay`, `into_pyobject`, `event_loop_resume_delay`, `as_dict`, `merge_as_dict`, `future_into_py_setup` |
| `db_operation_name` | `batch_read` (more ops may be instrumented later) |

**Buckets (sub-microsecond precision):**
`1μs, 5μs, 10μs, 50μs, 100μs, 500μs, 1ms, 2ms, 5ms, 10ms, 20ms, 50ms, 100ms, 500ms, 1s`

## Stage Reference (`batch_read`)

| Stage | What it measures |
|---|---|
| `key_parse` | Python keys → Rust tuples (GIL held) |
| `future_into_py_setup` | `future_into_py` sync setup (GIL held) |
| `tokio_schedule_delay` | Gap from *before* `future_into_py` setup to the start of the async body on a Tokio worker. **Note:** includes the synchronous `future_into_py_setup` window as well as pure scheduling delay — subtracting `future_into_py_setup` approximates the isolated scheduling component (a small `stage_timer!` macro overhead also falls inside this window). |
| `limiter_wait` | Time waiting for the backpressure semaphore |
| `io` | Aerospike network round-trip |
| `spawn_blocking_delay` | Gap between I/O completion and `IntoPyObject::into_pyobject` starting on a spawn-blocking thread (GIL-bound) |
| `into_pyobject` | `Arc` wrap + `BatchReadHandle` construction |
| `event_loop_resume_delay` | Gap between `into_pyobject` returning and the Python coroutine actually resuming in the event loop |
| `as_dict` | `batch_to_dict_py` conversion (GIL held) |
| `merge_as_dict` | Static `BatchReadHandle.merge_as_dict` — single-GIL merge of multiple handles |

## Why This Is Opt-In

Stage profiling adds measurable latency: each `batch_read` pays ~10× `Instant::now()` plus 10 histogram observations. On a benchmark with 20 concurrent workers we measured, for `db_client_operation_duration_seconds` of `batch_read`:

| | OFF | ON | Δ |
|---|---|---|---|
| avg | 2.16 ms | 3.22 ms | +1.06 ms |
| p95 | 4.67 ms | 7.61 ms | +2.94 ms |
| p99 | 4.93 ms | 9.51 ms | +4.58 ms |

Leave it **off in production**, and flip it on only when you are actively hunting a latency regression.

## Scraping and Visualization

The histogram is exposed via the same `get_metrics()` / `start_metrics_server()` surface as the operational histogram — no separate endpoint. A Grafana panel can query, for example, the p95 of `as_dict`:

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(
    db_client_internal_stage_seconds_bucket{stage="as_dict"}[5m]
  ))
)
```

A stacked timeseries of all stages gives you a quick view of where each `batch_read` is spending its time:

```promql
sum by (stage, db_operation_name) (
  rate(db_client_internal_stage_seconds_sum[1m])
) / sum by (stage, db_operation_name) (
  rate(db_client_internal_stage_seconds_count[1m])
)
```

## Confirming the Toggle State

At process start, aerospike-py logs its effective state:

```
[aerospike-py] internal_stage_metrics_enabled=False (AEROSPIKE_PY_INTERNAL_METRICS=None)
```

You can also publish it as a Prometheus gauge in your own app for dashboard visibility:

```python
from prometheus_client import Gauge
import aerospike_py

g = Gauge("aerospike_py_internal_stage_metrics_enabled",
          "1 if stage profiling is ON, 0 otherwise")
g.set(1 if aerospike_py.is_internal_stage_metrics_enabled() else 0)
```

## Troubleshooting

**`db_client_internal_stage_seconds` shows up in `/metrics` but has no samples**
The `# HELP` / `# TYPE` headers are always registered; samples appear only after the toggle is ON **and** a `batch_read` has actually completed.

**My context-manager block raised an exception — is the flag still ON?**
No. `internal_stage_profiling()` restores the previous state via `finally`, identical to `contextlib.contextmanager` semantics.

**Does this affect `db_client_operation_duration_seconds`?**
No. Operational metrics (`db_client_operation_duration_seconds`) are controlled by `set_metrics_enabled` / `is_metrics_enabled` and are independent of the stage toggle.
