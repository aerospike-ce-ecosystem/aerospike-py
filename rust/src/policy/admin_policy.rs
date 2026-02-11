use aerospike_core::{Privilege, PrivilegeCode};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

pub fn parse_admin_policy(
    policy: Option<&Bound<'_, PyDict>>,
) -> PyResult<aerospike_core::AdminPolicy> {
    trace!("Parsing admin policy");
    let mut p = aerospike_core::AdminPolicy::default();
    if let Some(dict) = policy {
        if let Some(val) = dict.get_item("timeout")? {
            p.timeout = val.extract::<u32>()?;
        }
    }
    Ok(p)
}

/// Convert a Python privilege code integer to a Rust PrivilegeCode.
fn code_to_privilege_code(code: u8) -> PyResult<PrivilegeCode> {
    match code {
        0 => Ok(PrivilegeCode::UserAdmin),
        1 => Ok(PrivilegeCode::SysAdmin),
        2 => Ok(PrivilegeCode::DataAdmin),
        3 => Ok(PrivilegeCode::UDFAdmin),
        4 => Ok(PrivilegeCode::SIndexAdmin),
        10 => Ok(PrivilegeCode::Read),
        11 => Ok(PrivilegeCode::ReadWrite),
        12 => Ok(PrivilegeCode::ReadWriteUDF),
        13 => Ok(PrivilegeCode::Write),
        14 => Ok(PrivilegeCode::Truncate),
        _ => Err(crate::errors::InvalidArgError::new_err(format!(
            "Unknown privilege code: {}",
            code
        ))),
    }
}

/// Convert a Rust PrivilegeCode to a Python integer.
fn privilege_code_to_int(code: &PrivilegeCode) -> u8 {
    match code {
        PrivilegeCode::UserAdmin => 0,
        PrivilegeCode::SysAdmin => 1,
        PrivilegeCode::DataAdmin => 2,
        PrivilegeCode::UDFAdmin => 3,
        PrivilegeCode::SIndexAdmin => 4,
        PrivilegeCode::Read => 10,
        PrivilegeCode::ReadWrite => 11,
        PrivilegeCode::ReadWriteUDF => 12,
        PrivilegeCode::Write => 13,
        PrivilegeCode::Truncate => 14,
        _ => 255,
    }
}

/// Convert a Python list of privilege dicts to Vec<Privilege>.
/// Each dict: {"code": int, "ns": str (optional), "set": str (optional)}
pub fn parse_privileges(privileges: &Bound<'_, PyList>) -> PyResult<Vec<Privilege>> {
    let mut result = Vec::new();
    for item in privileges.iter() {
        let dict = item.cast::<PyDict>()?;
        let code: u8 = dict
            .get_item("code")?
            .ok_or_else(|| {
                crate::errors::InvalidArgError::new_err("Privilege dict must have 'code' key")
            })?
            .extract()?;
        let ns: Option<String> = dict.get_item("ns")?.and_then(|v| v.extract().ok());
        let set_name: Option<String> = dict.get_item("set")?.and_then(|v| v.extract().ok());
        result.push(Privilege::new(code_to_privilege_code(code)?, ns, set_name));
    }
    Ok(result)
}

/// Convert a Rust User to a Python dict.
pub fn user_to_py(py: Python<'_>, user: &aerospike_core::User) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("user", &user.user)?;
    let roles = PyList::empty(py);
    for r in &user.roles {
        roles.append(r)?;
    }
    dict.set_item("roles", roles)?;
    dict.set_item("conns_in_use", user.conns_in_use)?;
    if !user.read_info.is_empty() {
        let ri = PyList::empty(py);
        for v in &user.read_info {
            ri.append(*v)?;
        }
        dict.set_item("read_info", ri)?;
    }
    if !user.write_info.is_empty() {
        let wi = PyList::empty(py);
        for v in &user.write_info {
            wi.append(*v)?;
        }
        dict.set_item("write_info", wi)?;
    }
    Ok(dict.into_any().unbind())
}

/// Convert a Rust Role to a Python dict.
pub fn role_to_py(py: Python<'_>, role: &aerospike_core::Role) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("name", &role.name)?;

    let privs = PyList::empty(py);
    for p in &role.privileges {
        let pd = PyDict::new(py);
        pd.set_item("code", privilege_code_to_int(&p.code))?;
        if let Some(ns) = &p.namespace {
            pd.set_item("ns", ns)?;
        }
        if let Some(set) = &p.set_name {
            pd.set_item("set", set)?;
        }
        privs.append(pd)?;
    }
    dict.set_item("privileges", privs)?;

    let allowlist = PyList::empty(py);
    for a in &role.allowlist {
        allowlist.append(a)?;
    }
    dict.set_item("allowlist", allowlist)?;
    dict.set_item("read_quota", role.read_quota)?;
    dict.set_item("write_quota", role.write_quota)?;
    Ok(dict.into_any().unbind())
}
