---
name: release-check
description: Run pre-release validation (lint, unit tests, type check, stub consistency)
disable-model-invocation: true
---

# Release Check

릴리스 전 전체 검증을 수행합니다. 아래 단계를 순서대로 실행하세요.

## 검증 단계

### 1. Lint 검사
```bash
make lint
```
내부적으로 실행되는 명령어:
- `uv run ruff check src/ tests/ benchmark/` - Python 린트
- `uv run ruff format --check src/ tests/ benchmark/` - Python 포맷 확인
- `cargo clippy --manifest-path rust/Cargo.toml --features otel -- -D warnings` - Rust 린트 (otel feature 포함, 경고를 에러로)

모든 경고/에러가 해결되어야 합니다.

### 2. 포맷 자동 수정 (필요 시)
```bash
make fmt
```
내부적으로 실행되는 명령어:
- `uv run ruff format src/ tests/ benchmark/`
- `uv run ruff check --fix src/ tests/ benchmark/`
- `cargo fmt --manifest-path rust/Cargo.toml`

### 3. 유닛 테스트
```bash
make test-unit
```
서버 없이 실행 가능한 모든 유닛 테스트를 실행합니다. 빌드 포함 (`maturin develop --release`).

### 4. Pyright 타입 체크
```bash
uv run pyright src/
```
Python 타입 에러가 없는지 확인합니다. 설정 (`pyproject.toml`):
- `pythonVersion = "3.10"` (최소 지원 버전 기준)
- `typeCheckingMode = "basic"`
- `include = ["src/aerospike_py"]`

### 5. Type Stub 일관성 검증

`src/aerospike_py/__init__.pyi`와 Rust 구현을 비교합니다:

**확인 사항:**

| 검증 항목 | 비교 대상 |
|-----------|-----------|
| Sync Client 메서드 | `.pyi` `class Client` vs `rust/src/client.rs` `#[pymethods] impl PyClient` |
| Async Client 메서드 | `.pyi` `class AsyncClient` vs `rust/src/async_client.rs` `#[pymethods] impl PyAsyncClient` |
| Python 래퍼 메서드 | `.pyi` vs `src/aerospike_py/__init__.py` `class Client` / `class AsyncClient` |
| 시그니처 일치 | 파라미터 이름, 타입, 기본값, 반환 타입 |
| 상수 완전성 | `.pyi` 상수 vs `rust/src/constants.rs` + `__init__.py` re-export |
| 예외 클래스 | `.pyi` / `exception.pyi` vs `rust/src/errors.rs` |
| NamedTuple 정의 | `.pyi` 타입 vs `src/aerospike_py/types.py` |

**빠른 확인 방법:**
```bash
# Rust에서 #[pyo3(signature 가 있는 메서드 목록
grep -n '#\[pyo3(signature' rust/src/client.rs rust/src/async_client.rs

# .pyi에서 정의된 메서드 목록
grep -n 'def ' src/aerospike_py/__init__.pyi | head -60
```

### 6. 버전 확인

`pyproject.toml`의 `version` 필드가 올바르게 업데이트되었는지 확인합니다:
```bash
grep 'version' pyproject.toml
```
참고: 이 프로젝트는 `dynamic = ["version"]`이며 maturin이 `Cargo.toml`에서 버전을 가져옵니다.
```bash
grep '^version' rust/Cargo.toml
```

git tag와 일치하는지도 확인합니다:
```bash
git tag --sort=-version:refname | head -5
```

### 7. Pre-commit Hook 전체 실행
```bash
uvx pre-commit run --all-files
```
CI의 lint job에서도 이 명령을 실행합니다. 포함 항목:
- trailing-whitespace
- ruff format / ruff lint
- pyright
- cargo fmt
- cargo clippy (-D warnings)

### 8. Python 버전 매트릭스 테스트 (선택)
```bash
make test-matrix
```
Python 3.10, 3.11, 3.12, 3.13, 3.14, 3.14t (free-threaded) 전체에서 유닛 테스트를 실행합니다.
tox-uv를 사용하여 각 Python 버전별 가상환경을 자동 생성합니다.

### 9. 통합 테스트 (서버 필요, 선택)
```bash
make test-all
```
Aerospike 서버가 실행 중이어야 합니다 (`make run-aerospike-ce`).
모든 테스트 스위트를 실행합니다 (unit + integration + concurrency + feasibility + compat).

## 결과 보고

각 단계의 성공/실패를 요약하고, 실패한 항목에 대해 수정 방법을 제안합니다.

**릴리스 가능 조건:**
1. `make lint` 통과 (ruff + clippy 경고 0개)
2. `make test-unit` 통과
3. `uv run pyright src/` 에러 0개
4. Type stub 일관성 확인
5. 버전 번호 정확
6. (권장) `make test-matrix` 전체 통과
7. (권장) `make test-all` 전체 통과 (서버 필요)
