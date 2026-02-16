"""Aerospike Python Client - PyO3 + Rust binding.

Drop-in compatible replacement for the aerospike-client-python package.
"""

import logging
from typing import Any

from aerospike_py._aerospike import Client as _NativeClient
from aerospike_py._aerospike import AsyncClient as _NativeAsyncClient
from aerospike_py._aerospike import Query, Scan  # noqa: F401
from aerospike_py._aerospike import BatchRecord, BatchRecords  # noqa: F401
from aerospike_py._aerospike import get_metrics_text as _get_metrics_text
from aerospike_py._aerospike import init_tracing as _init_tracing
from aerospike_py._aerospike import shutdown_tracing as _shutdown_tracing

# Import all exceptions from native module
from aerospike_py._aerospike import (  # noqa: F401
    AerospikeError,
    ClientError,
    ClusterError,
    InvalidArgError,
    RecordError,
    ServerError,
    AerospikeTimeoutError,
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

# Re-export exception subclasses from exception module for backward compat
from aerospike_py import exception  # noqa: F401
from aerospike_py import predicates  # noqa: F401
from aerospike_py.numpy_batch import NumpyBatchRecords  # noqa: F401
from aerospike_py import list_operations  # noqa: F401
from aerospike_py import map_operations  # noqa: F401
from aerospike_py import exp  # noqa: F401

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _get_version

    __version__ = _get_version("aerospike-py")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development

logger = logging.getLogger("aerospike_py")
logger.addHandler(logging.NullHandler())


class Client(_NativeClient):
    """Aerospike client wrapper that supports method chaining on connect()."""

    def connect(self, username: str | None = None, password: str | None = None) -> "Client":
        """Connect to the Aerospike cluster.

        Returns ``self`` for method chaining.

        Args:
            username: Optional username for authentication.
            password: Optional password for authentication.

        Returns:
            The connected client instance.

        Raises:
            ClusterError: Failed to connect to any cluster node.

        Example:
            ```python
            client = aerospike_py.client(config).connect()

            # With authentication
            client = aerospike_py.client(config).connect("admin", "admin")
            ```
        """
        logger.info("Connecting to Aerospike cluster")
        super().connect(username, password)
        return self

    def batch_read(self, keys, bins=None, policy=None, _dtype=None):
        """Read multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            bins: Optional list of bin names to read. ``None`` reads all bins;
                an empty list performs an existence check only.
            policy: Optional batch policy dict.
            _dtype: Optional NumPy dtype. When provided, returns
                ``NumpyBatchRecords`` instead of ``BatchRecords``.

        Returns:
            ``BatchRecords`` (or ``NumpyBatchRecords`` when ``_dtype`` is set).

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            batch = client.batch_read(keys, bins=["name", "age"])
            for br in batch.batch_records:
                if br.record:
                    key, meta, bins = br.record
                    print(bins)
            ```
        """
        return super().batch_read(keys, bins, policy, _dtype)

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        logger.debug("Closing client connection")
        self.close()
        return False


class AsyncClient:
    """Aerospike async client wrapper with numpy batch_read support.

    Delegates to _NativeAsyncClient (PyO3 type that cannot be subclassed).
    """

    def __init__(self, config: dict):
        self._inner = _NativeAsyncClient(config)

    # -- Delegate all native methods via __getattr__ --
    def __getattr__(self, name: str) -> Any:
        try:
            inner = object.__getattribute__(self, "_inner")
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' (client may not be fully initialized)"
            ) from None
        try:
            return getattr(inner, name)
        except AttributeError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'") from None

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        await self.close()
        return False

    async def connect(self, username: str | None = None, password: str | None = None) -> None:
        """Connect to the Aerospike cluster.

        Args:
            username: Optional username for authentication.
            password: Optional password for authentication.

        Raises:
            ClusterError: Failed to connect to any cluster node.

        Example:
            ```python
            await client.connect()
            await client.connect("admin", "admin")
            ```
        """
        logger.info("Async client connecting")
        return await self._inner.connect(username, password)

    async def close(self) -> None:
        """Close the connection to the cluster.

        Example:
            ```python
            await client.close()
            ```
        """
        logger.debug("Async client closing")
        return await self._inner.close()

    async def batch_read(
        self, keys: list, bins: list[str] | None = None, policy: dict[str, Any] | None = None, _dtype: Any = None
    ) -> Any:
        """Read multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            bins: Optional list of bin names to read. ``None`` reads all bins;
                an empty list performs an existence check only.
            policy: Optional batch policy dict.
            _dtype: Optional NumPy dtype. When provided, returns
                ``NumpyBatchRecords`` instead of ``BatchRecords``.

        Returns:
            ``BatchRecords`` (or ``NumpyBatchRecords`` when ``_dtype`` is set).

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            batch = await client.batch_read(keys, bins=["name", "age"])
            for br in batch.batch_records:
                if br.record:
                    key, meta, bins = br.record
                    print(bins)
            ```
        """
        return await self._inner.batch_read(keys, bins, policy, _dtype)


def set_log_level(level: int) -> None:
    """Set the aerospike_py log level.

    Accepts ``LOG_LEVEL_*`` constants. Controls both Rust-internal
    and Python-side logging.

    Args:
        level: One of ``LOG_LEVEL_OFF`` (-1), ``LOG_LEVEL_ERROR`` (0),
            ``LOG_LEVEL_WARN`` (1), ``LOG_LEVEL_INFO`` (2),
            ``LOG_LEVEL_DEBUG`` (3), ``LOG_LEVEL_TRACE`` (4).

    Example:
        ```python
        import aerospike_py

        aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
        ```
    """
    _LEVEL_MAP = {
        -1: logging.CRITICAL + 1,  # OFF
        0: logging.ERROR,
        1: logging.WARNING,
        2: logging.INFO,
        3: logging.DEBUG,
        4: 5,  # TRACE
    }
    py_level = _LEVEL_MAP.get(level, level)
    logging.getLogger("aerospike_py").setLevel(py_level)
    logging.getLogger("_aerospike").setLevel(py_level)
    logging.getLogger("aerospike_core").setLevel(py_level)
    logging.getLogger("aerospike").setLevel(py_level)


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


def get_metrics() -> str:
    """Return collected metrics in Prometheus text format."""
    return _get_metrics_text()


_metrics_server = None
_metrics_server_thread = None


def start_metrics_server(port: int = 9464) -> None:
    """Start a background HTTP server serving /metrics for Prometheus scraping."""
    global _metrics_server, _metrics_server_thread
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/metrics":
                body = _get_metrics_text().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    new_server = HTTPServer(("", port), _MetricsHandler)

    if _metrics_server is not None:
        _metrics_server.shutdown()

    _metrics_server = new_server
    _metrics_server_thread = threading.Thread(target=_metrics_server.serve_forever, daemon=True)
    _metrics_server_thread.start()


def stop_metrics_server() -> None:
    """Stop the background metrics HTTP server."""
    global _metrics_server, _metrics_server_thread
    if _metrics_server is not None:
        try:
            _metrics_server.shutdown()
        finally:
            _metrics_server = None
            _metrics_server_thread = None


def init_tracing() -> None:
    """Initialize OpenTelemetry tracing.

    Reads standard OTEL_* environment variables for configuration.
    Key variables:
        OTEL_EXPORTER_OTLP_ENDPOINT  - gRPC endpoint (default: http://localhost:4317)
        OTEL_SERVICE_NAME            - service name (default: aerospike-py)
        OTEL_SDK_DISABLED=true       - disable tracing entirely
        OTEL_TRACES_EXPORTER=none    - disable trace export
    """
    _init_tracing()


def shutdown_tracing() -> None:
    """Shut down the tracer provider, flushing pending spans.

    Call before process exit to ensure all spans are exported.
    """
    _shutdown_tracing()


__all__ = [
    # Core classes and factory
    "Client",
    "AsyncClient",
    "Query",
    "Scan",
    "BatchRecord",
    "BatchRecords",
    "NumpyBatchRecords",
    "client",
    "set_log_level",
    "get_metrics",
    "start_metrics_server",
    "stop_metrics_server",
    "init_tracing",
    "shutdown_tracing",
    "__version__",
    # Submodules
    "exception",
    "predicates",
    "list_operations",
    "map_operations",
    "exp",
    # Exception classes
    "AerospikeError",
    "ClientError",
    "ClusterError",
    "InvalidArgError",
    "RecordError",
    "ServerError",
    "AerospikeTimeoutError",
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
