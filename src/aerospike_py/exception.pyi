"""Type stubs for aerospike_py.exception module.

Exception hierarchy::

    AerospikeError (base)
      +-- ClientError              (connection, configuration, internal)
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

Deprecated aliases (emit ``DeprecationWarning`` on access):
    - ``TimeoutError`` -- use ``AerospikeTimeoutError`` instead.
    - ``IndexError`` -- use ``AerospikeIndexError`` instead.
"""

class AerospikeError(Exception):
    """Base exception for all Aerospike errors."""

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

class TimeoutError(AerospikeError):
    """Deprecated: use ``AerospikeTimeoutError`` instead.

    Accessing this name emits a ``DeprecationWarning``.
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

class IndexError(ServerError):
    """Deprecated: use ``AerospikeIndexError`` instead.

    Accessing this name emits a ``DeprecationWarning``.
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
