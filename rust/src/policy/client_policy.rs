//! Client-level policy parsing, including authentication and cluster settings.

use aerospike_core::{AuthMode, ClientPolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::extract_policy_fields;

/// Parse a Python config dict into a ClientPolicy
pub fn parse_client_policy(config: &Bound<'_, PyDict>) -> PyResult<ClientPolicy> {
    trace!("Parsing client policy");
    let mut policy = ClientPolicy::default();

    extract_policy_fields!(config, {
        "timeout" => policy.timeout;
        "idle_timeout" => policy.idle_timeout;
        "max_conns_per_node" => policy.max_conns_per_node;
        "min_conns_per_node" => policy.min_conns_per_node;
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
                if mode_val == 1 {
                    AuthMode::External(username, password)
                } else {
                    AuthMode::Internal(username, password)
                }
            } else {
                AuthMode::Internal(username, password)
            };
            policy.auth_mode = auth_mode;
        }
    }

    Ok(policy)
}
