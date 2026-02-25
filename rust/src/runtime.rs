//! Shared Tokio runtime used by the synchronous [`crate::client::PyClient`].
//!
//! The runtime is initialized lazily on first access and lives for the
//! lifetime of the Python process.
//!
//! # Why `panic!` instead of `Result`
//!
//! [`LazyLock<T>`] requires `T` (not `Result<T, E>`), so the initializer
//! closure must return a valid `Runtime` or abort.  Runtime creation failure
//! is an unrecoverable environment issue (e.g. OS thread-limit exhaustion)
//! that cannot be meaningfully handled at the call-site, so panicking with a
//! descriptive message is the appropriate strategy here.

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
                "aerospike-py: failed to create Tokio runtime: {e}\n\
                 \n\
                 Requested workers : {workers}\n\
                 Env var           : AEROSPIKE_RUNTIME_WORKERS\n\
                 \n\
                 Troubleshooting:\n\
                 1. Reduce workers — export AEROSPIKE_RUNTIME_WORKERS=1\n\
                 2. Check thread limits — ulimit -u  (nproc)\n\
                 3. On Linux containers, verify /proc/sys/kernel/threads-max\n\
                 \n\
                 This panic is intentional: LazyLock<Runtime> cannot propagate \
                 errors, and a missing Tokio runtime is unrecoverable."
            )
        })
});
