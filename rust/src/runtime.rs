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
///
/// Defaults to 2 worker threads (configurable via `AEROSPIKE_RUNTIME_WORKERS` env var).
///
/// 2 workers is sufficient because Aerospike operations are I/O-bound and Tokio uses
/// cooperative scheduling. This minimizes CPU overhead from native threads, which is
/// important when colocated with CPU-intensive workloads (e.g. PyTorch inference).
///
/// Uses `enable_io()` + `enable_time()` instead of `enable_all()` to avoid the
/// signal driver, which can conflict with Python's own signal handling.
pub static RUNTIME: LazyLock<tokio::runtime::Runtime> = LazyLock::new(|| {
    let workers = std::env::var("AEROSPIKE_RUNTIME_WORKERS")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(2)
        .max(1);

    info!(
        "Initializing Tokio multi-thread runtime with {} workers",
        workers
    );
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(workers)
        .enable_io()
        .enable_time()
        .build()
        .unwrap_or_else(|e| {
            crate::bug_report::log_unexpected_error(
                "runtime::RUNTIME",
                &format!("Failed to create Tokio runtime: {e}"),
            );
            panic!(
                "aerospike-py: Failed to create Tokio runtime ({e}). \
                 This is likely a system resource issue (e.g. thread limit reached). \
                 Try reducing AEROSPIKE_RUNTIME_WORKERS (current: {workers}) or check system limits (ulimit -u)."
            )
        })
});
