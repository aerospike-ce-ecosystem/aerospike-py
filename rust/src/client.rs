use std::sync::Arc;

use crate::traced_op;
use aerospike_core::{
    BatchDeletePolicy, BatchOperation, BatchReadPolicy, BatchWritePolicy, Bin, Bins,
    Client as AsClient, Error as AsError, ResultCode, Task, UDFLang, Value,
};
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::batch_types::batch_to_batch_records_py;
use crate::errors::as_to_pyerr;
use crate::operations::py_ops_to_rust;
use crate::policy::admin_policy::{parse_admin_policy, parse_privileges, role_to_py, user_to_py};
use crate::policy::batch_policy::parse_batch_policy;
use crate::policy::client_policy::parse_client_policy;
use crate::policy::read_policy::parse_read_policy;
use crate::policy::read_policy::DEFAULT_READ_POLICY;
use crate::policy::write_policy::parse_write_policy;
use crate::policy::write_policy::DEFAULT_WRITE_POLICY;
use crate::record_helpers::{batch_records_to_py, record_to_meta};
use crate::runtime::RUNTIME;
use crate::types::bin::py_dict_to_bins;
use crate::types::host::parse_hosts_from_config;
use crate::types::key::{key_to_py, py_to_key};
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
        // Validate: username requires password
        if username.is_some() && password.is_none() {
            return Err(crate::errors::ClientError::new_err(
                "Password is required when username is provided.",
            ));
        }

        let config_dict = self.config.bind(py).cast::<PyDict>()?;

        // Copy the config dict so we don't mutate the caller's original
        let effective_config = config_dict.copy()?;

        // If username/password provided to connect(), override in the copy
        if let (Some(user), Some(pass)) = (username, password) {
            effective_config.set_item("user", user)?;
            effective_config.set_item("password", pass)?;
        }

        let parsed = parse_hosts_from_config(&effective_config)?;
        let client_policy = parse_client_policy(&effective_config)?;

        // Build connection info for span attributes
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
        let admin_policy = parse_admin_policy(policy)?;
        let cmd = command.to_string();

        py.detach(|| {
            RUNTIME.block_on(async {
                let nodes = client.nodes().await;
                let mut results = Vec::new();
                for node in &nodes {
                    match node.info(&admin_policy, &[&cmd]).await {
                        Ok(map) => {
                            let response = map.get(&cmd).cloned().unwrap_or_default();
                            results.push((node.name().to_string(), 0, response));
                        }
                        Err(e) => {
                            let code = match &e {
                                aerospike_core::Error::ServerError(rc, _, _) => {
                                    crate::errors::result_code_to_int(rc)
                                }
                                _ => -1,
                            };
                            results.push((node.name().to_string(), code, e.to_string()));
                        }
                    }
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
        let admin_policy = parse_admin_policy(policy)?;
        let cmd = command.to_string();

        py.detach(|| {
            RUNTIME.block_on(async {
                let node = client
                    .cluster
                    .get_random_node()
                    .await
                    .map_err(as_to_pyerr)?;
                let map = node
                    .info(&admin_policy, &[&cmd])
                    .await
                    .map_err(as_to_pyerr)?;
                Ok(map.get(&cmd).cloned().unwrap_or_default())
            })
        })
    }

    /// Write a record
    #[pyo3(signature = (key, bins, meta=None, policy=None))]
    fn put(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        bins: &Bound<'_, PyDict>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let client = self.get_client()?;
        let rust_key = py_to_key(key)?;
        debug!("put: ns={} set={}", rust_key.namespace, rust_key.set_name);
        let rust_bins = py_dict_to_bins(bins)?;

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        if policy.is_none() && meta.is_none() {
            let wp = &*DEFAULT_WRITE_POLICY;
            return py.detach(|| {
                RUNTIME.block_on(async {
                    traced_op!(
                        "put",
                        &rust_key.namespace,
                        &rust_key.set_name,
                        parent_ctx,
                        conn_info,
                        { client.put(wp, &rust_key, &rust_bins).await }
                    )
                })
            });
        }

        let write_policy = parse_write_policy(policy, meta)?;
        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "put",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.put(&write_policy, &rust_key, &rust_bins).await }
                )
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
        let rust_key = py_to_key(key)?;
        debug!("get: ns={} set={}", rust_key.namespace, rust_key.set_name);

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        if policy.is_none() {
            let rp = &*DEFAULT_READ_POLICY;
            let record = py.detach(|| {
                RUNTIME.block_on(async {
                    traced_op!(
                        "get",
                        &rust_key.namespace,
                        &rust_key.set_name,
                        parent_ctx,
                        conn_info,
                        { client.get(rp, &rust_key, Bins::All).await }
                    )
                })
            })?;
            return record_to_py(py, &record);
        }

        let read_policy = parse_read_policy(policy)?;
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "get",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.get(&read_policy, &rust_key, Bins::All).await }
                )
            })
        })?;

        record_to_py(py, &record)
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
        let rust_key = py_to_key(key)?;
        debug!(
            "select: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );

        let bin_names: Vec<String> = bins.extract()?;
        let bin_refs: Vec<&str> = bin_names.iter().map(|s| s.as_str()).collect();
        let bins_selector = Bins::from(bin_refs.as_slice());

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        if policy.is_none() {
            let rp = &*DEFAULT_READ_POLICY;
            let record = py.detach(|| {
                RUNTIME.block_on(async {
                    traced_op!(
                        "select",
                        &rust_key.namespace,
                        &rust_key.set_name,
                        parent_ctx,
                        conn_info,
                        { client.get(rp, &rust_key, bins_selector).await }
                    )
                })
            })?;
            return record_to_py(py, &record);
        }

        let read_policy = parse_read_policy(policy)?;
        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "select",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.get(&read_policy, &rust_key, bins_selector).await }
                )
            })
        })?;

        record_to_py(py, &record)
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
        let rust_key = py_to_key(key)?;
        debug!(
            "exists: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let key_py = key_to_py(py, &rust_key)?;

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[allow(unused)]
        let conn_info = &self.connection_info;

        let timer = crate::metrics::OperationTimer::start(
            "exists",
            &rust_key.namespace,
            &rust_key.set_name,
        );

        let result = if policy.is_none() {
            let rp = &*DEFAULT_READ_POLICY;
            py.detach(|| RUNTIME.block_on(async { client.get(rp, &rust_key, Bins::None).await }))
        } else {
            let read_policy = parse_read_policy(policy)?;
            py.detach(|| {
                RUNTIME.block_on(async { client.get(&read_policy, &rust_key, Bins::None).await })
            })
        };

        match &result {
            Ok(_) => timer.finish(""),
            Err(AsError::ServerError(ResultCode::KeyNotFoundError, _, _)) => timer.finish(""),
            Err(e) => timer.finish(&crate::metrics::error_type_from_aerospike_error(e)),
        }

        // OTel span for exists
        #[cfg(feature = "otel")]
        {
            use opentelemetry::trace::{SpanKind, TraceContextExt, Tracer};
            use opentelemetry::KeyValue;
            let tracer = crate::tracing::otel_impl::get_tracer();
            let span_name = format!("EXISTS {}.{}", rust_key.namespace, rust_key.set_name);
            let span = tracer
                .span_builder(span_name)
                .with_kind(SpanKind::Client)
                .with_attributes(vec![
                    KeyValue::new("db.system.name", "aerospike"),
                    KeyValue::new("db.namespace", rust_key.namespace.clone()),
                    KeyValue::new("db.collection.name", rust_key.set_name.clone()),
                    KeyValue::new("db.operation.name", "EXISTS"),
                    KeyValue::new("server.address", conn_info.server_address.clone()),
                    KeyValue::new("server.port", conn_info.server_port),
                    KeyValue::new("db.aerospike.cluster_name", conn_info.cluster_name.clone()),
                ])
                .start_with_context(&tracer, &parent_ctx);
            let cx = parent_ctx.with_span(span);
            let span_ref = opentelemetry::trace::TraceContextExt::span(&cx);
            match &result {
                Ok(_) | Err(AsError::ServerError(ResultCode::KeyNotFoundError, _, _)) => {}
                Err(e) => {
                    crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
                }
            }
            span_ref.end();
        }

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
        let rust_key = py_to_key(key)?;
        debug!(
            "remove: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let write_policy = parse_write_policy(policy, meta)?;

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "delete",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.delete(&write_policy, &rust_key).await }
                )
                .map(|_| ())
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
        let rust_key = py_to_key(key)?;
        debug!("touch: ns={} set={}", rust_key.namespace, rust_key.set_name);
        let mut write_policy = parse_write_policy(policy, meta)?;

        if val > 0 {
            write_policy.expiration = aerospike_core::Expiration::Seconds(val);
        }

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "touch",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.touch(&write_policy, &rust_key).await }
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
        let rust_key = py_to_key(key)?;
        debug!(
            "append: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = crate::types::value::py_to_value(val)?;
        let bins = [Bin::new(bin.to_string(), value)];

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "append",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.append(&write_policy, &rust_key, &bins).await }
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
        let rust_key = py_to_key(key)?;
        debug!(
            "prepend: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = crate::types::value::py_to_value(val)?;
        let bins = [Bin::new(bin.to_string(), value)];

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "prepend",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.prepend(&write_policy, &rust_key, &bins).await }
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
        let rust_key = py_to_key(key)?;
        debug!(
            "increment: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = crate::types::value::py_to_value(offset)?;
        let bins = [Bin::new(bin.to_string(), value)];

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "increment",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.add(&write_policy, &rust_key, &bins).await }
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;

        let names: Vec<String> = bin_names.extract()?;
        let bins: Vec<Bin> = names.into_iter().map(|n| Bin::new(n, Value::Nil)).collect();

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "remove_bin",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.put(&write_policy, &rust_key, &bins).await }
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;
        let rust_ops = py_ops_to_rust(ops)?;
        debug!(
            "operate: ns={} set={} ops_count={}",
            rust_key.namespace,
            rust_key.set_name,
            rust_ops.len()
        );

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "operate",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.operate(&write_policy, &rust_key, &rust_ops).await }
                )
            })
        })?;

        record_to_py(py, &record)
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;
        let rust_ops = py_ops_to_rust(ops)?;
        debug!(
            "operate_ordered: ns={} set={} ops_count={}",
            rust_key.namespace,
            rust_key.set_name,
            rust_ops.len()
        );

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        let record = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "operate_ordered",
                    &rust_key.namespace,
                    &rust_key.set_name,
                    parent_ctx,
                    conn_info,
                    { client.operate(&write_policy, &rust_key, &rust_ops).await }
                )
            })
        })?;

        // For operate_ordered, return (key, meta, ordered_bins)
        // where ordered_bins is a list of (bin_name, value) tuples
        let key_py = match &record.key {
            Some(k) => key_to_py(py, k)?,
            None => py.None(),
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

    // ── Query / Scan / Index ─────────────────────────────────────

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

    /// Create a Scan object for the given namespace and set.
    fn scan(&self, namespace: &str, set_name: &str) -> PyResult<crate::query::PyScan> {
        debug!("Creating scan: ns={} set={}", namespace, set_name);
        let client = self.get_client()?.clone();
        Ok(crate::query::PyScan::new(
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
        let admin_policy = parse_admin_policy(policy)?;

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .drop_index(&admin_policy, namespace, "", index_name)
                    .await
                    .map_err(as_to_pyerr)?;
                Ok(())
            })
        })
    }

    // ── Truncate ──────────────────────────────────────────────────

    /// Remove records in specified namespace/set efficiently.
    /// truncate(namespace, set_name, nanos, policy=None)
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
        let admin_policy = parse_admin_policy(policy)?;

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .truncate(&admin_policy, namespace, set_name, nanos)
                    .await
                    .map_err(as_to_pyerr)
            })
        })
    }

    // ── UDF ───────────────────────────────────────────────────────

    /// Register a UDF module from a file.
    /// udf_put(filename, udf_type=0, policy=None)
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
        let admin_policy = parse_admin_policy(policy)?;
        let language = match udf_type {
            0 => UDFLang::Lua,
            _ => {
                return Err(crate::errors::InvalidArgError::new_err(
                    "Only Lua UDF (udf_type=0) is supported.",
                ))
            }
        };

        // Read the file contents
        let udf_body = std::fs::read(filename).map_err(|e| {
            crate::errors::ClientError::new_err(format!(
                "Failed to read UDF file '{}': {}",
                filename, e
            ))
        })?;

        // Extract the server path (basename)
        let server_path = std::path::Path::new(filename)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(filename);
        let server_path = server_path.to_string();

        py.detach(|| {
            RUNTIME.block_on(async {
                let task = client
                    .register_udf(&admin_policy, &udf_body, &server_path, language)
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
    /// udf_remove(module, policy=None)
    #[pyo3(signature = (module, policy=None))]
    fn udf_remove(
        &self,
        py: Python<'_>,
        module: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        info!("Removing UDF: module={}", module);
        let client = self.get_client()?.clone();
        let admin_policy = parse_admin_policy(policy)?;
        let server_path = if module.ends_with(".lua") {
            module.to_string()
        } else {
            format!("{}.lua", module)
        };

        py.detach(|| {
            RUNTIME.block_on(async {
                let task = client
                    .remove_udf(&admin_policy, &server_path)
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
    /// apply(key, module, function, args=None, policy=None)
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
        let rust_key = py_to_key(key)?;
        debug!(
            "apply UDF: ns={} set={} module={} function={}",
            rust_key.namespace, rust_key.set_name, module, function
        );
        let write_policy = parse_write_policy(policy, None)?;

        // Convert args
        let rust_args: Option<Vec<Value>> = match args {
            Some(list) => {
                let mut v = Vec::new();
                for item in list.iter() {
                    v.push(crate::types::value::py_to_value(&item)?);
                }
                Some(v)
            }
            None => None,
        };

        let module = module.to_string();
        let function = function.to_string();

        let result = py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .execute_udf(
                        &write_policy,
                        &rust_key,
                        &module,
                        &function,
                        rust_args.as_deref(),
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        let wl = whitelist.unwrap_or_default();
        let wl_refs: Vec<&str> = wl.iter().map(|s| s.as_str()).collect();

        py.detach(|| {
            RUNTIME.block_on(async {
                client
                    .create_role(
                        &admin_policy,
                        role,
                        &rust_privileges,
                        &wl_refs,
                        read_quota,
                        write_quota,
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
    /// bins=None → read all bins; bins=["a","b"] → specific bins; bins=[] → existence check.
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
        let batch_policy = parse_batch_policy(policy)?;
        let read_policy = BatchReadPolicy::default();

        let bins_selector = match &bins {
            None => Bins::All,
            Some(b) if b.is_empty() => Bins::None,
            Some(b) => {
                let refs: Vec<&str> = b.iter().map(|s| s.as_str()).collect();
                Bins::from(refs.as_slice())
            }
        };

        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        let ops: Vec<BatchOperation> = rust_keys
            .iter()
            .map(|k| BatchOperation::read(&read_policy, k.clone(), bins_selector.clone()))
            .collect();

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_read",
                    &batch_ns,
                    &batch_set,
                    parent_ctx,
                    conn_info,
                    { client.batch(&batch_policy, &ops).await }
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
        let batch_policy = parse_batch_policy(policy)?;
        let write_policy = BatchWritePolicy::default();
        let rust_ops = py_ops_to_rust(ops)?;

        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        let batch_ops: Vec<BatchOperation> = rust_keys
            .iter()
            .map(|k| BatchOperation::write(&write_policy, k.clone(), rust_ops.clone()))
            .collect();

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_operate",
                    &batch_ns,
                    &batch_set,
                    parent_ctx,
                    conn_info,
                    { client.batch(&batch_policy, &batch_ops).await }
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
        let batch_policy = parse_batch_policy(policy)?;
        let delete_policy = BatchDeletePolicy::default();

        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        let ops: Vec<BatchOperation> = rust_keys
            .iter()
            .map(|k| BatchOperation::delete(&delete_policy, k.clone()))
            .collect();

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        #[cfg(feature = "otel")]
        let parent_ctx = crate::tracing::otel_impl::extract_python_context(py);
        #[cfg(not(feature = "otel"))]
        let parent_ctx = ();
        let conn_info = self.connection_info.clone();

        let results = py.detach(|| {
            RUNTIME.block_on(async {
                traced_op!(
                    "batch_remove",
                    &batch_ns,
                    &batch_set,
                    parent_ctx,
                    conn_info,
                    { client.batch(&batch_policy, &ops).await }
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
        let admin_policy = parse_admin_policy(policy)?;

        py.detach(|| {
            RUNTIME.block_on(async {
                let task = client
                    .create_index_on_bin(
                        &admin_policy,
                        namespace,
                        set_name,
                        bin_name,
                        index_name,
                        index_type,
                        aerospike_core::CollectionIndexType::Default,
                        None,
                    )
                    .await
                    .map_err(as_to_pyerr)?;
                // Wait for index creation to complete
                task.wait_till_complete(None::<std::time::Duration>)
                    .await
                    .map_err(as_to_pyerr)?;
                Ok(())
            })
        })
    }
}
