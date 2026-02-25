# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
- PyO3 binding CPU overhead reduced via OTel fast-path and type conversion optimizations
- Cargo release profile with LTO and single codegen unit for smaller, faster binaries
- Cached default policies eliminate repeated allocation on `put()`/`get()`/`select()`/`exists()`
- Process-level CPU efficiency benchmarking (ops/CPU-sec metric)
