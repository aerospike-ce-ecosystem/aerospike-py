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
ruff check + cargo clippy (-D warnings) 실행. 모든 경고/에러가 해결되어야 합니다.

### 2. 유닛 테스트
```bash
make test-unit
```
서버 없이 실행 가능한 모든 유닛 테스트를 실행합니다.

### 3. Pyright 타입 체크
```bash
uv run pyright src/
```
Python 타입 에러가 없는지 확인합니다.

### 4. Type Stub 일관성 검증
`src/aerospike_py/__init__.pyi`와 `rust/src/client.rs`, `rust/src/async_client.rs`를 비교합니다:
- 모든 `#[pymethod]`가 `.pyi`에 반영되었는지
- 시그니처(파라미터 이름, 타입, 기본값) 일치 여부
- 반환 타입 정확성 확인
- 누락된 상수나 예외 클래스 확인

### 5. 버전 확인
`pyproject.toml`의 `version` 필드가 올바르게 업데이트되었는지 확인합니다.
git tag와 일치하는지도 확인합니다.

## 결과 보고

각 단계의 성공/실패를 요약하고, 실패한 항목에 대해 수정 방법을 제안합니다.
