# Postmortem — v0.5.6 `batch_to_dict_py` performance regression

**Date**: 2026-04-15
**Scope**: released in v0.5.6, reverted in v0.5.7
**Related**: issue [#281], PR [#282] (introduced), PR [#288] (revert), issue [#285] (follow-up bench)

[#281]: https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/281
[#282]: https://github.com/aerospike-ce-ecosystem/aerospike-py/pull/282
[#285]: https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/285
[#288]: https://github.com/aerospike-ce-ecosystem/aerospike-py/pull/288

## TL;DR

PR #282 added a per-call `HashMap<&str, Bound<PyString>>` cache for bin names in `batch_to_dict_py` based on issue #281's allocation-count analysis. A synthetic local microbench showed p50 −14.8% / p99 −18.5%. Production measurement on a FastAPI + Aerospike serving stack showed the opposite: end-to-end p50 **+91%**, and — crucially — a **~7.5x regression on unrelated Python code** (`inference`) sharing the same event loop. Reverted in v0.5.7; 0.5.5 performance was restored.

## Evidence

0.5.5 → 0.5.6 delta (only one runtime change landed between these releases: PR #282; PR #286 was CI-only):

| Section (p90, 10 VU) | 0.5.5 | 0.5.6 | Change |
| --- | ---: | ---: | ---: |
| `batch_read` per-set | ~60 ms | 108–134 ms | **~2x slower** |
| `aerospike_batch_read_all` | 145 ms | 255 ms | ~1.8x slower |
| `feature_extraction` | 10 ms | 9 ms | same |
| **`inference` (non-aerospike)** | **8 ms** | **60 ms** | **~7.5x slower** |
| E2E p50 | 155 ms | 296 ms | ~1.9x slower |
| RPS | 60.9 | 34.7 | −43% |

The smoking gun is the `inference` row: the ML inference step does not call aerospike-py at all. The only mechanism by which a change in `batch_to_dict_py` can slow it down is by **holding the GIL longer during batch conversion, serializing other Python work on the same loop.**

## Root cause

Per-call `HashMap<&str, Bound<PyString>>` adds CPU-bound work on the GIL-holding thread:

- SipHash over each bin name (`N × B` hashes per call)
- HashMap bucket traversal + entry API
- `Bound<PyString>::clone()` refcount bump per hit

The intended savings — avoiding PyString allocation for repeated bin names — are **already free in CPython**:

- `PyUnicode_FromStringAndSize` hits the small-string cache for short ASCII strings
- CPython automatically interns short identifier-shaped strings
- Python dict caches string hashes internally

Net effect: work moved from a fast C path into a slower Rust HashMap path. GIL hold time grew; throughput fell; anything else sharing the loop became a casualty.

## Why the local microbench missed it

The PR #282 validation used `asyncio.gather` with 10 VUs × 30 rounds × 200 keys × 7 bins against a plain Aerospike instance. No FastAPI, no Pydantic, no competing Python work. Reasons it failed to surface the regression:

1. **No GIL competitor.** Extending GIL hold time produces no observable effect if nothing else wants the GIL. All 10 VUs were doing the same thing.
2. **Scale mismatch.** Local p50 was ~5 ms; production p50 is ~150–300 ms. HashMap overhead is a ~constant per-call penalty — proportionally tiny at 5 ms total, material at 150 ms total.
3. **No upstream work.** Real serving stacks interleave FastAPI serialization, Pydantic validation, and business logic between aerospike calls. Their GIL demand is what amplifies the regression.

## Action items

- [x] Revert PR #282 via PR #288 → shipped in v0.5.7.
- [x] Close follow-up issues whose premise was invalidated: #283 (`.clone()` micro-opt), #284 (extend pattern to `record_to_py_inner` / `value_to_py`).
- [ ] Keep [#285] (permanent concurrent batch_read microbench) open. **Next attempt at this optimization must use a bench that reproduces a competing-Python-work scenario** (e.g., FastAPI handler doing both `await batch_read()` and a CPU-bound dummy computation on the same loop).
- [ ] PyO3 hot-path PR checklist to add:
  - [ ] `asyncio.gather` single-loop microbench (before/after)
  - [ ] Production-like load with competing Python work on the same loop (before/after)
  - [ ] Verify no regression on code paths that do not call the changed function

## Alternative approaches (for future investigation)

Do not attempt any of these without the checklist above:

- `PyString::intern` — leverage CPython's own intern table instead of a Rust-side HashMap. Avoids SipHash and refcount clone, but every unique bin name ever observed lives for the process lifetime.
- `IntoPyDict` / C-level dict construction — build the bins dict in one shot instead of `set_item` in a loop.
- Pre-converted bin name list — when the caller passes explicit `bins: list[str]`, convert those strings to PyString once before the batch loop and reuse.

## Lessons

1. **"Allocation count reduction" is not synonymous with "latency improvement"** on GIL-holding paths. The replacement code's CPU cost on the GIL-holding thread is what matters for end-to-end throughput.
2. **CPython already optimizes many things.** Before re-implementing caching / interning in Rust, check whether CPython's small-string cache, dict hash cache, or intern table already handles the case for free.
3. **Microbenches must resemble the real workload.** For async Python libraries, the benchmark must include competing CPU-bound Python work on the same event loop; otherwise GIL-hold regressions are invisible.
