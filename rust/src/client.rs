use std::sync::Arc;

use crate::client_common;
use crate::client_ops;
use aerospike_core::{Client as AsClient, Error as AsError, ResultCode};
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::backpressure::OperationLimiter;
use crate::batch_types::batch_to_batch_records_py;
use crate::errors::as_to_pyerr;
use crate::policy::admin_policy::{parse_privileges, role_to_py, user_to_py};
use crate::policy::client_policy::{parse_backpressure_config, parse_client_policy};
use crate::record_helpers::{batch_records_to_py, record_to_meta};
use crate::runtime::RUNTIME;
use crate::types::host::parse_hosts_from_config;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py_with_key;
use crate::types::value::value_to_py;

/// Synchronous Aerospike client exposed to Python as `Client`.
///
/// Wraps `aerospike_core::Client` and uses a shared Tokio runtime
/// ([`crate::runtime::RUNTIME`]) to block on async operations while
/// releasing the GIL via `py.detach()`.
#[pyclass(name = "Client", subclass)]
pub struct PyClient {
    /// The underlying async client, wrapped in `Arc` for cheap cloning.
    /// `None` before `connect()` is called.
    inner: Option<Arc<AsClient>>,
    /// Python config dict, retained for potential reconnection.
    config: Py<PyAny>,
    /// Connection metadata used for OTel span attributes (Arc for cheap cloning).
    connection_info: Arc<crate::tracing::ConnectionInfo>,
    /// Operation concurrency limiter (disabled by default).
    limiter: Arc<OperationLimiter>,
}

#[pymethods]
impl PyClient {
    #[new]
    fn new(config: Py<PyAny>) -> PyResult<Self> {
        Ok(PyClient {
            inner: None,
            config,
            connection_info: Arc::new(crate::tracing::ConnectionInfo::default()),
            limiter: Arc::new(OperationLimiter::new(0, 0)),
        })
    }

    /// Connect to the Aerospike cluster. Returns self for chaining.
    #[pyo3(signature = (username=None, password=None))]
    fn connect(
        &mut self,
        py: Python<'_>,
        username: Option<&str>,
        password: Option<&str>,
    ) -> PyResult<()> {
        if username.is_some() && password.is_none() {
            return Err(crate::errors::ClientError::new_err(
                "Password is required when username is provided.",
            ));
        }

        let config_dict = self.config.bind(py).cast::<PyDict>()?;
        let effective_config = config_dict.copy()?;

        if let (Some(user), Some(pass)) = (username, password) {
            effective_config.set_item("user", user)?;
            effective_config.set_item("password", pass)?;
        }

        let parsed = parse_hosts_from_config(&effective_config)?;
        let client_policy = parse_client_policy(&effective_config)?;
        let (max_ops, timeout_ms) = parse_backpressure_config(&effective_config)?;

        let cluster_name = client_common::extract_cluster_name(&effective_config)?;

        self.connection_info = Arc::new(crate::tracing::ConnectionInfo {
            server_address: Arc::from(parsed.first_address.as_str()),
            server_port: parsed.first_port as i64,
            cluster_name: Arc::from(cluster_name.as_str()),
        });

        let hosts_str = parsed.connection_string;
        info!("Connecting to Aerospike cluster: {}", hosts_str);
        let client = py.detach(|| {
            RUNTIME.block_on(async {
                AsClient::new(
                    &client_policy,
                    &hosts_str as &(dyn aerospike_core::ToHosts + Send + Sync),
                )
                .await
                .map_err(as_to_pyerr)
            })
        })?;

        self.inner = Some(Arc::new(client));
        self.limiter = Arc::new(OperationLimiter::new(max_ops, timeout_ms));
        info!("Connected to Aerospike cluster");
        Ok(())
    }

    /// Check if the client is connected
    fn is_connected(&self) -> bool {
        trace!("Checking client connection status");
        match &self.inner {
            Some(client) => client.is_connected(),
            None => false,
        }
    }

    /// Close the connection to the cluster
    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
        info!("Closing client connection");
        if let Some(client) = self.inner.take() {
            py.detach(|| RUNTIME.block_on(async { client.close().await.map_err(as_to_pyerr) }))?;
        }
        Ok(())
    }

    /// Get node names in the cluster
    fn get_node_names(&self) -> PyResult<Vec<String>> {
        Ok(self.get_client()?.node_names())
    }

    // ── Info ─────────────────────────────────────────────────────

    /// Send an info command to all nodes in the cluster.
    /// Returns a list of (node_name, error_code, response) tuples.
    #[pyo3(signature = (command, policy=None))]
    fn info_all(
        &self,
        py: Python<'_>,
        command: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Vec<(String, i32, String)>> {
        let client = self.get_client()?;
        let args = client_common::prepare_info_args(command, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_info_all(client, &args)))
    }

    /// Send an info command to a random node in the cluster.
    /// Returns the response string.
    #[pyo3(signature = (command, policy=None))]
    fn info_random_node(
        &self,
        py: Python<'_>,
        command: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<String> {
        let client = self.get_client()?;
        let args = client_common::prepare_info_args(command, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_info_random_node(client, &args)))
    }

    /// Write a record
    #[pyo3(signature = (key, bins, meta=None, policy=None))]
    fn put(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bins: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let args =
            client_common::prepare_put_args(py, key, bins, meta, policy, &self.connection_info)?;
        let client = self.get_client()?;
        let limiter = self.limiter.clone();
        debug!("put: ns={} set={}", args.key.namespace, args.key.set_name);
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_put(client, args).await
            })
        })
    }

    /// Read a record
    #[pyo3(signature = (key, policy=None))]
    fn get(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?;
        let limiter = self.limiter.clone();
        let args = client_common::prepare_get_args(py, key, policy, &self.connection_info)?;
        debug!("get: ns={} set={}", args.key.namespace, args.key.set_name);
        let key_py = key_to_py(py, &args.key)?;
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_get(client, &args).await
            })
        })?;
        record_to_py_with_key(py, &record, key_py)
    }

    /// Read specific bins of a record
    #[pyo3(signature = (key, bins, policy=None))]
    fn select(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bins: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_select_args(py, key, bins, policy, &self.connection_info)?;
        debug!(
            "select: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let key_py = key_to_py(py, &args.key)?;
        let limiter = self.limiter.clone();
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_select(client, &args).await
            })
        })?;
        record_to_py_with_key(py, &record, key_py)
    }

    /// Check if a record exists. Returns (key, meta) or (key, None)
    #[pyo3(signature = (key, policy=None))]
    fn exists(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let args = client_common::prepare_exists_args(py, key, policy, &self.connection_info)?;
        debug!(
            "exists: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let key_py = key_to_py(py, &args.key)?;
        let limiter = self.limiter.clone();
        let result = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                Ok::<_, pyo3::PyErr>(client_ops::do_exists(&client, &args).await)
            })
        })?;

        match result {
            Ok(record) => {
                let meta = record_to_meta(py, &record)?;
                let tuple = PyTuple::new(py, [key_py, meta])?;
                Ok(tuple.into_any().unbind())
            }
            Err(AsError::ServerError(ResultCode::KeyNotFoundError, _, _)) => {
                let tuple = PyTuple::new(py, [key_py, py.None()])?;
                Ok(tuple.into_any().unbind())
            }
            Err(e) => Err(as_to_pyerr(e)),
        }
    }

    /// Remove a record
    #[pyo3(signature = (key, meta=None, policy=None))]
    fn remove(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_remove_args(py, key, meta, policy, &self.connection_info)?;
        debug!(
            "remove: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_remove(client, args).await
            })
        })
    }

    /// Reset record's TTL
    #[pyo3(signature = (key, val=0, meta=None, policy=None))]
    fn touch(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        val: u32,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_touch_args(py, key, val, meta, policy, &self.connection_info)?;
        debug!("touch: ns={} set={}", args.key.namespace, args.key.set_name);
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_touch(client, args).await
            })
        })
    }

    /// Append a string to a bin
    #[pyo3(signature = (key, bin, val, meta=None, policy=None))]
    fn append(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        val: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args = client_common::prepare_single_bin_write_args(
            py,
            key,
            bin,
            val,
            meta,
            policy,
            &self.connection_info,
        )?;
        debug!(
            "append: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_append(client, args).await
            })
        })
    }

    /// Prepend a string to a bin
    #[pyo3(signature = (key, bin, val, meta=None, policy=None))]
    fn prepend(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        val: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args = client_common::prepare_single_bin_write_args(
            py,
            key,
            bin,
            val,
            meta,
            policy,
            &self.connection_info,
        )?;
        debug!(
            "prepend: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_prepend(client, args).await
            })
        })
    }

    /// Increment an integer bin
    #[pyo3(signature = (key, bin, offset, meta=None, policy=None))]
    fn increment(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        offset: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args = client_common::prepare_increment_args(
            py,
            key,
            bin,
            offset,
            meta,
            policy,
            &self.connection_info,
        )?;
        debug!(
            "increment: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_increment(client, args).await
            })
        })
    }

    /// Remove bins from a record by setting them to nil
    #[pyo3(signature = (key, bin_names, meta=None, policy=None))]
    fn remove_bin(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bin_names: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let args = client_common::prepare_remove_bin_args(
            py,
            key,
            bin_names,
            meta,
            policy,
            &self.connection_info,
        )?;
        let limiter = self.limiter.clone();
        py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_remove_bin(client, args).await
            })
        })
    }

    /// Perform multiple operations on a single record
    #[pyo3(signature = (key, ops, meta=None, policy=None))]
    fn operate(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        ops: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "operate: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );
        let key_py = key_to_py(py, &args.key)?;
        let limiter = self.limiter.clone();
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_operate(client, &args).await
            })
        })?;
        record_to_py_with_key(py, &record, key_py)
    }

    /// Perform multiple operations on a single record, returning ordered results
    #[pyo3(signature = (key, ops, meta=None, policy=None))]
    fn operate_ordered(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        ops: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "operate_ordered: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );
        let pre_key_py = key_to_py(py, &args.key)?;
        let limiter = self.limiter.clone();
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_operate_ordered(client, &args).await
            })
        })?;

        let key_py = match &record.key {
            Some(k) => key_to_py(py, k)?,
            None => pre_key_py,
        };

        let meta_dict_obj = record_to_meta(py, &record)?;

        let bin_items: Vec<Py<PyAny>> = record
            .bins
            .iter()
            .map(|(name, value)| {
                let tuple = PyTuple::new(
                    py,
                    [
                        name.as_str().into_pyobject(py)?.into_any().unbind(),
                        value_to_py(py, value)?,
                    ],
                )?;
                Ok(tuple.into_any().unbind())
            })
            .collect::<PyResult<_>>()?;
        let ordered_bins = PyList::new(py, &bin_items)?;

        let result = PyTuple::new(
            py,
            [key_py, meta_dict_obj, ordered_bins.into_any().unbind()],
        )?;
        Ok(result.into_any().unbind())
    }

    // ── Query / Index ─────────────────────────────────────

    /// Create a Query object for the given namespace and set.
    fn query(&self, namespace: &str, set_name: &str) -> PyResult<crate::query::PyQuery> {
        debug!("Creating query: ns={} set={}", namespace, set_name);
        let client = self.get_client()?.clone();
        Ok(crate::query::PyQuery::new(
            client,
            namespace.to_string(),
            set_name.to_string(),
            self.connection_info.clone(),
        ))
    }

    /// Create a secondary integer index.
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_integer_create(
        &self,
        py: Python<'_>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        self.create_index(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::Numeric,
            policy,
        )
    }

    /// Create a secondary string index.
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_string_create(
        &self,
        py: Python<'_>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        self.create_index(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::String,
            policy,
        )
    }

    /// Create a secondary geo2dsphere index.
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_geo2dsphere_create(
        &self,
        py: Python<'_>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        self.create_index(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::Geo2DSphere,
            policy,
        )
    }

    /// Remove a secondary index.
    #[pyo3(signature = (namespace, index_name, policy=None))]
    fn index_remove(
        &self,
        py: Python<'_>,
        namespace: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Removing index: ns={} index={}", namespace, index_name);
        let client = self.get_client()?.clone();
        let args = client_common::prepare_index_remove_args(namespace, index_name, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_index_remove(&client, args)))
    }

    // ── Truncate ──────────────────────────────────────────────────

    /// Remove records in specified namespace/set efficiently.
    #[pyo3(signature = (namespace, set_name, nanos=0, policy=None))]
    fn truncate(
        &self,
        py: Python<'_>,
        namespace: &str,
        set_name: &str,
        nanos: i64,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        warn!("Truncating: ns={} set={}", namespace, set_name);
        let client = self.get_client()?.clone();
        let args = client_common::prepare_truncate_args(namespace, set_name, nanos, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_truncate(&client, args)))
    }

    // ── UDF ───────────────────────────────────────────────────────

    /// Register a UDF module from a file.
    #[pyo3(signature = (filename, udf_type=0, policy=None))]
    fn udf_put(
        &self,
        py: Python<'_>,
        filename: &str,
        udf_type: u8,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Registering UDF: filename={}", filename);
        let client = self.get_client()?.clone();
        let args = client_common::prepare_udf_put_args(filename, udf_type, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_udf_put(&client, args)))
    }

    /// Remove a UDF module.
    #[pyo3(signature = (module, policy=None))]
    fn udf_remove(
        &self,
        py: Python<'_>,
        module: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Removing UDF: module={}", module);
        let client = self.get_client()?.clone();
        let args = client_common::prepare_udf_remove_args(module, policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_udf_remove(&client, args)))
    }

    /// Execute a UDF on a single record.
    #[pyo3(signature = (key, module, function, args=None, policy=None))]
    fn apply(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        module: &str,
        function: &str,
        args: Option<&Bound<'_, PyList>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let a = client_common::prepare_apply_args(key, module, function, args, policy)?;
        debug!(
            "apply UDF: ns={} set={} module={} function={}",
            a.key.namespace, a.key.set_name, a.module, a.function
        );
        let result = py.detach(|| RUNTIME.block_on(client_ops::do_apply(&client, &a)))?;
        match result {
            Some(val) => value_to_py(py, &val),
            None => Ok(py.None()),
        }
    }

    // ── Admin operations ──────────────────────────────────────────

    /// Create a new user with the given roles.
    #[pyo3(signature = (username, password, roles, policy=None))]
    fn admin_create_user(
        &self,
        py: Python<'_>,
        username: &str,
        password: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Creating user: username={}", username);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_create_user(
                &client,
                &admin_policy,
                username,
                password,
                &roles,
            ))
        })
    }

    /// Drop (delete) a user.
    #[pyo3(signature = (username, policy=None))]
    fn admin_drop_user(
        &self,
        py: Python<'_>,
        username: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Dropping user: username={}", username);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_drop_user(
                &client,
                &admin_policy,
                username,
            ))
        })
    }

    /// Change user password.
    #[pyo3(signature = (username, password, policy=None))]
    fn admin_change_password(
        &self,
        py: Python<'_>,
        username: &str,
        password: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Changing password for user: username={}", username);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_change_password(
                &client,
                &admin_policy,
                username,
                password,
            ))
        })
    }

    /// Grant roles to a user.
    #[pyo3(signature = (username, roles, policy=None))]
    fn admin_grant_roles(
        &self,
        py: Python<'_>,
        username: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Granting roles to user: username={}", username);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_grant_roles(
                &client,
                &admin_policy,
                username,
                &roles,
            ))
        })
    }

    /// Revoke roles from a user.
    #[pyo3(signature = (username, roles, policy=None))]
    fn admin_revoke_roles(
        &self,
        py: Python<'_>,
        username: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Revoking roles from user: username={}", username);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_revoke_roles(
                &client,
                &admin_policy,
                username,
                &roles,
            ))
        })
    }

    /// Query info about a specific user.
    #[pyo3(signature = (username, policy=None))]
    fn admin_query_user_info(
        &self,
        py: Python<'_>,
        username: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();
        let users = py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_query_users(
                &client,
                &admin_policy,
                Some(&username),
            ))
        })?;

        if let Some(user) = users.first() {
            user_to_py(py, user)
        } else {
            Err(crate::errors::AdminError::new_err(format!(
                "User '{}' not found",
                username
            )))
        }
    }

    /// Query info about all users.
    #[pyo3(signature = (policy=None))]
    fn admin_query_users_info(
        &self,
        py: Python<'_>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let users = py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_query_users(
                &client,
                &admin_policy,
                None,
            ))
        })?;

        let list = PyList::empty(py);
        for user in &users {
            list.append(user_to_py(py, user)?)?;
        }
        Ok(list.into_any().unbind())
    }

    /// Create a new role with the given privileges.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0))]
    fn admin_create_role(
        &self,
        py: Python<'_>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
        whitelist: Option<Vec<String>>,
        read_quota: u32,
        write_quota: u32,
    ) -> PyResult<()> {
        info!("Creating role: role={}", role);
        let client = self.get_client()?.clone();
        let args = client_common::prepare_create_role_args(
            role,
            privileges,
            policy,
            whitelist,
            read_quota,
            write_quota,
        )?;
        py.detach(|| RUNTIME.block_on(client_ops::do_admin_create_role(&client, args)))
    }

    /// Drop (delete) a role.
    #[pyo3(signature = (role, policy=None))]
    fn admin_drop_role(
        &self,
        py: Python<'_>,
        role: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Dropping role: role={}", role);
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| RUNTIME.block_on(client_ops::do_admin_drop_role(&client, &admin_policy, role)))
    }

    /// Grant privileges to a role.
    #[pyo3(signature = (role, privileges, policy=None))]
    fn admin_grant_privileges(
        &self,
        py: Python<'_>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_grant_privileges(
                &client,
                &admin_policy,
                role,
                &rust_privileges,
            ))
        })
    }

    /// Revoke privileges from a role.
    #[pyo3(signature = (role, privileges, policy=None))]
    fn admin_revoke_privileges(
        &self,
        py: Python<'_>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_revoke_privileges(
                &client,
                &admin_policy,
                role,
                &rust_privileges,
            ))
        })
    }

    /// Query info about a specific role.
    #[pyo3(signature = (role, policy=None))]
    fn admin_query_role(
        &self,
        py: Python<'_>,
        role: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let role_name = role.to_string();
        let roles = py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_query_roles(
                &client,
                &admin_policy,
                Some(&role_name),
            ))
        })?;

        if let Some(r) = roles.first() {
            role_to_py(py, r)
        } else {
            Err(crate::errors::AdminError::new_err(format!(
                "Role '{}' not found",
                role_name
            )))
        }
    }

    /// Query info about all roles.
    #[pyo3(signature = (policy=None))]
    fn admin_query_roles(
        &self,
        py: Python<'_>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let roles = py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_query_roles(
                &client,
                &admin_policy,
                None,
            ))
        })?;

        let list = PyList::empty(py);
        for r in &roles {
            list.append(role_to_py(py, r)?)?;
        }
        Ok(list.into_any().unbind())
    }

    /// Set allowlist (whitelist) for a role.
    #[pyo3(signature = (role, whitelist, policy=None))]
    fn admin_set_whitelist(
        &self,
        py: Python<'_>,
        role: &str,
        whitelist: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_set_whitelist(
                &client,
                &admin_policy,
                role,
                &whitelist,
            ))
        })
    }

    /// Set quotas for a role.
    #[pyo3(signature = (role, read_quota=0, write_quota=0, policy=None))]
    fn admin_set_quotas(
        &self,
        py: Python<'_>,
        role: &str,
        read_quota: u32,
        write_quota: u32,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?.clone();
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        py.detach(|| {
            RUNTIME.block_on(client_ops::do_admin_set_quotas(
                &client,
                &admin_policy,
                role,
                read_quota,
                write_quota,
            ))
        })
    }

    // ── Batch operations ──────────────────────────────────────────

    /// Read multiple records. Returns BatchRecords, or NumpyBatchRecords when dtype is provided.
    #[pyo3(signature = (keys, bins=None, policy=None, _dtype=None))]
    fn batch_read(
        &self,
        py: Python<'_>,
        keys: &Bound<'_, PyList>,
        bins: Option<Vec<String>>,
        policy: Option<&Bound<'_, PyDict>>,
        _dtype: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        debug!("batch_read: keys_count={}", keys.len());
        let client = self.get_client()?.clone();
        let args =
            client_common::prepare_batch_read_args(py, keys, &bins, policy, &self.connection_info)?;
        let limiter = self.limiter.clone();
        let results = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_batch_read(&client, &args).await
            })
        })?;

        match _dtype {
            Some(d) => crate::numpy_support::batch_to_numpy_py(py, &results, d),
            None => {
                let br = batch_to_batch_records_py(py, &results)?;
                Ok(Py::new(py, br)?.into_any())
            }
        }
    }

    /// Perform operations on multiple records. Returns list of (key, meta, bins) tuples.
    #[pyo3(signature = (keys, ops, policy=None))]
    fn batch_operate(
        &self,
        py: Python<'_>,
        keys: &Bound<'_, PyList>,
        ops: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        debug!("batch_operate: keys_count={}", keys.len());
        let client = self.get_client()?.clone();
        let args = client_common::prepare_batch_operate_args(
            py,
            keys,
            ops,
            policy,
            &self.connection_info,
        )?;
        let limiter = self.limiter.clone();
        let results = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_batch_operate(&client, &args).await
            })
        })?;
        batch_records_to_py(py, &results)
    }

    /// Write multiple records from a numpy structured array.
    ///
    /// Each row becomes a separate write operation in the batch.
    /// The dtype must contain a `_key` field (or custom key_field) for the record key,
    /// and remaining non-underscore-prefixed fields become bins.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (data, namespace, set_name, _dtype, key_field="_key", policy=None))]
    fn batch_write_numpy(
        &self,
        py: Python<'_>,
        data: &Bound<'_, PyAny>,
        namespace: &str,
        set_name: &str,
        _dtype: &Bound<'_, PyAny>,
        key_field: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        debug!(
            "batch_write_numpy: namespace={}, set={}",
            namespace, set_name
        );
        let client = self.get_client()?.clone();
        let batch_policy = crate::policy::batch_policy::parse_batch_policy(policy)?;
        #[allow(clippy::let_unit_value)]
        let parent_ctx = client_common::extract_parent_context(py);
        let conn_info = self.connection_info.clone();

        let records = crate::numpy_support::numpy_to_records(
            py, data, _dtype, namespace, set_name, key_field,
        )?;

        let ns = namespace.to_string();
        let set = set_name.to_string();

        let limiter = self.limiter.clone();
        let results = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_batch_write(
                    &client,
                    &batch_policy,
                    &records,
                    &ns,
                    &set,
                    parent_ctx,
                    conn_info,
                )
                .await
            })
        })?;

        batch_records_to_py(py, &results)
    }

    /// Remove multiple records.
    #[pyo3(signature = (keys, policy=None))]
    fn batch_remove(
        &self,
        py: Python<'_>,
        keys: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        debug!("batch_remove: keys_count={}", keys.len());
        let client = self.get_client()?.clone();
        let args =
            client_common::prepare_batch_remove_args(py, keys, policy, &self.connection_info)?;
        let limiter = self.limiter.clone();
        let results = py.detach(|| {
            RUNTIME.block_on(async {
                let _permit = limiter.acquire().await?;
                client_ops::do_batch_remove(&client, &args).await
            })
        })?;
        batch_records_to_py(py, &results)
    }
}

impl PyClient {
    /// Returns a reference to the connected client, or an error if not yet connected.
    fn get_client(&self) -> PyResult<&Arc<AsClient>> {
        self.inner.as_ref().ok_or_else(|| {
            crate::errors::ClientError::new_err("Client is not connected. Call connect() first.")
        })
    }

    /// Internal helper for index creation
    #[allow(clippy::too_many_arguments)]
    fn create_index(
        &self,
        py: Python<'_>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        index_type: aerospike_core::IndexType,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!(
            "Creating index: ns={} set={} bin={} index={}",
            namespace, set_name, bin_name, index_name
        );
        let client = self.get_client()?.clone();
        let args = client_common::prepare_index_create_args(
            namespace, set_name, bin_name, index_name, index_type, policy,
        )?;
        py.detach(|| RUNTIME.block_on(client_ops::do_index_create(&client, args)))
    }
}
