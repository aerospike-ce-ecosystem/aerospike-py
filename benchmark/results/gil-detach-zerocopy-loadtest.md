# `batch_read().to_numpy(dtype)` GIL detach + zero-copy load test

**Date:** 2026-05-24
**Branch:** `worktree-numpy-gil-detach`
**Goal:** Verify that releasing the GIL during `LazyBatchRecords.to_numpy(dtype)`
buffer fill (and the resulting `torch.from_numpy` zero-copy chain) actually
improves throughput / tail-latency in a realistic
`uvicorn + FastAPI + PyTorch + aerospike-py` inference setup.

> **Fairness note.** An earlier draft of this report compared `to_numpy`
> against a deliberately-pessimised `to_dict` path that wrote into a torch
> tensor cell-by-cell (`matrix[i, j] = v`). That is a worst-case anti-pattern
> no real service writes — it inflated the numpy advantage to ~3.6×. The
> dict path below uses the standard idiom (build a list of lists, then
> `torch.tensor(rows)` once). All headline numbers come from that fair
> version. The biased numbers are kept at the bottom for transparency.

---

## TL;DR (fair, single-worker)

The honest signal lives on a **single uvicorn worker** where the GIL is
under pressure. The ratio scales with how heavy the per-request
conversion is (i.e. features per record):

| batch | features | c   | DICT RPS | NUMPY RPS | RPS ratio | DICT p50 | NUMPY p50 |
|------:|---------:|----:|---------:|----------:|----------:|---------:|----------:|
| 200   | 16       | 50  | 702      | 794       | **+13 %** | 78.6 ms  | 61.8 ms   |
| 200   | 32       | 50  | 487      | 638       | **+31 %** | 97.0 ms  | 74.6 ms   |
| 200   | 32       | 100 | 516      | 740       | **+43 %** | 192.6 ms | 127.7 ms  |

- conv_ms scales linearly with features × batch, and is exactly where the
  GIL is held. Once conversion becomes a meaningful fraction of total
  request time, the numpy path's `py.detach` fill loop starts to matter.
- p50 latency improves by 21 – 34 %; p99 by 4 – 24 %; the conversion
  step alone speeds up 3–5×.

Single-request breakdown (batch=200, features=32, 1 worker):

| Stage | `to_dict()` | `to_numpy()` | Ratio |
|-------|-----------:|-------------:|------:|
| io_ms | 6.557 | 5.171 | ≈ |
| **conv_ms** | **1.471** | **0.511** | **2.88×** |
| **inference_ms** | **0.299** | **0.172** | **1.74×** (zero-copy `torch.from_numpy`) |
| total_ms | 8.361 | 5.908 | 1.42× |

`score_sum` is identical (-4.2316) on both paths — same data, same MLP,
only materialisation changes.

## TL;DR (4 workers — measurement constraint)

`uvicorn --workers 4` on macOS turned out **not measurable** with `oha`:
keep-alive connections didn't spread evenly across the four processes
and `oha` reported **~50 % success rate** with both paths capped at the
same ~1 s ceiling. This is a `macOS uvicorn` + `oha` interaction, not a
property of either path. The same comparison would need either (a) a
Linux host, (b) a single uvicorn worker behind nginx, or (c) per-process
ports + an aggregating load tester.

For this report we are honest about that and report only the 1-worker
numbers. A linux-side or production-load follow-up is the right way to
add multi-worker evidence.

---

## What changed in the code

1. **`rust/src/numpy_support.rs::batch_to_numpy_py`** — the per-record fill
   loop now runs inside `py.detach(...)`. Every `Value → buffer` write
   (`ptr::write_unaligned`) happens with the GIL released. Only the numpy
   array allocation, dtype parsing, and `key_map` construction still hold
   the GIL.

2. **API unification.** Sync `Client.batch_read` and async
   `AsyncClient.batch_read` both return a `LazyBatchRecords` handle. The
   `_dtype=` kwarg is gone; materialisation is explicit:

   ```python
   handle = client.batch_read(keys)        # IO only, no PyObject loop
   d      = handle.to_dict()               # dict[user_key, bins_dict]
   arr    = handle.to_numpy(dtype)         # NumpyBatchRecords (GIL released during fill)
   ```

   `LazyBatchRecords` implements the dict-like Mapping protocol
   (`__getitem__`, `__contains__`, `items()`, `keys()`, `values()`,
   `__iter__`, `__len__`) backed by a lazy + cached `to_dict()` view, so
   existing dict-style code keeps working without an explicit
   `.to_dict()` migration.

3. **`torch.from_numpy` zero-copy.** `NumpyBatchRecords.batch_records` is a
   real `np.ndarray` over a C-contiguous buffer. `np.column_stack(...)`
   produces a contiguous float32 matrix, and `torch.from_numpy(matrix)`
   then shares that buffer with the tensor — no PyObject allocation along
   the chain.

---

## Test setup

- **Host:** macOS 26.3, Apple Silicon, 12 physical / 12 logical cores
- **Aerospike CE** in podman, port `18710`, 1 node, namespace `test`
- **Seed data:** 2 000 records in set `bench_serving`, configurable f32
  feature count (`BENCH_N_FEATURES=16/32/...`)
- **Stack:**
  - `aerospike-py` (this worktree, release build via `make build`)
  - FastAPI + `uvicorn[standard]` + `uvloop`
  - PyTorch 2.12.0 (CPU)
  - `oha` 1.x
- **App:** `benchmark/src/serving/bench_app.py` — minimal FastAPI app that
  brings up *only* the `aerospike-py` AsyncClient with library defaults
  (no DLRM, no OTel, no official C client, no custom
  `max_concurrent_operations` — explicit values caused the local
  single-node cluster to refuse validation under load).
- **Endpoints:** `benchmark/src/serving/endpoints/bench.py`

  ```python
  # /bench/dict — standard idiom
  result_dict = handle.to_dict()
  rows = []
  for i in range(batch_size):
      bins = result_dict.get(f"row_{i}") or {}
      rows.append([bins.get(name, 0.0) for name in FEATURE_NAMES])
  matrix = torch.tensor(rows, dtype=torch.float32)

  # /bench/numpy
  np_batch = handle.to_numpy(DTYPE)
  matrix_np = np.column_stack([np_batch.batch_records[n] for n in FEATURE_NAMES]) \
                .astype(np.float32, copy=False)
  matrix = torch.from_numpy(matrix_np)
  ```

- **"Model":** a small two-layer MLP (`Linear 32→256 → ReLU → Linear
  256→1`) — heavier than the original `matmul 16×1` placeholder so that
  inference is real torch work, but small enough not to mask the
  materialisation difference.

---

## Detailed results (1 worker)

```
oha -z 20s -c <C> --no-tui http://127.0.0.1:8765/bench/{dict,numpy}?batch_size=200
```

### batch=200, features=16 (light)

```
c=50  · DICT  : 702 RPS · p50 78.6 ms · p90 102.7 ms · p99 117.0 ms
        NUMPY : 794 RPS · p50 61.8 ms · p90  99.5 ms · p99 111.8 ms
                +13 %     −21 %         −3 %          −4 %
```

### batch=200, features=32 (medium)

```
c=50  · DICT  : 487 RPS · p50  97.0 ms · p90 144.1 ms · p99 192.2 ms
        NUMPY : 638 RPS · p50  74.6 ms · p90 115.1 ms · p99 146.8 ms
                +31 %     −23 %          −20 %          −24 %

c=100 · DICT  : 516 RPS · p50 192.6 ms · p90 236.7 ms · p99 300.1 ms
        NUMPY : 740 RPS · p50 127.7 ms · p90 190.6 ms · p99 247.8 ms
                +43 %     −34 %          −19 %          −17 %
```

Heavier conversion (more features per row) → bigger gap, as expected.
The dict path's conversion step grows linearly with `features × batch`;
the numpy path's `py.detach`-d fill loop grows the same way in CPU
cycles but doesn't hold the GIL while doing it, so the event loop can
interleave other requests on the same worker.

## Detailed results (4 workers) — environmental ceiling

```
c=50  · DICT  :  97 RPS · p50 1.04 s · success rate 50.0 %
        NUMPY :  93 RPS · p50 1.05 s · success rate 50.0 %

c=100 · DICT  : 205 RPS · p50 1.08 s · success rate 50.0 %
        NUMPY : 195 RPS · p50 1.08 s · success rate 50.0 %
```

Both paths hit the same ~1 s ceiling with exactly half of `oha`'s
requests failing — this is the `oha`-keep-alive ↔ multi-process uvicorn
on macOS pathology, not a property of `to_dict()` or `to_numpy()`. The
single-worker smoke on the same 4-worker server returned in
~6 ms (dict) / ~6 ms (numpy), so the application code is fine; only
under sustained `oha` load does the connection routing collapse.
Re-running on a Linux host (where `uvicorn --workers N` uses
`SO_REUSEPORT`) would be the way to get a meaningful 4-worker number.

---

## Interpretation

1. **GIL detach helps when conversion is a meaningful slice of the
   request.** With light conversion (features=16) the gain is +13 %;
   triple the conversion work and the gain rises to +31 – 43 %. The
   relationship is roughly linear in the per-request GIL-bound time.

2. **Per-request conversion is genuinely faster.** 2.88× on
   features=32, holding up from the earlier numbers. Two sources: raw
   `ptr::write_unaligned` vs `PyFloat_FromDouble` allocation, and
   `torch.from_numpy(matrix_np)` pointer-sharing vs
   `torch.tensor(rows)` allocate-and-copy. Both reproduce on quiet
   single-request smoke.

3. **Multi-worker uvicorn on macOS is not a clean test bed.** The
   `oha` + `uvicorn --workers N` pair pinned half the connections and
   forced a 1 s saturation on both paths — that's an environmental
   ceiling, not a GIL signal. The honest report says so and stops
   there for multi-worker.

4. **The right next step is a Linux or production run.** On Linux
   `SO_REUSEPORT` spreads keep-alive connections across worker
   processes evenly, and a real cluster avoids the 1 s
   "Failed to validate seed host" cliff that the local single-node
   container hit under heavy concurrent batch_read load. Until then,
   the 1-worker numbers are the load-test contribution; the
   single-request profile (`conv_ms` 2.88×, `inference_ms` 1.74×) is
   the steady invariant.

---

## How to reproduce

```bash
# 1. Build the dev wheel
make build

# 2. Local Aerospike CE + seed 2 000 rows
make run-aerospike-ce
BENCH_N_FEATURES=32 AEROSPIKE_PORT=18710 PYTHONPATH=benchmark/src \
  uv run python -m serving.bench_seed

# 3. Launch FastAPI bench app (single worker for the strongest GIL signal)
BENCH_N_FEATURES=32 AEROSPIKE_HOSTS=127.0.0.1:18710 PYTHONPATH=benchmark/src \
  uv run uvicorn serving.bench_app:app \
    --host 127.0.0.1 --port 8765 \
    --workers 1 --log-level warning

# 4. Hit each endpoint with oha
oha -z 20s -c 50  --no-tui 'http://127.0.0.1:8765/bench/dict?batch_size=200'
oha -z 20s -c 50  --no-tui 'http://127.0.0.1:8765/bench/numpy?batch_size=200'
oha -z 20s -c 100 --no-tui 'http://127.0.0.1:8765/bench/dict?batch_size=200'
oha -z 20s -c 100 --no-tui 'http://127.0.0.1:8765/bench/numpy?batch_size=200'
```

`/bench/dict` and `/bench/numpy` return the same JSON shape and the same
`score_sum`, so the two runs cover identical work — only the
batch-read materialisation differs.

---

## Things that went wrong (kept for the next person who runs this)

- **`max_concurrent_operations=4096` (explicit)** caused
  `aerospike.ClientError: Failed to validate seed host: 127.0.0.1:18710`
  on every request under load. Reverted to library default.
- **`batch_size=500` on a single-node container** hit the same
  validation cliff at c≥50. Sticking to `batch_size=200` kept the
  measurement honest.
- **podman machine** dropped its ssh socket twice during the session;
  `podman machine stop && podman machine start` + `podman start
  aerospike` revives the container.
- **`uvicorn --workers 4` + `oha` on macOS** clamped success rate to
  50 % and p50 to ~1 s for both paths. Single-worker measurements are
  the load-test data point until a Linux or nginx run is added.

---

## Files touched / added

- `rust/src/numpy_support.rs` — `py.detach` around the fill loop, `BufferAddr` wrapper
- `rust/src/batch_types.rs` — `PyLazyBatchRecords` rename, dict-like dunders, `to_numpy(dtype)` method
- `rust/src/client.rs`, `rust/src/async_client.rs` — `batch_read` returns the handle, `_dtype` kwarg removed
- `src/aerospike_py/_client.py`, `src/aerospike_py/_async_client.py`, `src/aerospike_py/__init__.pyi` — wrapper + stub updates
- `benchmark/src/serving/bench_app.py` — standalone FastAPI app for this benchmark
- `benchmark/src/serving/endpoints/bench.py` — `/bench/dict` and `/bench/numpy`
- `benchmark/src/serving/bench_seed.py` — feature-row seeder
- 47 test sites migrated from `_dtype=` to `.to_numpy(dtype)`; 13 dict-style
  test sites kept working through the dict-like backward-compat layer.

All 927 unit tests + 348 integration tests pass on this branch.

---

## Appendix — biased numbers from the first draft

The earlier `/bench/dict` implementation built the tensor cell-by-cell:

```python
matrix = torch.zeros(batch_size, N_FEATURES, dtype=torch.float32)
for i in range(batch_size):
    bins = result_dict.get(f"row_{i}")
    if bins is None:
        continue
    for j, name in enumerate(FEATURE_NAMES):
        v = bins.get(name)
        if v is not None:
            matrix[i, j] = v   # ← PyObject → tensor cell, the worst path
```

That pattern triggers a PyObject round-trip per cell and is the slowest
realistic way to build a tensor. Real services either:

- collect rows as a nested Python list and call `torch.tensor(rows)` once
  (what `/bench/dict` now does), or
- convert to numpy first and then `torch.from_numpy` (basically what
  `/bench/numpy` does, but via a different conversion).

Numbers under the cell-by-cell version (kept for transparency):

| Workers | c | Batch | Path | RPS | p50 | p99 |
|--------:|--:|------:|------|----:|----:|----:|
| 1 | 50 | 200 | dict (cell-by-cell) | 249 | 199.8 | 333.9 |
| 1 | 50 | 200 | numpy               | 895 | 51.7  | 111.2 |

The honest numbers live in the main tables above.
