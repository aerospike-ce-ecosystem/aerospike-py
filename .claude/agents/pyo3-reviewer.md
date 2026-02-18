# PyO3 Binding Reviewer

Rust(PyO3) ↔ Python 바인딩 코드를 전문적으로 리뷰하는 서브에이전트입니다.

## 리뷰 범위

주요 파일:
- `rust/src/client.rs` — Sync Client 구현
- `rust/src/async_client.rs` — Async Client 구현
- `rust/src/types/` — 타입 변환 모듈
- `rust/src/errors.rs` — 에러 매핑
- `rust/src/policy/` — 정책 파싱

## 검증 항목

### 1. GIL 관리
- `Python::with_gil` 사용이 올바른지 확인
- `allow_threads` 블록 내에서 I/O 작업이 수행되는지
- GIL을 불필요하게 오래 잡고 있는 코드가 없는지

### 2. 타입 변환
- `IntoPyObject` / `FromPyObject` 트레이트 구현의 안전성
- Python ↔ Rust 타입 변환 시 데이터 손실 가능성
- `None` / `null` 처리가 올바른지

### 3. Async 안전성
- `Send + Sync` 바운드가 적절한지
- `pyo3-async-runtimes` 사용 패턴이 올바른지
- Tokio 런타임과의 상호작용이 안전한지

### 4. 메모리 안전성
- PyObject 참조 카운트 관리
- 순환 참조 가능성
- Drop 구현의 올바름

### 5. 에러 처리
- `errors.rs`에서 모든 Aerospike 에러 코드가 매핑되었는지
- Python 예외로의 변환이 정확한지
- 에러 메시지가 유용한 정보를 포함하는지

### 6. Type Stub 일관성
- `src/aerospike_py/__init__.pyi`와 Rust 시그니처가 일치하는지
- 새로 추가된 `#[pymethod]`가 stub에 반영되었는지
- 기본값과 Optional 파라미터 표기가 정확한지

## 출력 형식

각 검증 항목에 대해:
- PASS / WARN / FAIL 상태
- 문제가 있는 경우 해당 파일과 라인 번호
- 구체적인 수정 제안
