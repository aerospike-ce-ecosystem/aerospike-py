//! Shared Tokio runtime used by the synchronous [`crate::client::PyClient`].
//!
//! The runtime is initialized lazily on first access and lives for the
//! lifetime of the Python process.

use std::sync::LazyLock;

use log::info;

/// Global multi-threaded Tokio runtime shared across all sync client operations.
///
/// Async client operations do not use this runtime; they rely on
/// `pyo3_async_runtimes::tokio::future_into_py` which manages its own event loop.
pub static RUNTIME: LazyLock<tokio::runtime::Runtime> = LazyLock::new(|| {
    info!("Initializing Tokio multi-thread runtime");
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap_or_else(|e| {
            crate::bug_report::log_unexpected_error(
                "runtime::RUNTIME",
                &format!("Failed to create Tokio runtime: {e}"),
            );
            panic!("Failed to create Tokio runtime: {e}")
        })
});
