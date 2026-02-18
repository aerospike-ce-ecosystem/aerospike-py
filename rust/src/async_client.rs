use std::sync::{Arc, Mutex, PoisonError};

use crate::client_common::{self, PutPolicy};
use crate::traced_exists_op;
use crate::traced_op;
use aerospike_core::{
    BatchOperation, BatchWritePolicy, Bins, Client as AsClient, Error as AsError, ResultCode, Task,
};
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3_async_runtimes::tokio::future_into_py;

use crate::batch_types::batch_to_batch_records_py;
use crate::errors::as_to_pyerr;
use crate::policy::admin_policy::{parse_privileges, role_to_py, user_to_py};
use crate::policy::client_policy::parse_client_policy;
use crate::policy::write_policy::DEFAULT_WRITE_POLICY;
use crate::record_helpers::{batch_records_to_py, record_to_meta};
use crate::types::host::parse_hosts_from_config;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py;
use crate::types::value::value_to_py;

/// Thread-safe shared state for the async client.
///
/// Uses `Mutex<Option<...>>` so that `connect()` can set the client
/// and `close()` can take it out, while remaining `Send + Sync` for
/// use inside `future_into_py`.
type SharedClientState = Arc<Mutex<Option<Arc<AsClient>>>>;

/// Convert a [`PoisonError`] into a Python [`ClientError`].
fn lock_err<T>(e: PoisonError<T>) -> PyErr {
    crate::errors::ClientError::new_err(format!("Internal lock poisoned: {e}"))
}

/// Asynchronous Aerospike client exposed to Python as `AsyncClient`.
///
/// All I/O methods return Python awaitables via `future_into_py`.
/// The underlying `aerospike_core::Client` is shared behind a `Mutex`
/// to allow safe concurrent access from multiple Python coroutines.
#[pyclass(name = "AsyncClient")]
pub struct PyAsyncClient {
    /// The underlying async client, wrapped in `Arc<Mutex<Option<...>>>`.
    /// `None` before `connect()` is called; taken by `close()`.
    inner: SharedClientState,
    /// Python config dict, retained for potential reconnection.
    config: Py<PyAny>,
    /// Connection metadata used for OTel span attributes.
    connection_info: crate::tracing::ConnectionInfo,
}

#[pymethods]
impl PyAsyncClient {
    #[new]
    fn new(config: Py<PyAny>) -> PyResult<Self> {
        Ok(PyAsyncClient {
            inner: Arc::new(Mutex::new(None)),
            config,
            connection_info: crate::tracing::ConnectionInfo::default(),
        })
    }

    /// Connect to the Aerospike cluster (async).
    #[pyo3(signature = (username=None, password=None))]
    fn connect<'py>(
        &mut self,
        py: Python<'py>,
        username: Option<&str>,
        password: Option<&str>,
    ) -> PyResult<Bound<'py, PyAny>> {
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
        let inner = self.inner.clone();

        let cluster_name = effective_config
            .get_item("cluster_name")?
            .and_then(|v| {
                if v.is_none() {
                    None
                } else {
                    v.extract::<String>().ok()
                }
            })
            .unwrap_or_default();

        self.connection_info = crate::tracing::ConnectionInfo {
            server_address: parsed.first_address,
            server_port: parsed.first_port as i64,
            cluster_name,
        };

        let hosts_str = parsed.connection_string;
        info!("Async connecting to Aerospike cluster: {}", hosts_str);
        future_into_py(py, async move {
            let client = AsClient::new(
                &client_policy,
                &hosts_str as &(dyn aerospike_core::ToHosts + Send + Sync),
            )
            .await
            .map_err(as_to_pyerr)?;

            *inner.lock().map_err(lock_err)? = Some(Arc::new(client));
            Ok(())
        })
    }

    /// Check if connected (sync, no I/O).
    fn is_connected(&self) -> bool {
        trace!("Checking async client connection status");
        self.inner
            .lock()
            .map(|guard| guard.is_some())
            .unwrap_or(false)
    }

    /// Close connection (async).
    fn close<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        info!("Closing async client connection");
        let client = self.inner.lock().map_err(lock_err)?.take();
        future_into_py(py, async move {
            if let Some(c) = client {
                c.close().await.map_err(as_to_pyerr)?;
            }
            Ok(())
        })
    }

    /// Get node names (async).
    fn get_node_names<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        future_into_py(py, async move { Ok(client.node_names().await) })
    }

    // ── Info ─────────────────────────────────────────────────────

    /// Send an info command to all nodes in the cluster (async).
    #[pyo3(signature = (command, policy=None))]
    fn info_all<'py>(
        &self,
        py: Python<'py>,
        command: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args = client_common::prepare_info_args(command, policy)?;

        future_into_py(py, async move {
            let nodes = client.nodes().await;
            let mut results: Vec<(String, i32, String)> = Vec::new();
            for node in &nodes {
                let r = node.info(&args.admin_policy, &[&args.command]).await;
                results.push(client_common::info_node_result(node, &args.command, r));
            }
            Ok(results)
        })
    }

    /// Send an info command to a random node in the cluster (async).
    #[pyo3(signature = (command, policy=None))]
    fn info_random_node<'py>(
        &self,
        py: Python<'py>,
        command: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args = client_common::prepare_info_args(command, policy)?;

        future_into_py(py, async move {
            let node = client
                .cluster
                .get_random_node()
                .await
                .map_err(as_to_pyerr)?;
            let map = node
                .info(&args.admin_policy, &[&args.command])
                .await
                .map_err(as_to_pyerr)?;
            Ok(map.get(&args.command).cloned().unwrap_or_default())
        })
    }

    /// Async context manager entry.
    fn __aenter__<'py>(slf: Py<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        future_into_py(py, async move { Ok(slf) })
    }

    /// Async context manager exit.
    #[pyo3(signature = (_exc_type=None, _exc_val=None, _exc_tb=None))]
    fn __aexit__<'py>(
        &self,
        py: Python<'py>,
        _exc_type: Option<&Bound<'_, PyAny>>,
        _exc_val: Option<&Bound<'_, PyAny>>,
        _exc_tb: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.inner.lock().map_err(lock_err)?.take();
        future_into_py(py, async move {
            if let Some(c) = client {
                c.close().await.map_err(as_to_pyerr)?;
            }
            Ok(false)
        })
    }

    // ── CRUD ──────────────────────────────────────────────────

    /// Write a record (async).
    #[pyo3(signature = (key, bins, meta=None, policy=None))]
    fn put<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bins: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let args =
            client_common::prepare_put_args(py, key, bins, meta, policy, &self.connection_info)?;
        let client = self.get_client()?;
        debug!(
            "async put: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        match args.policy {
            PutPolicy::Default => {
                let wp = DEFAULT_WRITE_POLICY.clone();
                future_into_py(py, async move {
                    traced_op!(
                        "put",
                        &args.key.namespace,
                        &args.key.set_name,
                        args.parent_ctx,
                        args.conn_info,
                        { client.put(&wp, &args.key, &args.bins).await }
                    )
                })
            }
            PutPolicy::Custom(wp) => future_into_py(py, async move {
                traced_op!(
                    "put",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.put(&wp, &args.key, &args.bins).await }
                )
            }),
        }
    }

    /// Read a record (async).
    #[pyo3(signature = (key, policy=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args = client_common::prepare_get_args(py, key, policy, &self.connection_info)?;
        debug!(
            "async get: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        let rp = args.read_policy().clone();
        future_into_py(py, async move {
            let record = traced_op!(
                "get",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.get(&rp, &args.key, Bins::All).await }
            )?;

            Python::attach(|py| record_to_py(py, &record, Some(&args.key)))
        })
    }

    /// Read specific bins (async).
    #[pyo3(signature = (key, bins, policy=None))]
    fn select<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bins: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_select_args(py, key, bins, policy, &self.connection_info)?;
        debug!(
            "async select: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        let rp = args.read_policy().clone();
        future_into_py(py, async move {
            let bin_refs: Vec<&str> = args.bin_names.iter().map(|s| s.as_str()).collect();
            let bins_selector = Bins::from(bin_refs.as_slice());
            let record = traced_op!(
                "select",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.get(&rp, &args.key, bins_selector).await }
            )?;

            Python::attach(|py| record_to_py(py, &record, Some(&args.key)))
        })
    }

    /// Check if a record exists (async).
    #[pyo3(signature = (key, policy=None))]
    fn exists<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args = client_common::prepare_exists_args(py, key, policy, &self.connection_info)?;
        debug!(
            "async exists: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        future_into_py(py, async move {
            let result = traced_exists_op!(
                "exists",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.get(&args.read_policy, &args.key, Bins::None).await }
            );

            Python::attach(|py| {
                let key_py = key_to_py(py, &args.key)?;
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
            })
        })
    }

    /// Remove a record (async).
    #[pyo3(signature = (key, meta=None, policy=None))]
    fn remove<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_remove_args(py, key, meta, policy, &self.connection_info)?;
        debug!(
            "async remove: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        future_into_py(py, async move {
            let existed = traced_op!(
                "delete",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.delete(&args.write_policy, &args.key).await }
            )?;

            if !existed {
                return Err(crate::errors::RecordNotFound::new_err(
                    "AEROSPIKE_ERR (2): Record not found",
                ));
            }
            Ok(())
        })
    }

    /// Touch a record (async).
    #[pyo3(signature = (key, val=0, meta=None, policy=None))]
    fn touch<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        val: u32,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_touch_args(py, key, val, meta, policy, &self.connection_info)?;
        debug!(
            "async touch: ns={} set={}",
            args.key.namespace, args.key.set_name
        );

        future_into_py(py, async move {
            traced_op!(
                "touch",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.touch(&args.write_policy, &args.key).await }
            )
        })
    }

    /// Increment a bin (async).
    #[pyo3(signature = (key, bin, offset, meta=None, policy=None))]
    fn increment<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        offset: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
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
            "async increment: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );

        future_into_py(py, async move {
            traced_op!(
                "increment",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.add(&args.write_policy, &args.key, &args.bins).await }
            )
        })
    }

    /// Operate on a record (async).
    #[pyo3(signature = (key, ops, meta=None, policy=None))]
    fn operate<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        ops: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "async operate: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );

        future_into_py(py, async move {
            let record = traced_op!(
                "operate",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                {
                    client
                        .operate(&args.write_policy, &args.key, &args.ops)
                        .await
                }
            )?;

            Python::attach(|py| record_to_py(py, &record, Some(&args.key)))
        })
    }

    // ── String / Numeric ───────────────────────────────────────

    /// Append a string to a bin (async).
    #[pyo3(signature = (key, bin, val, meta=None, policy=None))]
    fn append<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        val: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
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
            "async append: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );

        future_into_py(py, async move {
            traced_op!(
                "append",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                {
                    client
                        .append(&args.write_policy, &args.key, &args.bins)
                        .await
                }
            )
        })
    }

    /// Prepend a string to a bin (async).
    #[pyo3(signature = (key, bin, val, meta=None, policy=None))]
    fn prepend<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bin: &str,
        val: &Bound<'_, PyAny>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
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
            "async prepend: ns={} set={} bin={}",
            args.key.namespace, args.key.set_name, bin
        );

        future_into_py(py, async move {
            traced_op!(
                "prepend",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                {
                    client
                        .prepend(&args.write_policy, &args.key, &args.bins)
                        .await
                }
            )
        })
    }

    /// Remove bins from a record by setting them to nil (async).
    #[pyo3(signature = (key, bin_names, meta=None, policy=None))]
    fn remove_bin<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        bin_names: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args = client_common::prepare_remove_bin_args(
            py,
            key,
            bin_names,
            meta,
            policy,
            &self.connection_info,
        )?;

        future_into_py(py, async move {
            traced_op!(
                "remove_bin",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                { client.put(&args.write_policy, &args.key, &args.bins).await }
            )
        })
    }

    // ── Multi-operation (ordered) ────────────────────────────────

    /// Perform multiple operations on a single record, returning ordered results (async).
    #[pyo3(signature = (key, ops, meta=None, policy=None))]
    fn operate_ordered<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        ops: &Bound<'_, PyList>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "async operate_ordered: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );

        future_into_py(py, async move {
            let record = traced_op!(
                "operate_ordered",
                &args.key.namespace,
                &args.key.set_name,
                args.parent_ctx,
                args.conn_info,
                {
                    client
                        .operate(&args.write_policy, &args.key, &args.ops)
                        .await
                }
            )?;

            Python::attach(|py| {
                let key_py = match &record.key {
                    Some(k) => key_to_py(py, k)?,
                    None => key_to_py(py, &args.key)?,
                };
                let meta_dict_obj = record_to_meta(py, &record)?;
                let ordered_bins = PyList::empty(py);
                for (name, value) in &record.bins {
                    let tuple = PyTuple::new(
                        py,
                        [
                            name.as_str().into_pyobject(py)?.into_any().unbind(),
                            value_to_py(py, value)?,
                        ],
                    )?;
                    ordered_bins.append(tuple)?;
                }
                let result = PyTuple::new(
                    py,
                    [key_py, meta_dict_obj, ordered_bins.into_any().unbind()],
                )?;
                Ok(result.into_any().unbind())
            })
        })
    }

    // ── Truncate ─────────────────────────────────────────────

    /// Remove records in specified namespace/set efficiently (async).
    #[pyo3(signature = (namespace, set_name, nanos=0, policy=None))]
    fn truncate<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        nanos: i64,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        warn!("Async truncating: ns={} set={}", namespace, set_name);
        let client = self.get_client()?;
        let args = client_common::prepare_truncate_args(namespace, set_name, nanos, policy)?;

        future_into_py(py, async move {
            client
                .truncate(
                    &args.admin_policy,
                    &args.namespace,
                    &args.set_name,
                    args.nanos,
                )
                .await
                .map_err(as_to_pyerr)
        })
    }

    // ── UDF ──────────────────────────────────────────────────

    /// Register a UDF module from a file (async).
    #[pyo3(signature = (filename, udf_type=0, policy=None))]
    fn udf_put<'py>(
        &self,
        py: Python<'py>,
        filename: &str,
        udf_type: u8,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async registering UDF: filename={}", filename);
        let client = self.get_client()?;
        let args = client_common::prepare_udf_put_args(filename, udf_type, policy)?;

        future_into_py(py, async move {
            let task = client
                .register_udf(
                    &args.admin_policy,
                    &args.udf_body,
                    &args.server_path,
                    args.language,
                )
                .await
                .map_err(as_to_pyerr)?;
            task.wait_till_complete(None::<std::time::Duration>)
                .await
                .map_err(as_to_pyerr)?;
            Ok(())
        })
    }

    /// Remove a UDF module (async).
    #[pyo3(signature = (module, policy=None))]
    fn udf_remove<'py>(
        &self,
        py: Python<'py>,
        module: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async removing UDF: module={}", module);
        let client = self.get_client()?;
        let args = client_common::prepare_udf_remove_args(module, policy)?;

        future_into_py(py, async move {
            let task = client
                .remove_udf(&args.admin_policy, &args.server_path)
                .await
                .map_err(as_to_pyerr)?;
            task.wait_till_complete(None::<std::time::Duration>)
                .await
                .map_err(as_to_pyerr)?;
            Ok(())
        })
    }

    /// Execute a UDF on a single record (async).
    #[pyo3(signature = (key, module, function, args=None, policy=None))]
    fn apply<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'_, PyAny>,
        module: &str,
        function: &str,
        args: Option<&Bound<'_, PyList>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let a = client_common::prepare_apply_args(key, module, function, args, policy)?;
        debug!(
            "async apply UDF: ns={} set={} module={} function={}",
            a.key.namespace, a.key.set_name, a.module, a.function
        );

        future_into_py(py, async move {
            let result = client
                .execute_udf(
                    &a.write_policy,
                    &a.key,
                    &a.module,
                    &a.function,
                    a.args.as_deref(),
                )
                .await
                .map_err(as_to_pyerr)?;

            Python::attach(|py| match result {
                Some(val) => value_to_py(py, &val),
                None => Ok(py.None()),
            })
        })
    }

    // ── Batch ─────────────────────────────────────────────────

    /// Read multiple records (async).
    #[pyo3(signature = (keys, bins=None, policy=None, _dtype=None))]
    fn batch_read<'py>(
        &self,
        py: Python<'py>,
        keys: &Bound<'_, PyList>,
        bins: Option<Vec<String>>,
        policy: Option<&Bound<'_, PyDict>>,
        _dtype: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!("async batch_read: keys_count={}", keys.len());
        let client = self.get_client()?;
        let args =
            client_common::prepare_batch_read_args(py, keys, &bins, policy, &self.connection_info)?;

        let use_numpy = _dtype.is_some();
        let dtype_py: Option<Py<PyAny>> = _dtype.map(|d| d.clone().unbind());

        future_into_py(py, async move {
            let ops = args.to_batch_ops();
            let results = traced_op!(
                "batch_read",
                &args.batch_ns,
                &args.batch_set,
                args.parent_ctx,
                args.conn_info,
                { client.batch(&args.batch_policy, &ops).await }
            )?;

            Python::attach(|py| {
                if use_numpy {
                    crate::numpy_support::batch_to_numpy_py(
                        py,
                        &results,
                        &dtype_py.unwrap().into_bound(py),
                    )
                } else {
                    let batch_records = batch_to_batch_records_py(py, &results)?;
                    Ok(Py::new(py, batch_records)?.into_any())
                }
            })
        })
    }

    /// Perform operations on multiple records (async).
    #[pyo3(signature = (keys, ops, policy=None))]
    fn batch_operate<'py>(
        &self,
        py: Python<'py>,
        keys: &Bound<'_, PyList>,
        ops: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!("async batch_operate: keys_count={}", keys.len());
        let client = self.get_client()?;
        let args = client_common::prepare_batch_operate_args(
            py,
            keys,
            ops,
            policy,
            &self.connection_info,
        )?;

        future_into_py(py, async move {
            let batch_ops = args.to_batch_ops();
            let results = traced_op!(
                "batch_operate",
                &args.batch_ns,
                &args.batch_set,
                args.parent_ctx,
                args.conn_info,
                { client.batch(&args.batch_policy, &batch_ops).await }
            )?;
            Python::attach(|py| batch_records_to_py(py, &results))
        })
    }

    /// Write multiple records from a numpy structured array (async).
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (data, namespace, set_name, _dtype, key_field="_key", policy=None))]
    fn batch_write_numpy<'py>(
        &self,
        py: Python<'py>,
        data: &Bound<'_, PyAny>,
        namespace: &str,
        set_name: &str,
        _dtype: &Bound<'_, PyAny>,
        key_field: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!(
            "async batch_write_numpy: namespace={}, set={}",
            namespace, set_name
        );
        let client = self.get_client()?;
        let batch_policy = crate::policy::batch_policy::parse_batch_policy(policy)?;
        #[allow(clippy::let_unit_value)]
        let parent_ctx = client_common::extract_parent_context(py);
        let conn_info = self.connection_info.clone();

        let records = crate::numpy_support::numpy_to_records(
            py, data, _dtype, namespace, set_name, key_field,
        )?;

        let ns = namespace.to_string();
        let set = set_name.to_string();

        future_into_py(py, async move {
            let write_policy = BatchWritePolicy::default();
            let batch_ops: Vec<BatchOperation> = records
                .iter()
                .map(|(key, bins)| {
                    let ops: Vec<aerospike_core::operations::Operation> =
                        bins.iter().map(aerospike_core::operations::put).collect();
                    BatchOperation::write(&write_policy, key.clone(), ops)
                })
                .collect();

            let results = traced_op!("batch_write_numpy", &ns, &set, parent_ctx, conn_info, {
                client.batch(&batch_policy, &batch_ops).await
            })?;
            Python::attach(|py| batch_records_to_py(py, &results))
        })
    }

    /// Remove multiple records (async).
    #[pyo3(signature = (keys, policy=None))]
    fn batch_remove<'py>(
        &self,
        py: Python<'py>,
        keys: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!("async batch_remove: keys_count={}", keys.len());
        let client = self.get_client()?;
        let args =
            client_common::prepare_batch_remove_args(py, keys, policy, &self.connection_info)?;

        future_into_py(py, async move {
            let ops = args.to_batch_ops();
            let results = traced_op!(
                "batch_remove",
                &args.batch_ns,
                &args.batch_set,
                args.parent_ctx,
                args.conn_info,
                { client.batch(&args.batch_policy, &ops).await }
            )?;
            Python::attach(|py| batch_records_to_py(py, &results))
        })
    }

    // ── Query ─────────────────────────────────────────────────

    /// Create a Query object.
    fn query(&self, namespace: &str, set_name: &str) -> PyResult<crate::query::PyQuery> {
        debug!("Creating async query: ns={} set={}", namespace, set_name);
        let client = self.get_client()?.clone();
        Ok(crate::query::PyQuery::new(
            client,
            namespace.to_string(),
            set_name.to_string(),
            self.connection_info.clone(),
        ))
    }

    // ── Index ─────────────────────────────────────────────────

    /// Create a secondary integer index (async).
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_integer_create<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.create_index_async(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::Numeric,
            policy,
        )
    }

    /// Create a secondary string index (async).
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_string_create<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.create_index_async(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::String,
            policy,
        )
    }

    /// Create a secondary geo2dsphere index (async).
    #[pyo3(signature = (namespace, set_name, bin_name, index_name, policy=None))]
    fn index_geo2dsphere_create<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.create_index_async(
            py,
            namespace,
            set_name,
            bin_name,
            index_name,
            aerospike_core::IndexType::Geo2DSphere,
            policy,
        )
    }

    /// Remove a secondary index (async).
    #[pyo3(signature = (namespace, index_name, policy=None))]
    fn index_remove<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        index_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!(
            "Async removing index: ns={} index={}",
            namespace, index_name
        );
        let client = self.get_client()?;
        let args = client_common::prepare_index_remove_args(namespace, index_name, policy)?;

        future_into_py(py, async move {
            client
                .drop_index(&args.admin_policy, &args.namespace, "", &args.index_name)
                .await
                .map_err(as_to_pyerr)?;
            Ok(())
        })
    }

    // ── Admin: User ──────────────────────────────────────────────

    /// Create a new user with the given roles (async).
    #[pyo3(signature = (username, password, roles, policy=None))]
    fn admin_create_user<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        password: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async creating user: username={}", username);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();
        let password = password.to_string();

        future_into_py(py, async move {
            let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
            client
                .create_user(&admin_policy, &username, &password, &role_refs)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Drop (delete) a user (async).
    #[pyo3(signature = (username, policy=None))]
    fn admin_drop_user<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async dropping user: username={}", username);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();

        future_into_py(py, async move {
            client
                .drop_user(&admin_policy, &username)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Change user password (async).
    #[pyo3(signature = (username, password, policy=None))]
    fn admin_change_password<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        password: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async changing password for user: username={}", username);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();
        let password = password.to_string();

        future_into_py(py, async move {
            client
                .change_password(&admin_policy, &username, &password)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Grant roles to a user (async).
    #[pyo3(signature = (username, roles, policy=None))]
    fn admin_grant_roles<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async granting roles to user: username={}", username);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();

        future_into_py(py, async move {
            let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
            client
                .grant_roles(&admin_policy, &username, &role_refs)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Revoke roles from a user (async).
    #[pyo3(signature = (username, roles, policy=None))]
    fn admin_revoke_roles<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        roles: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async revoking roles from user: username={}", username);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();

        future_into_py(py, async move {
            let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
            client
                .revoke_roles(&admin_policy, &username, &role_refs)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Query info about a specific user (async).
    #[pyo3(signature = (username, policy=None))]
    fn admin_query_user_info<'py>(
        &self,
        py: Python<'py>,
        username: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let username = username.to_string();

        future_into_py(py, async move {
            let users = client
                .query_users(&admin_policy, Some(&username))
                .await
                .map_err(as_to_pyerr)?;

            Python::attach(|py| {
                if let Some(user) = users.first() {
                    user_to_py(py, user)
                } else {
                    Err(crate::errors::AdminError::new_err(format!(
                        "User '{}' not found",
                        username
                    )))
                }
            })
        })
    }

    /// Query info about all users (async).
    #[pyo3(signature = (policy=None))]
    fn admin_query_users_info<'py>(
        &self,
        py: Python<'py>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;

        future_into_py(py, async move {
            let users = client
                .query_users(&admin_policy, None)
                .await
                .map_err(as_to_pyerr)?;

            Python::attach(|py| {
                let list = PyList::empty(py);
                for user in &users {
                    list.append(user_to_py(py, user)?)?;
                }
                Ok(list.into_any().unbind())
            })
        })
    }

    // ── Admin: Role ──────────────────────────────────────────────

    /// Create a new role with the given privileges (async).
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0))]
    fn admin_create_role<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
        whitelist: Option<Vec<String>>,
        read_quota: u32,
        write_quota: u32,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async creating role: role={}", role);
        let client = self.get_client()?;
        let args = client_common::prepare_create_role_args(
            role,
            privileges,
            policy,
            whitelist,
            read_quota,
            write_quota,
        )?;

        future_into_py(py, async move {
            let wl_refs: Vec<&str> = args.whitelist.iter().map(|s| s.as_str()).collect();
            client
                .create_role(
                    &args.admin_policy,
                    &args.role,
                    &args.privileges,
                    &wl_refs,
                    args.read_quota,
                    args.write_quota,
                )
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Drop (delete) a role (async).
    #[pyo3(signature = (role, policy=None))]
    fn admin_drop_role<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!("Async dropping role: role={}", role);
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let role = role.to_string();

        future_into_py(py, async move {
            client
                .drop_role(&admin_policy, &role)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Grant privileges to a role (async).
    #[pyo3(signature = (role, privileges, policy=None))]
    fn admin_grant_privileges<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        let role = role.to_string();

        future_into_py(py, async move {
            client
                .grant_privileges(&admin_policy, &role, &rust_privileges)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Revoke privileges from a role (async).
    #[pyo3(signature = (role, privileges, policy=None))]
    fn admin_revoke_privileges<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        privileges: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        let role = role.to_string();

        future_into_py(py, async move {
            client
                .revoke_privileges(&admin_policy, &role, &rust_privileges)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Query info about a specific role (async).
    #[pyo3(signature = (role, policy=None))]
    fn admin_query_role<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let role_name = role.to_string();

        future_into_py(py, async move {
            let roles = client
                .query_roles(&admin_policy, Some(&role_name))
                .await
                .map_err(as_to_pyerr)?;

            Python::attach(|py| {
                if let Some(r) = roles.first() {
                    role_to_py(py, r)
                } else {
                    Err(crate::errors::AdminError::new_err(format!(
                        "Role '{}' not found",
                        role_name
                    )))
                }
            })
        })
    }

    /// Query info about all roles (async).
    #[pyo3(signature = (policy=None))]
    fn admin_query_roles<'py>(
        &self,
        py: Python<'py>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;

        future_into_py(py, async move {
            let roles = client
                .query_roles(&admin_policy, None)
                .await
                .map_err(as_to_pyerr)?;

            Python::attach(|py| {
                let list = PyList::empty(py);
                for r in &roles {
                    list.append(role_to_py(py, r)?)?;
                }
                Ok(list.into_any().unbind())
            })
        })
    }

    /// Set allowlist (whitelist) for a role (async).
    #[pyo3(signature = (role, whitelist, policy=None))]
    fn admin_set_whitelist<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        whitelist: Vec<String>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let role = role.to_string();

        future_into_py(py, async move {
            let wl_refs: Vec<&str> = whitelist.iter().map(|s| s.as_str()).collect();
            client
                .set_allowlist(&admin_policy, &role, &wl_refs)
                .await
                .map_err(as_to_pyerr)
        })
    }

    /// Set quotas for a role (async).
    #[pyo3(signature = (role, read_quota=0, write_quota=0, policy=None))]
    fn admin_set_quotas<'py>(
        &self,
        py: Python<'py>,
        role: &str,
        read_quota: u32,
        write_quota: u32,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let admin_policy = client_common::prepare_admin_policy(policy)?;
        let role = role.to_string();

        future_into_py(py, async move {
            client
                .set_quotas(&admin_policy, &role, read_quota, write_quota)
                .await
                .map_err(as_to_pyerr)
        })
    }
}

impl PyAsyncClient {
    /// Returns a cloned `Arc` to the connected client, or an error if not yet connected.
    fn get_client(&self) -> PyResult<Arc<AsClient>> {
        self.inner
            .lock()
            .map_err(lock_err)?
            .as_ref()
            .cloned()
            .ok_or_else(|| {
                crate::errors::ClientError::new_err(
                    "Client is not connected. Call connect() first.",
                )
            })
    }

    /// Internal helper for index creation (async).
    #[allow(clippy::too_many_arguments)]
    fn create_index_async<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        bin_name: &str,
        index_name: &str,
        index_type: aerospike_core::IndexType,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        info!(
            "Async creating index: ns={} set={} bin={} index={}",
            namespace, set_name, bin_name, index_name
        );
        let client = self.get_client()?;
        let args = client_common::prepare_index_create_args(
            namespace, set_name, bin_name, index_name, index_type, policy,
        )?;

        future_into_py(py, async move {
            let task = client
                .create_index_on_bin(
                    &args.admin_policy,
                    &args.namespace,
                    &args.set_name,
                    &args.bin_name,
                    &args.index_name,
                    args.index_type,
                    aerospike_core::CollectionIndexType::Default,
                    None,
                )
                .await
                .map_err(as_to_pyerr)?;
            task.wait_till_complete(None::<std::time::Duration>)
                .await
                .map_err(as_to_pyerr)?;
            Ok(())
        })
    }
}
