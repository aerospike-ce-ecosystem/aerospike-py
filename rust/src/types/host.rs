//! Host configuration parsing from Python config dicts to connection strings.

use log::debug;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

/// Default Aerospike service port used when a host entry omits one.
const DEFAULT_PORT: u16 = 3000;

/// Result of parsing the hosts config.
#[derive(Debug)]
pub struct ParsedHosts {
    /// Connection string: "host1:port1,host2:port2"
    pub connection_string: String,
    /// First host address (for span attributes)
    pub first_address: String,
    /// First host port (for span attributes)
    pub first_port: u16,
}

/// Parse a config dict to extract hosts as a connection string
/// Config format: {"hosts": [("host", port), ...]}
/// Returns ParsedHosts with the connection string and first host info
pub fn parse_hosts_from_config(config: &Bound<'_, PyDict>) -> PyResult<ParsedHosts> {
    let hosts_obj = config.get_item("hosts")?.ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("Config must contain 'hosts' key")
    })?;

    let hosts_list = hosts_obj.cast::<PyList>()?;
    let mut host_strings = Vec::with_capacity(hosts_list.len());
    let mut first_address = String::new();
    let mut first_port: u16 = DEFAULT_PORT;

    for (i, item) in hosts_list.iter().enumerate() {
        if let Ok(tuple) = item.cast::<PyTuple>() {
            if tuple.is_empty() {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "Host tuple must contain at least a host address, got an empty tuple",
                ));
            }
            let host: String = tuple.get_item(0)?.extract()?;
            let port: u16 = if tuple.len() > 1 {
                tuple.get_item(1)?.extract()?
            } else {
                DEFAULT_PORT
            };
            if i == 0 {
                first_address = host.clone();
                first_port = port;
            }
            host_strings.push(format!("{host}:{port}"));
        } else if let Ok(s) = item.extract::<String>() {
            if i == 0 {
                // Parse "host:port" or just "host".
                //
                // Only treat the string as host:port when there is exactly one
                // ':'. A bare IPv6 literal (e.g. "fe80::1") contains multiple
                // ':' and must be treated as a whole address, otherwise
                // rsplit_once(':') would mis-split it into ("fe80:", "1") and
                // corrupt the telemetry attributes.
                if s.matches(':').count() == 1 {
                    // Safe to unwrap: exactly one ':' guarantees a split.
                    let (h, p) = s.rsplit_once(':').unwrap();
                    first_address = h.to_string();
                    first_port = p.parse().map_err(|_| {
                        pyo3::exceptions::PyValueError::new_err(format!(
                            "Invalid port in host string '{s}': '{p}' is not a valid port number"
                        ))
                    })?;
                } else {
                    // Bare hostname (no ':') or bare IPv6 literal (multiple
                    // ':'): the whole string is the address and the default
                    // port applies.
                    first_address = s.clone();
                    first_port = DEFAULT_PORT;
                }
            }
            // Normalize a bare hostname (no ':') to "host:DEFAULT_PORT" so the
            // string form matches the tuple form. The downstream
            // aerospike_core host parser applies the same default port to a
            // bare hostname, so this is behavior-preserving (see PR notes).
            // IPv6 literals (multiple ':') are pushed verbatim to avoid
            // mangling an address the core parser handles itself.
            if s.contains(':') {
                host_strings.push(s);
            } else {
                host_strings.push(format!("{s}:{DEFAULT_PORT}"));
            }
        } else {
            return Err(pyo3::exceptions::PyTypeError::new_err(
                "Host must be a (host, port) tuple or a string",
            ));
        }
    }

    if host_strings.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "hosts list must not be empty",
        ));
    }

    let connection_string = host_strings.join(",");
    debug!("Parsed hosts: {}", connection_string);
    Ok(ParsedHosts {
        connection_string,
        first_address,
        first_port,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::{PyDict, PyList, PyTuple};
    use pyo3::IntoPyObjectExt;

    /// Build a config dict `{"hosts": <list>}` from the given host entries.
    fn config_with_hosts<'py>(
        py: Python<'py>,
        entries: &[Bound<'py, PyAny>],
    ) -> Bound<'py, PyDict> {
        let list = PyList::new(py, entries).unwrap();
        let dict = PyDict::new(py);
        dict.set_item("hosts", list).unwrap();
        dict
    }

    #[test]
    fn default_port_constant_is_3000() {
        assert_eq!(DEFAULT_PORT, 3000);
    }

    /// A bare hostname string must default to `DEFAULT_PORT` for telemetry and
    /// be normalized to "host:DEFAULT_PORT" in the connection string (matching
    /// the tuple form; the core parser applies the same default port).
    #[test]
    fn bare_string_host_uses_default_port() {
        Python::initialize();
        Python::attach(|py| {
            let host = "node1".into_bound_py_any(py).unwrap();
            let config = config_with_hosts(py, &[host]);
            let parsed = parse_hosts_from_config(&config).expect("bare host must parse");
            assert_eq!(parsed.first_address, "node1");
            assert_eq!(parsed.first_port, DEFAULT_PORT);
            assert_eq!(parsed.connection_string, "node1:3000");
        });
    }

    /// A "host:port" string must use the explicit port.
    #[test]
    fn string_host_with_explicit_port() {
        Python::initialize();
        Python::attach(|py| {
            let host = "node1:4000".into_bound_py_any(py).unwrap();
            let config = config_with_hosts(py, &[host]);
            let parsed = parse_hosts_from_config(&config).expect("host:port must parse");
            assert_eq!(parsed.first_address, "node1");
            assert_eq!(parsed.first_port, 4000);
            assert_eq!(parsed.connection_string, "node1:4000");
        });
    }

    /// A single-element tuple ("node1",) regression: default port applies.
    #[test]
    fn single_element_tuple_uses_default_port() {
        Python::initialize();
        Python::attach(|py| {
            let tuple = PyTuple::new(py, ["node1"]).unwrap().into_any();
            let config = config_with_hosts(py, &[tuple]);
            let parsed = parse_hosts_from_config(&config).expect("(host,) must parse");
            assert_eq!(parsed.first_address, "node1");
            assert_eq!(parsed.first_port, DEFAULT_PORT);
            assert_eq!(parsed.connection_string, "node1:3000");
        });
    }

    /// A (host, port) tuple regression: explicit port is honored.
    #[test]
    fn host_port_tuple_is_honored() {
        Python::initialize();
        Python::attach(|py| {
            let host = "node1".into_pyobject(py).unwrap().into_any();
            let port = 4000u16.into_pyobject(py).unwrap().into_any();
            let tuple = PyTuple::new(py, [host, port]).unwrap().into_any();
            let config = config_with_hosts(py, &[tuple]);
            let parsed = parse_hosts_from_config(&config).expect("(host, port) must parse");
            assert_eq!(parsed.first_address, "node1");
            assert_eq!(parsed.first_port, 4000);
            assert_eq!(parsed.connection_string, "node1:4000");
        });
    }

    /// An empty tuple () must raise a clear ValueError, not an opaque
    /// IndexError from get_item(0).
    #[test]
    fn empty_tuple_raises_value_error() {
        Python::initialize();
        Python::attach(|py| {
            let tuple = PyTuple::empty(py).into_any();
            let config = config_with_hosts(py, &[tuple]);
            let err = parse_hosts_from_config(&config).expect_err("empty tuple must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
            assert!(err.to_string().contains("empty tuple"));
        });
    }

    /// An empty hosts list must raise the existing ValueError.
    #[test]
    fn empty_hosts_list_raises_value_error() {
        Python::initialize();
        Python::attach(|py| {
            let config = config_with_hosts(py, &[]);
            let err =
                parse_hosts_from_config(&config).expect_err("empty hosts list must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
            assert!(err.to_string().contains("must not be empty"));
        });
    }

    /// A bare IPv6 literal must NOT be mis-split: first_address is the whole
    /// literal and first_port is DEFAULT_PORT. The connection string is left
    /// verbatim for the core parser to handle.
    #[test]
    fn ipv6_literal_is_not_mis_split() {
        Python::initialize();
        Python::attach(|py| {
            let host = "fe80::1".into_bound_py_any(py).unwrap();
            let config = config_with_hosts(py, &[host]);
            let parsed = parse_hosts_from_config(&config).expect("IPv6 literal must parse");
            assert_eq!(parsed.first_address, "fe80::1");
            assert_eq!(parsed.first_port, DEFAULT_PORT);
            assert_eq!(parsed.connection_string, "fe80::1");
        });
    }

    /// A non-string, non-tuple host entry must raise a TypeError.
    #[test]
    fn invalid_host_type_raises_type_error() {
        Python::initialize();
        Python::attach(|py| {
            let host = 12345i64.into_bound_py_any(py).unwrap();
            let config = config_with_hosts(py, &[host]);
            let err = parse_hosts_from_config(&config).expect_err("int host must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyTypeError>(py));
        });
    }
}
