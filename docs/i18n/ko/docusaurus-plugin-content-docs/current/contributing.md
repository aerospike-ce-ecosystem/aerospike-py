---
title: Contributing
sidebar_label: Contributing
sidebar_position: 100
description: Development setup, build, test, and code style guidelines.
---

## Setup

```bash
git clone https://github.com/aerospike-ce-ecosystem/aerospike-py.git
cd aerospike-py
make install          # uv sync --all-groups
make build            # uv run maturin develop --release
```

## Aerospike 시작

```bash
make run-aerospike-ce   # port 18710 의 Aerospike CE
```

## Build

```bash
make build                    # Release build (권장)
maturin develop               # Debug build (컴파일 더 빠름)
maturin build --release       # wheel 빌드
```

## Test

```bash
make test-unit          # 서버 불필요
make test-integration   # 서버 필요
make test-all           # 전체 테스트
```

## Lint & Format

```bash
make lint     # ruff check + cargo clippy
make fmt      # ruff format + cargo fmt
```

## Pre-commit

```bash
pip install pre-commit
pre-commit install
```

## Project Structure

```
aerospike-py/
├── rust/src/               # PyO3 Rust bindings
│   ├── client.rs           # Sync Client
│   ├── async_client.rs     # Async Client
│   ├── errors.rs           # Error → Exception
│   ├── types/              # Type converter
│   └── policy/             # Policy parser
├── src/aerospike_py/       # Python package
├── tests/                  # unit/ integration/ concurrency/ compatibility/
├── docs/                   # Docusaurus
└── benchmark/              # Benchmark
```

## 변경 가이드

1. **Rust** (`rust/src/`): 편집 후 `maturin develop` 으로 재빌드
2. **Python** (`src/aerospike_py/`): 변경 즉시 반영
3. **Tests**: `tests/unit/` 또는 `tests/integration/` 에 추가
4. **Docs**: `docs/docs/` 편집, `cd docs && npm start` 로 미리보기

## 아키텍처 노트

- **Sync Client**: 전역 Tokio runtime, `py.allow_threads(|| RUNTIME.block_on(...))` 가 GIL release
- **Async Client**: `pyo3_async_runtimes::tokio::future_into_py()` 가 Python coroutine 반환
- **Type conversion**: `types/value.rs` 안에서 Python ↔ Rust `Value` enum
- **Error mapping**: `errors.rs` 안에서 `aerospike_core::Error` → Python exception
