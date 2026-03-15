# Goal 1: Rust v2 바인딩

aerospike-client-rust v2 (`2.0.0-alpha.9`)를 PyO3로 래핑하여 sync/async 양쪽 Python API를 제공한다.

## 기술 스택

| 컴포넌트 | 버전 |
|---------|------|
| `aerospike` crate (features: `async`, `rt-tokio`) | `2.0.0-alpha.9` |
| PyO3 | `0.28.2` |
| pyo3-async-runtimes (feature: `tokio-runtime`) | `0.28` |
| Tokio (multi-thread) | `1.x` |

## GIL 패턴

- **Sync** (`client.rs`): `py.detach(|| RUNTIME.block_on(async { ... }))` — 모든 I/O 메서드에 일관 적용
- **Async** (`async_client.rs`): `future_into_py(py, async move { ... })` — Python awaitable 반환, `Python::attach()`로 결과 변환

## 구현 완료 API

CRUD · operate · batch(read/write/remove) · query · index · truncate · UDF · admin · info

## 주요 파일

- `rust/src/client.rs` — sync PyClient
- `rust/src/async_client.rs` — async PyAsyncClient
- `rust/src/runtime.rs` — Tokio 런타임 초기화
- `rust/Cargo.toml` — crate 버전 및 features
