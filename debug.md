# Debug Notes

## Python 3.14t (free-threaded) Import Failure

### Error

```
E   SystemError: init function of _aerospike returned uninitialized object
```

Occurred when importing the module with Python 3.14t in the CI `build-freethreaded` job.

### Root Cause: Cargo Cache Contamination

The `build` job (Python 3.10–3.14, GIL-enabled) and the `build-freethreaded` job (Python 3.14t) were sharing the same Cargo cache key `"rust-build"`.

GIL-enabled and free-threaded Python have different `PyObject` struct layouts. When cached artifacts from a GIL-enabled build are reused in a free-threaded build, the type field offset in `PyModuleDef` is misaligned, causing the `Py_IS_TYPE(m, NULL)` check to fail.

CPython 3.14 `Python/importdl.c`:

```c
if (Py_IS_TYPE(m, NULL)) {
    /* PyModuleDef returned without calling PyModuleDef_Init */
    _Py_ext_module_loader_result_set_error(
        &res, _Py_ext_module_loader_result_ERR_UNINITIALIZED);
}
```

### Fix

Separated the Cargo cache key for the free-threaded build jobs in `.github/workflows/ci.yaml`:

```yaml
# Before (contaminated)
shared-key: "rust-build"

# After (isolated)
shared-key: "rust-build-freethreaded"
```

Affected jobs: `build-freethreaded`, `test-concurrency-freethreaded`

Additionally, `#[pymodule(gil_used = true)]` was declared in `rust/src/lib.rs` to explicitly indicate that the module requires the GIL. This causes the GIL to be automatically re-enabled when the module is imported under free-threaded Python.

### References

- [PyO3/pyo3#5722](https://github.com/PyO3/pyo3/issues/5722) — Same Cargo cache contamination issue
- [CPython importdl.c](https://github.com/python/cpython/blob/main/Python/importdl.c) — Location where the error is raised
- [PyO3 Free-Threading Guide](https://pyo3.rs/main/free-threading.html)
- [Python Free-Threading Extensions](https://docs.python.org/3/howto/free-threading-extensions.html)

### Key Takeaway

When building for both GIL-enabled and free-threaded Python in the same CI pipeline for a PyO3 project, **Cargo cache keys must be kept separate**. `pyo3-build-config` generates different code at compile time based on the `Py_GIL_DISABLED` flag, so mixing caches causes ABI mismatches.
