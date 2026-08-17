# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

[Unreleased]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.beta2...HEAD

### Added
- Structured `.result_code` attribute on every `AerospikeError` (and subclass) exception instance ([ADR-0027](https://aerospike-ce-ecosystem.github.io/project-hub/docs/architecture/adr/2026-03-30-structured-result-code)). Callers can now classify errors by a stable integer code instead of matching on the message string — e.g. `except AerospikeError as exc: if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND: ...`. Server errors carry the real Aerospike wire code (`2` = record-not-found, `5` = record-exists, `22` = forbidden, `9` = timeout, etc.), matching the existing `AEROSPIKE_ERR_*` constants; batch failures expose the same code as their single-record equivalents. Client-side errors that never received a server response (connection failures, client timeouts, invalid arguments, backpressure, caught Rust panics) expose the sentinel `-1`. The base `AerospikeError` carries a class-level default so `.result_code` is always present. This unblocks Cluster Manager's string-matching error-classification TODOs.
- `LazyBatchRecords.to_list()` — positional bulk conversion returning `list[bins_dict | None]` aligned 1:1 with the request key order, materialised in a single Rust pass (same cost shape as `to_dict()`, no per-record lazy `BatchRecord.record` conversion). Slots are identified purely by position, so batches that read the same `user_key` from multiple sets do not collide (the dict views keep only one of the colliding records), and successful digest-only reads return their bins instead of being skipped. Failed reads and not-found records are `None` at their position; misses should be checked with `is None` (`{}` means found with no selected bins). On a 720-key production-shaped batch the conversion cost drops from 2.86 ms (`batch_records` loop) to 0.51 ms.

### Changed
- **`WritePolicy` now defaults `max_retries` to `0` (was `2`) — behaviour change for existing users.** Both write-policy construction sites inherited `aerospike-core`'s `BasePolicy::default()`, which sets `max_retries: 2, sleep_between_retries: 0` inside a `total_timeout` of 1000 ms. `increment()`, `append()`, `prepend()`, and `operate()` with an increment op are **not idempotent**, so a spurious client-side timeout on a write the server had already committed was retried up to twice with zero backoff — over-counting counters and appending strings twice, silently. This contradicted the project's own documentation, which already specified the safe default in two places (`docs/docs/api/types.md` `WritePolicy` table listed `max_retries` default `0`; the performance-tuning guide recommends "2-3 for reads, 0 for writes (idempotency)"), and it disagreed with the official Aerospike clients, which default write retries to 0 for the same reason. Writes are now safe by default and callers opt back in explicitly: `client.increment(key, "counter", 1, policy={"max_retries": 2})`.

    **Affected operations.** Every operation that parses a write policy takes the new default, not just the non-idempotent ones: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`, and `apply()`. Of these, only `increment`/`append`/`prepend`, `operate` with an increment op, and `apply` (an arbitrary UDF, not safely retryable in the general case) actually gain safety from it. `put()`, `remove()`, `touch()`, and `remove_bin()` are idempotent in their effect on bin data, so for those four this is a deliberate trade of retry resilience for one uniform default rather than a correctness fix — accepted because `docs/docs/api/types.md` already names `remove()` and `touch()` as `WritePolicy` consumers on the same table that publishes `max_retries` default `0`, so a separate default for them would re-create the docs/code divergence this change closes.

    **Migration:** code that silently depended on the client absorbing a transient write failure will now surface that failure as an exception instead of retrying. For the idempotent operations above — and for a plain `put()` of full bin values — pass `max_retries` explicitly to restore the old behaviour: `client.remove(key, policy={"max_retries": 2})`. For the non-idempotent ones, the previous behaviour was double-applying them. Read, query, scan, and batch policy defaults are untouched, and `batch_write(retry=N)` (a separate per-record mechanism, already defaulting to `0`) is unaffected.
- Batch key conversion (`batch_read` / `batch_operate` key lists) is now a two-pass pipeline: Python-object extraction runs once under the GIL with `(namespace, set)` pointer memoisation — batch callers typically build every key tuple from the same `str` objects, so the `PyString` cast + UTF-8 validation runs once per distinct object instead of once per key — and RIPEMD-160 digest computation for the whole batch runs with the GIL released (`Python::detach`), so other Python threads (e.g. an asyncio event loop) keep running while the batch is hashed. On a 720-key batch the `key_parse` stage drops ~70% (0.63 ms → 0.19 ms measured locally); behaviour (validation errors, explicit-digest handling, bytes-key STRING-particle digests) is unchanged.
- `Privilege.code` (used by `admin_create_role` / `admin_grant_privileges` / `admin_revoke_privileges`) now accepts the canonical asadm-style string name in addition to the int constant. Both `{"code": aerospike_py.PRIV_READ}` and `{"code": "read"}` are valid; recognised names are `read`, `read-write`, `read-write-udf`, `write`, `truncate`, `user-admin`, `sys-admin`, `data-admin`, `udf-admin`, `sindex-admin`. Names are case-insensitive and `_` is treated as a synonym for `-`. Removes the need for downstream consumers receiving privilege codes from a wire format (HTTP forms, JSON) to maintain a name → int translation table. Closes #326.

### Security
- Upgraded the bundled `pyo3` from 0.28.2 to 0.29.0 (and `pyo3-async-runtimes` 0.28 → 0.29), fixing two advisories embedded in every published wheel: [RUSTSEC-2026-0176](https://rustsec.org/advisories/RUSTSEC-2026-0176) (out-of-bounds read in the `PyList`/`PyTuple` iterator `nth`/`nth_back` implementations) and [RUSTSEC-2026-0177](https://rustsec.org/advisories/RUSTSEC-2026-0177) (missing `Sync` bound on `PyCFunction::new_closure` allowing non-thread-safe closures to be shared across threads). Also bumps the transitive `anyhow` to 1.0.103 (RUSTSEC-2026-0190 unsoundness warning). No public API changes.

### Removed
- Support for the **free-threaded build of Python 3.13 (3.13t)**. pyo3 0.29 — required for the RUSTSEC-2026-0176 / RUSTSEC-2026-0177 security fixes above — dropped 3.13t upstream ("CPython declared free-threading supported starting with Python 3.14"), and `pyo3-ffi` 0.29 refuses to compile against it. Free-threaded **3.14t and 3.15t remain supported and tested in CI**, and the regular (GIL) build of 3.13 is unaffected. 3.13t users should move to 3.14t, the first free-threaded build CPython itself declares supported.

### Fixed
- `Client.remove()` / `AsyncClient.remove()` on a non-existent record now raises `RecordNotFound` with the real wire code in `.result_code` (`2`, `AEROSPIKE_ERR_RECORD_NOT_FOUND`) instead of the client-side sentinel `-1`. The delete path builds its exception client-side (aerospike-core collapses the server's KEY_NOT_FOUND response into a boolean), so it bypassed the ADR-0027 code attachment even though the exception type and its message (`AEROSPIKE_ERR (2): Record not found`) already identified the server code — the documented classification pattern `exc.result_code == AEROSPIKE_ERR_RECORD_NOT_FOUND` now works for `remove()` as well.
- OTel spans emitted by the Rust client (e.g. `BATCH_READ <ns>.<set>`) no longer detach into orphan root traces when the calling Python context carries a W3C Trace Context **Level 2** `traceparent` — i.e. trace-flags with the `random-trace-id` bit set (`0x03 = SAMPLED | RANDOM`), which recent `opentelemetry-python` versions emit by default. The bundled `opentelemetry-rust` (≤ 0.31) `TraceContextPropagator` rejects version-00 headers whose flags byte is greater than `0x02`, so a perfectly valid parent context was silently dropped and every client span became a separate single-span trace (inflating trace ingest and breaking span-level latency attribution). The injected `traceparent` is now masked to the `SAMPLED` bit before extraction; the workaround can be removed once the project moves to an opentelemetry-rust release that accepts Level 2 flags (upstream has already removed the strict check on `main`). Closes #406.
- A `list_sort` operation in `operate()` (`list_operations.list_sort(bin, sort_flags=...)`) whose `sort_flags` is an unrecognised integer — anything other than `LIST_SORT_DEFAULT` (0) or `LIST_SORT_DROP_DUPLICATES` (2) — now raises `ValueError` when the op is translated, instead of being silently coerced to `LIST_SORT_DEFAULT`. Previously a typo such as `sort_flags=1` or the bitmask `3` was mapped to the `Default` sort by a catch-all match arm, so a caller asking to drop duplicates would silently keep them, with no diagnostic. The valid codes are validated up front, matching the existing `return_type` (`int_to_list_return_type`) and bit overflow `action` (`get_overflow_action`) validation in the same module.
- A `bit_add` / `bit_subtract` operation in `operate()` whose `action` (overflow action) is an unrecognised integer — anything other than `BIT_OVERFLOW_FAIL` (0), `BIT_OVERFLOW_SATURATE` (2), or `BIT_OVERFLOW_WRAP` (4) — now raises `ValueError` when the op is translated, instead of being silently coerced to `FAIL`. Previously a typo such as `action=1` or `action=3` was mapped to the `FAIL` overflow action by a catch-all match arm, so an operation the caller believed would saturate or wrap would instead fail (or vice versa) with no diagnostic. The valid codes are validated up front, matching the existing `get_resize_flags` validation in the same module.
- A top-level `increment` operation in `operate()` (`{"op": aerospike_py.OPERATOR_INCR, "bin": ..., "val": ...}`) whose `val` is not an `int` or `float` — e.g. a string `"5"`, a list, a dict, or `bytes` — now raises `TypeError` when the op list is built, instead of shipping the non-numeric value to the server and failing the `add` with an opaque `BinTypeError`. This brings the `operate()` increment path in line with the `client.increment()` offset guard (`parse_increment_offset`) and the `list_increment` value guard (`parse_increment_value`), which already validated their numeric arguments client-side. A missing or `None`/`Nil` `val` still defaults to `+1`.
- An `equals` predicate with a value type the server cannot index on — most commonly a `float` (`predicates.equals("score", 1.5)`) or a `bool` (`predicates.equals("flag", True)`) — now raises `InvalidArgError` when the query is built, instead of panicking through the PyO3 boundary. Aerospike secondary-index equality filters accept only integers, strings, or `bytes`; the underlying `Filter::equal(..)` builder asserted this, and the panic was raised in `build_statement` (outside the query-execution panic-safety net), so it was not catchable as a normal Python exception. The `equals` value type is now validated up front, matching the existing `between` integer-bound and `contains` index-type predicate guards.
- Passing a `bytearray` where a bytes value is expected now writes a blob bin instead of raising `TypeError: Unsupported type for Aerospike value: bytearray`. The native `py_to_value` converter handled `bytes` but not its mutable counterpart `bytearray`, so any `bytearray` argument fell through to the catch-all type error. This affected every value path: `put`/bin values, `operate` operands, and notably the bit operations (`bit_insert`, `bit_set`, `bit_or`, `bit_and`, `bit_xor`, …) whose public signatures already advertise `value: Union[bytes, bytearray]`. A `bytearray` is now snapshotted via `to_vec()` and stored as the same `Value::Blob` as the equivalent `bytes`.
- `map_get_by_index_range`, `map_get_by_rank_range`, `map_remove_by_index_range`, and `map_remove_by_rank_range` called without an explicit `count` now correctly select every element from the given index/rank to the end of the map. Previously an omitted `count` was silently collapsed to `count=1` in the native translation layer, so these calls returned (or removed) only a single element instead of the open-ended range the Python signature documents (`count: Optional[int] = None`). The fix uses `aerospike-core`'s open-ended `*_range_from` variants — matching how the equivalent list operations (`list_get_by_index_range`, etc.) already behaved.
- A 4-element key tuple `(namespace, set, key, digest)` whose explicit digest is not exactly 20 bytes now raises `ValueError` instead of being silently discarded. Previously a wrong-length digest (e.g. an off-by-one slice) was ignored and the client recomputed the digest from the user key, so the operation addressed a *different* record than the caller specified, with no error. A key tuple with more than 4 elements is likewise rejected now rather than having the extra elements silently ignored.
- Reading a record with a language-specific blob particle type (PYTHON_BLOB=8, JAVA_BLOB=5, CSHARP_BLOB=7, RUBY_BLOB=9, PHP_BLOB=10, ERLANG_BLOB=11, LUA_BLOB=22) no longer aborts the Python process. The native panic from `aerospike-core` is now caught at every read/write entry point and surfaced to Python as `aerospike_py.RustPanicError` (subclass of `ClientError`), so callers can `try/except` around individual operations or per-record in scans/batch reads. The bin data itself is not recovered — the operation reports the failure and aborts; only the Python process survives. Closes #280.

### Changed
- Release profile panic policy switched from `"abort"` to `"unwind"` to enable the `RustPanicError` recovery path. Wheel size grows accordingly: `+0.63 MB` / `+33%` on macOS arm64 with LTO=fat (1.99 MB → 2.66 MB); typically smaller on Linux x86_64. Hot-path read/write throughput is unaffected (LLVM `invoke` vs `call` is a no-op on modern CPUs when no panic propagates).

### Added
- `aerospike_py.RustPanicError` — re-exported from the top-level package and from `aerospike_py.exception`. Catch it (or its parent `ClientError`) to handle records that the underlying Rust client cannot decode.

### Changed (BREAKING)
- `Client.batch_read` and `AsyncClient.batch_read` now return a **`LazyBatchRecords`** (zero-conversion wrapper around the raw Rust results). Materialise explicitly via `.to_dict()` for a `dict[UserKey, bins_dict]` or `.to_numpy(dtype)` for a `NumpyBatchRecords`. `LazyBatchRecords` also implements the dict-style Mapping protocol (`__getitem__`, `__contains__`, `__iter__`, `__len__`, `keys`, `values`, `items`, `get`) backed by a single cached `to_dict()` materialisation, so existing dict-style call sites keep working without a `.to_dict()` rewrite. The previous `_dtype=` kwarg on `batch_read` is removed; switch to `(await client.batch_read(keys)).to_numpy(dtype)`. The transitional `as_dict()` / `merge_as_dict()` aliases that briefly existed during this release cycle are also removed — use `to_dict()` / `merge_to_dict()` directly. Migration:
    ```python
    # Before
    for br in result.batch_records:
        if br.result == 0: print(br.record.bins)
    # After (explicit)
    for user_key, bins in result.to_dict().items():
        print(user_key, bins)
    # After (dict-style, no rewrite)
    for user_key, bins in result.items():
        print(user_key, bins)
    ```
- `Client.batch_operate`, `Client.batch_remove`, `AsyncClient.batch_operate`, `AsyncClient.batch_remove` now declare their return type as `BatchWriteResult` in the type stubs (previously `BatchRecords`). Runtime shape is unchanged — `BatchWriteResult` is a NamedTuple with `.batch_records: list[BatchRecord]`. Typecheckers may flag code that still expects the old annotation.
- `BatchRecord` (used inside `BatchWriteResult`) now carries an `in_doubt: bool = False` field indicating whether a transport-level ambiguity occurred. Positional unpacking (`key, result, record = br`) breaks; switch to attribute access.
- New top-level exports in `aerospike_py.__all__`: `BatchWriteResult`, `UserKey`, `AerospikeRecord`. Previously only `BatchRecord` and `BatchRecords` were exported.
- `LazyBatchRecords.all_user_keys()` is **positional** and now returns `list[UserKey | None]` instead of dropping digest-only requests. Every batch record gets exactly one slot in request order — digest-only requests yield `None` rather than being filtered out — so `zip(handle.all_user_keys(), handle.batch_records)` and downstream NumPy-row alignment work in mixed batches. Callers that previously assumed every element was a non-None `str/int/bytes` (`set(handle.all_user_keys())`, `for k in handle.all_user_keys(): k.startswith(...)`, requeuing the list into another `batch_read`) must filter `None` first:
    ```python
    # Before (filtered, length <= len(batch_records))
    for k in handle.all_user_keys():
        do_something(k)
    # After (positional, length == len(batch_records))
    for k in handle.all_user_keys():
        if k is None:
            continue          # digest-only slot
        do_something(k)
    ```
    **Heads-up: `None` is hashable.** `set(handle.all_user_keys())` and `dict.fromkeys(handle.all_user_keys())` *silently include* `None` rather than raising — the failure only surfaces a step later when downstream code does `k.startswith(...)` / sends `None` back into a `batch_read` and hits `AttributeError` / `TypeError`. Strip `None` before any aggregate-into-set/dict operation:
    ```python
    requested_keys = {k for k in handle.all_user_keys() if k is not None}
    ```
    `LazyBatchRecords.keys()` (Mapping-protocol view) is unchanged — it still excludes digest-only / failed slots and matches `to_dict().keys()`. Use `keys()` when you want the dict-view cardinality; use `all_user_keys()` when you need positional alignment.

### Changed
- Internal: `PyAsyncClient::close` and `PyAsyncClient::__aexit__` (Rust, PyO3) share a new `prepare_close()` helper. Python users of `aerospike_py.AsyncClient` see no behaviour change — the Python wrapper's `__aexit__` already delegated to `close()`, so `async with` exiting during an in-flight `connect()` has always raised `ClientError`. The refactor removes a dead-code divergence at the native layer. Closes #293.
- Native Rust MSRV raised to **1.87** (`rust-version = "1.87"` in `rust/Cargo.toml`, mirrored by the `MSRV` env in the CI `msrv-check` job). The resolved dependency tree pulls in `aerospike-rt 2.0.0`, whose manifest declares `rust-version = "1.87"`, so the resolver fails on older toolchains with `aerospike-rt@2.0.0 requires rustc 1.87`. This 1.87 floor subsumes the intermediate 1.85 requirement from `block-buffer 0.12.0` (via `digest 0.11`, whose manifest declares `edition = "2024"`, stabilised in Rust 1.85) and the older 1.80 floor the crate's own code needed (std items stabilised in 1.77 / 1.80, plus `Mutex::clear_poison()` (1.74+) used by `LazyBatchRecords::release_cache`'s poison-recovery path). Only affects `pip install --no-binary` / `cargo install` builds; the published wheels remain compatible with their existing Python version range.

### Added
- `Client.batch_write` / `AsyncClient.batch_write` — per-record bins with optional per-record TTL via `WriteMeta`. Each entry is `(key, bins)` or `(key, bins, meta)`.
- `LazyBatchRecords` — zero-conversion wrapper returned by both sync and async `batch_read`; methods include `to_dict()`, `to_numpy(dtype)`, `batch_records`, `iter_records()`, `all_user_keys()`, `keys()`, `values()`, `items()`, `get()`, `found_count()`, `release_cache()`, and a static `merge_to_dict()` for combining multiple results in a single GIL acquisition.
- `AsyncClient` lifecycle state machine — explicit `Disconnected → Connecting → Connected → Closing` transitions with idempotent `close()`; `connect()` now errors when called on a non-disconnected client.
- Internal stage profiling metric `db_client_internal_stage_seconds` — off by default, opt-in via `aerospike_py.set_internal_stage_metrics_enabled(True)`, the `aerospike_py.internal_stage_profiling()` context manager, or the `AEROSPIKE_PY_INTERNAL_METRICS=1` environment variable (case-insensitive: `1`, `true`, `yes`, `on`). Stages captured for `batch_read`: `key_parse`, `future_into_py_setup`, `tokio_schedule_delay`, `limiter_wait`, `io`, `spawn_blocking_delay`, `into_pyobject`, `event_loop_resume_delay`, `to_dict`, `to_numpy`, `merge_to_dict`.
- NumPy-based batch write support (`batch_write_numpy`) for high-throughput ingestion
- OpenTelemetry distributed tracing with OTLP export and connection-level attributes
- Prometheus-compatible metrics for database operation monitoring
- Structured logging bridge from Rust to Python
- `info_all()` and `info_random_node()` for cluster information queries
- CDT (List/Map) operations and expression filter API
- NamedTuple/TypedDict return types for all API methods
- `AsyncClient` with full async context manager support
- Official aerospike-client-python compatibility test suite
- Python 3.14t (free-threaded) support with `gil_used=true` declaration
- Bug report logging for unexpected internal errors
- FastAPI integration example with observability endpoints

### Changed
- License changed from AGPL-3.0 to Apache-2.0
- Package renamed to `aerospike-py` with dynamic versioning
- Removed deprecated Scan API (use Query with no predicate instead)
- Removed deprecated `get_many`/`exists_many`/`select_many` (use `batch_operate`)
- Narrowed Tokio features for smaller binary size
- Cached default `ReadPolicy`/`WritePolicy` for hot-path performance

### Fixed
- `put()` now allows `None` bin values for single-bin deletion
- `remove()` properly raises `RecordNotFound` for missing keys
- `get()`/`select()`/`operate()` return key tuple instead of `None`
- Recursion depth limit added to nested Python-to-Value conversion
- Resolved Python 3.14t import failure caused by Cargo cache contamination
- Renamed `TimeoutError`/`IndexError` to avoid shadowing Python builtins

### Performance
- `batch_write` / `batch_write_numpy` now share a single `Arc<BatchWritePolicy>` across all records instead of deep-cloning the policy per record. Per-record meta still allocates a fresh `Arc`, but the common no-meta path (the whole numpy hot path) drops to a refcount bump. Closes #294.
- PyO3 binding CPU overhead reduced via OTel fast-path and type conversion optimizations
- Cargo release profile with LTO and single codegen unit for smaller, faster binaries
- Cached default policies eliminate repeated allocation on `put()`/`get()`/`select()`/`exists()`
- Process-level CPU efficiency benchmarking (ops/CPU-sec metric)

## [0.0.1.beta2] - 2026-02-22

[0.0.1.beta2]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.beta1...v0.0.1.beta2

### Added
- Documentation versioning infrastructure with tab-separated CDT operations
- Bug report logging for unexpected internal errors

## [0.0.1.beta1] - 2026-02-22

[0.0.1.beta1]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.alpha6...v0.0.1.beta1

### Added
- `batch_write_numpy` API for high-throughput NumPy-based batch writes
- Restructured documentation with sub-categories and domain-specific skill files
- Comprehensive Rust doc comments for all public items

### Changed
- Major code deduplication and infrastructure refactoring (Phase 3)
- Split monolithic docs into Read/Write guides and merged CDT operations

## [0.0.1.alpha6] - 2026-02-16

[0.0.1.alpha6]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.alpha4...v0.0.1.alpha6

### Added
- `get_many()` for batch get operations on Client and AsyncClient

### Fixed
- Python 3.14t import failure caused by Cargo cache contamination
- `remove()` raises `RecordNotFound` for missing keys; `put()` allows `None` bin values
- `get()`/`select()`/`operate()` return key tuple instead of `None`

### Changed
- Declared `gil_used=true` for free-threaded Python 3.14t compatibility
- Removed deprecated `get_many()` method (replaced by `batch_operate`)

## [0.0.1.alpha4] - 2026-02-10

[0.0.1.alpha4]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.alpha3...v0.0.1.alpha4

### Added
- `info_all()` and `info_random_node()` for cluster information queries
- OpenTelemetry tracing with OTLP export and connection-level attributes
- Prometheus-compatible metrics for database operation monitoring
- Observability documentation (logging, metrics, distributed tracing)

### Fixed
- PEP 440 to Cargo semver version conversion in publish workflow

## [0.0.1.alpha3] - 2026-02-05

[0.0.1.alpha3]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.alpha...v0.0.1.alpha3

### Added
- Unit tests for predicates module
- PyPI classifiers, keywords, and project URLs

### Changed
- Merged `tox.toml` into `pyproject.toml` with dependency-groups
- Added explicit ruff lint configuration

### Performance
- Cached `DEFAULT_READ_POLICY` in `select()` and `exists()`
- Cargo release profile with LTO and single codegen unit
