//! Minimal Rust `log` → Python `logging` bridge.
//!
//! Implements the `log::Log` trait to forward Rust log messages
//! to Python's `logging` module via PyO3. Falls back to stderr
//! when the Python GIL is unavailable (e.g. during shutdown).

use log::{Level, LevelFilter, Log, Metadata, Record};
use pyo3::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;

/// Maps Rust log levels to Python logging levels.
fn rust_to_python_level(level: Level) -> u32 {
    match level {
        Level::Error => 40,
        Level::Warn => 30,
        Level::Info => 20,
        Level::Debug => 10,
        Level::Trace => 5,
    }
}

/// A `log::Log` implementation that forwards to Python's `logging` module.
struct PyLogger;

static LOGGER: OnceLock<PyLogger> = OnceLock::new();

/// Counter tracking how many log messages were dropped (GIL unavailable).
static DROPPED_LOG_COUNT: AtomicU64 = AtomicU64::new(0);

/// Return the number of log messages dropped since process start.
pub fn dropped_log_count() -> u64 {
    DROPPED_LOG_COUNT.load(Ordering::Relaxed)
}

impl Log for PyLogger {
    fn enabled(&self, _metadata: &Metadata) -> bool {
        true
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }

        let level = rust_to_python_level(record.level());
        let target = record.target();
        let message = format!("{}", record.args());

        // Try to acquire the GIL and forward to Python.
        // If we can't (e.g., during shutdown), fall back to stderr for
        // WARN/ERROR messages so critical diagnostics are not lost.
        match Python::try_attach(|py| -> PyResult<()> {
            let logging = py.import("logging")?;
            let logger = logging.call_method1("getLogger", (target,))?;
            logger.call_method1("log", (level, &message))?;
            Ok(())
        }) {
            Some(Ok(())) => {} // Successfully forwarded to Python
            None => {
                // GIL genuinely unavailable (interpreter shutdown)
                DROPPED_LOG_COUNT.fetch_add(1, Ordering::Relaxed);
                if record.level() <= Level::Warn {
                    eprintln!(
                        "[aerospike-py/{}] {}: {}",
                        record.level(),
                        target,
                        message
                    );
                }
            }
            Some(Err(_)) => {
                // GIL acquired but Python logging call failed
                // (e.g. misconfigured handler). Always emit to stderr.
                eprintln!(
                    "[aerospike-py/LOGGING-ERROR] {}: {}",
                    target, message
                );
            }
        }
    }

    fn flush(&self) {}
}

/// Initialize the Rust → Python logging bridge.
///
/// Call this once at module init time. Subsequent calls are no-ops.
pub fn init() {
    let logger = LOGGER.get_or_init(|| PyLogger);
    // set_logger may fail if called more than once; that's fine.
    let _ = log::set_logger(logger);
    log::set_max_level(LevelFilter::Trace);
}
