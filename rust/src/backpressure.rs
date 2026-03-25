//! Operation-level concurrency limiter for backpressure.
//!
//! Wraps a `tokio::sync::Semaphore` to limit the number of concurrent
//! in-flight operations, preventing the upstream connection pool from
//! exhaustion (`NoMoreConnections` errors).
//!
//! When disabled (`max_concurrent == 0`), all methods are zero-cost no-ops.

use std::sync::Arc;
use std::time::Duration;

use pyo3::prelude::*;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

use crate::errors::BackpressureError;

/// Guards a single in-flight operation slot.
///
/// Dropping this releases the semaphore permit, allowing a waiting caller
/// to proceed. When the limiter is disabled, this is `None` (zero cost).
pub type OperationPermit = Option<OwnedSemaphorePermit>;

/// Limits the number of concurrent in-flight operations per client.
///
/// The upstream `aerospike-core` connection pool already handles connection
/// reuse and idle timeout. This limiter prevents pool exhaustion by gating
/// how many operations can be in-flight simultaneously.
#[derive(Clone)]
pub struct OperationLimiter {
    semaphore: Option<Arc<Semaphore>>,
    max_concurrent: usize,
    timeout_ms: u64,
}

impl OperationLimiter {
    /// Create a new limiter.
    ///
    /// - `max_concurrent == 0`: disabled (all operations pass through immediately).
    /// - `max_concurrent > 0`: at most `max_concurrent` operations in-flight.
    /// - `timeout_ms == 0`: wait indefinitely for a permit.
    /// - `timeout_ms > 0`: raise `BackpressureError` after this many ms.
    pub fn new(max_concurrent: usize, timeout_ms: u64) -> Self {
        let semaphore = if max_concurrent > 0 {
            Some(Arc::new(Semaphore::new(max_concurrent)))
        } else {
            None
        };
        Self {
            semaphore,
            max_concurrent,
            timeout_ms,
        }
    }

    /// Acquire a permit for one operation.
    ///
    /// Returns `None` when the limiter is disabled (zero overhead path).
    /// Returns `Some(permit)` when a slot is available.
    /// Raises `BackpressureError` if the timeout expires while waiting.
    ///
    /// The `operation` name is included in error messages for diagnostics.
    pub async fn acquire_named(&self, operation: &str) -> PyResult<OperationPermit> {
        let sem = match &self.semaphore {
            None => return Ok(None),
            Some(s) => s.clone(),
        };

        if self.timeout_ms > 0 {
            tokio::time::timeout(Duration::from_millis(self.timeout_ms), sem.acquire_owned())
                .await
                .map_err(|_| {
                    BackpressureError::new_err(format!(
                        "Backpressure timeout on '{}' after {}ms: max_concurrent_operations={} exceeded",
                        operation, self.timeout_ms, self.max_concurrent
                    ))
                })?
                .map(Some)
                .map_err(|_| {
                    BackpressureError::new_err(format!(
                        "Semaphore closed unexpectedly during '{}' (max_concurrent={}, timeout={}ms)",
                        operation, self.max_concurrent, self.timeout_ms
                    ))
                })
        } else {
            sem.acquire_owned()
                .await
                .map(Some)
                .map_err(|_| {
                    BackpressureError::new_err(format!(
                        "Semaphore closed unexpectedly during '{}' (max_concurrent={})",
                        operation, self.max_concurrent
                    ))
                })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_disabled_limiter_returns_none() {
        let limiter = OperationLimiter::new(0, 0);
        let permit = limiter.acquire_named("test").await.unwrap();
        assert!(permit.is_none());
    }

    #[tokio::test]
    async fn test_enabled_limiter_returns_permit() {
        let limiter = OperationLimiter::new(2, 0);
        let p1 = limiter.acquire_named("test").await.unwrap();
        assert!(p1.is_some());
        let p2 = limiter.acquire_named("test").await.unwrap();
        assert!(p2.is_some());
    }

    #[tokio::test]
    async fn test_permit_released_on_drop() {
        let limiter = OperationLimiter::new(1, 1000);
        {
            let _p = limiter.acquire_named("test").await.unwrap();
            // permit held
        }
        // permit dropped — should be able to acquire again
        let p2 = limiter.acquire_named("test").await.unwrap();
        assert!(p2.is_some());
    }

    #[tokio::test]
    async fn test_timeout_when_exhausted() {
        let limiter = OperationLimiter::new(1, 50); // 50ms timeout
        let _p = limiter.acquire_named("test").await.unwrap(); // hold the only permit

        // Second acquire should timeout
        let result = limiter.acquire_named("test").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_acquire_named_includes_op_in_error() {
        let limiter = OperationLimiter::new(1, 50);
        let _p = limiter.acquire_named("batch_read").await.unwrap();

        let result = limiter.acquire_named("batch_read").await;
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("batch_read"),
            "Error message should include the operation name, got: {err_msg}"
        );
    }
}
