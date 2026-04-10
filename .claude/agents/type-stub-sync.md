# Type Stub Synchronization Checker

A sub-agent that verifies consistency between Rust source code and Python type stubs.

## Comparison Targets

| Rust Source | Python Stub |
|-----------|-------------|
| `rust/src/client.rs` | `src/aerospike_py/__init__.pyi` (Client class) |
| `rust/src/async_client.rs` | `src/aerospike_py/__init__.pyi` (AsyncClient class) |
| `rust/src/constants.rs` | `src/aerospike_py/__init__.pyi` (constant definitions) |
| `rust/src/errors.rs` | `src/aerospike_py/exception.py` + `__init__.pyi` |
| `rust/src/lib.rs` | `src/aerospike_py/__init__.pyi` (module-level functions) |

## Validation Checklist

### 1. Method Existence
- All methods with `#[pymethod]` attribute in Rust exist in `.pyi`
- No methods exist only in `.pyi` but not in Rust (deleted APIs)

### 2. Signature Match
- Parameter name match
- Parameter type match (Rust → Python type mapping)
- Default value match (`#[pyo3(signature = (...))]` vs `.pyi`)
- Return type match

### 3. Constant Synchronization
- All constants from `rust/src/constants.rs` are reflected in `.pyi`
- Constant values match

### 4. Exception Classes
- All exception mappings from `rust/src/errors.rs` exist in `exception.py`
- Exception hierarchy matches

### 5. NamedTuple / TypedDict
- NamedTuple definitions used as return types are correct
- TypedDict input type fields match Rust parsing code

## Output Format

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
