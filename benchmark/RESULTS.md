# Performance Analysis: Rust Binding vs C Binding

## Environment

- macOS (Apple Silicon, M4 Pro)
- Aerospike CE 8.1.0.3 (Docker)
- 10,000 ops x 30 rounds, warmup=200

## 1. Sync Performance Gap Analysis

### Optimization Attempts Comparison

| Approach | put (Rust/C) | get (Rust/C) |
|----------|-------------|-------------|
| baseline (`block_on`) | ~1.10x | ~1.12x |
| `spawn+oneshot` | 1.12x | 1.14x |
| `block_on` + DEFAULT_POLICY caching | 1.10x | 1.12x |

### Final Result (block_on + DEFAULT_POLICY caching)

```
Op       |     Rust avg |        C avg |    Ratio |   Rust stdev |      C stdev
--------------------------------------------------------------------------------
put      |      0.126ms |      0.114ms |    1.11x |     0.0018ms |     0.0031ms
get      |      0.126ms |      0.112ms |    1.13x |     0.0021ms |     0.0017ms
```

### Root Cause of ~10% Gap

1. **py.detach() (GIL release/reacquire)**: ~3-5μs — the C client also releases the GIL, but implementation differs
2. **Async protocol overhead**: The Rust aerospike client is async-only.
   Mechanical overhead from Future creation, poll, waker, etc. compared to the C client's direct synchronous I/O
3. **Python↔Rust conversion**: PyO3 type conversion cost ~1-3μs

### block_on Overhead Details

Analysis of the Tokio source reveals the actual overhead of `Runtime::block_on()`:
- Thread-local context setup (`enter_runtime`): ~5-15ns
- `CachedParkThread` creation: ~5ns (thread-local caching)
- Waker creation: ~10-20ns
- Guard drop: ~5-10ns
- **Total: ~30-50ns per call** — less than 0.05% of network I/O (~100,000ns)

### spawn+oneshot Has No Effect

The `RUNTIME.spawn()` + `oneshot::channel()` pattern is actually slower than `block_on`.
Cross-thread communication overhead (oneshot channel send/recv + task spawn) exceeds
the cost of block_on's runtime context enter/exit.

## 2. Is the 10% Sync Gap Actually a Problem?

### Absolute Values

```
Rust: 0.126ms/op  vs  C: 0.114ms/op  →  difference 0.012ms (12μs)
```

- 1,000 ops/sec workload: total 12ms/sec difference → negligible
- 10,000 ops/sec workload: total 120ms/sec difference → still negligible
- In real-world environments where network latency (1ms+) dominates, even less significant

### Impact by Production Pattern

| Pattern | API Used | Impact |
|---------|----------|--------|
| Web server (FastAPI, etc.) | async | Rust binding is **2.2-2.4x faster** |
| Batch processing | batch_read | On par with C (1.0x) |
| Simple scripts | sync | 10% gap imperceptible (12μs) |

## 3. Async Performance: The Key Differentiator

### C Client's Python async/await Limitations

The C client itself supports async APIs (libev/libuv/libevent-based callbacks). However:

- **Cannot expose async in Python bindings** — attempted and removed: [PR #462](https://github.com/aerospike/aerospike-client-python/pull/462)
- The C client's async is callback-based, making direct integration with Python's `asyncio` event loop difficult
- As a result, the only concurrency option with the C client: `asyncio.run_in_executor()` (thread pool, not true async)

### aerospike-py's Async Architecture

```
aerospike-py:  asyncio.gather(*[put(i) for i in range(N)])
               → PyO3 future_into_py → Tokio async runtime → true async I/O

C client:      asyncio.run_in_executor(pool, client.put, ...)
               → sync call in thread pool → GIL contention → limited concurrency
```

### Why batch_read Shows sync ≈ async

| Operation | sync measurement | async measurement |
|-----------|-----------------|-------------------|
| put/get | `for i in range(N): client.put(...)` (sequential) | `asyncio.gather(*[put(i) for i in range(N)])` (concurrent) |
| batch_read | `client.batch_read(keys)` (single call) | `await client.batch_read(keys)` (single call) |

`batch_read(5000 keys)` → one request, one response (server-side batch processing).
Whether async or sync, there's only 1 operation to execute → nothing to parallelize.
**Async itself isn't faster — the concurrency via `asyncio.gather` is what's faster.**

## 4. Strategic Conclusion: Should We Switch to C Binding?

### No.

| Criteria | Keep Rust Binding | Switch to C Binding |
|----------|:---:|:---:|
| sync performance | 1.10-1.13x (12μs gap) | 1.0x (baseline) |
| async performance | **Native async/await** | Not exposed in Python bindings ([PR #462](https://github.com/aerospike/aerospike-client-python/pull/462)) |
| Development cost | 0 (already complete) | 2-4 months |
| Maintenance | PyO3 automation | Manual C API |
| Memory safety | Guaranteed by Rust | segfault risk |
| Build convenience | maturin (simple) | C toolchain (complex) |
| Industry direction | Aligned (see below) | Against the trend |

### Alignment with Aerospike's Official Roadmap

Aerospike is planning to release a **new Python client based on the Rust client** in H1 2026:

- [Issue #263](https://github.com/aerospike/aerospike-client-python/issues/263) — Ronen Botzer: *"We're going to be releasing a fluent Python client, built on the Rust client, in H1 of this year"*
- [Issue #147](https://github.com/aerospike/aerospike-client-python/issues/147) — The Rust client will serve as the foundation for multi-language bindings (Python, Node.js, Ruby, etc.)
- [PR #462](https://github.com/aerospike/aerospike-client-python/pull/462) — Incomplete async code removed from C Python client → C-based Python async implementation abandoned

**The industry direction itself is Rust bindings. Binding a new C client would go against this trend.**

## 5. Applied Optimizations

- `DEFAULT_WRITE_POLICY` / `DEFAULT_READ_POLICY` LazyLock caching (minimal but harmless optimization)
- `put()`, `get()` use cached default policy when policy=None

### Optimizations Attempted and Removed

- `spawn_blocking_op` (spawn+oneshot pattern) — actually slower, so removed
