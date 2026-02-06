use std::sync::{Arc, Mutex};

use aerospike_core::{
    BatchDeletePolicy, BatchOperation, BatchReadPolicy, Bin, Bins, Client as AsClient,
    Error as AsError, PartitionFilter, ResultCode, Statement, Task, UDFLang, Value,
};
use futures::StreamExt;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3_async_runtimes::tokio::future_into_py;

use crate::errors::as_to_pyerr;
use crate::operations::py_ops_to_rust;
use crate::policy::admin_policy::parse_admin_policy;
use crate::policy::batch_policy::parse_batch_policy;
use crate::policy::client_policy::parse_client_policy;
use crate::policy::query_policy::parse_query_policy;
use crate::policy::read_policy::parse_read_policy;
use crate::policy::write_policy::parse_write_policy;
use crate::record_helpers::{batch_record_meta, batch_records_to_py, record_to_meta};
use crate::types::bin::py_dict_to_bins;
use crate::types::host::parse_hosts_from_config;
use crate::types::key::{key_to_py, py_to_key};
use crate::types::record::record_to_py;
use crate::types::value::{py_to_value, value_to_py};

#[pyclass(name = "AsyncClient")]
pub struct PyAsyncClient {
    inner: Arc<Mutex<Option<Arc<AsClient>>>>,
    config: PyObject,
}

#[pymethods]
impl PyAsyncClient {
    #[new]
    fn new(config: PyObject) -> PyResult<Self> {
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

        let config_dict = self.config.bind(py).downcast::<PyDict>()?;

        // Copy the config dict so we don't mutate the caller's original
        let effective_config = config_dict.copy()?;

        if let (Some(user), Some(pass)) = (username, password) {
            effective_config.set_item("user", user)?;
            effective_config.set_item("password", pass)?;
        }

        let hosts_str = parse_hosts_from_config(&effective_config)?;
        let client_policy = parse_client_policy(&effective_config)?;
        let inner = self.inner.clone();

        future_into_py(py, async move {
            let client = AsClient::new(
                &client_policy,
                &hosts_str as &(dyn aerospike_core::ToHosts + Send + Sync),
            )
            .await
            .map_err(as_to_pyerr)?;

            *inner
                .lock()
                .map_err(|_| crate::errors::ClientError::new_err("Internal lock poisoned"))? =
                Some(Arc::new(client));
            Ok(())
        })
    }

    /// Check if connected (sync, no I/O).
    fn is_connected(&self) -> bool {
        self.inner
            .lock()
            .map(|guard| guard.is_some())
            .unwrap_or(false)
    }

    /// Close connection (async).
    fn close<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .inner
            .lock()
            .map_err(|_| crate::errors::ClientError::new_err("Internal lock poisoned"))?
            .take();
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
        let rust_bins = py_dict_to_bins(bins)?;
        let write_policy = parse_write_policy(policy, meta)?;

        future_into_py(py, async move {
            client
                .put(&write_policy, &rust_key, &rust_bins)
                .await
                .map_err(as_to_pyerr)
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
        let read_policy = parse_read_policy(policy)?;

        future_into_py(py, async move {
            let record = client
                .get(&read_policy, &rust_key, Bins::All)
                .await
                .map_err(as_to_pyerr)?;

            Python::with_gil(|py| record_to_py(py, &record))
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
        let read_policy = parse_read_policy(policy)?;
        let bin_names: Vec<String> = bins.extract()?;

        future_into_py(py, async move {
            let bin_refs: Vec<&str> = bin_names.iter().map(|s| s.as_str()).collect();
            let bins_selector = Bins::from(bin_refs.as_slice());
            let record = client
                .get(&read_policy, &rust_key, bins_selector)
                .await
                .map_err(as_to_pyerr)?;

            Python::with_gil(|py| record_to_py(py, &record))
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
        let read_policy = parse_read_policy(policy)?;

        future_into_py(py, async move {
            let result = client.get(&read_policy, &rust_key, Bins::None).await;

            Python::with_gil(|py| {
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
        let write_policy = parse_write_policy(policy, meta)?;

        future_into_py(py, async move {
            client
                .delete(&write_policy, &rust_key)
                .await
                .map_err(as_to_pyerr)?;
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
        let rust_key = py_to_key(key)?;
        let mut write_policy = parse_write_policy(policy, meta)?;
        if val > 0 {
            write_policy.expiration = aerospike_core::Expiration::Seconds(val);
        }

        future_into_py(py, async move {
            client
                .touch(&write_policy, &rust_key)
                .await
                .map_err(as_to_pyerr)
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
        let write_policy = parse_write_policy(policy, meta)?;
        let value = py_to_value(offset)?;
        let bins = vec![Bin::new(bin.to_string(), value)];

        future_into_py(py, async move {
            client
                .add(&write_policy, &rust_key, &bins)
                .await
                .map_err(as_to_pyerr)
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

        future_into_py(py, async move {
            let record = client
                .operate(&write_policy, &rust_key, &rust_ops)
                .await
                .map_err(as_to_pyerr)?;

            Python::with_gil(|py| record_to_py(py, &record))
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

            Python::with_gil(|py| match result {
                Some(val) => value_to_py(py, &val),
                None => Ok(py.None()),
            })
        })
    }

    // ── Batch ─────────────────────────────────────────────────

    /// Read multiple records (async).
    #[pyo3(signature = (keys, policy=None))]
    fn get_many<'py>(
        &self,
        py: Python<'py>,
        keys: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let batch_policy = parse_batch_policy(policy)?;
        let read_policy = BatchReadPolicy::default();
        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        future_into_py(py, async move {
            let ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::read(&read_policy, k.clone(), Bins::All))
                .collect();

            let results = client
                .batch(&batch_policy, &ops)
                .await
                .map_err(as_to_pyerr)?;
            Python::with_gil(|py| batch_records_to_py(py, &results))
        })
    }

    /// Check if multiple records exist (async).
    #[pyo3(signature = (keys, policy=None))]
    fn exists_many<'py>(
        &self,
        py: Python<'py>,
        keys: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self.get_client()?;
        let batch_policy = parse_batch_policy(policy)?;
        let read_policy = BatchReadPolicy::default();
        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        future_into_py(py, async move {
            let ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::read(&read_policy, k.clone(), Bins::None))
                .collect();

            let results = client
                .batch(&batch_policy, &ops)
                .await
                .map_err(as_to_pyerr)?;

            Python::with_gil(|py| {
                let py_list = PyList::empty(py);
                for br in &results {
                    let key_py = key_to_py(py, &br.key)?;
                    let meta = batch_record_meta(py, br);
                    let tuple = PyTuple::new(py, [key_py, meta])?;
                    py_list.append(tuple)?;
                }
                Ok(py_list.into_any().unbind())
            })
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
        let client = self.get_client()?;
        let batch_policy = parse_batch_policy(policy)?;
        let delete_policy = BatchDeletePolicy::default();
        let rust_keys: Vec<aerospike_core::Key> = keys
            .iter()
            .map(|k| py_to_key(&k))
            .collect::<PyResult<_>>()?;

        future_into_py(py, async move {
            let ops: Vec<BatchOperation> = rust_keys
                .iter()
                .map(|k| BatchOperation::delete(&delete_policy, k.clone()))
                .collect();

            let results = client
                .batch(&batch_policy, &ops)
                .await
                .map_err(as_to_pyerr)?;
            Python::with_gil(|py| batch_records_to_py(py, &results))
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
        let client = self.get_client()?;
        let query_policy = parse_query_policy(policy)?;
        let stmt = Statement::new(namespace, set_name, Bins::All);

        future_into_py(py, async move {
            let rs = client
                .query(&query_policy, PartitionFilter::all(), stmt)
                .await
                .map_err(as_to_pyerr)?;
            let mut stream = rs.into_stream();
            let mut records = Vec::new();
            while let Some(result) = stream.next().await {
                records.push(result.map_err(as_to_pyerr)?);
            }

            Python::with_gil(|py| {
                let py_list = PyList::empty(py);
                for record in &records {
                    py_list.append(record_to_py(py, record)?)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }
}

impl PyAsyncClient {
    fn get_client(&self) -> PyResult<Arc<AsClient>> {
        self.inner
            .lock()
            .map_err(|_| crate::errors::ClientError::new_err("Internal lock poisoned"))?
            .as_ref()
            .cloned()
            .ok_or_else(|| {
                crate::errors::ClientError::new_err(
                    "Client is not connected. Call connect() first.",
                )
            })
    }
}
