//! Shared Tokio runtimes for aerospike-py.
//!
//! Two runtimes are managed:
//!
//! 1. **Sync runtime** (`RUNTIME`) — used by [`crate::client::PyClient`] via
//!    `block_on()`. Lazily initialized on first sync operation.
//!
//! 2. **Async runtime** — used by [`crate::async_client::PyAsyncClient`] via
//!    `pyo3_async_runtimes::tokio::future_into_py`. Configured during module
//!    init via [`init_async_runtime`] to limit worker threads and reduce GIL
//!    contention.
//!
//! Both default to 2 worker threads (configurable via `AEROSPIKE_RUNTIME_WORKERS`).
//! Fewer Tokio workers means fewer threads competing for the GIL after async I/O
//! completes, which significantly reduces contention under high concurrency.
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

/// Read the configured worker count from `AEROSPIKE_RUNTIME_WORKERS` env var.
/// Defaults to 2, minimum 1.
fn configured_workers() -> usize {
    std::env::var("AEROSPIKE_RUNTIME_WORKERS")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(2)
        .max(1)
}

/// Global multi-threaded Tokio runtime shared across all sync client operations.
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
    let workers = configured_workers();

    info!("Initializing sync Tokio runtime with {} workers", workers);
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

/// Configure the `pyo3-async-runtimes` Tokio runtime used by `AsyncClient`.
///
/// Must be called **before** any `future_into_py()` invocation (i.e. before
/// any `AsyncClient` method is awaited).  Called from module init.
///
/// By default, `pyo3-async-runtimes` creates a runtime with CPU-count workers,
/// which causes excessive GIL contention when many Tokio workers simultaneously
/// call `Python::attach()` after I/O completion.  Limiting workers to 2 (or
/// the value of `AEROSPIKE_RUNTIME_WORKERS`) dramatically reduces contention.
pub fn init_async_runtime() {
    let workers = configured_workers();
    info!(
        "Configuring async (pyo3-async-runtimes) Tokio runtime with {} workers",
        workers
    );
    let mut builder = tokio::runtime::Builder::new_multi_thread();
    builder.worker_threads(workers).enable_all();
    pyo3_async_runtimes::tokio::init(builder);
}
