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

/// Convert a canonical privilege name (asadm-style) to a Rust PrivilegeCode.
///
/// Accepts the same names the server / asadm emits, e.g. `"read"`,
/// `"read-write"`, `"sys-admin"`. Also accepts the `_` variant
/// (`"read_write"`, `"sys_admin"`) for ergonomics with Python code that
/// avoids hyphens.
fn name_to_privilege_code(name: &str) -> PyResult<PrivilegeCode> {
    match name.to_ascii_lowercase().replace('_', "-").as_str() {
        "user-admin" => Ok(PrivilegeCode::UserAdmin),
        "sys-admin" => Ok(PrivilegeCode::SysAdmin),
        "data-admin" => Ok(PrivilegeCode::DataAdmin),
        "udf-admin" => Ok(PrivilegeCode::UDFAdmin),
        "sindex-admin" => Ok(PrivilegeCode::SIndexAdmin),
        "read" => Ok(PrivilegeCode::Read),
        "read-write" => Ok(PrivilegeCode::ReadWrite),
        "read-write-udf" => Ok(PrivilegeCode::ReadWriteUDF),
        "write" => Ok(PrivilegeCode::Write),
        "truncate" => Ok(PrivilegeCode::Truncate),
        _ => Err(crate::errors::InvalidArgError::new_err(format!(
            "Unknown privilege name: {:?}. Expected one of: read, read-write, \
             read-write-udf, write, truncate, user-admin, sys-admin, data-admin, \
             udf-admin, sindex-admin",
            name
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
///
/// Each dict: `{"code": int | str, "ns": str (optional), "set": str (optional)}`.
/// `code` accepts either the int constant (`aerospike_py.PRIV_READ = 10`) or
/// the canonical string name (`"read"`, `"read-write"`, `"sys-admin"`, …) so
/// callers receiving privilege names from a wire format (HTTP form, JSON, asadm
/// output) don't need a translation table.
pub fn parse_privileges(privileges: &Bound<'_, PyList>) -> PyResult<Vec<Privilege>> {
    let mut result = Vec::new();
    for item in privileges.iter() {
        let dict = item.cast::<PyDict>()?;
        let code_obj = dict.get_item("code")?.ok_or_else(|| {
            crate::errors::InvalidArgError::new_err("Privilege dict must have 'code' key")
        })?;
        let priv_code = if let Ok(code_int) = code_obj.extract::<u8>() {
            code_to_privilege_code(code_int)?
        } else if let Ok(code_str) = code_obj.extract::<String>() {
            name_to_privilege_code(&code_str)?
        } else {
            let type_name = code_obj
                .get_type()
                .name()
                .map(|n| n.to_string())
                .unwrap_or_else(|_| "unknown".to_string());
            return Err(pyo3::exceptions::PyTypeError::new_err(format!(
                "privilege 'code' must be int or str, got {type_name}"
            )));
        };
        let ns = extract_optional_string(dict, "ns")?;
        let set_name = extract_optional_string(dict, "set")?;
        result.push(Privilege::new(priv_code, ns, set_name));
    }
    Ok(result)
}

fn extract_optional_string(dict: &Bound<'_, PyDict>, field_name: &str) -> PyResult<Option<String>> {
    match dict.get_item(field_name)? {
        Some(value) if value.is_none() => Ok(None),
        Some(value) => value.extract::<String>().map(Some).map_err(|_| {
            let type_name = value
                .get_type()
                .name()
                .map(|n| n.to_string())
                .unwrap_or_else(|_| "unknown".to_string());
            pyo3::exceptions::PyTypeError::new_err(format!(
                "privilege '{field_name}' must be str or None, got {type_name}"
            ))
        }),
        None => Ok(None),
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

    #[test]
    fn parse_privileges_accepts_string_code() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            for name in [
                "read",
                "read-write",
                "read-write-udf",
                "write",
                "truncate",
                "user-admin",
                "sys-admin",
                "data-admin",
                "udf-admin",
                "sindex-admin",
            ] {
                let dict = PyDict::new(py);
                dict.set_item("code", name).unwrap();
                privileges.append(dict).unwrap();
            }

            let parsed = parse_privileges(&privileges).expect("string codes should parse");
            assert_eq!(parsed.len(), 10);
            assert!(matches!(parsed[0].code, PrivilegeCode::Read));
            assert!(matches!(parsed[1].code, PrivilegeCode::ReadWrite));
            assert!(matches!(parsed[2].code, PrivilegeCode::ReadWriteUDF));
            assert!(matches!(parsed[3].code, PrivilegeCode::Write));
            assert!(matches!(parsed[4].code, PrivilegeCode::Truncate));
            assert!(matches!(parsed[5].code, PrivilegeCode::UserAdmin));
            assert!(matches!(parsed[6].code, PrivilegeCode::SysAdmin));
            assert!(matches!(parsed[7].code, PrivilegeCode::DataAdmin));
            assert!(matches!(parsed[8].code, PrivilegeCode::UDFAdmin));
            assert!(matches!(parsed[9].code, PrivilegeCode::SIndexAdmin));
        });
    }

    #[test]
    fn parse_privileges_string_code_is_case_and_separator_insensitive() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            for name in ["READ", "Read-Write", "sys_admin", "READ_WRITE_UDF"] {
                let dict = PyDict::new(py);
                dict.set_item("code", name).unwrap();
                privileges.append(dict).unwrap();
            }

            let parsed = parse_privileges(&privileges).expect("normalized names should parse");
            assert_eq!(parsed.len(), 4);
            assert!(matches!(parsed[0].code, PrivilegeCode::Read));
            assert!(matches!(parsed[1].code, PrivilegeCode::ReadWrite));
            assert!(matches!(parsed[2].code, PrivilegeCode::SysAdmin));
            assert!(matches!(parsed[3].code, PrivilegeCode::ReadWriteUDF));
        });
    }

    #[test]
    fn parse_privileges_rejects_unknown_string_code() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", "super-admin").unwrap();
            privileges.append(dict).unwrap();

            let err = parse_privileges(&privileges).expect_err("unknown name must be rejected");
            assert!(err.to_string().contains("Unknown privilege name"));
        });
    }

    #[test]
    fn parse_privileges_rejects_non_int_non_str_code() {
        Python::initialize();
        Python::attach(|py| {
            let privileges = PyList::empty(py);
            let dict = PyDict::new(py);
            dict.set_item("code", 1.5_f64).unwrap();
            privileges.append(dict).unwrap();

            let err = parse_privileges(&privileges)
                .expect_err("float code must be rejected as TypeError");
            assert!(err.is_instance_of::<PyTypeError>(py));
        });
    }
}
