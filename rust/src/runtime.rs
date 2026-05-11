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

use log::{info, warn};

/// Maximum allowed worker threads to prevent accidental resource exhaustion.
const MAX_WORKERS: usize = 32;

/// Read the configured worker count from `AEROSPIKE_RUNTIME_WORKERS` env var.
/// Defaults to 2, minimum 1, maximum [`MAX_WORKERS`].
fn configured_workers() -> usize {
    let raw = std::env::var("AEROSPIKE_RUNTIME_WORKERS")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(2)
        .max(1);
    if raw > MAX_WORKERS {
        warn!(
            "AEROSPIKE_RUNTIME_WORKERS={raw} exceeds maximum {MAX_WORKERS}, clamping to {MAX_WORKERS}"
        );
        MAX_WORKERS
    } else {
        raw
    }
}

/// Tokio runtime flavor selectable via `AEROSPIKE_RUNTIME_MODE`.
#[derive(Clone, Copy)]
enum RuntimeMode {
    /// Default — `tokio::runtime::Builder::new_multi_thread()` with
    /// `AEROSPIKE_RUNTIME_WORKERS` worker threads. Backward-compatible
    /// behavior; work-stealing pool suited to single-process deployments.
    MultiThread,
    /// `tokio::runtime::Builder::new_current_thread()` — single-threaded,
    /// no work-stealing. Suitable for multi-process servers (uvicorn,
    /// gunicorn) where each Python worker process runs its own Tokio
    /// runtime and the parallelism comes from process count, not threads.
    /// Eliminates work-stealing/sync overhead at the cost of removing
    /// background thread-level concurrency inside the runtime.
    CurrentThread,
}

/// Read the runtime mode from `AEROSPIKE_RUNTIME_MODE` env var.
/// Accepts `multi_thread` (default) or `current_thread` (case-insensitive,
/// underscores or dashes accepted).
fn configured_mode() -> RuntimeMode {
    match std::env::var("AEROSPIKE_RUNTIME_MODE")
        .ok()
        .as_deref()
        .map(|s| s.trim().to_ascii_lowercase().replace('-', "_"))
        .as_deref()
    {
        Some("current_thread") => RuntimeMode::CurrentThread,
        Some("multi_thread") | None => RuntimeMode::MultiThread,
        Some(other) => {
            warn!(
                "AEROSPIKE_RUNTIME_MODE={other:?} not recognized; falling back to multi_thread \
                 (valid: multi_thread, current_thread)"
            );
            RuntimeMode::MultiThread
        }
    }
}

/// Build a Tokio runtime builder honoring the configured mode + worker count.
fn make_builder(mode: RuntimeMode, workers: usize) -> tokio::runtime::Builder {
    match mode {
        RuntimeMode::MultiThread => {
            let mut b = tokio::runtime::Builder::new_multi_thread();
            b.worker_threads(workers);
            b
        }
        RuntimeMode::CurrentThread => tokio::runtime::Builder::new_current_thread(),
    }
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
    let mode = configured_mode();
    let workers = configured_workers();

    let mode_name = match mode {
        RuntimeMode::MultiThread => "multi_thread",
        RuntimeMode::CurrentThread => "current_thread",
    };
    info!("Initializing sync Tokio runtime ({mode_name}, workers={workers})");

    make_builder(mode, workers)
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
                 Mode              : {mode_name}\n\
                 Requested workers : {workers}\n\
                 Env vars          : AEROSPIKE_RUNTIME_MODE, AEROSPIKE_RUNTIME_WORKERS\n\
                 \n\
                 Troubleshooting:\n\
                 1. Reduce workers — export AEROSPIKE_RUNTIME_WORKERS=1\n\
                 2. Try single-thread mode — export AEROSPIKE_RUNTIME_MODE=current_thread\n\
                 3. Check thread limits — ulimit -u  (nproc)\n\
                 4. On Linux containers, verify /proc/sys/kernel/threads-max\n\
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
    let mode = configured_mode();
    let workers = configured_workers();
    let mode_name = match mode {
        RuntimeMode::MultiThread => "multi_thread",
        RuntimeMode::CurrentThread => "current_thread",
    };
    info!(
        "Configuring async (pyo3-async-runtimes) Tokio runtime ({mode_name}, workers={workers})"
    );
    let mut builder = make_builder(mode, workers);
    builder.enable_all();
    pyo3_async_runtimes::tokio::init(builder);
}
