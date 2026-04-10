---
name: new-api
description: Guide for adding a new Client/AsyncClient API method across Rust, Python wrapper, type stubs, and tests
args: "[method-name] [description]"
---

# New API Method

Adds a new Client/AsyncClient API method to aerospike-py. Consistently creates all layers from the Rust implementation through Python type stubs and tests.

## Arguments

Invoke with `/new-api [method-name] [description]`.

- `method-name`: Name of the method to add (e.g., `get_key_digest`)
- `description`: Description of the method behavior (e.g., "Returns the RIPEMD-160 digest of the key")

## File Modification Checklist

When adding a new API method, you **must** modify all of the following files:

| Order | File | Role |
|------|------|------|
| 1 | `rust/src/client_common.rs` | Shared parameter parsing functions (`prepare_*_args`) |
| 2 | `rust/src/client.rs` | Sync Client Rust implementation (`#[pymethods] impl PyClient`) |
| 3 | `rust/src/async_client.rs` | Async Client Rust implementation (`#[pymethods] impl PyAsyncClient`) |
| 4 | `src/aerospike_py/__init__.py` | Python wrapper (only when NamedTuple conversion is needed) |
| 5 | `src/aerospike_py/__init__.pyi` | Type stubs (both Client and AsyncClient classes) |
| 6 | `tests/unit/test_*.py` | Unit tests (no server required — argument validation, etc.) |
| 7 | `tests/integration/test_*.py` | Integration tests (requires running Aerospike server) |

Additional files that may need modification:

| File | Condition |
|------|------|
| `rust/src/policy/*.rs` | When a new policy type is needed |
| `rust/src/types/*.rs` | When a new type conversion is needed |
| `rust/src/errors.rs` | When a new error type is needed |
| `rust/src/operations.rs` | When adding operate operations |
| `src/aerospike_py/types.py` | When a new NamedTuple/TypedDict is needed |

## Steps

### 1. Check the aerospike_core API

First, check the available APIs in the `aerospike_core` crate:

```bash
cargo doc --manifest-path rust/Cargo.toml --open
```

Alternatively, check the aerospike-core version (`2.0.0-alpha.9`) in `rust/Cargo.toml` and search for the API on docs.rs.

### 2. Shared Parameter Parsing (`rust/src/client_common.rs`)

Define a `prepare_*_args` function first so both sync/async clients share the same parameter parsing logic.

**Reference existing pattern** (e.g., `prepare_get_args`):

```rust
/// Parsed arguments for `get` / `select` operations.
pub(crate) struct GetArgs {
    pub key: aerospike_core::Key,
    pub parent_ctx: ParentContext,  // OTel context (opentelemetry::Context when otel feature is enabled)
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

**Key points:**
- `ParentContext` type is `opentelemetry::Context` or `()` depending on the `otel` feature.
- OTel context extraction must be performed **while holding the GIL** (requires Python SDK calls).
- Provide a fast path using default policies (`DEFAULT_*_POLICY`) when policy is `None`.

### 3. Rust Sync Client Implementation (`rust/src/client.rs`)

Add the method inside the `#[pymethods] impl PyClient` block.

**Actual code pattern** (based on the `put` method):

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
    // 1. Parse parameters using shared function (while holding GIL)
    let args = client_common::prepare_put_args(
        py, key, bins, meta, policy, &self.connection_info
    )?;
    let client = self.get_client()?;

    // 2. Release GIL with py.detach() + execute async via RUNTIME.block_on()
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

**Key rules:**
- Specify the Python signature with `#[pyo3(signature = (...))]` macro.
- Check connection state with `self.get_client()?` (raises `ClientError` if not connected).
- Use the `py.detach(|| { ... })` pattern to release the GIL and execute blocking code.
- Call aerospike_core's async API inside `RUNTIME.block_on(async { ... })`.
- Use the `traced_op!` macro for automatic OTel span + Prometheus metric instrumentation.
- Errors are converted to Python exceptions via `as_to_pyerr()` inside the `traced_op!` macro.
- Return type conversion: use existing helpers like `record_to_py()`, `key_to_py()`, `value_to_py()`.

### 4. Rust Async Client Implementation (`rust/src/async_client.rs`)

Same logic as sync, but wrapped with `future_into_py`.

**Actual code pattern** (based on the `get` method):

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

    // future_into_py: returns a Python awaitable
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

        // Reacquire GIL to create Python objects
        Python::attach(|py| record_to_py(py, &record, Some(&args.key)))
    })
}
```

**Key differences from sync:**
- Return type is `PyResult<Bound<'py, PyAny>>` (Python awaitable).
- Uses `future_into_py(py, async move { ... })`.
- Uses `.await` directly for aerospike_core calls (no block_on needed).
- Reacquires GIL with `Python::attach(|py| ...)` when creating Python objects.
- `SharedClientState`: safe sharing via `Arc<Mutex<Option<Arc<AsClient>>>>` pattern.

### 5. Python Wrapper (`src/aerospike_py/__init__.py`)

Add a wrapper only when the return value needs NamedTuple conversion.

**`Client` class** (`class Client(_NativeClient):`):
```python
def get(self, key, policy=None):
    return _wrap_record(super().get(key, policy))

def exists(self, key, policy=None):
    return _wrap_exists(super().exists(key, policy))
```

**`AsyncClient` class** (`class AsyncClient:`):
```python
async def get(self, key, policy=None):
    return _wrap_record(await self._inner.get(key, policy))

async def exists(self, key, policy=None):
    return _wrap_exists(await self._inner.exists(key, policy))
```

**Wrapping helper functions:**
- `_wrap_record(raw)` -> `Record(key, meta, bins)` NamedTuple
- `_wrap_exists(raw)` -> `ExistsResult(key, meta)` NamedTuple
- `_wrap_operate_ordered(raw)` -> `OperateOrderedResult(key, meta, bin_list)` NamedTuple

Methods that don't need NamedTuple wrapping (e.g., `put`, `remove` — void return or simple types) are exposed directly from the native method, so no wrapper is needed.

### 6. Type Stubs (`src/aerospike_py/__init__.pyi`)

Add signatures to **both** the Client and AsyncClient classes:

```python
# Inside Client class
def method_name(
    self,
    key: Key,
    param1: str,
    param2: Optional[dict[str, Any]] = None,
    policy: Optional[ReadPolicy] = None,
) -> Record: ...

# Inside AsyncClient class
async def method_name(
    self,
    key: Key,
    param1: str,
    param2: Optional[dict[str, Any]] = None,
    policy: Optional[ReadPolicy] = None,
) -> Record: ...
```

**Note:** Maintain consistent ordering, naming, and types with existing method signatures.

### 7. Unit Tests (`tests/unit/`)

Write tests that can run without a server. Mainly test argument validation, type errors, and errors when not connected:

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

### 8. Integration Tests (`tests/integration/`)

Write tests that communicate with a real Aerospike server. Use fixtures from `conftest.py`:

**Key fixtures:**
- `client` (module-scoped) — sync client, auto-skips if server unavailable
- `async_client` (function-scoped) — async client, auto-skips if server unavailable
- `cleanup` (function-scoped) — append keys to the `keys` list for automatic deletion after test
- `async_cleanup` (function-scoped) — async version of cleanup

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

**Note:** With `asyncio_mode = "auto"` configured, the `@pytest.mark.asyncio` decorator is not needed for async tests.

### 9. Build and Verify

```bash
# Compilation check (quick verification)
cargo check --manifest-path rust/Cargo.toml

# Build
make build

# Type check
uv run pyright

# Unit tests
uv run pytest tests/unit/ -v -k "test_method_name"

# Integration tests (requires server)
uv run pytest tests/integration/ -v -k "test_method_name"
```

## `traced_op!` Macro Details

The `traced_op!` macro records both OTel spans and Prometheus metrics simultaneously:

```rust
traced_op!(
    "operation_name",          // Operation name (span name: "OP ns.set")
    &args.key.namespace,       // namespace (metrics label)
    &args.key.set_name,        // set (metrics label)
    args.parent_ctx,           // OTel parent context
    args.conn_info,            // ConnectionInfo (server.address, server.port, cluster_name)
    { client.operation(...).await }  // Async block to execute (Result<T, aerospike_core::Error>)
)
// Returns: Result<T, PyErr>
```

**When `otel` feature is disabled**: `traced_op!` falls back to `timed_op!` (Prometheus metrics only).

**`traced_exists_op!`**: Dedicated to `exists` operations. Does not treat `KeyNotFoundError` as an error. Return type is `Result<T, aerospike_core::Error>` (not PyErr).

## Important Notes

- **Sync/Async consistency**: Always implement in both `client.rs` and `async_client.rs`.
- **Share parsing logic in client_common.rs**: Parameter parsing goes in shared `prepare_*_args` functions.
- **OTel tracing**: All I/O methods must be wrapped with the `traced_op!` macro.
- **Type stub synchronization**: `.pyi` file signatures must exactly match the Rust implementation.
- **NamedTuple returns**: `get`, `select`, `exists`, `operate`, `operate_ordered`, `info_all`, etc. are converted to NamedTuples in the Python wrapper. New methods with compound return values should define appropriate NamedTuples.
- **GIL safety**:
  - Sync: `py.detach(|| { ... })` pattern to release GIL before blocking.
  - Async: Reacquire GIL with `Python::attach(|py| ...)` when creating Python objects inside `future_into_py()`.
- **`otel` feature gate**: Use `#[cfg(feature = "otel")]` for OTel context extraction code. Already handled in `client_common.rs`, so usually no additional work is needed.
