"""Type stubs for aerospike_py.exception module.

Exception hierarchy::

    AerospikeError (base)
      +-- ClientError              (connection, configuration, internal)
      |     +-- BackpressureError  (concurrent operations limit exceeded)
      |     +-- RustPanicError     (native Rust panic; process survived)
      +-- ServerError              (server-side errors)
      |     +-- AerospikeIndexError
      |     |     +-- IndexNotFound
      |     |     +-- IndexFoundError
      |     +-- QueryError
      |     |     +-- QueryAbortedError
      |     +-- AdminError
      |     +-- UDFError
      +-- RecordError              (record-level errors)
      |     +-- RecordNotFound
      |     +-- RecordExistsError
      |     +-- RecordGenerationError
      |     +-- RecordTooBig
      |     +-- BinNameError
      |     +-- BinExistsError
      |     +-- BinNotFound
      |     +-- BinTypeError
      |     +-- FilteredOut
      +-- ClusterError             (cluster connectivity / node errors)
      +-- AerospikeTimeoutError    (operation timed out)
      +-- InvalidArgError          (invalid argument)

Every exception in this hierarchy carries a structured integer ``result_code``
attribute (ADR-0027) so callers can classify errors by a stable server code
instead of matching on the message string::

    try:
        client.get(key)
    except aerospike_py.AerospikeError as exc:
        if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND:
            ...

Server errors expose the real Aerospike wire code (e.g. ``2`` for
record-not-found, ``5`` for record-exists, ``22`` for forbidden), matching the
``AEROSPIKE_ERR_*`` constants re-exported from the top-level package. Purely
client-side errors that never received a server response (connection failures,
client timeouts, invalid arguments) expose the sentinel ``-1``.

The ``-1`` cases are told apart by ``error_type``, and a write that failed
says whether it may have been applied anyway::

    try:
        client.put(key, bins)
    except aerospike_py.AerospikeError as exc:
        if exc.error_type == "Timeout" and exc.in_doubt:
            ...  # the write may be in; read before writing again

A batch call that fails as a whole keeps the rows it did collect::

    try:
        client.batch_write(records)
    except aerospike_py.AerospikeError as exc:
        if exc.partial_result is not None:
            done = [br.key for br in exc.partial_result.batch_records if br.result == 0]

Deprecated aliases (emit ``DeprecationWarning`` on access; **removed in v1.0.0**):
    - ``TimeoutError`` -- use ``AerospikeTimeoutError`` instead.
    - ``IndexError`` -- use ``AerospikeIndexError`` instead.
"""

from aerospike_py.types import BatchWriteResult

class AerospikeError(Exception):
    """Base exception for all Aerospike errors.

    Attributes:
        result_code: Structured Aerospike server result code (ADR-0027). The
            real wire code for server errors (e.g. ``2`` = record-not-found);
            ``-1`` for client-side errors that never received a server response.
        error_type: What kind of failure this is, by the same name the
            Prometheus ``error_type`` label and the OpenTelemetry
            ``error.type`` attribute carry. A server result code is named
            after the code (``"KeyNotFoundError"``, ``"KeyExistsError"``,
            ``"GenerationError"``, ``"FilteredOut"``, ``"DeviceOverload"``,
            ...), with ``"ServerTimeout"`` for a timeout the server reported.
            Client-side failures are ``"Timeout"`` (the client's own
            deadline), ``"MaxRetriesExceeded"``, ``"Connection"``,
            ``"NoMoreConnections"``, ``"MaxErrorRate"``, ``"InvalidNode"``,
            ``"InvalidArgument"``, ``"UdfBadResponse"``,
            ``"StreamTerminated"``, ``"BadResponse"``, ``"Backpressure"``,
            ``"RustPanic"`` and ``"Client"``.
        in_doubt: ``True`` when a write failed after it was sent, so the
            server may have applied it. Always ``False`` for reads.
        partial_result: The per-record rows of a batch call that failed as a
            whole (a ``BatchWriteResult``), ``None`` for every other failure.
            One entry per requested record, in request order: the records
            other nodes answered keep their results, the rest say why they
            have none (``result``, ``error_type``, ``in_doubt``).
    """

    result_code: int
    error_type: str
    in_doubt: bool
    partial_result: BatchWriteResult | None

class ClientError(AerospikeError):
    """Client-side error such as connection failure, misconfiguration, or internal error."""

class ServerError(AerospikeError):
    """Server-side error returned by the Aerospike cluster."""

class RecordError(AerospikeError):
    """Record-level error (not found, already exists, generation mismatch, etc.)."""

class ClusterError(AerospikeError):
    """Cluster connectivity or node-level error."""

class AerospikeTimeoutError(AerospikeError):
    """Raised when an operation exceeds its timeout threshold."""

class TimeoutError(AerospikeTimeoutError):
    """Deprecated: use ``AerospikeTimeoutError`` instead.

    Accessing this name emits a ``DeprecationWarning``. Scheduled for removal in
    v1.0.0.
    """

class BackpressureError(ClientError):
    """Raised when the maximum number of concurrent operations is exceeded.

    Only raised when ``max_concurrent_operations`` is configured in the client
    config and the ``operation_queue_timeout_ms`` deadline expires while waiting
    for a free slot.
    """

class RustPanicError(ClientError):
    """Raised when a native Rust panic was caught at a client API boundary.

    The Python process survived; the operation did not complete.

    Up to 0.14.x the usual cause was a record carrying a language-specific
    blob particle type (``PYTHON_BLOB``, ``JAVA_BLOB``, ...), see issue #280.
    Such a bin is now returned as ``bytes`` holding its raw payload, so this
    exception means an actual defect: please report it.
    """

class InvalidArgError(AerospikeError):
    """Raised when an invalid argument is passed to a client operation."""

class RecordNotFound(RecordError):
    """Raised when the requested record does not exist (result code 2)."""

class RecordExistsError(RecordError):
    """Raised on ``CREATE_ONLY`` write when the record already exists (result code 5)."""

class RecordGenerationError(RecordError):
    """Raised when the record generation does not match the expected value (result code 3)."""

class RecordTooBig(RecordError):
    """Raised when the record size exceeds the server limit (result code 13)."""

class BinNameError(RecordError):
    """Raised when a bin name exceeds the maximum allowed length (result code 21)."""

class BinExistsError(RecordError):
    """Raised when a bin already exists and the operation forbids it (result code 6)."""

class BinNotFound(RecordError):
    """Raised when the specified bin does not exist on the record (result code 17)."""

class BinTypeError(RecordError):
    """Raised when the bin data type is incompatible with the operation (result code 12)."""

class FilteredOut(RecordError):
    """Raised when a record is excluded by an expression filter (result code 27)."""

class AerospikeIndexError(ServerError):
    """Base exception for secondary index errors."""

class IndexError(AerospikeIndexError):
    """Deprecated: use ``AerospikeIndexError`` instead.

    Accessing this name emits a ``DeprecationWarning``. Scheduled for removal in
    v1.0.0.
    """

class IndexNotFound(AerospikeIndexError):
    """Raised when the specified secondary index does not exist (result code 201)."""

class IndexFoundError(AerospikeIndexError):
    """Raised when creating a secondary index that already exists (result code 200)."""

class QueryError(ServerError):
    """Raised when query execution fails on the server."""

class QueryAbortedError(QueryError):
    """Raised when a query is aborted by the server (result code 210)."""

class AdminError(ServerError):
    """Raised on admin or security operation failures (authentication, roles, etc.)."""

class UDFError(ServerError):
    """Raised when a User-Defined Function (UDF) execution fails on the server."""
