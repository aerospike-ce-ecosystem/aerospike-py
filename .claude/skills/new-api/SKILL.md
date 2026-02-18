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
| 1 | `rust/src/client_common.rs` | 공유 파라미터 파싱 함수 (`prepare_*_args`) |
| 2 | `rust/src/client.rs` | Sync Client Rust 구현 (`#[pymethods] impl PyClient`) |
| 3 | `rust/src/async_client.rs` | Async Client Rust 구현 (`#[pymethods] impl PyAsyncClient`) |
| 4 | `src/aerospike_py/__init__.py` | Python 래퍼 (NamedTuple 변환이 필요한 경우만) |
| 5 | `src/aerospike_py/__init__.pyi` | 타입 스텁 (Client 클래스 + AsyncClient 클래스 양쪽) |
| 6 | `tests/unit/test_*.py` | 유닛 테스트 (서버 불필요, 인자 검증 등) |
| 7 | `tests/integration/test_*.py` | 통합 테스트 (실제 Aerospike 서버 필요) |

필요에 따라 추가로 수정할 수 있는 파일:

| 파일 | 조건 |
|------|------|
| `rust/src/policy/*.rs` | 새 정책 타입이 필요한 경우 |
| `rust/src/types/*.rs` | 새 타입 변환이 필요한 경우 |
| `rust/src/errors.rs` | 새 에러 타입이 필요한 경우 |
| `rust/src/operations.rs` | operate 연산 추가 시 |
| `src/aerospike_py/types.py` | 새 NamedTuple/TypedDict가 필요한 경우 |

## 실행 단계

### 1. aerospike_core API 확인

먼저 `aerospike_core` 크레이트에서 사용할 수 있는 API를 확인합니다:

```bash
cargo doc --manifest-path rust/Cargo.toml --open
```

또는 `rust/Cargo.toml`에서 aerospike-core 버전(`2.0.0-alpha.9`)을 확인하고 docs.rs에서 API를 검색합니다.

### 2. 공유 파라미터 파싱 (`rust/src/client_common.rs`)

sync/async 클라이언트 양쪽에서 동일한 파라미터 파싱 로직을 공유하기 위해 `prepare_*_args` 함수를 먼저 정의합니다.

**기존 패턴 참조** (예: `prepare_get_args`):

```rust
/// Parsed arguments for `get` / `select` operations.
pub(crate) struct GetArgs {
    pub key: aerospike_core::Key,
    pub parent_ctx: ParentContext,  // OTel 컨텍스트 (otel feature 시 opentelemetry::Context)
    pub conn_info: ConnectionInfo,
    read_policy: Option<aerospike_core::ReadPolicy>,
}

impl GetArgs {
    pub fn read_policy(&self) -> &aerospike_core::ReadPolicy {
        self.read_policy
            .as_ref()
            .unwrap_or(&*DEFAULT_READ_POLICY)
    }
}

pub(crate) fn prepare_get_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<GetArgs> {
    let rust_key = py_to_key(key)?;

    #[cfg(feature = "otel")]
    let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
    #[cfg(not(feature = "otel"))]
    let parent_ctx = ();

    let rp = policy.map(parse_read_policy).transpose()?;

    Ok(GetArgs {
        key: rust_key,
        parent_ctx,
        conn_info: conn_info.clone(),
        read_policy: rp,
    })
}
```

**핵심 포인트:**
- `ParentContext` 타입은 `otel` feature에 따라 `opentelemetry::Context` 또는 `()`.
- OTel 컨텍스트 추출은 **GIL 보유 상태에서** 수행해야 함 (Python SDK 호출 필요).
- 정책이 `None`이면 기본 정책(`DEFAULT_*_POLICY`)을 사용하는 빠른 경로 제공.

### 3. Rust Sync Client 구현 (`rust/src/client.rs`)

`#[pymethods] impl PyClient` 블록 안에 메서드를 추가합니다.

**실제 코드 패턴** (`put` 메서드 기준):

```rust
/// Write a record
#[pyo3(signature = (key, bins, meta=None, policy=None))]
fn put(
    &self,
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bins: &Bound<'_, PyAny>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<()> {
    // 1. 공유 함수로 파라미터 파싱 (GIL 보유 상태)
    let args = client_common::prepare_put_args(
        py, key, bins, meta, policy, &self.connection_info
    )?;
    let client = self.get_client()?;

    // 2. py.detach()로 GIL 해제 + RUNTIME.block_on()으로 async 실행
    match args.policy {
        PutPolicy::Default => {
            let wp = &*DEFAULT_WRITE_POLICY;
            py.detach(|| {
                RUNTIME.block_on(async {
                    traced_op!(
                        "put",
                        &args.key.namespace,
                        &args.key.set_name,
                        args.parent_ctx,
                        args.conn_info,
                        { client.put(wp, &args.key, &args.bins).await }
                    )
                })
            })
        }
        PutPolicy::Custom(ref wp) => py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "put",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.put(wp, &args.key, &args.bins).await }
                )
            })
        }),
    }
}
```

**핵심 규칙:**
- `#[pyo3(signature = (...))]` 매크로로 Python 시그니처 명시.
- `self.get_client()?`로 연결 상태 확인 (미연결 시 `ClientError` 발생).
- `py.detach(|| { ... })` 패턴으로 GIL을 해제하고 블로킹 실행.
- `RUNTIME.block_on(async { ... })` 안에서 aerospike_core의 async API 호출.
- `traced_op!` 매크로로 OTel 스팬 + Prometheus 메트릭 자동 계측.
- 에러는 `traced_op!` 매크로 내부에서 `as_to_pyerr()`로 Python 예외 변환.
- 반환 타입 변환: `record_to_py()`, `key_to_py()`, `value_to_py()` 등 기존 헬퍼 활용.

### 4. Rust Async Client 구현 (`rust/src/async_client.rs`)

Sync와 동일한 로직이지만, `future_into_py`로 감쌉니다.

**실제 코드 패턴** (`get` 메서드 기준):

```rust
/// Read a record
#[pyo3(signature = (key, policy=None))]
fn get<'py>(
    &self,
    py: Python<'py>,
    key: &Bound<'_, PyAny>,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let client = self.get_client()?;
    let args = client_common::prepare_get_args(
        py, key, policy, &self.connection_info
    )?;

    // future_into_py: Python awaitable 반환
    future_into_py(py, async move {
        let rp = args.read_policy();
        let record = traced_op!(
            "get",
            &args.key.namespace,
            &args.key.set_name,
            args.parent_ctx,
            args.conn_info,
            { client.get(rp, &args.key, Bins::All).await }
        )?;

        // GIL 재획득하여 Python 객체 생성
        Python::attach(|py| record_to_py(py, &record, Some(&args.key)))
    })
}
```

**Sync와의 핵심 차이:**
- 반환 타입이 `PyResult<Bound<'py, PyAny>>` (Python awaitable).
- `future_into_py(py, async move { ... })` 사용.
- aerospike_core 호출에 `.await` 직접 사용 (block_on 불필요).
- Python 객체 생성 시 `Python::attach(|py| ...)` 로 GIL 재획득.
- `SharedClientState`: `Arc<Mutex<Option<Arc<AsClient>>>>` 패턴으로 안전한 공유.

### 5. Python 래퍼 (`src/aerospike_py/__init__.py`)

반환값이 NamedTuple로 변환이 필요한 경우에만 래퍼를 추가합니다.

**`Client` 클래스** (`class Client(_NativeClient):`):
```python
def get(self, key, policy=None):
    return _wrap_record(super().get(key, policy))

def exists(self, key, policy=None):
    return _wrap_exists(super().exists(key, policy))
```

**`AsyncClient` 클래스** (`class AsyncClient:`):
```python
async def get(self, key, policy=None):
    return _wrap_record(await self._inner.get(key, policy))

async def exists(self, key, policy=None):
    return _wrap_exists(await self._inner.exists(key, policy))
```

**래핑 헬퍼 함수:**
- `_wrap_record(raw)` -> `Record(key, meta, bins)` NamedTuple
- `_wrap_exists(raw)` -> `ExistsResult(key, meta)` NamedTuple
- `_wrap_operate_ordered(raw)` -> `OperateOrderedResult(key, meta, bin_list)` NamedTuple

NamedTuple 래핑이 필요 없는 메서드(예: `put`, `remove` 등 void 반환 또는 단순 타입 반환)는 네이티브 메서드가 직접 노출되므로 래퍼 불필요.

### 6. 타입 스텁 (`src/aerospike_py/__init__.pyi`)

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

### 7. 유닛 테스트 (`tests/unit/`)

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

### 8. 통합 테스트 (`tests/integration/`)

실제 Aerospike 서버와 통신하는 테스트를 작성합니다. `conftest.py`의 fixture를 활용합니다:

**주요 fixture:**
- `client` (module-scoped) - sync 클라이언트, 서버 미가용 시 자동 skip
- `async_client` (function-scoped) - async 클라이언트, 서버 미가용 시 자동 skip
- `cleanup` (function-scoped) - `keys` 리스트에 append하면 테스트 후 자동 삭제
- `async_cleanup` (function-scoped) - async 버전의 cleanup

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

**참고:** `asyncio_mode = "auto"` 설정이므로 async 테스트에 `@pytest.mark.asyncio` 데코레이터가 불필요합니다.

### 9. 빌드 및 검증

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

## `traced_op!` 매크로 상세

`traced_op!` 매크로는 OTel 스팬과 Prometheus 메트릭을 동시에 기록합니다:

```rust
traced_op!(
    "operation_name",          // 연산 이름 (span name: "OP ns.set")
    &args.key.namespace,       // namespace (metrics label)
    &args.key.set_name,        // set (metrics label)
    args.parent_ctx,           // OTel 부모 컨텍스트
    args.conn_info,            // ConnectionInfo (server.address, server.port, cluster_name)
    { client.operation(...).await }  // 실행할 async 블록 (Result<T, aerospike_core::Error>)
)
// 반환: Result<T, PyErr>
```

**`otel` feature 미활성화 시**: `traced_op!`은 `timed_op!`으로 폴백 (Prometheus 메트릭만 기록).

**`traced_exists_op!`**: `exists` 연산 전용. `KeyNotFoundError`를 에러로 취급하지 않음. 반환 타입이 `Result<T, aerospike_core::Error>` (PyErr가 아님).

## 주의사항

- **Sync/Async 일관성**: 반드시 `client.rs`와 `async_client.rs` 양쪽에 구현합니다.
- **client_common.rs에 파싱 로직 공유**: 파라미터 파싱은 `prepare_*_args` 패턴으로 공유 함수에 위치합니다.
- **OTel 트레이싱**: 모든 I/O 메서드는 `traced_op!` 매크로로 감싸야 합니다.
- **타입 스텁 동기화**: `.pyi` 파일의 시그니처가 Rust 구현과 정확히 일치해야 합니다.
- **NamedTuple 반환**: `get`, `select`, `exists`, `operate`, `operate_ordered`, `info_all` 등은 Python 래퍼에서 NamedTuple로 변환합니다. 새 메서드도 복합 반환값이면 적절한 NamedTuple을 정의합니다.
- **GIL 안전성**:
  - Sync: `py.detach(|| { ... })` 패턴으로 GIL 해제 후 블로킹.
  - Async: `future_into_py()` 안에서 Python 객체 생성 시 `Python::attach(|py| ...)` 로 GIL 재획득.
- **`otel` feature gate**: OTel 컨텍스트 추출 코드에 `#[cfg(feature = "otel")]`를 사용합니다. `client_common.rs`에서 이미 처리되므로 보통 신경 쓸 필요 없음.
