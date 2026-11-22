//! Client-level policy parsing, including authentication and cluster settings.

use aerospike_core::{AuthMode, ClientPolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::extract_policy_fields;

/// `ClientPolicy::timeout` this binding runs with when the config omits it.
pub const DEFAULT_CLIENT_TIMEOUT_MS: u32 = 30_000;

/// `ClientPolicy::idle_timeout` this binding runs with when the config omits it.
pub const DEFAULT_IDLE_TIMEOUT_MS: u32 = 30_000;

/// The client policy before any user configuration is applied.
///
/// Rust client 3.0 lowered two defaults: `timeout` from 30 s to 1 s, and
/// `idle_timeout` from 30 s to 0, which turns the idle check off. A dependency
/// upgrade must not change how long a connection attempt may take or how long
/// an idle connection is kept, so the values this binding has always run with
/// are set here explicitly. A value in the caller's config still overrides
/// them.
///
/// Every other default is the Rust client's own, including the new
/// `login_timeout` (5 s).
pub fn default_client_policy() -> ClientPolicy {
    ClientPolicy {
        timeout: DEFAULT_CLIENT_TIMEOUT_MS,
        idle_timeout: DEFAULT_IDLE_TIMEOUT_MS,
        ..ClientPolicy::default()
    }
}

/// Parse a Python config dict into a ClientPolicy
pub fn parse_client_policy(config: &Bound<'_, PyDict>) -> PyResult<ClientPolicy> {
    trace!("Parsing client policy");
    let mut policy = default_client_policy();

    extract_policy_fields!(config, {
        "timeout" => policy.timeout;
        "idle_timeout" => policy.idle_timeout;
        "use_buffer_pool" => policy.use_buffer_pool;
        "buffer_pool_min_size" => policy.buffer_pool_min_size;
        "buffer_pool_max_size" => policy.buffer_pool_max_size;
        "buffer_pool_tier_bytes" => policy.buffer_pool_tier_bytes;
        "max_conns_per_node" => policy.max_conns_per_node;
        "min_conns_per_node" => policy.min_conns_per_node;
        "conn_pools_per_node" => policy.conn_pools_per_node;
        "tend_interval" => policy.tend_interval;
        "use_services_alternate" => policy.use_services_alternate
    });

    // Cluster name (needs None check)
    if let Some(cluster_name) = config.get_item("cluster_name")? {
        if !cluster_name.is_none() {
            policy.cluster_name = Some(cluster_name.extract::<String>()?);
        }
    }

    // Authentication: user/password (complex logic)
    if let Some(user) = config.get_item("user")? {
        if !user.is_none() {
            let username: String = user.extract()?;
            let password: String = config
                .get_item("password")?
                .map(|p| p.extract::<String>())
                .unwrap_or(Ok(String::new()))?;

            let auth_mode = if let Some(mode) = config.get_item("auth_mode")? {
                let mode_val: i32 = mode.extract()?;
                match mode_val {
                    0 => AuthMode::Internal(username, password),
                    1 => AuthMode::External(username, password),
                    2 => AuthMode::Pki,
                    other => {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "auth_mode must be AUTH_INTERNAL (0), AUTH_EXTERNAL (1), \
                             or AUTH_PKI (2); got {other}"
                        )));
                    }
                }
            } else {
                AuthMode::Internal(username, password)
            };
            policy.auth_mode = auth_mode;
        }
    }

    Ok(policy)
}

/// Parse backpressure configuration from a Python config dict.
///
/// Returns `(max_concurrent_operations, operation_queue_timeout_ms)`.
/// Both default to 0 (disabled / no timeout).
pub fn parse_backpressure_config(config: &Bound<'_, PyDict>) -> PyResult<(usize, u64)> {
    let max_ops: usize = config
        .get_item("max_concurrent_operations")?
        .map(|v| v.extract())
        .unwrap_or(Ok(0))?;
    let timeout_ms: u64 = config
        .get_item("operation_queue_timeout_ms")?
        .map(|v| v.extract())
        .unwrap_or(Ok(0))?;
    Ok((max_ops, timeout_ms))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn configured_buffer_pool_limits_reach_the_core() {
        Python::initialize();
        Python::attach(|py| {
            let config = PyDict::new(py);
            config.set_item("use_buffer_pool", false).unwrap();
            config.set_item("buffer_pool_min_size", 4096).unwrap();
            config.set_item("buffer_pool_max_size", 65536).unwrap();
            config.set_item("buffer_pool_tier_bytes", 131072).unwrap();
            let policy = parse_client_policy(&config).unwrap();
            assert!(!policy.use_buffer_pool);
            assert_eq!(policy.buffer_pool_min_size, 4096);
            assert_eq!(policy.buffer_pool_max_size, 65536);
            assert_eq!(policy.buffer_pool_tier_bytes, 131072);
        });
    }

    /// The reason `default_client_policy` exists: the Rust client's own
    /// defaults are no longer the ones this binding has always run with. If
    /// this assertion starts failing, upstream changed them again and the
    /// explicit values above need another look.
    #[test]
    fn rust_client_defaults_differ_from_the_ones_kept_here() {
        let upstream = ClientPolicy::default();
        assert_eq!(upstream.timeout, 1_000);
        assert_eq!(upstream.idle_timeout, 0);
    }

    #[test]
    fn omitted_timeouts_keep_their_pre_3_0_values() {
        Python::initialize();
        Python::attach(|py| {
            let config = PyDict::new(py);
            let policy = parse_client_policy(&config).unwrap();
            assert_eq!(policy.timeout, 30_000);
            assert_eq!(policy.idle_timeout, 30_000);
        });
    }

    #[test]
    fn configured_timeouts_override_the_defaults() {
        Python::initialize();
        Python::attach(|py| {
            let config = PyDict::new(py);
            config.set_item("timeout", 1_500u32).unwrap();
            config.set_item("idle_timeout", 0u32).unwrap();
            let policy = parse_client_policy(&config).unwrap();
            assert_eq!(policy.timeout, 1_500);
            assert_eq!(policy.idle_timeout, 0);
        });
    }
}
