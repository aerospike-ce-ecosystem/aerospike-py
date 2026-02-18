"""Aerospike exception hierarchy.

Re-exports all exception classes from the native Rust module.
This module provides the full exception hierarchy for compatibility
with the existing aerospike-client-python.
"""

import warnings

from aerospike_py._aerospike import (
    # Base exceptions
    AerospikeError,
    ClientError,
    ClusterError,
    InvalidArgError,
    RecordError,
    ServerError,
    AerospikeTimeoutError,
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
    IndexNotFound,
    IndexFoundError,
    # Query exceptions
    QueryError,
    QueryAbortedError,
    # Admin / UDF exceptions
    AdminError,
    UDFError,
)

from aerospike_py._aerospike import (
    TimeoutError as _TimeoutError,  # deprecated alias for AerospikeTimeoutError
    IndexError as _IndexError,  # deprecated alias for AerospikeIndexError
)

_DEPRECATED_ALIASES: dict[str, tuple[type, str]] = {
    "TimeoutError": (_TimeoutError, "AerospikeTimeoutError"),
    "IndexError": (_IndexError, "AerospikeIndexError"),
}


def __getattr__(name: str):
    if name in _DEPRECATED_ALIASES:
        cls, replacement = _DEPRECATED_ALIASES[name]
        warnings.warn(
            f"aerospike_py.exception.{name} is deprecated, use {replacement} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls
    raise AttributeError(f"module 'aerospike_py.exception' has no attribute {name!r}")


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
