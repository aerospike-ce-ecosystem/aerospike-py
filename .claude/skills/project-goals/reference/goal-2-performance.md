# Goal 2: Performance (GIL-free, outperform C client)

## Design Principles

- Default 2 Tokio workers (`AEROSPIKE_RUNTIME_WORKERS`): minimizes GIL reacquire contention
- Signal driver disabled (`enable_io()` + `enable_time()`, not `enable_all()`): prevents Python signal handler conflicts
- ArcSwapOption: lock-free access to async client state

## Benchmark Results (vs aerospike-client-python C client)

| Path | put | get | batch_read_numpy |
|------|-----|-----|-----------------|
| Sync (sequential) | ~1.1x slower | ~1.1x slower | — |
| Async (concurrent) | **2.1x faster** | **1.6x faster** | **3.4x faster** |

## Sync Gap Root Cause (structural limitation)

1. `py.detach()` GIL transition cost ~3-5µs
2. async-only crate → `block_on` Future creation overhead
3. PyO3 type conversion ~1-3µs

→ Absolute difference ~12µs. The async path is the key differentiator.

## Key Files

- `rust/src/runtime.rs` — runtime tuning rationale
- `benchmark/bench_compare.py` — comparison benchmark
- `benchmark/RESULTS.md` — detailed analysis and rationale
