//! Host configuration parsing from Python config dicts to connection strings.

use log::debug;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

/// Result of parsing the hosts config.
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
    let mut first_port: u16 = 3000;

    for (i, item) in hosts_list.iter().enumerate() {
        if let Ok(tuple) = item.cast::<PyTuple>() {
            let host: String = tuple.get_item(0)?.extract()?;
            let port: u16 = if tuple.len() > 1 {
                tuple.get_item(1)?.extract()?
            } else {
                3000
            };
            if i == 0 {
                first_address = host.clone();
                first_port = port;
            }
            host_strings.push(format!("{host}:{port}"));
        } else if let Ok(s) = item.extract::<String>() {
            if i == 0 {
                // Parse "host:port" or just "host"
                if let Some((h, p)) = s.rsplit_once(':') {
                    first_address = h.to_string();
                    first_port = p.parse().unwrap_or(3000);
                } else {
                    first_address = s.clone();
                    first_port = 3000;
                }
            }
            host_strings.push(s);
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
