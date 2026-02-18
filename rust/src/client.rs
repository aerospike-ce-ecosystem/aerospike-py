use std::sync::Arc;

use crate::client_common::{self, PutPolicy};
use crate::traced_exists_op;
use crate::traced_op;
use aerospike_core::{Bins, Client as AsClient, Error as AsError, ResultCode, Task};
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::batch_types::batch_to_batch_records_py;
use crate::errors::as_to_pyerr;
use crate::policy::admin_policy::{parse_privileges, role_to_py, user_to_py};
use crate::policy::client_policy::parse_client_policy;
use crate::policy::write_policy::DEFAULT_WRITE_POLICY;
use crate::record_helpers::{batch_records_to_py, record_to_meta};
use crate::runtime::RUNTIME;
use crate::types::host::parse_hosts_from_config;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py;
use crate::types::value::value_to_py;

#[pyclass(name = "Client", subclass)]
pub struct PyClient {
    inner: Option<Arc<AsClient>>,
    config: Py<PyAny>,
    connection_info: crate::tracing::ConnectionInfo,
}

#[pymethods]
impl PyClient {
    #[new]
    fn new(config: Py<PyAny>) -> PyResult<Self> {
        Ok(PyClient {
            inner: None,
            config,
            connection_info: crate::tracing::ConnectionInfo::default(),
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
        info!("Connected to Aerospike cluster");
        Ok(())
    }

    /// Check if the client is connected
    fn is_connected(&self, py: Python<'_>) -> PyResult<bool> {
        trace!("Checking client connection status");
        match &self.inner {
            Some(client) => {
                let client = client.clone();
                Ok(py.detach(|| RUNTIME.block_on(async { client.is_connected().await })))
            }
            None => Ok(false),
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
    fn get_node_names(&self, py: Python<'_>) -> PyResult<Vec<String>> {
        let client = self.get_client()?;
        py.detach(|| RUNTIME.block_on(async { Ok(client.node_names().await) }))
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

        py.detach(|| {
            RUNTIME.block_on(async {
                let nodes = client.nodes().await;
                let mut results = Vec::new();
                for node in &nodes {
                    let r = node.info(&args.admin_policy, &[&args.command]).await;
                    results.push(client_common::info_node_result(node, &args.command, r));
                }
                Ok(results)
            })
        })
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

        py.detach(|| {
            RUNTIME.block_on(async {
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
        })
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
        debug!("put: ns={} set={}", args.key.namespace, args.key.set_name);

        match args.policy {
            PutPolicy::Default => {
                let wp = &*DEFAULT_WRITE_POLICY;
                py.detach(|| {
                    RUNTIME.block_on(async {
                        traced_op!(
                            "put",
                            &args.key.namespace,
                            &args.key.set_name,
                            args.parent_ctx,
                            args.conn_info,
                            { client.put(wp, &args.key, &args.bins).await }
                        )
                    })
                })
            }
            PutPolicy::Custom(ref wp) => py.detach(|| {
                RUNTIME.block_on(async {
                    traced_op!(
                        "put",
                        &args.key.namespace,
                        &args.key.set_name,
                        args.parent_ctx,
                        args.conn_info,
                        { client.put(wp, &args.key, &args.bins).await }
                    )
                })
            }),
        }
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
        let args = client_common::prepare_get_args(py, key, policy, &self.connection_info)?;
        debug!("get: ns={} set={}", args.key.namespace, args.key.set_name);

        let rp = args.read_policy();
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "get",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.get(rp, &args.key, Bins::All).await }
                )
            })
        })?;

        record_to_py(py, &record, Some(&args.key))
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

        let rp = args.read_policy();
        let bins_selector = args.bins_selector();
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "select",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.get(rp, &args.key, bins_selector).await }
                )
            })
        })?;

        record_to_py(py, &record, Some(&args.key))
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

        let result = py.detach(|| {
            RUNTIME.block_on(async {
                traced_exists_op!(
                    "exists",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.get(&args.read_policy, &args.key, Bins::None).await }
                )
            })
        });

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

        let existed = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "delete",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.delete(&args.write_policy, &args.key).await }
                )
            })
        })?;

        if !existed {
            return Err(crate::errors::RecordNotFound::new_err(
                "AEROSPIKE_ERR (2): Record not found",
            ));
        }
        Ok(())
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

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "touch",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.touch(&args.write_policy, &args.key).await }
                )
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

        py.detach(|| {
            RUNTIME.block_on(async {
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

        py.detach(|| {
            RUNTIME.block_on(async {
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

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "increment",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.add(&args.write_policy, &args.key, &args.bins).await }
                )
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

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "remove_bin",
                    &args.key.namespace,
                    &args.key.set_name,
                    args.parent_ctx,
                    args.conn_info,
                    { client.put(&args.write_policy, &args.key, &args.bins).await }
                )
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

        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
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
                )
            })
        })?;

        record_to_py(py, &record, Some(&args.key))
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

        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
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
                )
            })
        })?;

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

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .drop_index(&args.admin_policy, &args.namespace, "", &args.index_name)
                    .await
                    .map_err(as_to_pyerr)?;
                Ok(())
            })
        })
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

        py.detach(|| {
            RUNTIME.block_on(async {
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
        })
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

        py.detach(|| {
            RUNTIME.block_on(async {
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
        })
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

        py.detach(|| {
            RUNTIME.block_on(async {
                let task = client
                    .remove_udf(&args.admin_policy, &args.server_path)
                    .await
                    .map_err(as_to_pyerr)?;
                task.wait_till_complete(None::<std::time::Duration>)
                    .await
                    .map_err(as_to_pyerr)?;
                Ok(())
            })
        })
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

        let result = py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .execute_udf(
                        &a.write_policy,
                        &a.key,
                        &a.module,
                        &a.function,
                        a.args.as_deref(),
                    )
                    .await
                    .map_err(as_to_pyerr)
            })
        })?;

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
        let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .create_user(&admin_policy, username, password, &role_refs)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .drop_user(&admin_policy, username)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .change_password(&admin_policy, username, password)
                    .await
                    .map_err(as_to_pyerr)
            })
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
        let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .grant_roles(&admin_policy, username, &role_refs)
                    .await
                    .map_err(as_to_pyerr)
            })
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
        let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .revoke_roles(&admin_policy, username, &role_refs)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .query_users(&admin_policy, Some(&username))
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .query_users(&admin_policy, None)
                    .await
                    .map_err(as_to_pyerr)
            })
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
        let wl_refs: Vec<&str> = args.whitelist.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
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
        })
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

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .drop_role(&admin_policy, role)
                    .await
                    .map_err(as_to_pyerr)
            })
        })
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
            RUNTIME.block_on(async {
                client
                    .grant_privileges(&admin_policy, role, &rust_privileges)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .revoke_privileges(&admin_policy, role, &rust_privileges)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .query_roles(&admin_policy, Some(&role_name))
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .query_roles(&admin_policy, None)
                    .await
                    .map_err(as_to_pyerr)
            })
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
        let wl_refs: Vec<&str> = whitelist.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .set_allowlist(&admin_policy, role, &wl_refs)
                    .await
                    .map_err(as_to_pyerr)
            })
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
            RUNTIME.block_on(async {
                client
                    .set_quotas(&admin_policy, role, read_quota, write_quota)
                    .await
                    .map_err(as_to_pyerr)
            })
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
        let ops = args.to_batch_ops();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_read",
                    &args.batch_ns,
                    &args.batch_set,
                    args.parent_ctx,
                    args.conn_info,
                    { client.batch(&args.batch_policy, &ops).await }
                )
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
        let batch_ops = args.to_batch_ops();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_operate",
                    &args.batch_ns,
                    &args.batch_set,
                    args.parent_ctx,
                    args.conn_info,
                    { client.batch(&args.batch_policy, &batch_ops).await }
                )
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
        let ops = args.to_batch_ops();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_remove",
                    &args.batch_ns,
                    &args.batch_set,
                    args.parent_ctx,
                    args.conn_info,
                    { client.batch(&args.batch_policy, &ops).await }
                )
            })
        })?;

        batch_records_to_py(py, &results)
    }
}

impl PyClient {
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

        py.detach(|| {
            RUNTIME.block_on(async {
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
        })
    }
}
