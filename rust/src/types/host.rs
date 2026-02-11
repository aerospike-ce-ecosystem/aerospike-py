use log::debug;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

/// Parse a config dict to extract hosts as a connection string
/// Config format: {"hosts": [("host", port), ...]}
/// Returns a string like "host1:port1,host2:port2"
pub fn parse_hosts_from_config(config: &Bound<'_, PyDict>) -> PyResult<String> {
    let hosts_obj = config.get_item("hosts")?.ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("Config must contain 'hosts' key")
    })?;

    let hosts_list = hosts_obj.cast::<PyList>()?;
    let mut host_strings = Vec::with_capacity(hosts_list.len());

    for item in hosts_list.iter() {
        if let Ok(tuple) = item.cast::<PyTuple>() {
            let host: String = tuple.get_item(0)?.extract()?;
            let port: u16 = if tuple.len() > 1 {
                tuple.get_item(1)?.extract()?
            } else {
                3000
            };
            host_strings.push(format!("{host}:{port}"));
        } else if let Ok(s) = item.extract::<String>() {
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

    let result = host_strings.join(",");
    debug!("Parsed hosts: {}", result);
    Ok(result)
}
