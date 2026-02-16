# Debug Notes

## Python 3.14t (free-threaded) Import Failure

### Error

```
E   SystemError: init function of _aerospike returned uninitialized object
```

CI의 `build-freethreaded` 잡에서 Python 3.14t로 모듈 import 시 발생.

### Root Cause: Cargo Cache Contamination

`build` 잡(Python 3.10~3.14, GIL-enabled)과 `build-freethreaded` 잡(Python 3.14t)이 동일한 Cargo 캐시 키 `"rust-build"`를 공유하고 있었다.

GIL-enabled Python과 free-threaded Python은 `PyObject` 구조체 레이아웃이 다르다. GIL-enabled 빌드에서 생성된 캐시 아티팩트가 free-threaded 빌드에 재사용되면, `PyModuleDef`의 type 필드 오프셋이 어긋나 `Py_IS_TYPE(m, NULL)` 체크에서 실패한다.

CPython 3.14 `Python/importdl.c`:

```c
if (Py_IS_TYPE(m, NULL)) {
    /* PyModuleDef returned without calling PyModuleDef_Init */
    _Py_ext_module_loader_result_set_error(
        &res, _Py_ext_module_loader_result_ERR_UNINITIALIZED);
}
```

### Fix

`.github/workflows/ci.yaml`에서 free-threaded 빌드 잡의 Cargo 캐시 키를 분리:

```yaml
# Before (contaminated)
shared-key: "rust-build"

# After (isolated)
shared-key: "rust-build-freethreaded"
```

대상 잡: `build-freethreaded`, `test-concurrency-freethreaded`

추가로 `rust/src/lib.rs`에 `#[pymodule(gil_used = true)]`를 선언하여 모듈이 GIL을 필요로 함을 명시했다. 이 설정은 free-threaded Python에서 import 시 GIL을 자동으로 재활성화한다.

### References

- [PyO3/pyo3#5722](https://github.com/PyO3/pyo3/issues/5722) — 동일한 Cargo 캐시 오염 이슈
- [CPython importdl.c](https://github.com/python/cpython/blob/main/Python/importdl.c) — 에러 발생 위치
- [PyO3 Free-Threading Guide](https://pyo3.rs/main/free-threading.html)
- [Python Free-Threading Extensions](https://docs.python.org/3/howto/free-threading-extensions.html)

### Key Takeaway

PyO3 프로젝트에서 GIL-enabled Python과 free-threaded Python을 동일 CI에서 빌드할 때, **반드시 Cargo 캐시 키를 분리**해야 한다. `pyo3-build-config`가 컴파일 시 `Py_GIL_DISABLED` 플래그를 기반으로 다른 코드를 생성하므로, 캐시가 섞이면 ABI 불일치가 발생한다.
