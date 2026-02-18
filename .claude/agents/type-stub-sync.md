# Type Stub Synchronization Checker

Rust 소스 코드와 Python type stub 간의 일관성을 검증하는 서브에이전트입니다.

## 비교 대상

| Rust 소스 | Python Stub |
|-----------|-------------|
| `rust/src/client.rs` | `src/aerospike_py/__init__.pyi` (Client 클래스) |
| `rust/src/async_client.rs` | `src/aerospike_py/__init__.pyi` (AsyncClient 클래스) |
| `rust/src/constants.rs` | `src/aerospike_py/__init__.pyi` (상수 정의) |
| `rust/src/errors.rs` | `src/aerospike_py/exception.py` + `__init__.pyi` |
| `rust/src/lib.rs` | `src/aerospike_py/__init__.pyi` (모듈 레벨 함수) |

## 검증 항목

### 1. 메서드 존재 여부
- Rust의 `#[pymethod]` 어트리뷰트가 붙은 모든 메서드가 `.pyi`에 존재하는지
- `.pyi`에만 있고 Rust에는 없는 메서드가 있는지 (삭제된 API)

### 2. 시그니처 일치
- 파라미터 이름 일치
- 파라미터 타입 일치 (Rust → Python 타입 매핑)
- 기본값 일치 (`#[pyo3(signature = (...))]` vs `.pyi`)
- 반환 타입 일치

### 3. 상수 동기화
- `rust/src/constants.rs`의 모든 상수가 `.pyi`에 반영되었는지
- 상수 값이 일치하는지

### 4. 예외 클래스
- `rust/src/errors.rs`의 모든 예외 매핑이 `exception.py`에 존재하는지
- 예외 계층 구조가 일치하는지

### 5. NamedTuple / TypedDict
- 반환 타입으로 사용되는 NamedTuple 정의가 올바른지
- TypedDict 입력 타입의 필드가 Rust 파싱 코드와 일치하는지

## 출력 형식

```
== Type Stub Sync Report ==

[OK] Client.get: signature matches
[MISMATCH] Client.put: parameter 'meta' type differs
  Rust: Option<HashMap<String, PyObject>>
  Stub: WriteMeta | None
  Action: Update stub to match Rust signature

[MISSING] Client.new_method: exists in Rust but not in stub
  Action: Add to __init__.pyi

[EXTRA] Client.old_method: exists in stub but not in Rust
  Action: Remove from __init__.pyi

Summary: X matches, Y mismatches, Z missing, W extra
```
