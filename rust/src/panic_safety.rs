//! Convert native Rust panics into `aerospike_py.RustPanicError` so the
//! Python process survives them.
//!
//! Background (issue #280): `aerospike-core 2.0.0` panics with
//! `unreachable!()` for language-specific blob particle types
//! (PYTHON_BLOB, JAVA_BLOB, ...). Combined with `panic = "abort"` this would
//! SIGABRT the Python process. We compile release with `panic = "unwind"`
//! and wrap every read/write chokepoint with the helpers below.
//!
//! Two chokepoints, two helpers:
//! - sync `Client` methods funnel through `py.detach(|| RUNTIME.block_on(...))`
//!   → wrap with [`catch_panic_sync`].
//! - async `AsyncClient` methods funnel through
//!   `pyo3_async_runtimes::tokio::future_into_py(...)` → use
//!   [`future_into_py_panic_safe`] as a drop-in replacement.

use std::any::Any;
use std::future::Future;
use std::panic::{AssertUnwindSafe, catch_unwind};

use futures::FutureExt;
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;

use crate::bug_report::log_unexpected_error;
use crate::errors::RustPanicError;

/// Best-effort extraction of a human-readable message from a panic payload.
fn panic_msg(payload: &(dyn Any + Send)) -> String {
    if let Some(s) = payload.downcast_ref::<&'static str>() {
        (*s).to_owned()
    } else if let Some(s) = payload.downcast_ref::<String>() {
        s.clone()
    } else {
        "<non-string panic payload>".to_owned()
    }
}

/// Convert a caught panic into a logged `RustPanicError` `PyErr`.
fn payload_to_pyerr(op: &'static str, payload: Box<dyn Any + Send>) -> PyErr {
    let msg = panic_msg(&*payload);
    log_unexpected_error(op, &msg);
    RustPanicError::new_err(format!("Rust panic in `{op}`: {msg}"))
}

/// Run `f`; if it panics, surface `RustPanicError`. Use this to wrap the
/// closure passed to `py.detach(...)` in every sync API entry point.
pub fn catch_panic_sync<F, R>(op: &'static str, f: F) -> PyResult<R>
where
    F: FnOnce() -> PyResult<R>,
{
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(payload) => Err(payload_to_pyerr(op, payload)),
    }
}

/// Drop-in replacement for `future_into_py` that catches panics from the
/// inner future and surfaces them as `RustPanicError`.
pub fn future_into_py_panic_safe<'py, F, R>(
    py: Python<'py>,
    op: &'static str,
    fut: F,
) -> PyResult<Bound<'py, PyAny>>
where
    F: Future<Output = PyResult<R>> + Send + 'static,
    R: for<'a> IntoPyObject<'a> + Send + 'static,
{
    future_into_py(py, async move {
        match AssertUnwindSafe(fut).catch_unwind().await {
            Ok(result) => result,
            Err(payload) => Err(payload_to_pyerr(op, payload)),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ensure_python() {
        static INIT: std::sync::Once = std::sync::Once::new();
        INIT.call_once(pyo3::Python::initialize);
    }

    #[test]
    fn panic_msg_string_payload() {
        let payload: Box<dyn Any + Send> = Box::new(String::from("boom"));
        assert_eq!(panic_msg(&*payload), "boom");
    }

    #[test]
    fn panic_msg_static_str_payload() {
        let payload: Box<dyn Any + Send> = Box::new("static boom");
        assert_eq!(panic_msg(&*payload), "static boom");
    }

    #[test]
    fn panic_msg_unknown_payload_falls_back() {
        let payload: Box<dyn Any + Send> = Box::new(42_i32);
        assert_eq!(panic_msg(&*payload), "<non-string panic payload>");
    }

    #[test]
    fn catch_panic_sync_passes_ok_through() {
        let r = catch_panic_sync("noop", || Ok::<_, PyErr>(42));
        assert!(matches!(r, Ok(42)));
    }

    #[test]
    fn catch_panic_sync_converts_panic_to_pyerr() {
        ensure_python();
        pyo3::Python::attach(|py| {
            let r: PyResult<()> = catch_panic_sync("synthetic_op", || {
                panic!("synthetic panic");
            });
            let err = r.unwrap_err();
            assert!(err.is_instance_of::<RustPanicError>(py));
            let msg = err.value(py).to_string();
            assert!(msg.contains("synthetic_op"), "missing op in {msg}");
            assert!(msg.contains("synthetic panic"), "missing payload in {msg}");
        });
    }

    #[test]
    fn catch_panic_sync_survives_after_prior_panic() {
        pyo3::Python::attach(|_py| {
            let _ = catch_panic_sync::<_, ()>("first", || panic!("first"));
            let r = catch_panic_sync("second", || Ok::<_, PyErr>(7));
            assert!(matches!(r, Ok(7)));
        });
    }

    #[test]
    fn catch_panic_sync_string_payload_preserved() {
        ensure_python();
        pyo3::Python::attach(|py| {
            let r: PyResult<()> = catch_panic_sync("op_with_format", || {
                let detail = String::from("dynamic detail");
                panic!("{}", detail);
            });
            let err = r.unwrap_err();
            assert!(
                err.value(py)
                    .to_string()
                    .contains("dynamic detail"),
            );
        });
    }
}
