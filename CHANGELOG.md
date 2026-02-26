# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

[Unreleased]: https://github.com/KimSoungRyoul/aerospike-py/compare/v0.0.1.beta2...HEAD

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
