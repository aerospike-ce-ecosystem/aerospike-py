use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Arc;

use crate::backpressure::OperationLimiter;
use crate::client_common;
use crate::client_ops;
use aerospike_core::Client as AsClient;
use arc_swap::ArcSwapOption;
use log::{debug, info, trace, warn};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3_async_runtimes::tokio::future_into_py;

// Lifecycle states for the client state machine.
const DISCONNECTED: u8 = 0;
const CONNECTING: u8 = 1;
const CONNECTED: u8 = 2;
const CLOSING: u8 = 3;

use crate::batch_types::{PendingBatchRead, PendingBatchRecords};
use crate::errors::as_to_pyerr;
use crate::policy::admin_policy::{parse_privileges, role_to_py, user_to_py};
use crate::policy::client_policy::{parse_backpressure_config, parse_client_policy};
use crate::record_helpers::{PendingExists, PendingOrderedRecord, PendingRecord};
use crate::types::host::parse_hosts_from_config;
use crate::types::key::key_to_py;
use crate::types::value::value_to_py;

/// Thread-safe shared state for the async client.
///
/// Uses `ArcSwapOption` for lock-free atomic reads (Arc clone).
/// `connect()` stores the client, `close()` swaps it to `None`.
type SharedClientState = Arc<ArcSwapOption<AsClient>>;

/// Asynchronous Aerospike client exposed to Python as `AsyncClient`.
///
/// All I/O methods return Python awaitables via `future_into_py`.
/// The underlying `aerospike_core::Client` is shared behind a `Mutex`
/// to allow safe concurrent access from multiple Python coroutines.
#[pyclass(name = "AsyncClient")]
pub struct PyAsyncClient {
    /// The underlying async client, wrapped in `ArcSwapOption` for lock-free access.
    /// `None` before `connect()` is called; swapped to `None` by `close()`.
    inner: SharedClientState,
    /// Python config dict, retained for potential reconnection.
    config: Py<PyAny>,
    /// Connection metadata used for OTel span attributes (Arc for cheap cloning).
    connection_info: Arc<crate::tracing::ConnectionInfo>,
    /// Operation concurrency limiter (disabled by default).
    limiter: Arc<OperationLimiter>,
    /// Lifecycle state: Disconnected(0) → Connecting(1) → Connected(2) → Closing(3).
    state: Arc<AtomicU8>,
}

#[pymethods]
impl PyAsyncClient {
    #[new]
    fn new(config: Py<PyAny>) -> PyResult<Self> {
        Ok(PyAsyncClient {
            inner: Arc::new(ArcSwapOption::empty()),
            config,
            connection_info: Arc::new(crate::tracing::ConnectionInfo::default()),
            limiter: Arc::new(OperationLimiter::new(0, 0)),
            state: Arc::new(AtomicU8::new(DISCONNECTED)),
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
        // Guard: only allow Disconnected → Connecting transition.
        // Validate and parse config BEFORE the CAS so that config errors
        // don't leave the client stuck in CONNECTING.
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

        // Config parsed successfully — now atomically transition to Connecting.
        if self
            .state
            .compare_exchange(DISCONNECTED, CONNECTING, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            let current = self.state.load(Ordering::SeqCst);
            let state_name = match current {
                CONNECTING => "connecting",
                CONNECTED => "connected",
                CLOSING => "closing",
                _ => "unknown",
            };
            return Err(crate::errors::ClientError::new_err(format!(
                "Cannot connect: client is already {state_name}. Close the client before reconnecting."
            )));
        }

        let inner = self.inner.clone();
        let state = self.state.clone();

        self.connection_info = Arc::new(crate::tracing::ConnectionInfo {
            server_address: Arc::from(parsed.first_address.as_str()),
            server_port: parsed.first_port as i64,
            cluster_name: Arc::from(cluster_name.as_str()),
        });

        self.limiter = Arc::new(OperationLimiter::new(max_ops, timeout_ms));

        let hosts_str = parsed.connection_string;
        info!("Async connecting to Aerospike cluster: {}", hosts_str);
        future_into_py(py, async move {
            let result = AsClient::new(
                &client_policy,
                &hosts_str as &(dyn aerospike_core::ToHosts + Send + Sync),
            )
            .await;

            match result {
                Ok(client) => {
                    inner.store(Some(Arc::new(client)));
                    state.store(CONNECTED, Ordering::SeqCst);
                    Ok(())
                }
                Err(e) => {
                    // Revert to Disconnected so retry is possible.
                    state.store(DISCONNECTED, Ordering::SeqCst);
                    Err(as_to_pyerr(e))
                }
            }
        })
    }

    /// Check if connected (sync, no I/O, lock-free).
    fn is_connected(&self) -> bool {
        trace!("Checking async client connection status");
        self.state.load(Ordering::SeqCst) == CONNECTED && self.inner.load().is_some()
    }

    /// Lightweight health check: returns `True` if a random node responds.
    fn ping<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.inner.load_full();
        future_into_py(py, async move {
            match client {
                Some(c) => Ok(client_ops::do_ping(&c).await),
                None => Ok(false),
            }
        })
    }

    /// Close connection (async).
    fn close<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        info!("Closing async client connection");
        let current = self.state.load(Ordering::SeqCst);
        if current == DISCONNECTED || current == CLOSING {
            // Already disconnected or closing — idempotent no-op.
            return future_into_py(py, async move { Ok(()) });
        }
        if current == CONNECTING {
            return Err(crate::errors::ClientError::new_err(
                "Cannot close: client is currently connecting.",
            ));
        }

        self.state.store(CLOSING, Ordering::SeqCst);
        let client = self.inner.swap(None);
        let state = self.state.clone();

        // Reset connection metadata and limiter to default.
        self.connection_info = Arc::new(crate::tracing::ConnectionInfo::default());
        self.limiter = Arc::new(OperationLimiter::new(0, 0));

        future_into_py(py, async move {
            let result = if let Some(c) = client {
                c.close().await.map_err(as_to_pyerr)
            } else {
                Ok(())
            };
            // Always transition to Disconnected — inner is already None.
            state.store(DISCONNECTED, Ordering::SeqCst);
            result
        })
    }

    /// Get node names (sync, no I/O, lock-free).
    fn get_node_names(&self) -> PyResult<Vec<String>> {
        Ok(self.get_client()?.node_names())
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
        future_into_py(
            py,
            async move { client_ops::do_info_all(&client, &args).await },
        )
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
            client_ops::do_info_random_node(&client, &args).await
        })
    }

    /// Async context manager entry.
    fn __aenter__<'py>(slf: Py<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        future_into_py(py, async move { Ok(slf) })
    }

    /// Async context manager exit.
    #[pyo3(signature = (_exc_type=None, _exc_val=None, _exc_tb=None))]
    fn __aexit__<'py>(
        &mut self,
        py: Python<'py>,
        _exc_type: Option<&Bound<'_, PyAny>>,
        _exc_val: Option<&Bound<'_, PyAny>>,
        _exc_tb: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let current = self.state.load(Ordering::SeqCst);
        if current != CONNECTED {
            return future_into_py(py, async move { Ok(false) });
        }
        self.state.store(CLOSING, Ordering::SeqCst);
        let client = self.inner.swap(None);
        let state = self.state.clone();

        // Reset connection metadata and limiter to default.
        self.connection_info = Arc::new(crate::tracing::ConnectionInfo::default());
        self.limiter = Arc::new(OperationLimiter::new(0, 0));

        future_into_py(py, async move {
            let result = if let Some(c) = client {
                c.close().await.map_err(as_to_pyerr)
            } else {
                Ok(())
            };
            // Always transition to Disconnected — inner is already None.
            state.store(DISCONNECTED, Ordering::SeqCst);
            result.map(|()| false)
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
        let limiter = self.limiter.clone();
        debug!(
            "async put: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        future_into_py(py, async move {
            let _permit = limiter.acquire_named("put").await?;
            client_ops::do_put(&client, args).await
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
        let limiter = self.limiter.clone();
        let args = client_common::prepare_get_args(py, key, policy, &self.connection_info)?;
        debug!(
            "async get: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let key_py = key_to_py(py, &args.key)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("get").await?;
            let record = client_ops::do_get(&client, &args).await?;
            Ok(PendingRecord { record, key_py })
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_select_args(py, key, bins, policy, &self.connection_info)?;
        debug!(
            "async select: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let key_py = key_to_py(py, &args.key)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("select").await?;
            let record = client_ops::do_select(&client, &args).await?;
            Ok(PendingRecord { record, key_py })
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
        let limiter = self.limiter.clone();
        let args = client_common::prepare_exists_args(py, key, policy, &self.connection_info)?;
        debug!(
            "async exists: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        let key_py = key_to_py(py, &args.key)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("exists").await?;
            let result = client_ops::do_exists(&client, &args).await;
            Ok(PendingExists { result, key_py })
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_remove_args(py, key, meta, policy, &self.connection_info)?;
        debug!(
            "async remove: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        future_into_py(py, async move {
            let _permit = limiter.acquire_named("remove").await?;
            client_ops::do_remove(&client, args).await
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_touch_args(py, key, val, meta, policy, &self.connection_info)?;
        debug!(
            "async touch: ns={} set={}",
            args.key.namespace, args.key.set_name
        );
        future_into_py(py, async move {
            let _permit = limiter.acquire_named("touch").await?;
            client_ops::do_touch(&client, args).await
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
        let limiter = self.limiter.clone();
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
            let _permit = limiter.acquire_named("increment").await?;
            client_ops::do_increment(&client, args).await
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "async operate: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );
        let key_py = key_to_py(py, &args.key)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("operate").await?;
            let record = client_ops::do_operate(&client, &args).await?;
            Ok(PendingRecord { record, key_py })
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
        let limiter = self.limiter.clone();
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
            let _permit = limiter.acquire_named("append").await?;
            client_ops::do_append(&client, args).await
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
        let limiter = self.limiter.clone();
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
            let _permit = limiter.acquire_named("prepend").await?;
            client_ops::do_prepend(&client, args).await
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
        let limiter = self.limiter.clone();
        let args = client_common::prepare_remove_bin_args(
            py,
            key,
            bin_names,
            meta,
            policy,
            &self.connection_info,
        )?;
        future_into_py(py, async move {
            let _permit = limiter.acquire_named("remove_bin").await?;
            client_ops::do_remove_bin(&client, args).await
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_operate_args(py, key, ops, meta, policy, &self.connection_info)?;
        debug!(
            "async operate_ordered: ns={} set={} ops_count={}",
            args.key.namespace,
            args.key.set_name,
            args.ops.len()
        );
        let pre_key_py = key_to_py(py, &args.key)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("operate_ordered").await?;
            let record = client_ops::do_operate_ordered(&client, &args).await?;
            Ok(PendingOrderedRecord {
                record,
                key_py: pre_key_py,
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
        future_into_py(
            py,
            async move { client_ops::do_truncate(&client, args).await },
        )
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
        future_into_py(
            py,
            async move { client_ops::do_udf_put(&client, args).await },
        )
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
        future_into_py(
            py,
            async move { client_ops::do_udf_remove(&client, args).await },
        )
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
            let result = client_ops::do_apply(&client, &a).await?;
            Python::attach(|py| match result {
                Some(val) => value_to_py(py, &val),
                None => Ok(py.None()),
            })
        })
    }

    // ── Batch ─────────────────────────────────────────────────

    /// Read multiple records (async).
    ///
    /// Returns a `BatchReadHandle` — a zero-conversion handle wrapping raw
    /// Rust results. The async future completes with near-zero GIL cost
    /// (just `Arc::new`). Call methods on the handle to access data:
    /// - `handle.as_dict()` — fastest, returns `dict[key, bins_dict]`
    /// - `handle.batch_records` — compat, returns `list[BatchRecord]`
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_batch_read_args(py, keys, &bins, policy, &self.connection_info)?;

        let use_numpy = _dtype.is_some();
        let dtype_py: Option<Py<PyAny>> = _dtype.map(|d| d.clone().unbind());

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("batch_read").await?;
            let results = client_ops::do_batch_read(&client, &args).await?;
            if use_numpy {
                Ok(PendingBatchRead::Numpy {
                    results,
                    dtype: dtype_py.ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err(
                            "internal error: numpy path reached without dtype",
                        )
                    })?,
                })
            } else {
                Ok(PendingBatchRead::Handle(results))
            }
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
        let limiter = self.limiter.clone();
        let args = client_common::prepare_batch_operate_args(
            py,
            keys,
            ops,
            policy,
            &self.connection_info,
        )?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("batch_operate").await?;
            let results = client_ops::do_batch_operate(&client, &args).await?;
            Ok(PendingBatchRecords { results })
        })
    }

    /// Write multiple records with per-record bins (async).
    #[allow(clippy::unit_arg)]
    #[pyo3(signature = (records, policy=None, retry=0))]
    fn batch_write<'py>(
        &self,
        py: Python<'py>,
        records: &Bound<'_, PyList>,
        policy: Option<&Bound<'_, PyDict>>,
        retry: u32,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!("async batch_write: records_count={}", records.len());
        let client = self.get_client()?;
        let limiter = self.limiter.clone();
        let args = client_common::prepare_batch_write_args(
            py, records, policy, retry, &self.connection_info,
        )?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("batch_write").await?;
            let results = client_ops::do_batch_write(
                &client,
                &args.batch_policy,
                &args.records,
                &args.batch_ns,
                &args.batch_set,
                args.otel.parent_ctx,
                args.otel.conn_info,
                args.max_retries,
                "batch_write",
            )
            .await?;
            Ok(PendingBatchRecords { results })
        })
    }

    /// Write multiple records from a numpy structured array (async).
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (data, namespace, set_name, _dtype, key_field="_key", policy=None, retry=0))]
    fn batch_write_numpy<'py>(
        &self,
        py: Python<'py>,
        data: &Bound<'_, PyAny>,
        namespace: &str,
        set_name: &str,
        _dtype: &Bound<'_, PyAny>,
        key_field: &str,
        policy: Option<&Bound<'_, PyDict>>,
        retry: u32,
    ) -> PyResult<Bound<'py, PyAny>> {
        debug!(
            "async batch_write_numpy: namespace={}, set={}, retry={}",
            namespace, set_name, retry
        );
        let client = self.get_client()?;
        let limiter = self.limiter.clone();
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
            let _permit = limiter.acquire_named("batch_write_numpy").await?;
            let results = client_ops::do_batch_write(
                &client,
                &batch_policy,
                &records,
                &ns,
                &set,
                parent_ctx,
                conn_info,
                retry,
                "batch_write_numpy",
            )
            .await?;
            Ok(PendingBatchRecords { results })
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
        let limiter = self.limiter.clone();
        let args =
            client_common::prepare_batch_remove_args(py, keys, policy, &self.connection_info)?;

        future_into_py(py, async move {
            let _permit = limiter.acquire_named("batch_remove").await?;
            let results = client_ops::do_batch_remove(&client, &args).await?;
            Ok(PendingBatchRecords { results })
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
            client_ops::do_index_remove(&client, args).await
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
            client_ops::do_admin_create_user(&client, &admin_policy, &username, &password, &roles)
                .await
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
            client_ops::do_admin_drop_user(&client, &admin_policy, &username).await
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
            client_ops::do_admin_change_password(&client, &admin_policy, &username, &password).await
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
            client_ops::do_admin_grant_roles(&client, &admin_policy, &username, &roles).await
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
            client_ops::do_admin_revoke_roles(&client, &admin_policy, &username, &roles).await
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
            let users =
                client_ops::do_admin_query_users(&client, &admin_policy, Some(&username)).await?;
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
            let users = client_ops::do_admin_query_users(&client, &admin_policy, None).await?;
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
            client_ops::do_admin_create_role(&client, args).await
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
            client_ops::do_admin_drop_role(&client, &admin_policy, &role).await
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
            client_ops::do_admin_grant_privileges(&client, &admin_policy, &role, &rust_privileges)
                .await
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
            client_ops::do_admin_revoke_privileges(&client, &admin_policy, &role, &rust_privileges)
                .await
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
            let roles =
                client_ops::do_admin_query_roles(&client, &admin_policy, Some(&role_name)).await?;
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
            let roles = client_ops::do_admin_query_roles(&client, &admin_policy, None).await?;
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
            client_ops::do_admin_set_whitelist(&client, &admin_policy, &role, &whitelist).await
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
            client_ops::do_admin_set_quotas(&client, &admin_policy, &role, read_quota, write_quota)
                .await
        })
    }
}

impl PyAsyncClient {
    /// Returns a cloned `Arc` to the connected client, or an error if not yet connected.
    ///
    /// Uses `load_full()` for a lock-free atomic load + Arc clone.
    fn get_client(&self) -> PyResult<Arc<AsClient>> {
        self.inner.load_full().ok_or_else(|| {
            crate::errors::ClientError::new_err("Client is not connected. Call connect() first.")
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
            client_ops::do_index_create(&client, args).await
        })
    }
}
