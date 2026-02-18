---
name: new-api
description: Guide for adding a new Client/AsyncClient API method across Rust, Python wrapper, type stubs, and tests
args: "[method-name] [description]"
---

# New API Method

aerospike-py에 새로운 Client/AsyncClient API 메서드를 추가합니다. Rust 구현부터 Python 타입 스텁, 테스트까지 모든 레이어를 일관되게 생성합니다.

## 인자

`/new-api [method-name] [description]` 형식으로 호출합니다.

- `method-name`: 추가할 메서드 이름 (예: `get_key_digest`)
- `description`: 메서드 동작 설명 (예: "키의 RIPEMD-160 digest를 반환")

## 수정 대상 파일 체크리스트

새 API 메서드를 추가할 때 반드시 아래 파일들을 **모두** 수정해야 합니다:

| 순서 | 파일 | 역할 |
|------|------|------|
| 1 | `rust/src/client.rs` | Sync Client Rust 구현 (`#[pymethods] impl PyClient`) |
| 2 | `rust/src/async_client.rs` | Async Client Rust 구현 (`#[pymethods] impl PyAsyncClient`) |
| 3 | `src/aerospike_py/__init__.py` | Python 래퍼 (NamedTuple 변환이 필요한 경우만) |
| 4 | `src/aerospike_py/__init__.pyi` | 타입 스텁 (Client 클래스 + AsyncClient 클래스 양쪽) |
| 5 | `tests/unit/test_*.py` | 유닛 테스트 (서버 불필요, 인자 검증 등) |
| 6 | `tests/integration/test_*.py` | 통합 테스트 (실제 Aerospike 서버 필요) |

필요에 따라 추가로 수정할 수 있는 파일:

| 파일 | 조건 |
|------|------|
| `rust/src/policy/*.rs` | 새 정책 타입이 필요한 경우 |
| `rust/src/types/*.rs` | 새 타입 변환이 필요한 경우 |
| `rust/src/errors.rs` | 새 에러 타입이 필요한 경우 |
| `rust/src/operations.rs` | operate 연산 추가 시 |
| `src/aerospike_py/types.py` | 새 NamedTuple/TypedDict가 필요한 경우 |
| `CLAUDE.md` | API 문서 테이블에 새 메서드 추가 |

## 실행 단계

### 1. aerospike_core API 확인

먼저 `aerospike_core` 크레이트에서 사용할 수 있는 API를 확인합니다:

```bash
cargo doc --manifest-path rust/Cargo.toml --open
```

또는 `rust/Cargo.toml`에서 aerospike_core 버전을 확인하고 docs.rs에서 API를 검색합니다.

### 2. Rust Sync Client 구현 (`rust/src/client.rs`)

`#[pymethods] impl PyClient` 블록 안에 메서드를 추가합니다.

**패턴 참조** — 기존 `put` 메서드 구조를 따릅니다:

```rust
/// [docstring 설명]
#[pyo3(signature = (key, param1, param2=None, policy=None))]
fn method_name(
    &self,
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    param1: /* type */,
    param2: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult</* return type */> {
    let client = self.get_client()?;
    let rust_key = py_to_key(key)?;

    // OTel 트레이싱 컨텍스트 추출
    #[cfg(feature = "otel")]
    let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
    #[cfg(not(feature = "otel"))]
    let parent_ctx = ();
    let conn_info = self.connection_info.clone();

    // 정책이 없으면 기본값 사용 (빠른 경로)
    if policy.is_none() {
        let result = traced_op!(
            "method_name", parent_ctx, conn_info,
            rust_key.namespace, rust_key.set_name,
            client.method_name(&DEFAULT_POLICY, &rust_key)
        );
        return match result {
            Ok(val) => /* convert to Python */,
            Err(e) => Err(as_to_pyerr(e)),
        };
    }

    let parsed_policy = parse_read_policy(policy)?;
    let result = traced_op!(
        "method_name", parent_ctx, conn_info,
        rust_key.namespace, rust_key.set_name,
        client.method_name(&parsed_policy, &rust_key)
    );
    match result {
        Ok(val) => /* convert to Python */,
        Err(e) => Err(as_to_pyerr(e)),
    }
}
```

**핵심 규칙:**
- `#[pyo3(signature = (...))]` 매크로로 Python 시그니처 명시
- `self.get_client()?`로 연결 상태 확인
- `traced_op!` 매크로로 OTel 스팬 래핑
- 에러는 `as_to_pyerr()`로 Python 예외 변환
- 반환 타입 변환: `record_to_py()`, `key_to_py()`, `value_to_py()` 등 기존 헬퍼 활용

### 3. Rust Async Client 구현 (`rust/src/async_client.rs`)

Sync와 동일한 로직이지만, `future_into_py`로 감싸야 합니다:

```rust
fn method_name<'py>(
    &self,
    py: Python<'py>,
    /* 동일한 파라미터 */
) -> PyResult<Bound<'py, PyAny>> {
    let client = self.get_client()?;
    let rust_key = py_to_key(key)?;
    let parsed_policy = parse_read_policy(policy)?;

    #[cfg(feature = "otel")]
    let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
    #[cfg(not(feature = "otel"))]
    let parent_ctx = ();
    let conn_info = self.connection_info.clone();

    future_into_py(py, async move {
        let result = traced_op!(
            "method_name", parent_ctx, conn_info,
            rust_key.namespace, rust_key.set_name,
            client.method_name(&parsed_policy, &rust_key).await
        );
        match result {
            Ok(val) => Python::with_gil(|py| /* convert to Python */),
            Err(e) => Err(as_to_pyerr(e)),
        }
    })
}
```

**핵심 차이:**
- 반환 타입이 `PyResult<Bound<'py, PyAny>>`
- `future_into_py(py, async move { ... })` 사용
- aerospike_core 호출에 `.await` 추가
- Python 객체 생성 시 `Python::with_gil(|py| ...)` 사용

### 4. Python 래퍼 (`src/aerospike_py/__init__.py`)

반환값이 Record, ExistsResult 등 NamedTuple로 변환이 필요한 경우에만 래퍼를 추가합니다.

**`Client` 클래스** (`class Client(_NativeClient):`):
```python
def method_name(self, key, param1, policy=None) -> Record:
    return _wrap_record(super().method_name(key, param1, policy))
```

**`AsyncClient` 클래스** (`class AsyncClient(_NativeAsyncClient):`):
```python
async def method_name(self, key, param1, policy=None) -> Record:
    return _wrap_record(await super().method_name(key, param1, policy))
```

NamedTuple 래핑이 필요 없는 메서드(예: `put`, `remove` 등 void 반환)는 네이티브 메서드가 직접 노출되므로 래퍼 불필요.

### 5. 타입 스텁 (`src/aerospike_py/__init__.pyi`)

**Client 클래스**와 **AsyncClient 클래스** 양쪽에 시그니처를 추가합니다:

```python
# Client 클래스 내
def method_name(
    self,
    key: Key,
    param1: str,
    param2: Optional[dict[str, Any]] = None,
    policy: Optional[ReadPolicy] = None,
) -> Record: ...

# AsyncClient 클래스 내
async def method_name(
    self,
    key: Key,
    param1: str,
    param2: Optional[dict[str, Any]] = None,
    policy: Optional[ReadPolicy] = None,
) -> Record: ...
```

**주의:** 기존 메서드 시그니처와 일관된 순서, 네이밍, 타입을 유지합니다.

### 6. 유닛 테스트 (`tests/unit/`)

서버 없이 실행 가능한 테스트를 작성합니다. 주로 인자 검증, 타입 에러, 연결 안 된 상태에서의 에러를 테스트합니다:

```python
import pytest
import aerospike_py

class TestMethodName:
    def test_not_connected_raises_error(self):
        client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]})
        with pytest.raises(aerospike_py.ClientError):
            client.method_name(("test", "demo", "key1"), "param1")

    def test_invalid_key_type_raises_error(self):
        client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]})
        with pytest.raises((TypeError, aerospike_py.ClientError)):
            client.method_name("invalid_key", "param1")
```

### 7. 통합 테스트 (`tests/integration/`)

실제 Aerospike 서버와 통신하는 테스트를 작성합니다. `conftest.py`의 `client`, `async_client`, `cleanup` fixture를 활용합니다:

```python
import pytest

class TestMethodName:
    def test_basic_usage(self, client, cleanup):
        key = ("test", "demo", "test_method_name")
        cleanup.append(key)
        client.put(key, {"name": "Alice"})

        result = client.method_name(key, "param1")
        assert result is not None

    async def test_async_basic_usage(self, async_client, async_cleanup):
        key = ("test", "demo", "test_async_method_name")
        async_cleanup.append(key)
        await async_client.put(key, {"name": "Alice"})

        result = await async_client.method_name(key, "param1")
        assert result is not None
```

### 8. 빌드 및 검증

```bash
# 컴파일 체크 (빠른 확인)
cargo check --manifest-path rust/Cargo.toml

# 빌드
make build

# 타입 체크
uv run pyright

# 유닛 테스트
uv run pytest tests/unit/ -v -k "test_method_name"

# 통합 테스트 (서버 필요)
uv run pytest tests/integration/ -v -k "test_method_name"
```

### 9. CLAUDE.md 업데이트

`CLAUDE.md`의 해당 API 테이블 섹션에 새 메서드를 추가합니다.

## 주의사항

- **Sync/Async 일관성**: 반드시 `client.rs`와 `async_client.rs` 양쪽에 구현합니다. AsyncClient의 `query()` 같은 예외적인 경우만 한쪽에만 존재합니다.
- **OTel 트레이싱**: 모든 I/O 메서드는 `traced_op!` 매크로로 감싸야 합니다.
- **타입 스텁 동기화**: `.pyi` 파일의 시그니처가 Rust 구현과 정확히 일치해야 합니다. `type-stub-sync` 에이전트로 검증할 수 있습니다.
- **NamedTuple 반환**: `get`, `select`, `exists`, `operate`, `operate_ordered`, `info_all` 등은 Python 래퍼에서 NamedTuple로 변환합니다. 새 메서드도 복합 반환값이면 적절한 NamedTuple을 정의합니다.
- **GIL 안전성**: async 메서드에서 Python 객체를 생성할 때는 반드시 `Python::with_gil` 안에서 수행합니다.
