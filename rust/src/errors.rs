use aerospike_core::{Error as AsError, ResultCode};
use pyo3::exceptions::PyException;
use pyo3::prelude::*;

// Base exceptions
pyo3::create_exception!(aerospike, AerospikeError, PyException);
pyo3::create_exception!(aerospike, ClientError, AerospikeError);
pyo3::create_exception!(aerospike, ServerError, AerospikeError);
pyo3::create_exception!(aerospike, RecordError, AerospikeError);
pyo3::create_exception!(aerospike, ClusterError, AerospikeError);
pyo3::create_exception!(aerospike, TimeoutError, AerospikeError);
pyo3::create_exception!(aerospike, InvalidArgError, AerospikeError);

// Record-level exceptions
pyo3::create_exception!(aerospike, RecordNotFound, RecordError);
pyo3::create_exception!(aerospike, RecordExistsError, RecordError);
pyo3::create_exception!(aerospike, RecordGenerationError, RecordError);
pyo3::create_exception!(aerospike, RecordTooBig, RecordError);
pyo3::create_exception!(aerospike, BinNameError, RecordError);
pyo3::create_exception!(aerospike, BinExistsError, RecordError);
pyo3::create_exception!(aerospike, BinNotFound, RecordError);
pyo3::create_exception!(aerospike, BinTypeError, RecordError);
pyo3::create_exception!(aerospike, FilteredOut, RecordError);

// Index exceptions
pyo3::create_exception!(aerospike, IndexError, ServerError);
pyo3::create_exception!(aerospike, IndexNotFound, IndexError);
pyo3::create_exception!(aerospike, IndexFoundError, IndexError);

// Query exceptions
pyo3::create_exception!(aerospike, QueryError, ServerError);
pyo3::create_exception!(aerospike, QueryAbortedError, QueryError);

// Admin / UDF exceptions
pyo3::create_exception!(aerospike, AdminError, ServerError);
pyo3::create_exception!(aerospike, UDFError, ServerError);

fn result_code_to_int(rc: &ResultCode) -> i32 {
    match rc {
        ResultCode::Ok => 0,
        ResultCode::ServerError => 1,
        ResultCode::KeyNotFoundError => 2,
        ResultCode::GenerationError => 3,
        ResultCode::ParameterError => 4,
        ResultCode::KeyExistsError => 5,
        ResultCode::BinExistsError => 6,
        ResultCode::ClusterKeyMismatch => 7,
        ResultCode::ServerMemError => 8,
        ResultCode::Timeout => 9,
        ResultCode::AlwaysForbidden => 10,
        ResultCode::PartitionUnavailable => 11,
        ResultCode::BinTypeError => 12,
        ResultCode::RecordTooBig => 13,
        ResultCode::KeyBusy => 14,
        ResultCode::ScanAbort => 15,
        ResultCode::UnsupportedFeature => 16,
        ResultCode::BinNotFound => 17,
        ResultCode::DeviceOverload => 18,
        ResultCode::KeyMismatch => 19,
        ResultCode::InvalidNamespace => 20,
        ResultCode::BinNameTooLong => 21,
        ResultCode::FailForbidden => 22,
        ResultCode::ElementNotFound => 23,
        ResultCode::ElementExists => 24,
        ResultCode::EnterpriseOnly => 25,
        ResultCode::OpNotApplicable => 26,
        ResultCode::FilteredOut => 27,
        ResultCode::LostConflict => 28,
        ResultCode::XDRKeyBusy => 32,
        ResultCode::QueryEnd => 50,
        ResultCode::SecurityNotSupported => 51,
        ResultCode::SecurityNotEnabled => 52,
        ResultCode::InvalidUser => 60,
        ResultCode::NotAuthenticated => 80,
        ResultCode::RoleViolation => 81,
        ResultCode::UdfBadResponse => 100,
        ResultCode::BatchDisabled => 150,
        ResultCode::IndexFound => 200,
        ResultCode::IndexNotFound => 201,
        ResultCode::QueryAborted => 210,
        ResultCode::InvalidGeojson => 160,
        ResultCode::Unknown(code) => *code as i32,
        _ => -1,
    }
}

pub fn as_to_pyerr(err: AsError) -> PyErr {
    match &err {
        AsError::Connection(msg) => ClusterError::new_err(format!("Connection error: {msg}")),
        AsError::Timeout(msg) => TimeoutError::new_err(format!("Timeout: {msg}")),
        AsError::InvalidArgument(msg) => {
            InvalidArgError::new_err(format!("Invalid argument: {msg}"))
        }
        AsError::ServerError(rc, in_doubt, _node) => {
            let code = result_code_to_int(rc);
            let doubt_suffix = if *in_doubt { " [in_doubt]" } else { "" };
            let msg = format!("AEROSPIKE_ERR ({code}): {err}{doubt_suffix}");
            match rc {
                // Record-level: specific subclasses
                ResultCode::KeyNotFoundError => RecordNotFound::new_err(msg),
                ResultCode::KeyExistsError => RecordExistsError::new_err(msg),
                ResultCode::GenerationError => RecordGenerationError::new_err(msg),
                ResultCode::RecordTooBig => RecordTooBig::new_err(msg),
                ResultCode::BinNameTooLong => BinNameError::new_err(msg),
                ResultCode::BinExistsError => BinExistsError::new_err(msg),
                ResultCode::BinNotFound => BinNotFound::new_err(msg),
                ResultCode::BinTypeError => BinTypeError::new_err(msg),
                ResultCode::FilteredOut => FilteredOut::new_err(msg),
                ResultCode::ElementNotFound | ResultCode::ElementExists => {
                    RecordError::new_err(msg)
                }
                // Index
                ResultCode::IndexFound => IndexFoundError::new_err(msg),
                ResultCode::IndexNotFound => IndexNotFound::new_err(msg),
                // Query
                ResultCode::QueryAborted | ResultCode::ScanAbort => QueryAbortedError::new_err(msg),
                // UDF
                ResultCode::UdfBadResponse => UDFError::new_err(msg),
                // Admin / Security
                ResultCode::InvalidUser
                | ResultCode::NotAuthenticated
                | ResultCode::RoleViolation
                | ResultCode::SecurityNotSupported
                | ResultCode::SecurityNotEnabled => AdminError::new_err(msg),
                // Default server error
                _ => ServerError::new_err(msg),
            }
        }
        AsError::InvalidNode(msg) => ClusterError::new_err(format!("Invalid node: {msg}")),
        AsError::NoMoreConnections => ClusterError::new_err("No more connections available"),
        _ => ClientError::new_err(format!("{err}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_result_code_to_int_ok() {
        assert_eq!(result_code_to_int(&ResultCode::Ok), 0);
    }

    #[test]
    fn test_result_code_to_int_key_not_found() {
        assert_eq!(result_code_to_int(&ResultCode::KeyNotFoundError), 2);
    }

    #[test]
    fn test_result_code_to_int_key_exists() {
        assert_eq!(result_code_to_int(&ResultCode::KeyExistsError), 5);
    }

    #[test]
    fn test_result_code_to_int_timeout() {
        assert_eq!(result_code_to_int(&ResultCode::Timeout), 9);
    }

    #[test]
    fn test_result_code_to_int_index_found() {
        assert_eq!(result_code_to_int(&ResultCode::IndexFound), 200);
    }

    #[test]
    fn test_result_code_to_int_index_not_found() {
        assert_eq!(result_code_to_int(&ResultCode::IndexNotFound), 201);
    }

    #[test]
    fn test_result_code_to_int_query_aborted() {
        assert_eq!(result_code_to_int(&ResultCode::QueryAborted), 210);
    }

    #[test]
    fn test_result_code_to_int_unknown() {
        assert_eq!(result_code_to_int(&ResultCode::Unknown(250)), 250);
    }
}

pub fn register_exceptions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    // Base exceptions
    m.add("AerospikeError", py.get_type::<AerospikeError>())?;
    m.add("ClientError", py.get_type::<ClientError>())?;
    m.add("ServerError", py.get_type::<ServerError>())?;
    m.add("RecordError", py.get_type::<RecordError>())?;
    m.add("ClusterError", py.get_type::<ClusterError>())?;
    m.add("TimeoutError", py.get_type::<TimeoutError>())?;
    m.add("InvalidArgError", py.get_type::<InvalidArgError>())?;
    // Record-level exceptions
    m.add("RecordNotFound", py.get_type::<RecordNotFound>())?;
    m.add("RecordExistsError", py.get_type::<RecordExistsError>())?;
    m.add(
        "RecordGenerationError",
        py.get_type::<RecordGenerationError>(),
    )?;
    m.add("RecordTooBig", py.get_type::<RecordTooBig>())?;
    m.add("BinNameError", py.get_type::<BinNameError>())?;
    m.add("BinExistsError", py.get_type::<BinExistsError>())?;
    m.add("BinNotFound", py.get_type::<BinNotFound>())?;
    m.add("BinTypeError", py.get_type::<BinTypeError>())?;
    m.add("FilteredOut", py.get_type::<FilteredOut>())?;
    // Index exceptions
    m.add("IndexError", py.get_type::<IndexError>())?;
    m.add("IndexNotFound", py.get_type::<IndexNotFound>())?;
    m.add("IndexFoundError", py.get_type::<IndexFoundError>())?;
    // Query exceptions
    m.add("QueryError", py.get_type::<QueryError>())?;
    m.add("QueryAbortedError", py.get_type::<QueryAbortedError>())?;
    // Admin / UDF exceptions
    m.add("AdminError", py.get_type::<AdminError>())?;
    m.add("UDFError", py.get_type::<UDFError>())?;
    Ok(())
}
