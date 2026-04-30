"""aerospike-py: High-performance Aerospike client (Rust/PyO3).

Claude Code Plugin::

    claude plugin marketplace add aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins
    claude plugin install aerospike-ce-ecosystem
"""

import logging

from aerospike_py.types import BatchRecord, BatchRecords, BatchWriteResult, UserKey, AerospikeRecord  # noqa: F401

# Import all exceptions from native module
from aerospike_py._aerospike import (  # noqa: F401
    PartitionFilter,
    partition_filter_all,
    partition_filter_by_id,
    partition_filter_by_range,
)

from aerospike_py._aerospike import (  # noqa: F401
    AerospikeError,
    ClientError,
    ClusterError,
    InvalidArgError,
    RecordError,
    ServerError,
    AerospikeTimeoutError,
    BackpressureError,
    RustPanicError,
    TimeoutError,  # deprecated alias for AerospikeTimeoutError
    RecordNotFound,
    RecordExistsError,
    RecordGenerationError,
    RecordTooBig,
    BinNameError,
    BinExistsError,
    BinNotFound,
    BinTypeError,
    FilteredOut,
    AerospikeIndexError,
    IndexError,  # deprecated alias for AerospikeIndexError
    IndexNotFound,
    IndexFoundError,
    QueryError,
    QueryAbortedError,
    AdminError,
    UDFError,
)

# Import all constants from native module
from aerospike_py._aerospike import (  # noqa: F401
    # Policy Key
    POLICY_KEY_DIGEST,
    POLICY_KEY_SEND,
    # Policy Exists
    POLICY_EXISTS_IGNORE,
    POLICY_EXISTS_UPDATE,
    POLICY_EXISTS_UPDATE_ONLY,
    POLICY_EXISTS_REPLACE,
    POLICY_EXISTS_REPLACE_ONLY,
    POLICY_EXISTS_CREATE_ONLY,
    # Policy Gen
    POLICY_GEN_IGNORE,
    POLICY_GEN_EQ,
    POLICY_GEN_GT,
    # Policy Replica
    POLICY_REPLICA_MASTER,
    POLICY_REPLICA_SEQUENCE,
    POLICY_REPLICA_PREFER_RACK,
    # Policy Commit Level
    POLICY_COMMIT_LEVEL_ALL,
    POLICY_COMMIT_LEVEL_MASTER,
    # Policy Read Mode AP
    POLICY_READ_MODE_AP_ONE,
    POLICY_READ_MODE_AP_ALL,
    # Read Touch TTL Percent (server v8+)
    READ_TOUCH_TTL_PERCENT_SERVER_DEFAULT,
    READ_TOUCH_TTL_PERCENT_DONT_RESET,
    # Query Duration
    QUERY_DURATION_LONG,
    QUERY_DURATION_SHORT,
    QUERY_DURATION_LONG_RELAX_AP,
    # TTL Constants
    TTL_NAMESPACE_DEFAULT,
    TTL_NEVER_EXPIRE,
    TTL_DONT_UPDATE,
    TTL_CLIENT_DEFAULT,
    # Auth Mode
    AUTH_INTERNAL,
    AUTH_EXTERNAL,
    AUTH_PKI,
    # Operator Constants
    OPERATOR_READ,
    OPERATOR_WRITE,
    OPERATOR_INCR,
    OPERATOR_APPEND,
    OPERATOR_PREPEND,
    OPERATOR_TOUCH,
    OPERATOR_DELETE,
    # Index Type
    INDEX_NUMERIC,
    INDEX_STRING,
    INDEX_BLOB,
    INDEX_GEO2DSPHERE,
    # Index Collection Type
    INDEX_TYPE_DEFAULT,
    INDEX_TYPE_LIST,
    INDEX_TYPE_MAPKEYS,
    INDEX_TYPE_MAPVALUES,
    # Log Level
    LOG_LEVEL_OFF,
    LOG_LEVEL_ERROR,
    LOG_LEVEL_WARN,
    LOG_LEVEL_INFO,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_TRACE,
    # Serializer
    SERIALIZER_NONE,
    SERIALIZER_PYTHON,
    SERIALIZER_USER,
    # List Return Type
    LIST_RETURN_NONE,
    LIST_RETURN_INDEX,
    LIST_RETURN_REVERSE_INDEX,
    LIST_RETURN_RANK,
    LIST_RETURN_REVERSE_RANK,
    LIST_RETURN_COUNT,
    LIST_RETURN_VALUE,
    LIST_RETURN_EXISTS,
    # List Order
    LIST_UNORDERED,
    LIST_ORDERED,
    # List Sort Flags
    LIST_SORT_DEFAULT,
    LIST_SORT_DROP_DUPLICATES,
    # List Write Flags
    LIST_WRITE_DEFAULT,
    LIST_WRITE_ADD_UNIQUE,
    LIST_WRITE_INSERT_BOUNDED,
    LIST_WRITE_NO_FAIL,
    LIST_WRITE_PARTIAL,
    # Map Return Type
    MAP_RETURN_NONE,
    MAP_RETURN_INDEX,
    MAP_RETURN_REVERSE_INDEX,
    MAP_RETURN_RANK,
    MAP_RETURN_REVERSE_RANK,
    MAP_RETURN_COUNT,
    MAP_RETURN_KEY,
    MAP_RETURN_VALUE,
    MAP_RETURN_KEY_VALUE,
    MAP_RETURN_EXISTS,
    # Map Order
    MAP_UNORDERED,
    MAP_KEY_ORDERED,
    MAP_KEY_VALUE_ORDERED,
    # Map Write Flags
    MAP_WRITE_FLAGS_DEFAULT,
    MAP_WRITE_FLAGS_CREATE_ONLY,
    MAP_WRITE_FLAGS_UPDATE_ONLY,
    MAP_WRITE_FLAGS_NO_FAIL,
    MAP_WRITE_FLAGS_PARTIAL,
    MAP_UPDATE,
    MAP_UPDATE_ONLY,
    MAP_CREATE_ONLY,
    # Bit Write Flags
    BIT_WRITE_DEFAULT,
    BIT_WRITE_CREATE_ONLY,
    BIT_WRITE_UPDATE_ONLY,
    BIT_WRITE_NO_FAIL,
    BIT_WRITE_PARTIAL,
    # Bit Resize Flags
    BIT_RESIZE_DEFAULT,
    BIT_RESIZE_FROM_FRONT,
    BIT_RESIZE_GROW_ONLY,
    BIT_RESIZE_SHRINK_ONLY,
    # Bit Overflow Action
    BIT_OVERFLOW_FAIL,
    BIT_OVERFLOW_SATURATE,
    BIT_OVERFLOW_WRAP,
    # HLL Write Flags
    HLL_WRITE_DEFAULT,
    HLL_WRITE_CREATE_ONLY,
    HLL_WRITE_UPDATE_ONLY,
    HLL_WRITE_NO_FAIL,
    HLL_WRITE_ALLOW_FOLD,
    # Privilege codes
    PRIV_READ,
    PRIV_WRITE,
    PRIV_READ_WRITE,
    PRIV_READ_WRITE_UDF,
    PRIV_SYS_ADMIN,
    PRIV_USER_ADMIN,
    PRIV_DATA_ADMIN,
    PRIV_UDF_ADMIN,
    PRIV_SINDEX_ADMIN,
    PRIV_TRUNCATE,
    # Status codes
    AEROSPIKE_OK,
    AEROSPIKE_ERR_SERVER,
    AEROSPIKE_ERR_RECORD_NOT_FOUND,
    AEROSPIKE_ERR_RECORD_GENERATION,
    AEROSPIKE_ERR_PARAM,
    AEROSPIKE_ERR_RECORD_EXISTS,
    AEROSPIKE_ERR_BIN_EXISTS,
    AEROSPIKE_ERR_CLUSTER_KEY_MISMATCH,
    AEROSPIKE_ERR_SERVER_MEM,
    AEROSPIKE_ERR_TIMEOUT,
    AEROSPIKE_ERR_ALWAYS_FORBIDDEN,
    AEROSPIKE_ERR_PARTITION_UNAVAILABLE,
    AEROSPIKE_ERR_BIN_TYPE,
    AEROSPIKE_ERR_RECORD_TOO_BIG,
    AEROSPIKE_ERR_KEY_BUSY,
    AEROSPIKE_ERR_SCAN_ABORT,
    AEROSPIKE_ERR_UNSUPPORTED_FEATURE,
    AEROSPIKE_ERR_BIN_NOT_FOUND,
    AEROSPIKE_ERR_DEVICE_OVERLOAD,
    AEROSPIKE_ERR_KEY_MISMATCH,
    AEROSPIKE_ERR_INVALID_NAMESPACE,
    AEROSPIKE_ERR_BIN_NAME,
    AEROSPIKE_ERR_FAIL_FORBIDDEN,
    AEROSPIKE_ERR_ELEMENT_NOT_FOUND,
    AEROSPIKE_ERR_ELEMENT_EXISTS,
    AEROSPIKE_ERR_ENTERPRISE_ONLY,
    AEROSPIKE_ERR_OP_NOT_APPLICABLE,
    AEROSPIKE_ERR_FILTERED_OUT,
    AEROSPIKE_ERR_LOST_CONFLICT,
    AEROSPIKE_QUERY_END,
    AEROSPIKE_SECURITY_NOT_SUPPORTED,
    AEROSPIKE_SECURITY_NOT_ENABLED,
    AEROSPIKE_ERR_INVALID_USER,
    AEROSPIKE_ERR_NOT_AUTHENTICATED,
    AEROSPIKE_ERR_ROLE_VIOLATION,
    AEROSPIKE_ERR_UDF,
    AEROSPIKE_ERR_BATCH_DISABLED,
    AEROSPIKE_ERR_INDEX_FOUND,
    AEROSPIKE_ERR_INDEX_NOT_FOUND,
    AEROSPIKE_ERR_QUERY_ABORTED,
    AEROSPIKE_ERR_CLIENT,
    AEROSPIKE_ERR_CONNECTION,
    AEROSPIKE_ERR_CLUSTER,
    AEROSPIKE_ERR_INVALID_HOST,
    AEROSPIKE_ERR_NO_MORE_CONNECTIONS,
)

# Re-export submodules for backward compat
from aerospike_py import exception  # noqa: F401
from aerospike_py import predicates  # noqa: F401
from aerospike_py.numpy_batch import NumpyBatchRecords  # noqa: F401
from aerospike_py import list_operations  # noqa: F401
from aerospike_py import map_operations  # noqa: F401
from aerospike_py import hll_operations  # noqa: F401
from aerospike_py import bit_operations  # noqa: F401
from aerospike_py import exp  # noqa: F401
from aerospike_py.types import (  # noqa: F401
    AerospikeKey,
    RecordMetadata,
    Record,
    ExistsResult,
    InfoNodeResult,
    BinTuple,
    OperateOrderedResult,
    Bins,
    ReadPolicy,
    WritePolicy,
    BatchPolicy,
    BatchReadPolicy,
    BatchDeletePolicy,
    BatchDeleteMeta,
    AdminPolicy,
    QueryPolicy,
    WriteMeta,
    ClientConfig,
    Privilege,
    UserInfo,
    RoleInfo,
)
from aerospike_py._types import HLLPolicy, ListPolicy, MapPolicy, Operation  # noqa: F401

# Client and query classes (re-exported from internal modules)
from aerospike_py._client import Client, Query  # noqa: F401
from aerospike_py._async_client import AsyncClient, AsyncQuery  # noqa: F401

# Observability utilities (re-exported from internal module)
from aerospike_py._observability import (  # noqa: F401
    set_log_level,
    get_metrics,
    dropped_log_count,
    set_metrics_enabled,
    is_metrics_enabled,
    set_internal_stage_metrics_enabled,
    is_internal_stage_metrics_enabled,
    internal_stage_profiling,
    start_metrics_server,
    stop_metrics_server,
    init_tracing,
    shutdown_tracing,
)

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _get_version

    __version__ = _get_version("aerospike-py")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development

logger = logging.getLogger("aerospike_py")
logger.addHandler(logging.NullHandler())


def client(config: dict) -> Client:
    """Create a new Aerospike client instance.

    Args:
        config: Configuration dictionary. Must contain a ``"hosts"`` key
            with a list of ``(host, port)`` tuples.

    Returns:
        A new ``Client`` instance (not yet connected).

    Example:
        ```python
        import aerospike_py

        client = aerospike_py.client({
            "hosts": [("127.0.0.1", 3000)],
        }).connect()
        ```
    """
    return Client(config)


def async_client(config: dict) -> AsyncClient:
    """Create a new async Aerospike client instance.

    Args:
        config: Configuration dictionary. Must contain a ``"hosts"`` key
            with a list of ``(host, port)`` tuples.

    Returns:
        A new ``AsyncClient`` instance (not yet connected).

    Example:
        ```python
        import aerospike_py

        client = aerospike_py.async_client({
            "hosts": [("127.0.0.1", 3000)],
        })
        await client.connect()
        ```
    """
    return AsyncClient(config)


__all__ = [
    # Core classes and factory
    "Client",
    "AsyncClient",
    "Query",
    "AsyncQuery",
    "BatchRecord",
    "BatchRecords",
    "BatchWriteResult",
    "UserKey",
    "AerospikeRecord",
    "NumpyBatchRecords",
    "client",
    "async_client",
    "set_log_level",
    "get_metrics",
    "dropped_log_count",
    "set_metrics_enabled",
    "is_metrics_enabled",
    "set_internal_stage_metrics_enabled",
    "is_internal_stage_metrics_enabled",
    "internal_stage_profiling",
    "start_metrics_server",
    "stop_metrics_server",
    "init_tracing",
    "shutdown_tracing",
    "__version__",
    # Type classes
    "AerospikeKey",
    "RecordMetadata",
    "Record",
    "ExistsResult",
    "InfoNodeResult",
    "BinTuple",
    "OperateOrderedResult",
    "Bins",
    "ReadPolicy",
    "WritePolicy",
    "BatchPolicy",
    "BatchReadPolicy",
    "BatchDeletePolicy",
    "BatchDeleteMeta",
    "AdminPolicy",
    "QueryPolicy",
    "WriteMeta",
    "ClientConfig",
    "Privilege",
    "UserInfo",
    "RoleInfo",
    "ListPolicy",
    "MapPolicy",
    "HLLPolicy",
    "Operation",
    # Submodules
    "exception",
    "predicates",
    "list_operations",
    "map_operations",
    "hll_operations",
    "bit_operations",
    "exp",
    # Exception classes
    "AerospikeError",
    "ClientError",
    "ClusterError",
    "InvalidArgError",
    "RecordError",
    "ServerError",
    "AerospikeTimeoutError",
    "BackpressureError",
    "RustPanicError",
    "TimeoutError",  # deprecated alias
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
    # Policy Key
    "POLICY_KEY_DIGEST",
    "POLICY_KEY_SEND",
    # Policy Exists
    "POLICY_EXISTS_IGNORE",
    "POLICY_EXISTS_UPDATE",
    "POLICY_EXISTS_UPDATE_ONLY",
    "POLICY_EXISTS_REPLACE",
    "POLICY_EXISTS_REPLACE_ONLY",
    "POLICY_EXISTS_CREATE_ONLY",
    # Policy Gen
    "POLICY_GEN_IGNORE",
    "POLICY_GEN_EQ",
    "POLICY_GEN_GT",
    # Policy Replica
    "POLICY_REPLICA_MASTER",
    "POLICY_REPLICA_SEQUENCE",
    "POLICY_REPLICA_PREFER_RACK",
    # Policy Commit Level
    "POLICY_COMMIT_LEVEL_ALL",
    "POLICY_COMMIT_LEVEL_MASTER",
    # Policy Read Mode AP
    "POLICY_READ_MODE_AP_ONE",
    "POLICY_READ_MODE_AP_ALL",
    # Read Touch TTL Percent (server v8+)
    "READ_TOUCH_TTL_PERCENT_SERVER_DEFAULT",
    "READ_TOUCH_TTL_PERCENT_DONT_RESET",
    # Query Duration
    "QUERY_DURATION_LONG",
    "QUERY_DURATION_SHORT",
    "QUERY_DURATION_LONG_RELAX_AP",
    # PartitionFilter helpers
    "PartitionFilter",
    "partition_filter_all",
    "partition_filter_by_id",
    "partition_filter_by_range",
    # TTL Constants
    "TTL_NAMESPACE_DEFAULT",
    "TTL_NEVER_EXPIRE",
    "TTL_DONT_UPDATE",
    "TTL_CLIENT_DEFAULT",
    # Auth Mode
    "AUTH_INTERNAL",
    "AUTH_EXTERNAL",
    "AUTH_PKI",
    # Operator Constants
    "OPERATOR_READ",
    "OPERATOR_WRITE",
    "OPERATOR_INCR",
    "OPERATOR_APPEND",
    "OPERATOR_PREPEND",
    "OPERATOR_TOUCH",
    "OPERATOR_DELETE",
    # Index Type
    "INDEX_NUMERIC",
    "INDEX_STRING",
    "INDEX_BLOB",
    "INDEX_GEO2DSPHERE",
    # Index Collection Type
    "INDEX_TYPE_DEFAULT",
    "INDEX_TYPE_LIST",
    "INDEX_TYPE_MAPKEYS",
    "INDEX_TYPE_MAPVALUES",
    # Log Level
    "LOG_LEVEL_OFF",
    "LOG_LEVEL_ERROR",
    "LOG_LEVEL_WARN",
    "LOG_LEVEL_INFO",
    "LOG_LEVEL_DEBUG",
    "LOG_LEVEL_TRACE",
    # Serializer
    "SERIALIZER_NONE",
    "SERIALIZER_PYTHON",
    "SERIALIZER_USER",
    # List Return Type
    "LIST_RETURN_NONE",
    "LIST_RETURN_INDEX",
    "LIST_RETURN_REVERSE_INDEX",
    "LIST_RETURN_RANK",
    "LIST_RETURN_REVERSE_RANK",
    "LIST_RETURN_COUNT",
    "LIST_RETURN_VALUE",
    "LIST_RETURN_EXISTS",
    # List Order
    "LIST_UNORDERED",
    "LIST_ORDERED",
    # List Sort Flags
    "LIST_SORT_DEFAULT",
    "LIST_SORT_DROP_DUPLICATES",
    # List Write Flags
    "LIST_WRITE_DEFAULT",
    "LIST_WRITE_ADD_UNIQUE",
    "LIST_WRITE_INSERT_BOUNDED",
    "LIST_WRITE_NO_FAIL",
    "LIST_WRITE_PARTIAL",
    # Map Return Type
    "MAP_RETURN_NONE",
    "MAP_RETURN_INDEX",
    "MAP_RETURN_REVERSE_INDEX",
    "MAP_RETURN_RANK",
    "MAP_RETURN_REVERSE_RANK",
    "MAP_RETURN_COUNT",
    "MAP_RETURN_KEY",
    "MAP_RETURN_VALUE",
    "MAP_RETURN_KEY_VALUE",
    "MAP_RETURN_EXISTS",
    # Map Order
    "MAP_UNORDERED",
    "MAP_KEY_ORDERED",
    "MAP_KEY_VALUE_ORDERED",
    # Map Write Flags
    "MAP_WRITE_FLAGS_DEFAULT",
    "MAP_WRITE_FLAGS_CREATE_ONLY",
    "MAP_WRITE_FLAGS_UPDATE_ONLY",
    "MAP_WRITE_FLAGS_NO_FAIL",
    "MAP_WRITE_FLAGS_PARTIAL",
    "MAP_UPDATE",
    "MAP_UPDATE_ONLY",
    "MAP_CREATE_ONLY",
    # Bit Write Flags
    "BIT_WRITE_DEFAULT",
    "BIT_WRITE_CREATE_ONLY",
    "BIT_WRITE_UPDATE_ONLY",
    "BIT_WRITE_NO_FAIL",
    "BIT_WRITE_PARTIAL",
    # Bit Resize Flags
    "BIT_RESIZE_DEFAULT",
    "BIT_RESIZE_FROM_FRONT",
    "BIT_RESIZE_GROW_ONLY",
    "BIT_RESIZE_SHRINK_ONLY",
    # Bit Overflow Action
    "BIT_OVERFLOW_FAIL",
    "BIT_OVERFLOW_SATURATE",
    "BIT_OVERFLOW_WRAP",
    # HLL Write Flags
    "HLL_WRITE_DEFAULT",
    "HLL_WRITE_CREATE_ONLY",
    "HLL_WRITE_UPDATE_ONLY",
    "HLL_WRITE_NO_FAIL",
    "HLL_WRITE_ALLOW_FOLD",
    # Privilege codes
    "PRIV_READ",
    "PRIV_WRITE",
    "PRIV_READ_WRITE",
    "PRIV_READ_WRITE_UDF",
    "PRIV_SYS_ADMIN",
    "PRIV_USER_ADMIN",
    "PRIV_DATA_ADMIN",
    "PRIV_UDF_ADMIN",
    "PRIV_SINDEX_ADMIN",
    "PRIV_TRUNCATE",
    # Status codes
    "AEROSPIKE_OK",
    "AEROSPIKE_ERR_SERVER",
    "AEROSPIKE_ERR_RECORD_NOT_FOUND",
    "AEROSPIKE_ERR_RECORD_GENERATION",
    "AEROSPIKE_ERR_PARAM",
    "AEROSPIKE_ERR_RECORD_EXISTS",
    "AEROSPIKE_ERR_BIN_EXISTS",
    "AEROSPIKE_ERR_CLUSTER_KEY_MISMATCH",
    "AEROSPIKE_ERR_SERVER_MEM",
    "AEROSPIKE_ERR_TIMEOUT",
    "AEROSPIKE_ERR_ALWAYS_FORBIDDEN",
    "AEROSPIKE_ERR_PARTITION_UNAVAILABLE",
    "AEROSPIKE_ERR_BIN_TYPE",
    "AEROSPIKE_ERR_RECORD_TOO_BIG",
    "AEROSPIKE_ERR_KEY_BUSY",
    "AEROSPIKE_ERR_SCAN_ABORT",
    "AEROSPIKE_ERR_UNSUPPORTED_FEATURE",
    "AEROSPIKE_ERR_BIN_NOT_FOUND",
    "AEROSPIKE_ERR_DEVICE_OVERLOAD",
    "AEROSPIKE_ERR_KEY_MISMATCH",
    "AEROSPIKE_ERR_INVALID_NAMESPACE",
    "AEROSPIKE_ERR_BIN_NAME",
    "AEROSPIKE_ERR_FAIL_FORBIDDEN",
    "AEROSPIKE_ERR_ELEMENT_NOT_FOUND",
    "AEROSPIKE_ERR_ELEMENT_EXISTS",
    "AEROSPIKE_ERR_ENTERPRISE_ONLY",
    "AEROSPIKE_ERR_OP_NOT_APPLICABLE",
    "AEROSPIKE_ERR_FILTERED_OUT",
    "AEROSPIKE_ERR_LOST_CONFLICT",
    "AEROSPIKE_QUERY_END",
    "AEROSPIKE_SECURITY_NOT_SUPPORTED",
    "AEROSPIKE_SECURITY_NOT_ENABLED",
    "AEROSPIKE_ERR_INVALID_USER",
    "AEROSPIKE_ERR_NOT_AUTHENTICATED",
    "AEROSPIKE_ERR_ROLE_VIOLATION",
    "AEROSPIKE_ERR_UDF",
    "AEROSPIKE_ERR_BATCH_DISABLED",
    "AEROSPIKE_ERR_INDEX_FOUND",
    "AEROSPIKE_ERR_INDEX_NOT_FOUND",
    "AEROSPIKE_ERR_QUERY_ABORTED",
    "AEROSPIKE_ERR_CLIENT",
    "AEROSPIKE_ERR_CONNECTION",
    "AEROSPIKE_ERR_CLUSTER",
    "AEROSPIKE_ERR_INVALID_HOST",
    "AEROSPIKE_ERR_NO_MORE_CONNECTIONS",
]
