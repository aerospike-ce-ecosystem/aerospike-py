//! Admin policy parsing and user/role type conversion.

use aerospike_core::{Privilege, PrivilegeCode};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// Parse a Python policy dict into an `AdminPolicy`.
///
/// Supported keys: `"timeout"` (u32, milliseconds).
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
        let ns = extract_optional_string(dict, "ns")?;
        let set_name = extract_optional_string(dict, "set")?;
        result.push(Privilege::new(code_to_privilege_code(code)?, ns, set_name));
    }
    Ok(result)
}

fn extract_optional_string(dict: &Bound<'_, PyDict>, field_name: &str) -> PyResult<Option<String>> {
    match dict.get_item(field_name)? {
        Some(value) if value.is_none() => Ok(None),
        Some(value) => Ok(Some(value.extract::<String>()?)),
        None => Ok(None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::exceptions::PyTypeError;

    #[test]
    fn parse_privileges_accepts_string_ns_and_set() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", 10).unwrap();
            dict.set_item("ns", "test").unwrap();
            dict.set_item("set", "demo").unwrap();
            privileges.append(dict).unwrap();

            let parsed = parse_privileges(&privileges).expect("valid privilege list should parse");
            assert_eq!(parsed.len(), 1);
            assert_eq!(parsed[0].namespace.as_deref(), Some("test"));
            assert_eq!(parsed[0].set_name.as_deref(), Some("demo"));
        });
    }

    #[test]
    fn parse_privileges_rejects_non_string_ns() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", 10).unwrap();
            dict.set_item("ns", 123).unwrap();
            privileges.append(dict).unwrap();

            let err = parse_privileges(&privileges).expect_err("non-string ns must be rejected");
            assert!(err.is_instance_of::<PyTypeError>(py));
        });
    }

    #[test]
    fn parse_privileges_accepts_none_ns_and_set() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", 10).unwrap();
            dict.set_item("ns", py.None()).unwrap();
            dict.set_item("set", py.None()).unwrap();
            privileges.append(dict).unwrap();

            let parsed = parse_privileges(&privileges).expect("None ns/set should parse");
            assert_eq!(parsed.len(), 1);
            assert_eq!(parsed[0].namespace, None);
            assert_eq!(parsed[0].set_name, None);
        });
    }

    #[test]
    fn parse_privileges_rejects_non_string_set() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", 10).unwrap();
            dict.set_item("set", 456).unwrap();
            privileges.append(dict).unwrap();

            let err = parse_privileges(&privileges).expect_err("non-string set must be rejected");
            assert!(err.is_instance_of::<PyTypeError>(py));
        });
    }
}

/// Convert a slice to a Python list.
fn slice_to_pylist<'py, T>(py: Python<'py>, items: &[T]) -> PyResult<Bound<'py, PyList>>
where
    T: IntoPyObject<'py> + Clone,
{
    PyList::new(py, items.iter().cloned())
}

/// Convert a Rust User to a Python dict.
pub fn user_to_py(py: Python<'_>, user: &aerospike_core::User) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("user", &user.user)?;
    dict.set_item("roles", slice_to_pylist(py, &user.roles)?)?;
    dict.set_item("conns_in_use", user.conns_in_use)?;
    if !user.read_info.is_empty() {
        dict.set_item("read_info", slice_to_pylist(py, &user.read_info)?)?;
    }
    if !user.write_info.is_empty() {
        dict.set_item("write_info", slice_to_pylist(py, &user.write_info)?)?;
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

    dict.set_item("allowlist", slice_to_pylist(py, &role.allowlist)?)?;
    dict.set_item("read_quota", role.read_quota)?;
    dict.set_item("write_quota", role.write_quota)?;
    Ok(dict.into_any().unbind())
}
