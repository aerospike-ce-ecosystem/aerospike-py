//! Aerospike error types mapped to Python exceptions.
//!
//! The exception hierarchy mirrors the Aerospike error taxonomy:
//!
//! ```text
//! AerospikeError (base)
//!   +-- ClientError          (connection, config, internal)
//!   +-- ServerError          (server-side errors)
//!   |     +-- AerospikeIndexError
//!   |     |     +-- IndexNotFound / IndexFoundError
//!   |     +-- QueryError / QueryAbortedError
//!   |     +-- AdminError / UDFError
//!   +-- RecordError          (record-level)
//!   |     +-- RecordNotFound / RecordExistsError / RecordGenerationError / ...
//!   +-- ClusterError         (node/connectivity)
//!   +-- AerospikeTimeoutError
//!   +-- InvalidArgError
//! ```

use aerospike_core::{Error as AsError, ResultCode};
use log::debug;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;

// Base exceptions
pyo3::create_exception!(
    aerospike,
    AerospikeError,
    PyException,
    "Base exception for all Aerospike errors."
);
pyo3::create_exception!(
    aerospike,
    ClientError,
    AerospikeError,
    "Client-side error (connection, configuration, internal)."
);
pyo3::create_exception!(
    aerospike,
    ServerError,
    AerospikeError,
    "Server-side error returned by the Aerospike cluster."
);
pyo3::create_exception!(
    aerospike,
    RecordError,
    AerospikeError,
    "Record-level error (not found, exists, generation mismatch, etc.)."
);
pyo3::create_exception!(
    aerospike,
    ClusterError,
    AerospikeError,
    "Cluster connectivity or node error."
);
pyo3::create_exception!(
    aerospike,
    AerospikeTimeoutError,
    AerospikeError,
    "Operation timed out."
);
pyo3::create_exception!(
    aerospike,
    InvalidArgError,
    AerospikeError,
    "Invalid argument passed to an operation."
);
pyo3::create_exception!(
    aerospike,
    BackpressureError,
    ClientError,
    "Maximum concurrent operations exceeded; retry after backoff."
);
pyo3::create_exception!(
    aerospike,
    RustPanicError,
    ClientError,
    "Native Rust panic during an operation. The Python process survived; the \
     operation did not complete. Common cause: legacy records carrying \
     language-specific blob particle types (PYTHON_BLOB, JAVA_BLOB, ...) that \
     aerospike-core 2.0.0 cannot decode (see issue #280)."
);

// Record-level exceptions
pyo3::create_exception!(
    aerospike,
    RecordNotFound,
    RecordError,
    "Record does not exist (result code 2)."
);
pyo3::create_exception!(
    aerospike,
    RecordExistsError,
    RecordError,
    "Record already exists (result code 5)."
);
pyo3::create_exception!(
    aerospike,
    RecordGenerationError,
    RecordError,
    "Record generation mismatch (result code 3)."
);
pyo3::create_exception!(
    aerospike,
    RecordTooBig,
    RecordError,
    "Record size exceeds server limit (result code 13)."
);
pyo3::create_exception!(
    aerospike,
    BinNameError,
    RecordError,
    "Bin name too long (result code 21)."
);
pyo3::create_exception!(
    aerospike,
    BinExistsError,
    RecordError,
    "Bin already exists (result code 6)."
);
pyo3::create_exception!(
    aerospike,
    BinNotFound,
    RecordError,
    "Bin does not exist (result code 17)."
);
pyo3::create_exception!(
    aerospike,
    BinTypeError,
    RecordError,
    "Bin type mismatch for the operation (result code 12)."
);
pyo3::create_exception!(
    aerospike,
    FilteredOut,
    RecordError,
    "Record filtered out by expression filter (result code 27)."
);

// Index exceptions
pyo3::create_exception!(
    aerospike,
    AerospikeIndexError,
    ServerError,
    "Secondary index error."
);
pyo3::create_exception!(
    aerospike,
    IndexNotFound,
    AerospikeIndexError,
    "Secondary index does not exist (result code 201)."
);
pyo3::create_exception!(
    aerospike,
    IndexFoundError,
    AerospikeIndexError,
    "Secondary index already exists (result code 200)."
);

// Query exceptions
pyo3::create_exception!(aerospike, QueryError, ServerError, "Query execution error.");
pyo3::create_exception!(
    aerospike,
    QueryAbortedError,
    QueryError,
    "Query was aborted by the server (result code 210)."
);

// Admin / UDF exceptions
pyo3::create_exception!(
    aerospike,
    AdminError,
    ServerError,
    "Admin or security operation error."
);
pyo3::create_exception!(
    aerospike,
    UDFError,
    ServerError,
    "User-Defined Function (UDF) execution error."
);

/// Map an `aerospike_core::ResultCode` to its integer wire-protocol value.
///
/// Every variant is mapped explicitly to the wire code defined in the server's
/// `proto.h` (mirroring `ResultCode::from_u8` in aerospike-core), so that
/// `BatchRecord.result` and error messages always carry the real server code.
/// `Unknown(code)` carries the raw byte through. The match is exhaustive — a
/// new aerospike-core variant fails the build instead of silently collapsing
/// to a meaningless `-1`.
pub(crate) fn result_code_to_int(rc: &ResultCode) -> i32 {
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
        ResultCode::SecuritySchemeNotSupported => 53,
        ResultCode::InvalidCommand => 54,
        ResultCode::InvalidField => 55,
        ResultCode::IllegalState => 56,
        ResultCode::InvalidUser => 60,
        ResultCode::UserAlreadyExists => 61,
        ResultCode::InvalidPassword => 62,
        ResultCode::ExpiredPassword => 63,
        ResultCode::ForbiddenPassword => 64,
        ResultCode::InvalidCredential => 65,
        ResultCode::ExpiredSession => 66,
        ResultCode::InvalidRole => 70,
        ResultCode::RoleAlreadyExists => 71,
        ResultCode::InvalidPrivilege => 72,
        ResultCode::InvalidAllowlist => 73,
        ResultCode::QuotasNotEnabled => 74,
        ResultCode::InvalidQuota => 75,
        ResultCode::NotAuthenticated => 80,
        ResultCode::RoleViolation => 81,
        ResultCode::NotAllowlisted => 82,
        ResultCode::QuotaExceeded => 83,
        ResultCode::UdfBadResponse => 100,
        ResultCode::BatchDisabled => 150,
        ResultCode::BatchMaxRequestsExceeded => 151,
        ResultCode::BatchQueuesFull => 152,
        ResultCode::InvalidGeojson => 160,
        ResultCode::IndexFound => 200,
        ResultCode::IndexNotFound => 201,
        ResultCode::IndexOom => 202,
        ResultCode::IndexNotReadable => 203,
        ResultCode::IndexGeneric => 204,
        ResultCode::IndexNameMaxLen => 205,
        ResultCode::IndexMaxCount => 206,
        ResultCode::QueryAborted => 210,
        ResultCode::QueryQueueFull => 211,
        ResultCode::QueryTimeout => 212,
        ResultCode::QueryGeneric => 213,
        ResultCode::QueryNetioErr => 214,
        ResultCode::QueryDuplicate => 215,
        ResultCode::Unknown(code) => *code as i32,
    }
}

/// Map a server `ResultCode` (plus a pre-rendered message) to the most
/// specific Python exception subclass.
///
/// Shared by every `aerospike_core::Error` variant that carries a
/// `ResultCode` — `ServerError`, `BatchError`, and `BatchLastError` — so a
/// batch failure surfaces the same exception type as the equivalent
/// single-record failure (e.g. a batch server timeout becomes
/// `AerospikeTimeoutError`, not a generic `ClientError`).
fn result_code_to_pyerr(rc: &ResultCode, msg: String) -> PyErr {
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
        ResultCode::ElementNotFound | ResultCode::ElementExists => RecordError::new_err(msg),
        // Server-side timeout: a server timeout result code must surface
        // as AerospikeTimeoutError so callers (and HTTP layers mapping
        // AerospikeTimeoutError -> 504) handle it like a client timeout
        // instead of an opaque 500-class ServerError.
        ResultCode::Timeout | ResultCode::QueryTimeout => AerospikeTimeoutError::new_err(msg),
        // Index
        ResultCode::IndexFound => IndexFoundError::new_err(msg),
        ResultCode::IndexNotFound => IndexNotFound::new_err(msg),
        // Query
        ResultCode::QueryAborted | ResultCode::ScanAbort => QueryAbortedError::new_err(msg),
        // UDF
        ResultCode::UdfBadResponse => UDFError::new_err(msg),
        // Admin / Security — every security/auth/quota result code
        // routes to AdminError so callers catching auth failures do
        // not silently miss password/session/role/quota errors.
        ResultCode::InvalidUser
        | ResultCode::NotAuthenticated
        | ResultCode::RoleViolation
        | ResultCode::SecurityNotSupported
        | ResultCode::SecurityNotEnabled
        | ResultCode::SecuritySchemeNotSupported
        | ResultCode::InvalidCommand
        | ResultCode::InvalidField
        | ResultCode::IllegalState
        | ResultCode::UserAlreadyExists
        | ResultCode::InvalidPassword
        | ResultCode::ExpiredPassword
        | ResultCode::ForbiddenPassword
        | ResultCode::InvalidCredential
        | ResultCode::ExpiredSession
        | ResultCode::InvalidRole
        | ResultCode::RoleAlreadyExists
        | ResultCode::InvalidPrivilege
        | ResultCode::InvalidAllowlist
        | ResultCode::QuotasNotEnabled
        | ResultCode::InvalidQuota
        | ResultCode::NotAllowlisted
        | ResultCode::QuotaExceeded => AdminError::new_err(msg),
        // Default server error
        _ => {
            log::warn!(
                "Unmapped ResultCode encountered in aerospike-py. \
                 This may indicate aerospike-py needs updating for this server error code. \
                 Error: {msg}"
            );
            ServerError::new_err(msg)
        }
    }
}

/// Convert an `aerospike_core::Error` into the appropriate Python exception.
///
/// Maps each error variant to the most specific exception subclass
/// (e.g. `KeyNotFoundError` -> `RecordNotFound`), falling back to
/// broader categories like `ServerError` or `ClientError`.
pub fn as_to_pyerr(err: AsError) -> PyErr {
    debug!("Mapping aerospike error: {}", err);
    match &err {
        AsError::Connection(msg) => ClusterError::new_err(format!("Connection error: {msg}")),
        AsError::Timeout(msg) => AerospikeTimeoutError::new_err(format!("Timeout: {msg}")),
        AsError::InvalidArgument(msg) => {
            InvalidArgError::new_err(format!("Invalid argument: {msg}"))
        }
        AsError::ServerError(rc, in_doubt, _node) => {
            let code = result_code_to_int(rc);
            let doubt_suffix = if *in_doubt { " [in_doubt]" } else { "" };
            let msg = format!("AEROSPIKE_ERR ({code}): {err}{doubt_suffix}");
            result_code_to_pyerr(rc, msg)
        }
        // Batch errors carry a real server ResultCode. Route them through the
        // same mapping as ServerError so a batch KeyNotFoundError / Timeout /
        // auth failure raises the precise exception type instead of falling
        // through to a generic ClientError plus a spurious bug-report log.
        AsError::BatchError(idx, rc, in_doubt, _msg)
        | AsError::BatchLastError(idx, rc, in_doubt, _msg) => {
            let code = result_code_to_int(rc);
            let doubt_suffix = if *in_doubt { " [in_doubt]" } else { "" };
            let msg = format!("AEROSPIKE_ERR ({code}) [batch_index={idx}]: {err}{doubt_suffix}");
            result_code_to_pyerr(rc, msg)
        }
        AsError::InvalidNode(msg) => ClusterError::new_err(format!("Invalid node: {msg}")),
        AsError::NoMoreConnections => ClusterError::new_err("No more connections available"),
        _ => {
            crate::bug_report::log_unexpected_error(
                "errors::as_to_pyerr",
                &format!("Unmapped aerospike_core::Error variant: {err}"),
            );
            ClientError::new_err(format!("{err}"))
        }
    }
}

/// Register all Aerospike exception types on the native Python module.
pub fn register_exceptions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    // Base exceptions
    m.add("AerospikeError", py.get_type::<AerospikeError>())?;
    m.add("ClientError", py.get_type::<ClientError>())?;
    m.add("ServerError", py.get_type::<ServerError>())?;
    m.add("RecordError", py.get_type::<RecordError>())?;
    m.add("ClusterError", py.get_type::<ClusterError>())?;
    m.add(
        "AerospikeTimeoutError",
        py.get_type::<AerospikeTimeoutError>(),
    )?;
    m.add("TimeoutError", py.get_type::<AerospikeTimeoutError>())?; // backward compat
    m.add("InvalidArgError", py.get_type::<InvalidArgError>())?;
    m.add("BackpressureError", py.get_type::<BackpressureError>())?;
    m.add("RustPanicError", py.get_type::<RustPanicError>())?;
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
    m.add("AerospikeIndexError", py.get_type::<AerospikeIndexError>())?;
    m.add("IndexError", py.get_type::<AerospikeIndexError>())?; // backward compat
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

    #[test]
    fn test_result_code_to_int_query_timeout() {
        // QueryTimeout previously fell through to the catch-all `-1`.
        assert_eq!(result_code_to_int(&ResultCode::QueryTimeout), 212);
    }

    #[test]
    fn test_result_code_to_int_previously_unmapped_codes() {
        // These variants previously collapsed to the meaningless `-1` catch-all,
        // so BatchRecord.result and error messages lost the real wire code.
        // Each must now carry its proto.h wire value.
        assert_eq!(
            result_code_to_int(&ResultCode::BatchMaxRequestsExceeded),
            151
        );
        assert_eq!(result_code_to_int(&ResultCode::BatchQueuesFull), 152);
        assert_eq!(result_code_to_int(&ResultCode::IndexOom), 202);
        assert_eq!(result_code_to_int(&ResultCode::IndexNotReadable), 203);
        assert_eq!(result_code_to_int(&ResultCode::IndexGeneric), 204);
        assert_eq!(result_code_to_int(&ResultCode::IndexNameMaxLen), 205);
        assert_eq!(result_code_to_int(&ResultCode::IndexMaxCount), 206);
        assert_eq!(result_code_to_int(&ResultCode::QueryQueueFull), 211);
        assert_eq!(result_code_to_int(&ResultCode::QueryGeneric), 213);
        assert_eq!(result_code_to_int(&ResultCode::QueryNetioErr), 214);
        assert_eq!(result_code_to_int(&ResultCode::QueryDuplicate), 215);
        assert_eq!(result_code_to_int(&ResultCode::ExpiredSession), 66);
        assert_eq!(result_code_to_int(&ResultCode::InvalidPassword), 62);
        assert_eq!(result_code_to_int(&ResultCode::QuotaExceeded), 83);
        assert_eq!(result_code_to_int(&ResultCode::UserAlreadyExists), 61);
        assert_eq!(result_code_to_int(&ResultCode::IllegalState), 56);
    }

    #[test]
    fn test_result_code_to_int_no_longer_returns_minus_one() {
        // The `-1` catch-all is gone. Every named variant must map to its real
        // non-negative wire code; only an `Unknown` byte can still be passed
        // through verbatim. Spot-check a representative variant from each range.
        for rc in [
            ResultCode::Ok,
            ResultCode::ServerError,
            ResultCode::Timeout,
            ResultCode::ElementExists,
            ResultCode::XDRKeyBusy,
            ResultCode::QueryEnd,
            ResultCode::IllegalState,
            ResultCode::ExpiredSession,
            ResultCode::QuotaExceeded,
            ResultCode::UdfBadResponse,
            ResultCode::BatchQueuesFull,
            ResultCode::InvalidGeojson,
            ResultCode::IndexMaxCount,
            ResultCode::QueryDuplicate,
        ] {
            assert!(
                result_code_to_int(&rc) >= 0,
                "result_code_to_int must not return -1 for {rc:?}"
            );
        }
    }

    #[test]
    fn test_security_result_codes_map_to_admin_error() {
        // Password/session/role/quota security codes must surface as AdminError
        // so callers catching auth failures do not silently miss them.
        Python::initialize();
        Python::attach(|py| {
            for rc in [
                ResultCode::InvalidPassword,
                ResultCode::ExpiredSession,
                ResultCode::InvalidCredential,
                ResultCode::UserAlreadyExists,
                ResultCode::InvalidRole,
                ResultCode::QuotaExceeded,
                ResultCode::NotAllowlisted,
            ] {
                let err = as_to_pyerr(AsError::ServerError(rc, false, String::new()));
                assert!(
                    err.is_instance_of::<AdminError>(py),
                    "security result code {rc:?} must map to AdminError"
                );
            }
        });
    }

    #[test]
    fn test_server_timeout_maps_to_timeout_error() {
        // A server-side Timeout result code must surface as AerospikeTimeoutError,
        // not the generic ServerError it previously fell through to.
        Python::initialize();
        Python::attach(|py| {
            let err = as_to_pyerr(AsError::ServerError(
                ResultCode::Timeout,
                false,
                String::new(),
            ));
            assert!(
                err.is_instance_of::<AerospikeTimeoutError>(py),
                "server Timeout result code must map to AerospikeTimeoutError"
            );
        });
    }

    #[test]
    fn test_query_timeout_maps_to_timeout_error() {
        Python::initialize();
        Python::attach(|py| {
            let err = as_to_pyerr(AsError::ServerError(
                ResultCode::QueryTimeout,
                false,
                String::new(),
            ));
            assert!(
                err.is_instance_of::<AerospikeTimeoutError>(py),
                "QueryTimeout result code must map to AerospikeTimeoutError"
            );
        });
    }

    #[test]
    fn test_batch_error_maps_by_result_code() {
        // BatchError / BatchLastError carry a real server ResultCode and must
        // map to the same precise exception type as ServerError, instead of
        // collapsing to a generic ClientError.
        Python::initialize();
        Python::attach(|py| {
            let not_found = as_to_pyerr(AsError::BatchError(
                3,
                ResultCode::KeyNotFoundError,
                false,
                "node".into(),
            ));
            assert!(
                not_found.is_instance_of::<RecordNotFound>(py),
                "batch KeyNotFoundError must map to RecordNotFound"
            );

            let timeout = as_to_pyerr(AsError::BatchLastError(
                0,
                ResultCode::Timeout,
                true,
                "node".into(),
            ));
            assert!(
                timeout.is_instance_of::<AerospikeTimeoutError>(py),
                "batch Timeout must map to AerospikeTimeoutError"
            );

            let big = as_to_pyerr(AsError::BatchError(
                7,
                ResultCode::RecordTooBig,
                false,
                "node".into(),
            ));
            assert!(
                big.is_instance_of::<RecordTooBig>(py),
                "batch RecordTooBig must map to RecordTooBig"
            );
        });
    }

    #[test]
    fn test_batch_error_message_includes_index_and_in_doubt() {
        // The rendered message must surface the batch index and the in_doubt
        // flag so callers can retry/diagnose the failed sub-request.
        Python::initialize();
        Python::attach(|py| {
            let err = as_to_pyerr(AsError::BatchLastError(
                5,
                ResultCode::ServerError,
                true,
                "node".into(),
            ));
            let text = err.value(py).to_string();
            assert!(
                text.contains("batch_index=5"),
                "batch error message must include the batch index: {text}"
            );
            assert!(
                text.contains("in_doubt"),
                "in_doubt batch error message must be flagged: {text}"
            );
        });
    }
}
