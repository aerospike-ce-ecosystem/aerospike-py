//! Shared parameter-parsing helpers used by both `PyClient` (sync) and `PyAsyncClient` (async).
//!
//! Each `prepare_*` function converts Python arguments into their Rust equivalents,
//! so that the caller only needs a thin sync/async wrapper around the actual client call.

use aerospike_core::{
    operations::Operation, BatchDeletePolicy, BatchOperation, BatchReadPolicy, BatchWritePolicy,
    Bin, Bins, Key, ReadPolicy, UDFLang, Value, WritePolicy,
};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::operations::py_ops_to_rust;
use crate::policy::admin_policy::parse_admin_policy;
use crate::policy::batch_policy::parse_batch_policy;
use crate::policy::read_policy::{parse_read_policy, DEFAULT_READ_POLICY};
use crate::policy::write_policy::parse_write_policy;
use crate::tracing::ConnectionInfo;
use crate::types::bin::py_dict_to_bins;
use crate::types::key::py_to_key;

// ── OTel context extraction ──────────────────────────────────────────────────

/// Opaque type alias so callers don't depend on the concrete otel type.
#[cfg(feature = "otel")]
pub type ParentContext = opentelemetry::Context;

#[cfg(not(feature = "otel"))]
pub type ParentContext = ();

/// Extract the OTel parent context from the Python runtime (or `()` without otel).
#[cfg(feature = "otel")]
pub fn extract_parent_context(py: Python<'_>) -> ParentContext {
    crate::tracing::otel_impl::extract_python_context(py)
}

#[cfg(not(feature = "otel"))]
pub fn extract_parent_context(_py: Python<'_>) -> ParentContext {}

// ── put ──────────────────────────────────────────────────────────────────────

pub struct PutArgs {
    pub key: Key,
    pub bins: Vec<Bin>,
    pub policy: PutPolicy,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub enum PutPolicy {
    Default,
    Custom(WritePolicy),
}

pub fn prepare_put_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bins: &Bound<'_, PyAny>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<PutArgs> {
    let type_name = bins
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "unknown".to_string());
    let bins_dict = bins.cast::<PyDict>().map_err(|_| {
        pyo3::exceptions::PyTypeError::new_err(format!(
            "bins argument must be a dict, got {type_name}"
        ))
    })?;
    let rust_bins = py_dict_to_bins(bins_dict)?;
    let rust_key = py_to_key(key)?;

    let put_policy = if policy.is_none() && meta.is_none() {
        PutPolicy::Default
    } else {
        PutPolicy::Custom(parse_write_policy(policy, meta)?)
    };

    Ok(PutArgs {
        key: rust_key,
        bins: rust_bins,
        policy: put_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── get ──────────────────────────────────────────────────────────────────────

pub struct GetArgs {
    pub key: Key,
    pub policy: ReadPolicyChoice,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub enum ReadPolicyChoice {
    Default,
    Custom(ReadPolicy),
}

pub fn prepare_get_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<GetArgs> {
    let rust_key = py_to_key(key)?;
    let read_policy = if policy.is_none() {
        ReadPolicyChoice::Default
    } else {
        ReadPolicyChoice::Custom(parse_read_policy(policy)?)
    };

    Ok(GetArgs {
        key: rust_key,
        policy: read_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

impl GetArgs {
    pub fn read_policy(&self) -> &ReadPolicy {
        match &self.policy {
            ReadPolicyChoice::Default => &DEFAULT_READ_POLICY,
            ReadPolicyChoice::Custom(rp) => rp,
        }
    }
}

// ── select ───────────────────────────────────────────────────────────────────

pub struct SelectArgs {
    pub key: Key,
    pub bin_names: Vec<String>,
    pub policy: ReadPolicyChoice,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_select_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bins: &Bound<'_, PyList>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<SelectArgs> {
    let rust_key = py_to_key(key)?;
    let bin_names: Vec<String> = bins.extract()?;
    let read_policy = if policy.is_none() {
        ReadPolicyChoice::Default
    } else {
        ReadPolicyChoice::Custom(parse_read_policy(policy)?)
    };

    Ok(SelectArgs {
        key: rust_key,
        bin_names,
        policy: read_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

impl SelectArgs {
    pub fn read_policy(&self) -> &ReadPolicy {
        match &self.policy {
            ReadPolicyChoice::Default => &DEFAULT_READ_POLICY,
            ReadPolicyChoice::Custom(rp) => rp,
        }
    }

    pub fn bins_selector(&self) -> Bins {
        let refs: Vec<&str> = self.bin_names.iter().map(|s| s.as_str()).collect();
        Bins::from(refs.as_slice())
    }
}

// ── exists ───────────────────────────────────────────────────────────────────

pub struct ExistsArgs {
    pub key: Key,
    pub read_policy: ReadPolicy,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_exists_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<ExistsArgs> {
    let rust_key = py_to_key(key)?;
    let read_policy = if policy.is_none() {
        DEFAULT_READ_POLICY.clone()
    } else {
        parse_read_policy(policy)?
    };

    Ok(ExistsArgs {
        key: rust_key,
        read_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── remove ───────────────────────────────────────────────────────────────────

pub struct RemoveArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_remove_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<RemoveArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, meta)?;

    Ok(RemoveArgs {
        key: rust_key,
        write_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── touch ────────────────────────────────────────────────────────────────────

pub struct TouchArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_touch_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    val: u32,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<TouchArgs> {
    let rust_key = py_to_key(key)?;
    let mut write_policy = parse_write_policy(policy, meta)?;
    if val > 0 {
        write_policy.expiration = aerospike_core::Expiration::Seconds(val);
    }

    Ok(TouchArgs {
        key: rust_key,
        write_policy,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── append / prepend ─────────────────────────────────────────────────────────

pub struct SingleBinWriteArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub bins: Vec<Bin>,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_single_bin_write_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bin: &str,
    val: &Bound<'_, PyAny>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<SingleBinWriteArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, meta)?;
    let value = crate::types::value::py_to_value(val)?;
    let bins = vec![Bin::new(bin.to_string(), value)];

    Ok(SingleBinWriteArgs {
        key: rust_key,
        write_policy,
        bins,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── increment ────────────────────────────────────────────────────────────────

pub fn prepare_increment_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bin: &str,
    offset: &Bound<'_, PyAny>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<SingleBinWriteArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, meta)?;
    let value = crate::types::value::py_to_value(offset)?;
    let bins = vec![Bin::new(bin.to_string(), value)];

    Ok(SingleBinWriteArgs {
        key: rust_key,
        write_policy,
        bins,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── remove_bin ───────────────────────────────────────────────────────────────

pub struct RemoveBinArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub bins: Vec<Bin>,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_remove_bin_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    bin_names: &Bound<'_, PyList>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<RemoveBinArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, meta)?;
    let names: Vec<String> = bin_names.extract()?;
    let bins: Vec<Bin> = names.into_iter().map(|n| Bin::new(n, Value::Nil)).collect();

    Ok(RemoveBinArgs {
        key: rust_key,
        write_policy,
        bins,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── operate / operate_ordered ────────────────────────────────────────────────

pub struct OperateArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub ops: Vec<Operation>,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_operate_args(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    ops: &Bound<'_, PyList>,
    meta: Option<&Bound<'_, PyDict>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<OperateArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, meta)?;
    let rust_ops = py_ops_to_rust(ops)?;

    Ok(OperateArgs {
        key: rust_key,
        write_policy,
        ops: rust_ops,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

// ── batch_read ───────────────────────────────────────────────────────────────

pub struct BatchReadArgs {
    pub rust_keys: Vec<Key>,
    pub batch_policy: aerospike_core::BatchPolicy,
    pub bins_selector: Bins,
    pub batch_ns: String,
    pub batch_set: String,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_batch_read_args(
    py: Python<'_>,
    keys: &Bound<'_, PyList>,
    bins: &Option<Vec<String>>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<BatchReadArgs> {
    let batch_policy = parse_batch_policy(policy)?;
    let bins_selector = match bins {
        None => Bins::All,
        Some(b) if b.is_empty() => Bins::None,
        Some(b) => {
            let refs: Vec<&str> = b.iter().map(|s| s.as_str()).collect();
            Bins::from(refs.as_slice())
        }
    };

    let rust_keys: Vec<Key> = keys
        .iter()
        .map(|k| py_to_key(&k))
        .collect::<PyResult<_>>()?;

    let (batch_ns, batch_set) = rust_keys
        .first()
        .map(|k| (k.namespace.clone(), k.set_name.clone()))
        .unwrap_or_default();

    Ok(BatchReadArgs {
        rust_keys,
        batch_policy,
        bins_selector,
        batch_ns,
        batch_set,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

impl BatchReadArgs {
    pub fn to_batch_ops(&self) -> Vec<BatchOperation> {
        let read_policy = BatchReadPolicy::default();
        self.rust_keys
            .iter()
            .map(|k| BatchOperation::read(&read_policy, k.clone(), self.bins_selector.clone()))
            .collect()
    }
}

// ── batch_operate ────────────────────────────────────────────────────────────

pub struct BatchOperateArgs {
    pub rust_keys: Vec<Key>,
    pub batch_policy: aerospike_core::BatchPolicy,
    pub ops: Vec<Operation>,
    pub batch_ns: String,
    pub batch_set: String,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_batch_operate_args(
    py: Python<'_>,
    keys: &Bound<'_, PyList>,
    ops: &Bound<'_, PyList>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<BatchOperateArgs> {
    let batch_policy = parse_batch_policy(policy)?;
    let rust_ops = py_ops_to_rust(ops)?;
    let rust_keys: Vec<Key> = keys
        .iter()
        .map(|k| py_to_key(&k))
        .collect::<PyResult<_>>()?;

    let (batch_ns, batch_set) = rust_keys
        .first()
        .map(|k| (k.namespace.clone(), k.set_name.clone()))
        .unwrap_or_default();

    Ok(BatchOperateArgs {
        rust_keys,
        batch_policy,
        ops: rust_ops,
        batch_ns,
        batch_set,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

impl BatchOperateArgs {
    pub fn to_batch_ops(&self) -> Vec<BatchOperation> {
        let write_policy = BatchWritePolicy::default();
        self.rust_keys
            .iter()
            .map(|k| BatchOperation::write(&write_policy, k.clone(), self.ops.clone()))
            .collect()
    }
}

// ── batch_remove ─────────────────────────────────────────────────────────────

pub struct BatchRemoveArgs {
    pub rust_keys: Vec<Key>,
    pub batch_policy: aerospike_core::BatchPolicy,
    pub batch_ns: String,
    pub batch_set: String,
    pub parent_ctx: ParentContext,
    pub conn_info: ConnectionInfo,
}

pub fn prepare_batch_remove_args(
    py: Python<'_>,
    keys: &Bound<'_, PyList>,
    policy: Option<&Bound<'_, PyDict>>,
    conn_info: &ConnectionInfo,
) -> PyResult<BatchRemoveArgs> {
    let batch_policy = parse_batch_policy(policy)?;
    let rust_keys: Vec<Key> = keys
        .iter()
        .map(|k| py_to_key(&k))
        .collect::<PyResult<_>>()?;

    let (batch_ns, batch_set) = rust_keys
        .first()
        .map(|k| (k.namespace.clone(), k.set_name.clone()))
        .unwrap_or_default();

    Ok(BatchRemoveArgs {
        rust_keys,
        batch_policy,
        batch_ns,
        batch_set,
        parent_ctx: extract_parent_context(py),
        conn_info: conn_info.clone(),
    })
}

impl BatchRemoveArgs {
    pub fn to_batch_ops(&self) -> Vec<BatchOperation> {
        let delete_policy = BatchDeletePolicy::default();
        self.rust_keys
            .iter()
            .map(|k| BatchOperation::delete(&delete_policy, k.clone()))
            .collect()
    }
}

// ── info_all / info_random_node ──────────────────────────────────────────────

pub struct InfoArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub command: String,
}

pub fn prepare_info_args(command: &str, policy: Option<&Bound<'_, PyDict>>) -> PyResult<InfoArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    Ok(InfoArgs {
        admin_policy,
        command: command.to_string(),
    })
}

// ── info result helpers ──────────────────────────────────────────────────────

pub fn info_node_result(
    node: &aerospike_core::Node,
    cmd: &str,
    result: Result<std::collections::HashMap<String, String>, aerospike_core::Error>,
) -> (String, i32, String) {
    match result {
        Ok(map) => {
            let response = map.get(cmd).cloned().unwrap_or_default();
            (node.name().to_string(), 0, response)
        }
        Err(e) => {
            let code = match &e {
                aerospike_core::Error::ServerError(rc, _, _) => {
                    crate::errors::result_code_to_int(rc)
                }
                _ => -1,
            };
            (node.name().to_string(), code, e.to_string())
        }
    }
}

// ── truncate ─────────────────────────────────────────────────────────────────

pub struct TruncateArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub namespace: String,
    pub set_name: String,
    pub nanos: i64,
}

pub fn prepare_truncate_args(
    namespace: &str,
    set_name: &str,
    nanos: i64,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<TruncateArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    Ok(TruncateArgs {
        admin_policy,
        namespace: namespace.to_string(),
        set_name: set_name.to_string(),
        nanos,
    })
}

// ── UDF ──────────────────────────────────────────────────────────────────────

pub struct UdfPutArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub language: UDFLang,
    pub udf_body: Vec<u8>,
    pub server_path: String,
}

pub fn prepare_udf_put_args(
    filename: &str,
    udf_type: u8,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<UdfPutArgs> {
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

    Ok(UdfPutArgs {
        admin_policy,
        language,
        udf_body,
        server_path,
    })
}

pub struct UdfRemoveArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub server_path: String,
}

pub fn prepare_udf_remove_args(
    module: &str,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<UdfRemoveArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    let server_path = if module.ends_with(".lua") {
        module.to_string()
    } else {
        format!("{}.lua", module)
    };

    Ok(UdfRemoveArgs {
        admin_policy,
        server_path,
    })
}

pub struct ApplyArgs {
    pub key: Key,
    pub write_policy: WritePolicy,
    pub module: String,
    pub function: String,
    pub args: Option<Vec<Value>>,
}

pub fn prepare_apply_args(
    key: &Bound<'_, PyAny>,
    module: &str,
    function: &str,
    args: Option<&Bound<'_, PyList>>,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<ApplyArgs> {
    let rust_key = py_to_key(key)?;
    let write_policy = parse_write_policy(policy, None)?;
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

    Ok(ApplyArgs {
        key: rust_key,
        write_policy,
        module: module.to_string(),
        function: function.to_string(),
        args: rust_args,
    })
}

// ── Admin: User ──────────────────────────────────────────────────────────────

pub fn prepare_admin_policy(
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<aerospike_core::AdminPolicy> {
    parse_admin_policy(policy)
}

// ── Index ────────────────────────────────────────────────────────────────────

pub struct IndexCreateArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub namespace: String,
    pub set_name: String,
    pub bin_name: String,
    pub index_name: String,
    pub index_type: aerospike_core::IndexType,
}

pub fn prepare_index_create_args(
    namespace: &str,
    set_name: &str,
    bin_name: &str,
    index_name: &str,
    index_type: aerospike_core::IndexType,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<IndexCreateArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    Ok(IndexCreateArgs {
        admin_policy,
        namespace: namespace.to_string(),
        set_name: set_name.to_string(),
        bin_name: bin_name.to_string(),
        index_name: index_name.to_string(),
        index_type,
    })
}

pub struct IndexRemoveArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub namespace: String,
    pub index_name: String,
}

pub fn prepare_index_remove_args(
    namespace: &str,
    index_name: &str,
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<IndexRemoveArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    Ok(IndexRemoveArgs {
        admin_policy,
        namespace: namespace.to_string(),
        index_name: index_name.to_string(),
    })
}

// ── Admin: create_role ───────────────────────────────────────────────────────

pub struct CreateRoleArgs {
    pub admin_policy: aerospike_core::AdminPolicy,
    pub role: String,
    pub privileges: Vec<aerospike_core::Privilege>,
    pub whitelist: Vec<String>,
    pub read_quota: u32,
    pub write_quota: u32,
}

pub fn prepare_create_role_args(
    role: &str,
    privileges: &Bound<'_, PyList>,
    policy: Option<&Bound<'_, PyDict>>,
    whitelist: Option<Vec<String>>,
    read_quota: u32,
    write_quota: u32,
) -> PyResult<CreateRoleArgs> {
    let admin_policy = parse_admin_policy(policy)?;
    let rust_privileges = crate::policy::admin_policy::parse_privileges(privileges)?;
    Ok(CreateRoleArgs {
        admin_policy,
        role: role.to_string(),
        privileges: rust_privileges,
        whitelist: whitelist.unwrap_or_default(),
        read_quota,
        write_quota,
    })
}
