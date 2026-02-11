use std::sync::{Arc, Mutex, PoisonError};

use crate::timed_op;
use aerospike_core::{
    BatchDeletePolicy, BatchOperation, BatchReadPolicy, BatchWritePolicy, Bin, Bins,
    Client as AsClient, Error as AsError, PartitionFilter, ResultCode, Statement, Task, UDFLang,
    Value,
};
use futures::StreamExt;
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3_async_runtimes::tokio::future_into_py;

use crate::batch_types::batch_to_batch_records_py;
use crate::errors::as_to_pyerr;
use crate::operations::py_ops_to_rust;
use crate::policy::admin_policy::{parse_admin_policy, parse_privileges, role_to_py, user_to_py};
use crate::policy::batch_policy::parse_batch_policy;
use crate::policy::client_policy::parse_client_policy;
use crate::policy::query_policy::parse_query_policy;
use crate::policy::read_policy::parse_read_policy;
use crate::policy::write_policy::parse_write_policy;
use crate::record_helpers::{batch_records_to_py, record_to_meta};
use crate::types::bin::py_dict_to_bins;
use crate::types::host::parse_hosts_from_config;
use crate::types::key::{key_to_py, py_to_key};
use crate::types::record::record_to_py;
use crate::types::value::{py_to_value, value_to_py};

/// Shared async client state.
///
/// The triple wrapping is required by PyO3 async constraints:
/// - outer `Arc`: allows cloning into `future_into_py` closures (connect/close)
/// - `Mutex`: interior mutability for connect/close state changes
/// - `Option`: represents connected (Some) vs disconnected (None)
/// - inner `Arc<AsClient>`: cheap cloning per-operation without holding the Mutex lock
type SharedClientState = Arc<Mutex<Option<Arc<AsClient>>>>;

fn lock_err<T>(e: PoisonError<T>) -> PyErr {
    crate::errors::ClientError::new_err(format!("Internal lock poisoned: {e}"))
}

#[pyclass(name = "AsyncClient")]
pub struct PyAsyncClient {
    inner: SharedClientState,
    config: Py<PyAny>,
}

#[pymethods]
impl PyAsyncClient {
    #[new]
    fn new(config: Py<PyAny>) -> PyResult<Self> {
        Ok(PyAsyncClient {
            inner: Arc::new(Mutex::new(None)),
            config,
        })
    }

    /// Connect to the Aerospike cluster (async).
    #[pyo3(signature = (username=None, password=None))]
    fn connect<'py>(
        &self,
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

        // Copy the config dict so we don't mutate the caller's original
        let effective_config = config_dict.copy()?;

        if let (Some(user), Some(pass)) = (username, password) {
            effective_config.set_item("user", user)?;
            effective_config.set_item("password", pass)?;
        }

        let hosts_str = parse_hosts_from_config(&effective_config)?;
        let client_policy = parse_client_policy(&effective_config)?;
        let inner = self.inner.clone();

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

    /// Async context manager entry: `async with client as c:`
    fn __aenter__<'py>(slf: Py<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        future_into_py(py, async move { Ok(slf) })
    }

    /// Async context manager exit: closes the client.
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
        bins: &Bound<'_, PyDict>,
        meta: Option<&Bound<'_, PyDict>>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let rust_key = py_to_key(key)?;
        debug!(
            "async put: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let rust_bins = py_dict_to_bins(bins)?;
        let write_policy = parse_write_policy(policy, meta)?;

        future_into_py(py, async move {
            timed_op!("put", &rust_key.namespace, &rust_key.set_name, {
                client.put(&write_policy, &rust_key, &rust_bins).await
            })
        })
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async get: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let read_policy = parse_read_policy(policy)?;

        future_into_py(py, async move {
            let record = timed_op!("get", &rust_key.namespace, &rust_key.set_name, {
                client.get(&read_policy, &rust_key, Bins::All).await
            })?;

            Python::attach(|py| record_to_py(py, &record))
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async select: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let read_policy = parse_read_policy(policy)?;
        let bin_names: Vec<String> = bins.extract()?;

        future_into_py(py, async move {
            let bin_refs: Vec<&str> = bin_names.iter().map(|s| s.as_str()).collect();
            let bins_selector = Bins::from(bin_refs.as_slice());
            let record = timed_op!("select", &rust_key.namespace, &rust_key.set_name, {
                client.get(&read_policy, &rust_key, bins_selector).await
            })?;

            Python::attach(|py| record_to_py(py, &record))
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async exists: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let read_policy = parse_read_policy(policy)?;

        future_into_py(py, async move {
            let timer = crate::metrics::OperationTimer::start(
                "exists",
                &rust_key.namespace,
                &rust_key.set_name,
            );
            let result = client.get(&read_policy, &rust_key, Bins::None).await;

            match &result {
                Ok(_) => timer.finish(""),
                Err(AsError::ServerError(ResultCode::KeyNotFoundError, _, _)) => timer.finish(""),
                Err(e) => timer.finish(&crate::metrics::error_type_from_aerospike_error(e)),
            }

            Python::attach(|py| {
                let key_py = key_to_py(py, &rust_key)?;
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async remove: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let write_policy = parse_write_policy(policy, meta)?;

        future_into_py(py, async move {
            timed_op!("delete", &rust_key.namespace, &rust_key.set_name, {
                client.delete(&write_policy, &rust_key).await
            })
            .map(|_| ())
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async touch: ns={} set={}",
            rust_key.namespace, rust_key.set_name
        );
        let mut write_policy = parse_write_policy(policy, meta)?;
        if val > 0 {
            write_policy.expiration = aerospike_core::Expiration::Seconds(val);
        }

        future_into_py(py, async move {
            timed_op!("touch", &rust_key.namespace, &rust_key.set_name, {
                client.touch(&write_policy, &rust_key).await
            })
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async increment: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = py_to_value(offset)?;
        let bins = vec![Bin::new(bin.to_string(), value)];

        future_into_py(py, async move {
            timed_op!("increment", &rust_key.namespace, &rust_key.set_name, {
                client.add(&write_policy, &rust_key, &bins).await
            })
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;
        let rust_ops = py_ops_to_rust(ops)?;
        debug!(
            "async operate: ns={} set={} ops_count={}",
            rust_key.namespace,
            rust_key.set_name,
            rust_ops.len()
        );

        future_into_py(py, async move {
            let record = timed_op!("operate", &rust_key.namespace, &rust_key.set_name, {
                client.operate(&write_policy, &rust_key, &rust_ops).await
            })?;

            Python::attach(|py| record_to_py(py, &record))
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async append: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = py_to_value(val)?;
        let bins = vec![Bin::new(bin.to_string(), value)];

        future_into_py(py, async move {
            timed_op!("append", &rust_key.namespace, &rust_key.set_name, {
                client.append(&write_policy, &rust_key, &bins).await
            })
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async prepend: ns={} set={} bin={}",
            rust_key.namespace, rust_key.set_name, bin
        );
        let write_policy = parse_write_policy(policy, meta)?;
        let value = py_to_value(val)?;
        let bins = vec![Bin::new(bin.to_string(), value)];

        future_into_py(py, async move {
            timed_op!("prepend", &rust_key.namespace, &rust_key.set_name, {
                client.prepend(&write_policy, &rust_key, &bins).await
            })
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;
        let names: Vec<String> = bin_names.extract()?;
        let bins: Vec<Bin> = names.into_iter().map(|n| Bin::new(n, Value::Nil)).collect();

        future_into_py(py, async move {
            timed_op!("remove_bin", &rust_key.namespace, &rust_key.set_name, {
                client.put(&write_policy, &rust_key, &bins).await
            })
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
        let rust_key = py_to_key(key)?;
        let write_policy = parse_write_policy(policy, meta)?;
        let rust_ops = py_ops_to_rust(ops)?;
        debug!(
            "async operate_ordered: ns={} set={} ops_count={}",
            rust_key.namespace,
            rust_key.set_name,
            rust_ops.len()
        );

        future_into_py(py, async move {
            let record = timed_op!(
                "operate_ordered",
                &rust_key.namespace,
                &rust_key.set_name,
                { client.operate(&write_policy, &rust_key, &rust_ops).await }
            )?;

            Python::attach(|py| {
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
        let admin_policy = parse_admin_policy(policy)?;
        let namespace = namespace.to_string();
        let set_name = set_name.to_string();

        future_into_py(py, async move {
            client
                .truncate(&admin_policy, &namespace, &set_name, nanos)
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
        let admin_policy = parse_admin_policy(policy)?;
        let language = match udf_type {
            0 => UDFLang::Lua,
            _ => {
                return Err(crate::errors::InvalidArgError::new_err(
                    "Only Lua UDF (udf_type=0) is supported.",
                ))
            }
        };

        let udf_body = std::fs::read(filename).map_err(|e| {
            crate::errors::ClientError::new_err(format!(
                "Failed to read UDF file '{}': {}",
                filename, e
            ))
        })?;

        let server_path = std::path::Path::new(filename)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(filename)
            .to_string();

        future_into_py(py, async move {
            let task = client
                .register_udf(&admin_policy, &udf_body, &server_path, language)
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
        let admin_policy = parse_admin_policy(policy)?;
        let server_path = if module.ends_with(".lua") {
            module.to_string()
        } else {
            format!("{}.lua", module)
        };

        future_into_py(py, async move {
            let task = client
                .remove_udf(&admin_policy, &server_path)
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
        let rust_key = py_to_key(key)?;
        debug!(
            "async apply UDF: ns={} set={} module={} function={}",
            rust_key.namespace, rust_key.set_name, module, function
        );
        let write_policy = parse_write_policy(policy, None)?;

        let rust_args: Option<Vec<Value>> = match args {
            Some(list) => {
                let mut v = Vec::new();
                for item in list.iter() {
                    v.push(py_to_value(&item)?);
                }
                Some(v)
            }
            None => None,
        };

        let module = module.to_string();
        let function = function.to_string();

        future_into_py(py, async move {
            let result = client
                .execute_udf(
                    &write_policy,
                    &rust_key,
                    &module,
                    &function,
                    rust_args.as_deref(),
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

    /// Read multiple records (async). Returns BatchRecords, or NumpyBatchRecords when dtype is provided.
    /// bins=None → read all bins; bins=["a","b"] → specific bins; bins=[] → existence check.
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

        let use_numpy = _dtype.is_some();
        let dtype_py: Option<Py<PyAny>> = _dtype.map(|d| d.clone().unbind());

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        future_into_py(py, async move {
            let ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::read(&read_policy, k.clone(), bins_selector.clone()))
                .collect();

            let results = timed_op!("batch_read", &batch_ns, &batch_set, {
                client.batch(&batch_policy, &ops).await
            })?;

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
        let batch_policy = parse_batch_policy(policy)?;
        let write_policy = BatchWritePolicy::default();
        let rust_ops = py_ops_to_rust(ops)?;
        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        future_into_py(py, async move {
            let batch_ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::write(&write_policy, k.clone(), rust_ops.clone()))
                .collect();

            let results = timed_op!("batch_operate", &batch_ns, &batch_set, {
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
        let batch_policy = parse_batch_policy(policy)?;
        let delete_policy = BatchDeletePolicy::default();
        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        let (batch_ns, batch_set) = rust_keys
            .first()
            .map(|k| (k.namespace.clone(), k.set_name.clone()))
            .unwrap_or_default();

        future_into_py(py, async move {
            let ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::delete(&delete_policy, k.clone()))
                .collect();

            let results = timed_op!("batch_remove", &batch_ns, &batch_set, {
                client.batch(&batch_policy, &ops).await
            })?;
            Python::attach(|py| batch_records_to_py(py, &results))
        })
    }

    // ── Scan ──────────────────────────────────────────────────

    /// Scan all records (async). Returns list of (key, meta, bins).
    #[pyo3(signature = (namespace, set_name, policy=None))]
    fn scan<'py>(
        &self,
        py: Python<'py>,
        namespace: &str,
        set_name: &str,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!("async scan: ns={} set={}", namespace, set_name);
        let client = self.get_client()?;
        let query_policy = parse_query_policy(policy)?;
        let stmt = Statement::new(namespace, set_name, Bins::All);
        let ns = namespace.to_string();
        let set = set_name.to_string();

        future_into_py(py, async move {
            let timer = crate::metrics::OperationTimer::start("scan", &ns, &set);
            let scan_result: Result<Vec<_>, AsError> = async {
                let rs = client
                    .query(&query_policy, PartitionFilter::all(), stmt)
                    .await?;
                let mut stream = rs.into_stream();
                let mut results = Vec::new();
                while let Some(result) = stream.next().await {
                    results.push(result?);
                }
                Ok(results)
            }
            .await;

            match &scan_result {
                Ok(_) => timer.finish(""),
                Err(e) => timer.finish(&crate::metrics::error_type_from_aerospike_error(e)),
            }

            let records = scan_result.map_err(as_to_pyerr)?;

            Python::attach(|py| {
                let py_list = PyList::empty(py);
                for record in &records {
                    py_list.append(record_to_py(py, record)?)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
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
        let admin_policy = parse_admin_policy(policy)?;
        let namespace = namespace.to_string();
        let index_name = index_name.to_string();

        future_into_py(py, async move {
            client
                .drop_index(&admin_policy, &namespace, "", &index_name)
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
        let rust_privileges = parse_privileges(privileges)?;
        let role = role.to_string();
        let wl = whitelist.unwrap_or_default();

        future_into_py(py, async move {
            let wl_refs: Vec<&str> = wl.iter().map(|s| s.as_str()).collect();
            client
                .create_role(
                    &admin_policy,
                    &role,
                    &rust_privileges,
                    &wl_refs,
                    read_quota,
                    write_quota,
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;

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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
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
        let admin_policy = parse_admin_policy(policy)?;
        let namespace = namespace.to_string();
        let set_name = set_name.to_string();
        let bin_name = bin_name.to_string();
        let index_name = index_name.to_string();

        future_into_py(py, async move {
            let task = client
                .create_index_on_bin(
                    &admin_policy,
                    &namespace,
                    &set_name,
                    &bin_name,
                    &index_name,
                    index_type,
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
