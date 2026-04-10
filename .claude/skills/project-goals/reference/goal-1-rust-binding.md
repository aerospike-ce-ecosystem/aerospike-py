# Goal 1: Rust v2 Bindings

Wraps aerospike-client-rust v2 (`2.0.0-alpha.9`) via PyO3 to provide both sync/async Python APIs.

## Tech Stack

| Component | Version |
|---------|------|
| `aerospike` crate (features: `async`, `rt-tokio`) | `2.0.0-alpha.9` |
| PyO3 | `0.28.2` |
| pyo3-async-runtimes (feature: `tokio-runtime`) | `0.28` |
| Tokio (multi-thread) | `1.x` |

## GIL Patterns

- **Sync** (`client.rs`): `py.detach(|| RUNTIME.block_on(async { ... }))` — applied consistently to all I/O methods
- **Async** (`async_client.rs`): `future_into_py(py, async move { ... })` — returns Python awaitable, converts results via `Python::attach()`

## Implemented APIs

CRUD · operate · batch(read/write/remove) · query · index · truncate · UDF · admin · info

## Key Files

- `rust/src/client.rs` — sync PyClient
- `rust/src/async_client.rs` — async PyAsyncClient
- `rust/src/runtime.rs` — Tokio runtime initialization
- `rust/Cargo.toml` — crate versions and features
