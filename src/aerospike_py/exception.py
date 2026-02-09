"""Aerospike exception hierarchy.

Re-exports all exception classes from the native Rust module.
This module provides the full exception hierarchy for compatibility
with the existing aerospike-client-python.
"""

from aerospike_py._aerospike import (
    # Base exceptions
    AerospikeError,
    ClientError,
    ClusterError,
    InvalidArgError,
    RecordError,
    ServerError,
    AerospikeTimeoutError,
    TimeoutError,  # deprecated alias for AerospikeTimeoutError
    # Record-level exceptions
    RecordNotFound,
    RecordExistsError,
    RecordGenerationError,
    RecordTooBig,
    BinNameError,
    BinExistsError,
    BinNotFound,
    BinTypeError,
    FilteredOut,
    # Index exceptions
    AerospikeIndexError,
    IndexError,  # deprecated alias for AerospikeIndexError
    IndexNotFound,
    IndexFoundError,
    # Query exceptions
    QueryError,
    QueryAbortedError,
    # Admin / UDF exceptions
    AdminError,
    UDFError,
)

__all__ = [
    "AerospikeError",
    "ClientError",
    "ServerError",
    "RecordError",
    "ClusterError",
    "AerospikeTimeoutError",
    "TimeoutError",  # deprecated alias
    "InvalidArgError",
    "RecordNotFound",
    "RecordExistsError",
    "RecordGenerationError",
    "RecordTooBig",
    "BinNameError",
    "BinExistsError",
    "BinNotFound",
    "BinTypeError",
    "FilteredOut",
    "AerospikeIndexError",
    "IndexError",  # deprecated alias
    "IndexNotFound",
    "IndexFoundError",
    "QueryError",
    "QueryAbortedError",
    "AdminError",
    "UDFError",
]
