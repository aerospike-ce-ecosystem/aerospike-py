"""Type stubs for the aerospike_py package."""

from typing import Any, Callable, Optional, Union, overload

import numpy as np

from aerospike_py import exception as exception
from aerospike_py import list_operations as list_operations
from aerospike_py import map_operations as map_operations
from aerospike_py import predicates as predicates
from aerospike_py.numpy_batch import NumpyBatchRecords as NumpyBatchRecords

__version__: str

# ── Type aliases ─────────────────────────────────────────────

Key = tuple[str, str, Union[str, int, bytes]]
"""Aerospike key: (namespace, set, primary_key)"""

Metadata = dict[str, Any]
"""Record metadata dict with 'gen' (generation) and 'ttl' keys."""

Bins = dict[str, Any]
"""Record bins dict mapping bin name to value."""

Record = tuple[Optional[Key], Optional[Metadata], Optional[Bins]]
"""Full record tuple: (key, meta, bins)."""

ExistsResult = tuple[Optional[Key], Optional[Metadata]]
"""Exists result tuple: (key, meta) where meta is None if not found."""

class BatchRecord:
    """Single record result from a batch read operation."""

    key: Key
    result: int
    record: Optional[Record]

class BatchRecords:
    """Container for batch read results."""

    batch_records: list[BatchRecord]

PolicyDict = dict[str, Any]
"""Policy dictionary with keys like 'timeout', 'key', 'exists', 'gen', etc."""

OperationDict = dict[str, Any]
"""Operation dict with 'op', 'bin', 'val' keys."""

PrivilegeDict = dict[str, Any]
"""Privilege dict with 'code', optional 'ns', optional 'set' keys."""

# ── Client ───────────────────────────────────────────────────

class Client:
    """Aerospike client supporting sync operations.

    Wraps the native Rust client with Python-friendly API.
    Supports method chaining on ``connect()``.
    """

    def __init__(self, config: dict[str, Any]) -> None: ...
    def __enter__(self) -> "Client": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool: ...

    # -- Connection --
    def connect(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> "Client": ...
    def is_connected(self) -> bool: ...
    def close(self) -> None: ...
    def get_node_names(self) -> list[str]: ...

    # -- CRUD --
    def put(
        self,
        key: Key,
        bins: Bins,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def get(self, key: Key, policy: Optional[PolicyDict] = None) -> Record: ...
    def select(
        self, key: Key, bins: list[str], policy: Optional[PolicyDict] = None
    ) -> Record: ...
    def exists(self, key: Key, policy: Optional[PolicyDict] = None) -> ExistsResult: ...
    def remove(
        self,
        key: Key,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def touch(
        self,
        key: Key,
        val: int = 0,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- String / Numeric --
    def append(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def prepend(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def increment(
        self,
        key: Key,
        bin: str,
        offset: Union[int, float],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def remove_bin(
        self,
        key: Key,
        bin_names: list[str],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- Multi-operation --
    def operate(
        self,
        key: Key,
        ops: list[OperationDict],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> Record: ...
    def operate_ordered(
        self,
        key: Key,
        ops: list[OperationDict],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> tuple[Any, Metadata, list[tuple[str, Any]]]: ...

    # -- Batch --
    @overload
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        _dtype: None = None,
    ) -> BatchRecords: ...
    @overload
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        *,
        _dtype: np.dtype,
    ) -> NumpyBatchRecords: ...
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        _dtype: Optional[np.dtype] = None,
    ) -> Union[BatchRecords, NumpyBatchRecords]: ...
    def batch_operate(
        self,
        keys: list[Key],
        ops: list[OperationDict],
        policy: Optional[PolicyDict] = None,
    ) -> list[Record]: ...
    def batch_remove(
        self, keys: list[Key], policy: Optional[PolicyDict] = None
    ) -> list[Record]: ...

    # -- Query / Scan --
    def query(self, namespace: str, set_name: str) -> "Query": ...
    def scan(self, namespace: str, set_name: str) -> "Scan": ...

    # -- Index --
    def index_integer_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def index_string_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def index_geo2dsphere_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def index_remove(
        self,
        namespace: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- Truncate --
    def truncate(
        self,
        namespace: str,
        set_name: str,
        nanos: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- UDF --
    def udf_put(
        self,
        filename: str,
        udf_type: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def udf_remove(self, module: str, policy: Optional[PolicyDict] = None) -> None: ...
    def apply(
        self,
        key: Key,
        module: str,
        function: str,
        args: Optional[list[Any]] = None,
        policy: Optional[PolicyDict] = None,
    ) -> Any: ...

    # -- Admin: User --
    def admin_create_user(
        self,
        username: str,
        password: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_drop_user(
        self, username: str, policy: Optional[PolicyDict] = None
    ) -> None: ...
    def admin_change_password(
        self,
        username: str,
        password: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_grant_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_revoke_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_query_user_info(
        self, username: str, policy: Optional[PolicyDict] = None
    ) -> dict[str, Any]: ...
    def admin_query_users_info(
        self, policy: Optional[PolicyDict] = None
    ) -> list[dict[str, Any]]: ...

    # -- Admin: Role --
    def admin_create_role(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
        whitelist: Optional[list[str]] = None,
        read_quota: int = 0,
        write_quota: int = 0,
    ) -> None: ...
    def admin_drop_role(
        self, role: str, policy: Optional[PolicyDict] = None
    ) -> None: ...
    def admin_grant_privileges(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_revoke_privileges(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_query_role(
        self, role: str, policy: Optional[PolicyDict] = None
    ) -> dict[str, Any]: ...
    def admin_query_roles(
        self, policy: Optional[PolicyDict] = None
    ) -> list[dict[str, Any]]: ...
    def admin_set_whitelist(
        self,
        role: str,
        whitelist: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    def admin_set_quotas(
        self,
        role: str,
        read_quota: int = 0,
        write_quota: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

class AsyncClient:
    """Aerospike async client. All I/O methods return coroutines."""

    def __init__(self, config: dict[str, Any]) -> None: ...
    async def __aenter__(self) -> "AsyncClient": ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool: ...

    # -- Connection --
    async def connect(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None: ...
    def is_connected(self) -> bool: ...
    async def close(self) -> None: ...
    async def get_node_names(self) -> list[str]: ...

    # -- CRUD --
    async def put(
        self,
        key: Key,
        bins: Bins,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def get(self, key: Key, policy: Optional[PolicyDict] = None) -> Record: ...
    async def select(
        self, key: Key, bins: list[str], policy: Optional[PolicyDict] = None
    ) -> Record: ...
    async def exists(
        self, key: Key, policy: Optional[PolicyDict] = None
    ) -> ExistsResult: ...
    async def remove(
        self,
        key: Key,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def touch(
        self,
        key: Key,
        val: int = 0,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- String / Numeric --
    async def append(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def prepend(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def increment(
        self,
        key: Key,
        bin: str,
        offset: Union[int, float],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def remove_bin(
        self,
        key: Key,
        bin_names: list[str],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- Multi-operation --
    async def operate(
        self,
        key: Key,
        ops: list[OperationDict],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> Record: ...
    async def operate_ordered(
        self,
        key: Key,
        ops: list[OperationDict],
        meta: Optional[Metadata] = None,
        policy: Optional[PolicyDict] = None,
    ) -> tuple[Any, Metadata, list[tuple[str, Any]]]: ...

    # -- Batch --
    @overload
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        _dtype: None = None,
    ) -> BatchRecords: ...
    @overload
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        *,
        _dtype: np.dtype,
    ) -> NumpyBatchRecords: ...
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[PolicyDict] = None,
        _dtype: Optional[np.dtype] = None,
    ) -> Union[BatchRecords, NumpyBatchRecords]: ...
    async def batch_operate(
        self,
        keys: list[Key],
        ops: list[OperationDict],
        policy: Optional[PolicyDict] = None,
    ) -> list[Record]: ...
    async def batch_remove(
        self, keys: list[Key], policy: Optional[PolicyDict] = None
    ) -> list[Record]: ...

    # -- Scan --
    async def scan(
        self,
        namespace: str,
        set_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> list[Record]: ...

    # -- Index --
    async def index_integer_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def index_string_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def index_geo2dsphere_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def index_remove(
        self,
        namespace: str,
        index_name: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- Truncate --
    async def truncate(
        self,
        namespace: str,
        set_name: str,
        nanos: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

    # -- UDF --
    async def udf_put(
        self,
        filename: str,
        udf_type: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def udf_remove(
        self, module: str, policy: Optional[PolicyDict] = None
    ) -> None: ...
    async def apply(
        self,
        key: Key,
        module: str,
        function: str,
        args: Optional[list[Any]] = None,
        policy: Optional[PolicyDict] = None,
    ) -> Any: ...

    # -- Admin: User --
    async def admin_create_user(
        self,
        username: str,
        password: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_drop_user(
        self, username: str, policy: Optional[PolicyDict] = None
    ) -> None: ...
    async def admin_change_password(
        self,
        username: str,
        password: str,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_grant_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_revoke_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_query_user_info(
        self, username: str, policy: Optional[PolicyDict] = None
    ) -> dict[str, Any]: ...
    async def admin_query_users_info(
        self, policy: Optional[PolicyDict] = None
    ) -> list[dict[str, Any]]: ...

    # -- Admin: Role --
    async def admin_create_role(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
        whitelist: Optional[list[str]] = None,
        read_quota: int = 0,
        write_quota: int = 0,
    ) -> None: ...
    async def admin_drop_role(
        self, role: str, policy: Optional[PolicyDict] = None
    ) -> None: ...
    async def admin_grant_privileges(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_revoke_privileges(
        self,
        role: str,
        privileges: list[PrivilegeDict],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_query_role(
        self, role: str, policy: Optional[PolicyDict] = None
    ) -> dict[str, Any]: ...
    async def admin_query_roles(
        self, policy: Optional[PolicyDict] = None
    ) -> list[dict[str, Any]]: ...
    async def admin_set_whitelist(
        self,
        role: str,
        whitelist: list[str],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...
    async def admin_set_quotas(
        self,
        role: str,
        read_quota: int = 0,
        write_quota: int = 0,
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

class Query:
    """Secondary index query object."""

    def select(self, *bins: str) -> None: ...
    # Named 'where' in Python (maps to 'where_' in Rust)
    def where(self, predicate: tuple[str, ...]) -> None: ...
    def results(self, policy: Optional[PolicyDict] = None) -> list[Record]: ...
    def foreach(
        self,
        callback: Callable[[Record], Optional[bool]],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

class Scan:
    """Full namespace/set scan object."""

    def select(self, *bins: str) -> None: ...
    def results(self, policy: Optional[PolicyDict] = None) -> list[Record]: ...
    def foreach(
        self,
        callback: Callable[[Record], Optional[bool]],
        policy: Optional[PolicyDict] = None,
    ) -> None: ...

# ── Factory function ─────────────────────────────────────────

def client(config: dict[str, Any]) -> Client: ...

# ── Exceptions ───────────────────────────────────────────────

class AerospikeError(Exception): ...
class ClientError(AerospikeError): ...
class ServerError(AerospikeError): ...
class RecordError(AerospikeError): ...
class ClusterError(AerospikeError): ...
class AerospikeTimeoutError(AerospikeError): ...
class TimeoutError(AerospikeError): ...
class InvalidArgError(AerospikeError): ...

# Record-level
class RecordNotFound(RecordError): ...
class RecordExistsError(RecordError): ...
class RecordGenerationError(RecordError): ...
class RecordTooBig(RecordError): ...
class BinNameError(RecordError): ...
class BinExistsError(RecordError): ...
class BinNotFound(RecordError): ...
class BinTypeError(RecordError): ...
class FilteredOut(RecordError): ...

# Server-level
class AerospikeIndexError(ServerError): ...
class IndexError(ServerError): ...
class IndexNotFound(AerospikeIndexError): ...
class IndexFoundError(AerospikeIndexError): ...
class QueryError(ServerError): ...
class QueryAbortedError(QueryError): ...
class AdminError(ServerError): ...
class UDFError(ServerError): ...

# ── Constants ────────────────────────────────────────────────

# Policy Key
POLICY_KEY_DIGEST: int
POLICY_KEY_SEND: int

# Policy Exists
POLICY_EXISTS_IGNORE: int
POLICY_EXISTS_UPDATE: int
POLICY_EXISTS_UPDATE_ONLY: int
POLICY_EXISTS_REPLACE: int
POLICY_EXISTS_REPLACE_ONLY: int
POLICY_EXISTS_CREATE_ONLY: int

# Policy Generation
POLICY_GEN_IGNORE: int
POLICY_GEN_EQ: int
POLICY_GEN_GT: int

# Policy Replica
POLICY_REPLICA_MASTER: int
POLICY_REPLICA_SEQUENCE: int
POLICY_REPLICA_PREFER_RACK: int

# Policy Commit Level
POLICY_COMMIT_LEVEL_ALL: int
POLICY_COMMIT_LEVEL_MASTER: int

# Policy Read Mode AP
POLICY_READ_MODE_AP_ONE: int
POLICY_READ_MODE_AP_ALL: int

# TTL
TTL_NAMESPACE_DEFAULT: int
TTL_NEVER_EXPIRE: int
TTL_DONT_UPDATE: int
TTL_CLIENT_DEFAULT: int

# Auth Mode
AUTH_INTERNAL: int
AUTH_EXTERNAL: int
AUTH_PKI: int

# Operators
OPERATOR_READ: int
OPERATOR_WRITE: int
OPERATOR_INCR: int
OPERATOR_APPEND: int
OPERATOR_PREPEND: int
OPERATOR_TOUCH: int
OPERATOR_DELETE: int

# Index Type
INDEX_NUMERIC: int
INDEX_STRING: int
INDEX_BLOB: int
INDEX_GEO2DSPHERE: int

# Index Collection Type
INDEX_TYPE_DEFAULT: int
INDEX_TYPE_LIST: int
INDEX_TYPE_MAPKEYS: int
INDEX_TYPE_MAPVALUES: int

# Log Level
LOG_LEVEL_OFF: int
LOG_LEVEL_ERROR: int
LOG_LEVEL_WARN: int
LOG_LEVEL_INFO: int
LOG_LEVEL_DEBUG: int
LOG_LEVEL_TRACE: int

# Serializer
SERIALIZER_NONE: int
SERIALIZER_PYTHON: int
SERIALIZER_USER: int

# List Return Type
LIST_RETURN_NONE: int
LIST_RETURN_INDEX: int
LIST_RETURN_REVERSE_INDEX: int
LIST_RETURN_RANK: int
LIST_RETURN_REVERSE_RANK: int
LIST_RETURN_COUNT: int
LIST_RETURN_VALUE: int
LIST_RETURN_EXISTS: int

# List Order
LIST_UNORDERED: int
LIST_ORDERED: int

# List Sort Flags
LIST_SORT_DEFAULT: int
LIST_SORT_DROP_DUPLICATES: int

# List Write Flags
LIST_WRITE_DEFAULT: int
LIST_WRITE_ADD_UNIQUE: int
LIST_WRITE_INSERT_BOUNDED: int
LIST_WRITE_NO_FAIL: int
LIST_WRITE_PARTIAL: int

# Map Return Type
MAP_RETURN_NONE: int
MAP_RETURN_INDEX: int
MAP_RETURN_REVERSE_INDEX: int
MAP_RETURN_RANK: int
MAP_RETURN_REVERSE_RANK: int
MAP_RETURN_COUNT: int
MAP_RETURN_KEY: int
MAP_RETURN_VALUE: int
MAP_RETURN_KEY_VALUE: int
MAP_RETURN_EXISTS: int

# Map Order
MAP_UNORDERED: int
MAP_KEY_ORDERED: int
MAP_KEY_VALUE_ORDERED: int

# Map Write Flags
MAP_WRITE_FLAGS_DEFAULT: int
MAP_WRITE_FLAGS_CREATE_ONLY: int
MAP_WRITE_FLAGS_UPDATE_ONLY: int
MAP_WRITE_FLAGS_NO_FAIL: int
MAP_WRITE_FLAGS_PARTIAL: int
MAP_UPDATE: int
MAP_UPDATE_ONLY: int
MAP_CREATE_ONLY: int

# Bit Write Flags
BIT_WRITE_DEFAULT: int
BIT_WRITE_CREATE_ONLY: int
BIT_WRITE_UPDATE_ONLY: int
BIT_WRITE_NO_FAIL: int
BIT_WRITE_PARTIAL: int

# HLL Write Flags
HLL_WRITE_DEFAULT: int
HLL_WRITE_CREATE_ONLY: int
HLL_WRITE_UPDATE_ONLY: int
HLL_WRITE_NO_FAIL: int
HLL_WRITE_ALLOW_FOLD: int

# Privilege Codes
PRIV_READ: int
PRIV_WRITE: int
PRIV_READ_WRITE: int
PRIV_READ_WRITE_UDF: int
PRIV_USER_ADMIN: int
PRIV_SYS_ADMIN: int
PRIV_DATA_ADMIN: int
PRIV_UDF_ADMIN: int
PRIV_SINDEX_ADMIN: int
PRIV_TRUNCATE: int

# Status Codes
AEROSPIKE_OK: int
AEROSPIKE_ERR_SERVER: int
AEROSPIKE_ERR_RECORD_NOT_FOUND: int
AEROSPIKE_ERR_RECORD_GENERATION: int
AEROSPIKE_ERR_PARAM: int
AEROSPIKE_ERR_RECORD_EXISTS: int
AEROSPIKE_ERR_BIN_EXISTS: int
AEROSPIKE_ERR_CLUSTER_KEY_MISMATCH: int
AEROSPIKE_ERR_SERVER_MEM: int
AEROSPIKE_ERR_TIMEOUT: int
AEROSPIKE_ERR_ALWAYS_FORBIDDEN: int
AEROSPIKE_ERR_PARTITION_UNAVAILABLE: int
AEROSPIKE_ERR_BIN_TYPE: int
AEROSPIKE_ERR_RECORD_TOO_BIG: int
AEROSPIKE_ERR_KEY_BUSY: int
AEROSPIKE_ERR_SCAN_ABORT: int
AEROSPIKE_ERR_UNSUPPORTED_FEATURE: int
AEROSPIKE_ERR_BIN_NOT_FOUND: int
AEROSPIKE_ERR_DEVICE_OVERLOAD: int
AEROSPIKE_ERR_KEY_MISMATCH: int
AEROSPIKE_ERR_INVALID_NAMESPACE: int
AEROSPIKE_ERR_BIN_NAME: int
AEROSPIKE_ERR_FAIL_FORBIDDEN: int
AEROSPIKE_ERR_ELEMENT_NOT_FOUND: int
AEROSPIKE_ERR_ELEMENT_EXISTS: int
AEROSPIKE_ERR_ENTERPRISE_ONLY: int
AEROSPIKE_ERR_OP_NOT_APPLICABLE: int
AEROSPIKE_ERR_FILTERED_OUT: int
AEROSPIKE_ERR_LOST_CONFLICT: int
AEROSPIKE_QUERY_END: int
AEROSPIKE_SECURITY_NOT_SUPPORTED: int
AEROSPIKE_SECURITY_NOT_ENABLED: int
AEROSPIKE_ERR_INVALID_USER: int
AEROSPIKE_ERR_NOT_AUTHENTICATED: int
AEROSPIKE_ERR_ROLE_VIOLATION: int
AEROSPIKE_ERR_UDF: int
AEROSPIKE_ERR_BATCH_DISABLED: int
AEROSPIKE_ERR_INDEX_FOUND: int
AEROSPIKE_ERR_INDEX_NOT_FOUND: int
AEROSPIKE_ERR_QUERY_ABORTED: int

# Client Error Codes
AEROSPIKE_ERR_CLIENT: int
AEROSPIKE_ERR_CONNECTION: int
AEROSPIKE_ERR_CLUSTER: int
AEROSPIKE_ERR_INVALID_HOST: int
AEROSPIKE_ERR_NO_MORE_CONNECTIONS: int
