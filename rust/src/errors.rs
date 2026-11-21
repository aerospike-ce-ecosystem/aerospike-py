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

use std::borrow::Cow;
use std::fmt::Write as _;

use aerospike_core::{ClientResultCode, Error as AsError, ErrorKind, ResultCode};
use log::debug;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;

/// Sentinel `result_code` for client-side failures that never carried a server
/// wire code — connection errors, client timeouts, invalid arguments,
/// backpressure, caught Rust panics, and any not-yet-mapped
/// `aerospike_core::Error` variant.
///
/// Matches ADR-0027's "-1 for unknown / no server response" guidance and mirrors
/// the Aerospike C client's `AEROSPIKE_ERR_CLIENT = -1`. Exposed so downstream
/// code and tests can classify "no server code" without hard-coding the literal.
pub const CLIENT_SIDE_RESULT_CODE: i32 = -1;

/// Attach the structured classification to an exception instance so callers
/// can tell failures apart without parsing the message string:
///
/// - `result_code` (ADR-0027): the server wire code, or
///   [`CLIENT_SIDE_RESULT_CODE`] when no server answered;
/// - `error_type`: the class name that the Prometheus `error_type` label and
///   the OpenTelemetry `error.type` attribute also carry;
/// - `in_doubt`: whether a write may have been applied even though it failed.
///
/// The GIL is acquired only on the (exceptional) error path to materialise the
/// exception value and set the attributes; on the rare chance an assignment
/// fails it is logged and the original error is still raised. The per-instance
/// values shadow the class-level defaults set in [`register_exceptions`].
fn attach_error_info(err: PyErr, class: ErrorClass, in_doubt: bool) -> PyErr {
    Python::attach(|py| {
        let value = err.value(py);
        let set = value
            .setattr("result_code", class.result_code())
            .and_then(|()| value.setattr("error_type", class.label().as_ref()))
            .and_then(|()| value.setattr("in_doubt", in_doubt));
        if let Err(set_err) = set {
            debug!("failed to attach error info for {class:?} to exception: {set_err}");
        }
    });
    err
}

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
/// The conversion is aerospike-core's own (`u8::from`), so every code — also
/// one a newer server adds, which arrives as `Unknown(code)` — reports the
/// value the server put on the wire. `BatchRecord.result` and error messages
/// therefore always carry the real server code.
pub(crate) fn result_code_to_int(rc: &ResultCode) -> i32 {
    i32::from(u8::from(*rc))
}

/// What kind of failure an `aerospike_core::Error` is.
///
/// This is the one classification the binding uses. The Python exception
/// type, the `result_code` / `error_type` / `in_doubt` attributes on it, the
/// Prometheus `error_type` label and the OpenTelemetry `error.type` attribute
/// are all derived from it, so the three views of an error cannot disagree
/// about what happened.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorClass {
    /// The server answered with a non-OK result code. A server-reported
    /// timeout is `Server(ResultCode::Timeout)`, not [`ClientTimeout`](Self::ClientTimeout).
    Server(ResultCode),
    /// The client's own deadline elapsed before an answer arrived.
    ClientTimeout,
    /// More than one attempt was made and the retry budget ran out with every
    /// attempt timing out.
    RetriesExhausted,
    /// The connection to a node was lost or could not be made. Includes raw
    /// I/O errors: a node going down surfaces as one.
    Connection,
    /// A node's connection pool has no connection to give.
    NoMoreConnections,
    /// The per-node circuit breaker refused the command without sending it.
    MaxErrorRate,
    /// The target node is not an active member of the cluster.
    InvalidNode,
    /// The caller passed an invalid argument or an unknown namespace.
    InvalidArgument,
    /// A user-defined function failed: the server ran it (or could not find
    /// it) and answered with `UDF_BAD_RESPONSE` and the failure text.
    Udf,
    /// A scan or query record stream ended before it was complete.
    StreamTerminated,
    /// The server sent something the client could not interpret.
    BadResponse,
    /// A client-side failure with no more specific class.
    Client,
    /// A kind this binding has no name for: aerospike-core is newer than the
    /// mapping below. The only class that is reported as a possible bug.
    Unknown,
}

/// What one link of an error's cause chain contributes to its class: see
/// [`ErrorClass::weigh_cause`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CauseWeight {
    /// The cause is the real failure.
    Decides,
    /// The cause is of the wrapper's own kind: the wrapper stands.
    ConfirmsTheWrapper,
    /// A context message, or nothing recognisable. Look at its cause.
    SaysNothing,
}

impl ErrorClass {
    /// Classify one error by its own kind, ignoring what caused it.
    fn of_kind(err: &AsError) -> Self {
        match err.kind() {
            ErrorKind::Server { rc, .. } => Self::Server(*rc),
            ErrorKind::Timeout => {
                // The retry loop reports an exhausted budget as a timeout that
                // carries MAX_RETRIES_EXCEEDED. With a single attempt that is
                // simply the attempt timing out, so it only counts as
                // "retries exhausted" once a retry actually happened.
                let exhausted = err.client_result_code()
                    == Some(ClientResultCode::MaxRetriesExceeded)
                    && err.iteration().is_some_and(|tries| tries > 1);
                if exhausted {
                    Self::RetriesExhausted
                } else {
                    Self::ClientTimeout
                }
            }
            ErrorKind::Connection | ErrorKind::Io(_) => Self::Connection,
            ErrorKind::ConnectionPoolEmpty | ErrorKind::NoMoreConnections => {
                Self::NoMoreConnections
            }
            ErrorKind::MaxErrorRate => Self::MaxErrorRate,
            ErrorKind::InvalidNode => Self::InvalidNode,
            ErrorKind::InvalidArgument | ErrorKind::InvalidNamespace => Self::InvalidArgument,
            ErrorKind::UdfBadResponse => Self::Udf,
            ErrorKind::StreamTerminated => Self::StreamTerminated,
            ErrorKind::BadResponse
            | ErrorKind::ParsePeers
            | ErrorKind::InvalidUtf8(_)
            | ErrorKind::ParseAddr(_)
            | ErrorKind::ParseInt(_) => Self::BadResponse,
            ErrorKind::Client | ErrorKind::Commit { .. } => Self::Client,
            _ => Self::Unknown,
        }
    }

    /// Classify an error, looking through the two wrappers aerospike-core
    /// puts around the real failure.
    ///
    /// - When the retry budget runs out, the error on top is a timeout and its
    ///   cause is the failure of the last attempt. A node that is down is
    ///   then a `Connection` failure three levels of indirection away from
    ///   what the caller sees. Rust client 2.x returned the last attempt's
    ///   error itself, and so does this.
    /// - `Error::chain_error` puts a context message in front of a failure,
    ///   which makes the top error a plain client error.
    ///
    /// In both cases the first cause with a more specific class decides.
    pub fn of(err: &AsError) -> Self {
        Self::decided_by(err).0
    }

    /// [`of`](Self::of), together with the error in the chain that decided
    /// the class: `err` itself, or the cause that was looked through to.
    fn decided_by(err: &AsError) -> (Self, &AsError) {
        let own = Self::of_kind(err);
        if !own.is_a_wrapper() {
            return (own, err);
        }
        let mut cause = err.cause();
        while let Some(c) = cause {
            let class = Self::of_kind(c);
            match own.weigh_cause(class) {
                CauseWeight::Decides => return (class, c),
                CauseWeight::ConfirmsTheWrapper => return (own, err),
                CauseWeight::SaysNothing => cause = c.cause(),
            }
        }
        (own, err)
    }

    /// Whether an error of this class may be a wrapper around the real
    /// failure: a timeout (the retry budget or the deadline ran out) or a
    /// bare client error (a context message).
    fn is_a_wrapper(self) -> bool {
        matches!(
            self,
            Self::ClientTimeout | Self::RetriesExhausted | Self::Client
        )
    }

    /// What a cause of class `cause` means for a wrapper of class `self`.
    ///
    /// The first cause that is neither a context message nor unknown is the
    /// failure of the last attempt, and it settles the matter either way.
    /// When that attempt timed out under a timeout, the wrapper already says
    /// so. Looking further down from there would find the attempts *before*
    /// the last: the multi-key batch loop chains every attempt it made, newest
    /// first, and a call whose attempts were "connection refused, timeout,
    /// timeout" was reported as a connection failure, while a single-record
    /// command with the same history - which keeps earlier attempts out of the
    /// chain - was reported as the timeout it ended in.
    fn weigh_cause(self, cause: Self) -> CauseWeight {
        let self_is_timeout = matches!(self, Self::ClientTimeout | Self::RetriesExhausted);
        match cause {
            Self::Client | Self::Unknown => CauseWeight::SaysNothing,
            Self::ClientTimeout | Self::RetriesExhausted if self_is_timeout => {
                CauseWeight::ConfirmsTheWrapper
            }
            _ => CauseWeight::Decides,
        }
    }

    /// Short stable name of the class: the Prometheus `error_type` label, the
    /// OpenTelemetry `error.type` attribute and the `error_type` attribute of
    /// the Python exception.
    ///
    /// `Cow::Borrowed` (no allocation) for every class except a server result
    /// code without a dedicated arm.
    pub fn label(&self) -> Cow<'static, str> {
        Cow::Borrowed(match self {
            Self::Server(rc) => match rc {
                ResultCode::KeyNotFoundError => "KeyNotFoundError",
                ResultCode::KeyExistsError => "KeyExistsError",
                ResultCode::GenerationError => "GenerationError",
                ResultCode::RecordTooBig => "RecordTooBig",
                ResultCode::BinTypeError => "BinTypeError",
                ResultCode::BinNotFound => "BinNotFound",
                ResultCode::FilteredOut => "FilteredOut",
                // The codes a server under load answers many rows with: named
                // here so that labelling them allocates nothing.
                ResultCode::DeviceOverload => "DeviceOverload",
                ResultCode::KeyBusy => "KeyBusy",
                ResultCode::PartitionUnavailable => "PartitionUnavailable",
                // Kept apart from the client's own "Timeout": the server
                // answered, with result code 9.
                ResultCode::Timeout => "ServerTimeout",
                other => return Cow::Owned(format!("{other:?}")),
            },
            Self::ClientTimeout => "Timeout",
            Self::RetriesExhausted => "MaxRetriesExceeded",
            Self::Connection => "Connection",
            Self::NoMoreConnections => "NoMoreConnections",
            Self::MaxErrorRate => "MaxErrorRate",
            Self::InvalidNode => "InvalidNode",
            Self::InvalidArgument => "InvalidArgument",
            Self::Udf => "UdfBadResponse",
            Self::StreamTerminated => "StreamTerminated",
            Self::BadResponse => "BadResponse",
            Self::Client => "Client",
            Self::Unknown => "Unknown",
        })
    }

    /// The `result_code` a Python exception of this class carries: the wire
    /// code when a server answered, [`CLIENT_SIDE_RESULT_CODE`] otherwise.
    ///
    /// aerospike-core also gives client-side failures a negative code, but in
    /// the Java client's numbering, which disagrees with the constants of the
    /// official Python client (`-11` is "max retries exceeded" here and
    /// something else there). Exposing it would invite wrong comparisons, so
    /// every client-side failure keeps the single `-1` sentinel and is told
    /// apart by `error_type` instead.
    ///
    /// A UDF failure is a server answer. aerospike-core reports it as a kind
    /// of its own rather than as a server error, but the answer it stands for
    /// carried `UDF_BAD_RESPONSE` (100), so that is the code.
    pub fn result_code(&self) -> i32 {
        match self {
            Self::Server(rc) => result_code_to_int(rc),
            Self::Udf => result_code_to_int(&ResultCode::UdfBadResponse),
            _ => CLIENT_SIDE_RESULT_CODE,
        }
    }
}

/// True when `err` is the server saying the record does not exist.
pub(crate) fn is_key_not_found(err: &AsError) -> bool {
    matches!(
        err.kind(),
        ErrorKind::Server {
            rc: ResultCode::KeyNotFoundError,
            ..
        }
    )
}

/// Map a server `ResultCode` (plus a pre-rendered message) to the most
/// specific Python exception subclass.
///
/// Every failure that carries a server result code goes through here — a
/// single-record command and a batch row alike — so a batch failure surfaces
/// the same exception type as the equivalent single-record failure (e.g. a
/// batch server timeout becomes `AerospikeTimeoutError`, not a generic
/// `ClientError`).
fn result_code_exception(rc: &ResultCode, msg: String) -> PyErr {
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
        // What a server under load refuses a write with. A plain ServerError,
        // and nothing this library needs updating for: a batch that returns
        // such a row builds this exception only to drop it, and a warning per
        // refused call said otherwise.
        ResultCode::KeyBusy | ResultCode::DeviceOverload | ResultCode::PartitionUnavailable => {
            ServerError::new_err(msg)
        }
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

/// Prefixes aerospike-core puts in front of an error's own text. This module
/// writes its own, so they are removed to avoid "Invalid argument: Invalid
/// argument: ...".
const CORE_MESSAGE_PREFIXES: &[&str] = &[
    "Client Timeout: ",
    "Unable to communicate with server cluster: ",
    "Invalid argument: ",
    "Invalid cluster node: ",
    "Invalid namespace: ",
    "Bad Server Response: ",
];

fn bare_message(err: &AsError) -> String {
    let base = err.base_message();
    for prefix in CORE_MESSAGE_PREFIXES {
        if let Some(rest) = base.strip_prefix(prefix) {
            return rest.to_string();
        }
    }
    base
}

/// Render an error and its causes as one line of text.
///
/// `Display` on an aerospike-core error leads with its Java-numbered code
/// ("Error -11"), which would be read as a `result_code`. This keeps the
/// text, the node and the cause chain, and leaves the code out.
pub(crate) fn describe(err: &AsError) -> String {
    let mut out = bare_message(err);
    if let Some(node) = err.node() {
        let _ = write!(out, " [node={node}]");
    }
    let mut cause = err.cause();
    while let Some(c) = cause {
        let _ = write!(out, "; caused by: {}", c.base_message());
        cause = c.cause();
    }
    out
}

/// Build the Python exception for a classified failure.
///
/// Split from [`as_to_pyerr`] so the mapping can be tested for every class:
/// aerospike-core only lets its own code construct most error kinds.
fn build_pyerr(class: ErrorClass, detail: &str, node: Option<&str>, in_doubt: bool) -> PyErr {
    let doubt = if in_doubt { " [in_doubt]" } else { "" };
    let exception = match class {
        ErrorClass::Server(rc) => {
            let code = result_code_to_int(&rc);
            result_code_exception(&rc, format!("AEROSPIKE_ERR ({code}): {detail}{doubt}"))
        }
        ErrorClass::ClientTimeout | ErrorClass::RetriesExhausted => {
            AerospikeTimeoutError::new_err(format!("Timeout: {detail}{doubt}"))
        }
        ErrorClass::Connection => {
            ClusterError::new_err(format!("Connection error: {detail}{doubt}"))
        }
        ErrorClass::NoMoreConnections => {
            ClusterError::new_err(format!("No more connections available: {detail}"))
        }
        // aerospike-core's per-node circuit breaker: once a node exceeds
        // `ClientPolicy::max_error_rate` errors within one `error_rate_window`,
        // commands aimed at it are refused client-side until the counter
        // resets. That is a node-availability condition, so it belongs with
        // the other ClusterError cases.
        ErrorClass::MaxErrorRate => ClusterError::new_err(format!(
            "Node circuit breaker tripped (max_error_rate exceeded) for node {}",
            node.unwrap_or("<unknown>")
        )),
        ErrorClass::InvalidNode => ClusterError::new_err(format!("Invalid node: {detail}")),
        ErrorClass::InvalidArgument => {
            InvalidArgError::new_err(format!("Invalid argument: {detail}"))
        }
        ErrorClass::Udf => UDFError::new_err(format!("UDF error: {detail}{doubt}")),
        ErrorClass::StreamTerminated => {
            ClientError::new_err(format!("Record stream terminated: {detail}"))
        }
        ErrorClass::BadResponse => {
            ClientError::new_err(format!("Bad server response: {detail}{doubt}"))
        }
        ErrorClass::Client | ErrorClass::Unknown => {
            ClientError::new_err(format!("{detail}{doubt}"))
        }
    };
    attach_error_info(exception, class, in_doubt)
}

/// Convert an `aerospike_core::Error` into the appropriate Python exception.
///
/// The error is classified once ([`ErrorClass::of`]) and the exception type,
/// its message and its `result_code` / `error_type` / `in_doubt` attributes
/// all follow from that class.
pub fn as_to_pyerr(err: AsError) -> PyErr {
    debug!("Mapping aerospike error: {}", err);
    let class = ErrorClass::of(&err);
    if class == ErrorClass::Unknown {
        // Only a kind this mapping has never heard of is worth a report. A
        // node going down, a bad argument or a malformed response are things
        // that happen to a correct client.
        crate::bug_report::log_unexpected_error(
            "errors::as_to_pyerr",
            &format!("Unmapped aerospike_core::Error kind: {err}"),
        );
    }
    build_pyerr(
        class,
        &describe(&err),
        err.node(),
        may_have_been_applied(&err),
    )
}

/// Whether a write that failed with `err` may have been applied all the same:
/// the `in_doubt` of the Python exception, of a batch row and of the span.
///
/// aerospike-core decides this for every error in a chain, by one rule for a
/// server's answer (in doubt only when the server timed out, or when an
/// earlier attempt of the same command was sent and may have gone through)
/// and another for everything else (in doubt as soon as the command was
/// sent). Two kinds of server answer end up under "everything else", and are
/// put right here:
///
/// - **A UDF failure.** The server could not find the function, or ran it,
///   rolled the record back and said so. That is as definite as KEY_EXISTS,
///   and the Java client treats it that way.
/// - **An answer that would have been worth a retry** (KEY_BUSY,
///   DEVICE_OVERLOAD, PARTITION_UNAVAILABLE, the server's TIMEOUT) when no
///   attempt is left. aerospike-core hands it over wrapped in an "attempts
///   used up" error, which is a client-side failure and so says "in doubt" —
///   for a write the server has just refused to queue. The class of such an
///   error is the server's code ([`ErrorClass::of`] looks through the
///   wrapper); the doubt has to be read off the same error, and that one was
///   judged by the rule for a server's answer.
pub(crate) fn may_have_been_applied(err: &AsError) -> bool {
    if !err.in_doubt() {
        return false;
    }
    if let Some(answer) = udf_answer(err) {
        // The retry loop files the error of every earlier attempt under the
        // final one, so "no earlier attempt" reads as "no sub-errors". An
        // earlier attempt that failed before it was sent is filed too, which
        // errs on the side of saying "in doubt".
        return !answer.sub_errors().is_empty();
    }
    match ErrorClass::decided_by(err) {
        (ErrorClass::Server(_), answer) => answer.in_doubt(),
        _ => true,
    }
}

/// The server's "the UDF failed" answer that `err` reports, if it reports one.
///
/// A single-record command reports it as its own error. aerospike-core runs a
/// one-key batch as a single-record command and wraps that command's error in
/// the row's, so there it is the direct cause. (A row of a larger batch is a
/// plain server error and already follows the rule for a server's answer.)
fn udf_answer(err: &AsError) -> Option<&AsError> {
    let is_udf_answer = |e: &&AsError| matches!(e.kind(), ErrorKind::UdfBadResponse);
    match err.kind() {
        ErrorKind::UdfBadResponse => Some(err),
        ErrorKind::Server {
            rc: ResultCode::UdfBadResponse,
            ..
        } => err.cause().filter(is_udf_answer),
        _ => None,
    }
}

/// Build the `RecordNotFound` error raised when a delete targeted a record
/// that did not exist.
///
/// `aerospike-core` collapses the server's KEY_NOT_FOUND_ERROR delete response
/// into `Ok(false)` instead of surfacing an `Error`, so `do_remove` constructs
/// this exception itself. The failure *is* a server response, so it must carry
/// the real wire code (2 — matching both the message text and
/// `AEROSPIKE_ERR_RECORD_NOT_FOUND`), not the [`CLIENT_SIDE_RESULT_CODE`]
/// sentinel (ADR-0027).
///
/// `may_be_a_resend` is the delete's `max_retries > 0`: a delete that was sent
/// twice finds nothing the second time because the first time removed the
/// record. aerospike-core does not say whether that happened, so with
/// re-sending switched on the miss is reported in doubt.
pub(crate) fn record_not_found_for_delete(may_be_a_resend: bool) -> PyErr {
    build_pyerr(
        ErrorClass::Server(ResultCode::KeyNotFoundError),
        "Record not found",
        None,
        may_be_a_resend,
    )
}

/// Register all Aerospike exception types on the native Python module.
pub fn register_exceptions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    // Base exceptions
    m.add("AerospikeError", py.get_type::<AerospikeError>())?;
    // Expose class-level defaults on the base exception so every
    // AerospikeError subclass instance carries `.result_code: int` (ADR-0027),
    // `.in_doubt: bool` and `.error_type: str`, even those constructed outside
    // `as_to_pyerr` (e.g. BackpressureError, RustPanicError, InvalidArgError
    // from policy/query validation). `as_to_pyerr` overrides all three
    // per-instance; exceptions raised elsewhere keep these defaults, refined
    // per class below where the class alone says what the failure was.
    let base = py.get_type::<AerospikeError>();
    base.setattr("result_code", CLIENT_SIDE_RESULT_CODE)?;
    base.setattr("in_doubt", false)?;
    base.setattr("error_type", "Client")?;
    // Only a batch call that failed as a whole sets this, to the rows it did
    // collect (a `BatchRecords`). `None` everywhere else, so a handler can
    // read the attribute without first checking which call raised.
    base.setattr("partial_result", py.None())?;
    py.get_type::<InvalidArgError>()
        .setattr("error_type", "InvalidArgument")?;
    py.get_type::<AerospikeTimeoutError>()
        .setattr("error_type", "Timeout")?;
    py.get_type::<ClusterError>()
        .setattr("error_type", "Connection")?;
    py.get_type::<BackpressureError>()
        .setattr("error_type", "Backpressure")?;
    py.get_type::<RustPanicError>()
        .setattr("error_type", "RustPanic")?;
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

    fn attr<T: for<'a, 'py> FromPyObject<'a, 'py>>(py: Python<'_>, err: &PyErr, name: &str) -> T
    where
        for<'a, 'py> <T as FromPyObject<'a, 'py>>::Error: std::fmt::Debug,
    {
        err.value(py).getattr(name).unwrap().extract().unwrap()
    }

    // ── wire codes ──────────────────────────────────────────────

    #[test]
    fn result_code_to_int_reports_the_wire_value() {
        for (rc, wire) in [
            (ResultCode::Ok, 0),
            (ResultCode::KeyNotFoundError, 2),
            (ResultCode::GenerationError, 3),
            (ResultCode::KeyExistsError, 5),
            (ResultCode::Timeout, 9),
            (ResultCode::RecordTooBig, 13),
            (ResultCode::DeviceOverload, 18),
            (ResultCode::FilteredOut, 27),
            (ResultCode::XdrKeyBusy, 32),
            (ResultCode::NotAuthenticated, 80),
            (ResultCode::UdfBadResponse, 100),
            (ResultCode::BatchQueuesFull, 152),
            (ResultCode::IndexFound, 200),
            (ResultCode::IndexNotFound, 201),
            (ResultCode::QueryAborted, 210),
            (ResultCode::QueryTimeout, 212),
        ] {
            assert_eq!(result_code_to_int(&rc), wire, "{rc:?}");
        }
    }

    /// A code this client has no name for must keep its wire value, never
    /// collapse to the client-side sentinel.
    #[test]
    fn unknown_result_code_keeps_its_wire_value() {
        assert_eq!(result_code_to_int(&ResultCode::Unknown(123)), 123);
        assert_eq!(result_code_to_int(&ResultCode::from(250u8)), 250);
    }

    // ── classification of constructible errors ──────────────────

    #[test]
    fn invalid_argument_is_not_a_client_bug() {
        let err = AsError::invalid_argument("bad bin name");
        assert_eq!(ErrorClass::of(&err), ErrorClass::InvalidArgument);
    }

    /// Issue #445: an I/O error — what a node going down looks like — used to
    /// fall through to the "this may be a bug in aerospike-py" branch.
    #[test]
    fn io_error_is_a_connection_failure() {
        let io = std::io::Error::new(std::io::ErrorKind::ConnectionReset, "reset by peer");
        let err: AsError = io.into();
        assert_eq!(ErrorClass::of(&err), ErrorClass::Connection);
        assert_eq!(ErrorClass::of(&err).label(), "Connection");
    }

    #[test]
    fn plain_client_error_is_client() {
        let err = AsError::client_error("something client-side");
        assert_eq!(ErrorClass::of(&err), ErrorClass::Client);
    }

    /// `chain_error` puts a context message in front of the real failure.
    #[test]
    fn context_wrapper_is_classified_by_its_cause() {
        let io = std::io::Error::new(std::io::ErrorKind::BrokenPipe, "broken pipe");
        let err = AsError::from(io).chain_error("while sending the batch");
        assert_eq!(ErrorClass::of(&err), ErrorClass::Connection);

        let err = AsError::invalid_argument("bad key").chain_error("while building the command");
        assert_eq!(ErrorClass::of(&err), ErrorClass::InvalidArgument);

        let err = AsError::client_error("inner").chain_error("outer");
        assert_eq!(ErrorClass::of(&err), ErrorClass::Client);
    }

    #[test]
    fn describe_keeps_the_cause_chain_and_drops_core_prefixes() {
        let err = AsError::invalid_argument("bad bin name");
        assert_eq!(describe(&err), "bad bin name");

        let io = std::io::Error::new(std::io::ErrorKind::ConnectionReset, "reset by peer");
        let text = describe(&AsError::from(io).chain_error("while sending the batch"));
        assert!(text.starts_with("while sending the batch"), "{text}");
        assert!(text.contains("caused by:"), "{text}");
        assert!(text.contains("reset by peer"), "{text}");
        // The Java-numbered code of `Display` must not leak into the text.
        assert!(!text.contains("Error -"), "{text}");
    }

    // ── labels ──────────────────────────────────────────────────

    /// The chain of a retried multi-key batch holds every attempt, newest
    /// first. Only the newest is the reason the call failed. (A timeout with
    /// causes cannot be built outside aerospike-core, hence the classes.)
    #[test]
    fn the_last_attempt_decides_under_a_timeout() {
        use CauseWeight::{ConfirmsTheWrapper, Decides, SaysNothing};
        for wrapper in [ErrorClass::RetriesExhausted, ErrorClass::ClientTimeout] {
            assert_eq!(wrapper.weigh_cause(ErrorClass::Connection), Decides);
            assert_eq!(
                wrapper.weigh_cause(ErrorClass::Server(ResultCode::KeyBusy)),
                Decides
            );
            // The last attempt timed out: stop here, whatever came before it.
            assert_eq!(
                wrapper.weigh_cause(ErrorClass::ClientTimeout),
                ConfirmsTheWrapper
            );
            assert_eq!(
                wrapper.weigh_cause(ErrorClass::RetriesExhausted),
                ConfirmsTheWrapper
            );
            assert_eq!(wrapper.weigh_cause(ErrorClass::Client), SaysNothing);
            assert_eq!(wrapper.weigh_cause(ErrorClass::Unknown), SaysNothing);
        }
        // A context message takes the class of whatever it is put in front of.
        assert_eq!(
            ErrorClass::Client.weigh_cause(ErrorClass::ClientTimeout),
            Decides
        );
        assert_eq!(
            ErrorClass::Client.weigh_cause(ErrorClass::Connection),
            Decides
        );
        assert_eq!(
            ErrorClass::Client.weigh_cause(ErrorClass::Client),
            SaysNothing
        );
        assert!(!ErrorClass::Connection.is_a_wrapper());
        assert!(!ErrorClass::Server(ResultCode::KeyBusy).is_a_wrapper());
    }

    #[test]
    fn labels_tell_the_timeout_flavours_apart() {
        assert_eq!(ErrorClass::ClientTimeout.label(), "Timeout");
        assert_eq!(ErrorClass::RetriesExhausted.label(), "MaxRetriesExceeded");
        assert_eq!(
            ErrorClass::Server(ResultCode::Timeout).label(),
            "ServerTimeout"
        );
        assert_eq!(ErrorClass::Connection.label(), "Connection");
    }

    #[test]
    fn server_labels_are_the_result_code_names() {
        assert_eq!(
            ErrorClass::Server(ResultCode::KeyNotFoundError).label(),
            "KeyNotFoundError"
        );
        assert_eq!(
            ErrorClass::Server(ResultCode::DeviceOverload).label(),
            "DeviceOverload"
        );
        assert!(matches!(
            ErrorClass::Server(ResultCode::KeyExistsError).label(),
            Cow::Borrowed(_)
        ));
    }

    #[test]
    fn a_client_side_failure_is_never_a_missing_record() {
        // `exists()` and the metrics treat "record not found" as an answer.
        // Only the server can give that answer.
        assert!(!is_key_not_found(&AsError::client_error("not found")));
        assert!(!is_key_not_found(&AsError::invalid_argument("bad key")));
    }

    // ── Python exceptions ───────────────────────────────────────

    #[test]
    fn server_errors_map_to_their_exception_and_wire_code() {
        Python::initialize();
        Python::attach(|py| {
            let err = build_pyerr(
                ErrorClass::Server(ResultCode::KeyNotFoundError),
                "Key not found",
                None,
                false,
            );
            assert!(err.is_instance_of::<RecordNotFound>(py));
            assert_eq!(attr::<i32>(py, &err, "result_code"), 2);
            assert_eq!(attr::<String>(py, &err, "error_type"), "KeyNotFoundError");
            assert!(!attr::<bool>(py, &err, "in_doubt"));
            assert!(err.to_string().contains("AEROSPIKE_ERR (2)"));

            let err = build_pyerr(
                ErrorClass::Server(ResultCode::GenerationError),
                "Generation error",
                None,
                false,
            );
            assert!(err.is_instance_of::<RecordGenerationError>(py));
            assert_eq!(attr::<i32>(py, &err, "result_code"), 3);
        });
    }

    #[test]
    fn security_result_codes_map_to_admin_error() {
        Python::initialize();
        Python::attach(|py| {
            for rc in [
                ResultCode::InvalidUser,
                ResultCode::NotAuthenticated,
                ResultCode::RoleViolation,
                ResultCode::InvalidPassword,
                ResultCode::ExpiredSession,
                ResultCode::QuotaExceeded,
                ResultCode::NotAllowlisted,
            ] {
                let err = build_pyerr(ErrorClass::Server(rc), "denied", None, false);
                assert!(err.is_instance_of::<AdminError>(py), "{rc:?}");
                assert_eq!(
                    attr::<i32>(py, &err, "result_code"),
                    result_code_to_int(&rc)
                );
            }
        });
    }

    /// Server and client timeouts are the same exception type, and are told
    /// apart by `result_code` (9 versus -1) and `error_type`.
    #[test]
    fn timeouts_share_a_type_and_differ_in_code_and_label() {
        Python::initialize();
        Python::attach(|py| {
            let server = build_pyerr(
                ErrorClass::Server(ResultCode::Timeout),
                "Timeout",
                None,
                false,
            );
            assert!(server.is_instance_of::<AerospikeTimeoutError>(py));
            assert_eq!(attr::<i32>(py, &server, "result_code"), 9);
            assert_eq!(attr::<String>(py, &server, "error_type"), "ServerTimeout");

            let query = build_pyerr(
                ErrorClass::Server(ResultCode::QueryTimeout),
                "Query timeout",
                None,
                false,
            );
            assert!(query.is_instance_of::<AerospikeTimeoutError>(py));
            assert_eq!(attr::<i32>(py, &query, "result_code"), 212);

            let client = build_pyerr(ErrorClass::ClientTimeout, "deadline elapsed", None, true);
            assert!(client.is_instance_of::<AerospikeTimeoutError>(py));
            assert_eq!(
                attr::<i32>(py, &client, "result_code"),
                CLIENT_SIDE_RESULT_CODE
            );
            assert_eq!(attr::<String>(py, &client, "error_type"), "Timeout");
            assert!(attr::<bool>(py, &client, "in_doubt"));
            assert!(client.to_string().ends_with("[in_doubt]"));

            let exhausted = build_pyerr(ErrorClass::RetriesExhausted, "after 3 tries", None, false);
            assert!(exhausted.is_instance_of::<AerospikeTimeoutError>(py));
            assert_eq!(
                attr::<i32>(py, &exhausted, "result_code"),
                CLIENT_SIDE_RESULT_CODE
            );
            assert_eq!(
                attr::<String>(py, &exhausted, "error_type"),
                "MaxRetriesExceeded"
            );
        });
    }

    #[test]
    fn node_and_connection_failures_are_cluster_errors() {
        Python::initialize();
        Python::attach(|py| {
            for class in [
                ErrorClass::Connection,
                ErrorClass::NoMoreConnections,
                ErrorClass::MaxErrorRate,
                ErrorClass::InvalidNode,
            ] {
                let err = build_pyerr(class, "detail", Some("BB9: 10.0.0.1:3000"), false);
                assert!(err.is_instance_of::<ClusterError>(py), "{class:?}");
                assert_eq!(
                    attr::<i32>(py, &err, "result_code"),
                    CLIENT_SIDE_RESULT_CODE
                );
                assert_eq!(attr::<String>(py, &err, "error_type"), class.label());
            }
            let breaker = build_pyerr(
                ErrorClass::MaxErrorRate,
                "x",
                Some("BB9: 10.0.0.1:3000"),
                false,
            );
            assert!(breaker.to_string().contains("BB9: 10.0.0.1:3000"));
        });
    }

    #[test]
    fn remaining_classes_keep_the_existing_hierarchy() {
        Python::initialize();
        Python::attach(|py| {
            let invalid = build_pyerr(ErrorClass::InvalidArgument, "bad", None, false);
            assert!(invalid.is_instance_of::<InvalidArgError>(py));
            assert_eq!(
                invalid.to_string(),
                "InvalidArgError: Invalid argument: bad"
            );

            let udf = build_pyerr(ErrorClass::Udf, "boom", None, false);
            assert!(udf.is_instance_of::<UDFError>(py));
            assert_eq!(
                attr::<i32>(py, &udf, "result_code"),
                100,
                "the server answered UDF_BAD_RESPONSE; that is not a client-side failure"
            );
            assert_eq!(attr::<String>(py, &udf, "error_type"), "UdfBadResponse");

            for class in [
                ErrorClass::StreamTerminated,
                ErrorClass::BadResponse,
                ErrorClass::Client,
                ErrorClass::Unknown,
            ] {
                let err = build_pyerr(class, "detail", None, false);
                assert!(err.is_instance_of::<ClientError>(py), "{class:?}");
                assert!(!err.is_instance_of::<ClusterError>(py), "{class:?}");
            }
        });
    }

    #[test]
    fn io_error_converts_to_a_cluster_error() {
        Python::initialize();
        Python::attach(|py| {
            let io = std::io::Error::new(std::io::ErrorKind::ConnectionReset, "reset by peer");
            let err = as_to_pyerr(io.into());
            assert!(err.is_instance_of::<ClusterError>(py));
            assert_eq!(attr::<String>(py, &err, "error_type"), "Connection");
            assert!(err.to_string().contains("reset by peer"));
        });
    }

    #[test]
    fn delete_not_found_carries_record_not_found_code() {
        Python::initialize();
        Python::attach(|py| {
            let err = record_not_found_for_delete(false);
            assert!(err.is_instance_of::<RecordNotFound>(py));
            assert_eq!(attr::<i32>(py, &err, "result_code"), 2);
            assert!(!attr::<bool>(py, &err, "in_doubt"));
            assert_eq!(
                err.to_string(),
                "RecordNotFound: AEROSPIKE_ERR (2): Record not found"
            );
        });
    }
}
