"""Type stubs for the aerospike_py package."""

from typing import Any, Callable, Optional, Union, overload

import numpy as np

from aerospike_py import exception as exception
from aerospike_py import list_operations as list_operations
from aerospike_py import map_operations as map_operations
from aerospike_py import predicates as predicates
from aerospike_py.numpy_batch import NumpyBatchRecords as NumpyBatchRecords
from aerospike_py.types import (
    AdminPolicy as AdminPolicy,
    AerospikeKey as AerospikeKey,
    BatchPolicy as BatchPolicy,
    Bins as Bins,
    BinTuple as BinTuple,
    ClientConfig as ClientConfig,
    ExistsResult as ExistsResult,
    InfoNodeResult as InfoNodeResult,
    OperateOrderedResult as OperateOrderedResult,
    Privilege as Privilege,
    QueryPolicy as QueryPolicy,
    ReadPolicy as ReadPolicy,
    Record as Record,
    RecordMetadata as RecordMetadata,
    RoleInfo as RoleInfo,
    UserInfo as UserInfo,
    WriteMeta as WriteMeta,
    WritePolicy as WritePolicy,
)

__version__: str

# -- Type aliases --------------------------------------------------------

Key = tuple[str, str, Union[str, int, bytes]]
"""Aerospike key: (namespace, set, primary_key). Input type for all key parameters."""

class BatchRecord:
    """Single record result from a batch read operation."""

    key: Key
    result: int
    record: Optional[Record]

class BatchRecords:
    """Container for batch read results."""

    batch_records: list[BatchRecord]

# -- Client --------------------------------------------------------------

class Client:
    """Aerospike client for synchronous operations.

    Wraps the native Rust client with a Python-friendly API.
    Supports method chaining on ``connect()`` and context-manager usage.

    Example:
        ```python
        import aerospike_py

        client = aerospike_py.client({
            "hosts": [("127.0.0.1", 3000)],
        }).connect()

        client.put(("test", "demo", "key1"), {"name": "Alice"})
        record = client.get(("test", "demo", "key1"))
        print(record.bins)  # {"name": "Alice"}
        print(record.meta.gen)  # generation number

        client.close()
        ```
    """

    def __init__(self, config: dict[str, Any]) -> None: ...
    def __enter__(self) -> "Client": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool: ...

    # -- Connection --

    def connect(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> "Client":
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
        ...

    def is_connected(self) -> bool:
        """Check whether the client is connected to the cluster.

        Returns:
            ``True`` if the client has an active cluster connection.

        Example:
            ```python
            if client.is_connected():
                print("Connected")
            ```
        """
        ...

    def close(self) -> None:
        """Close the connection to the cluster.

        After calling this method the client can no longer be used for
        database operations.

        Example:
            ```python
            client.close()
            ```
        """
        ...

    def get_node_names(self) -> list[str]:
        """Return the names of all nodes in the cluster.

        Returns:
            A list of node name strings.

        Example:
            ```python
            nodes = client.get_node_names()
            # ['BB9020011AC4202', 'BB9030011AC4202']
            ```
        """
        ...

    # -- Info --

    def info_all(
        self,
        command: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> list[InfoNodeResult]:
        """Send an info command to all cluster nodes.

        Args:
            command: The info command string (e.g. ``"namespaces"``).
            policy: Optional info policy dict.

        Returns:
            A list of ``InfoNodeResult(node_name, error_code, response)`` tuples.

        Example:
            ```python
            results = client.info_all("namespaces")
            for node, err, response in results:
                print(f"{node}: {response}")
            ```
        """
        ...

    def info_random_node(
        self,
        command: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send an info command to a random cluster node.

        Args:
            command: The info command string.
            policy: Optional info policy dict.

        Returns:
            The info response string.

        Example:
            ```python
            response = client.info_random_node("build")
            ```
        """
        ...

    # -- CRUD --

    def put(
        self,
        key: Key,
        bins: Bins,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write a record to the Aerospike cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bins: Dictionary of bin name-value pairs to write.
            meta: Optional metadata dict (e.g. ``{"ttl": 300, "gen": 2}``).
            policy: Optional write policy dict.

        Raises:
            RecordExistsError: Record already exists (with CREATE_ONLY policy).
            RecordTooBig: Record size exceeds the configured write-block-size.

        Example:
            ```python
            key = ("test", "demo", "user1")
            client.put(key, {"name": "Alice", "age": 30})

            # With TTL (seconds)
            client.put(key, {"score": 100}, meta={"ttl": 300})

            # Create only (fail if exists)
            import aerospike_py
            client.put(
                key,
                {"x": 1},
                policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )
            ```
        """
        ...

    def get(self, key: Key, policy: Optional[dict[str, Any]] = None) -> Record:
        """Read a record from the cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            policy: Optional read policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            record = client.get(("test", "demo", "user1"))
            print(record.bins)  # {"name": "Alice", "age": 30}
            ```
        """
        ...

    def select(
        self,
        key: Key,
        bins: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> Record:
        """Read specific bins from a record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bins: List of bin names to retrieve.
            policy: Optional read policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            record = client.select(("test", "demo", "user1"), ["name"])
            # record.bins = {"name": "Alice"}
            ```
        """
        ...

    def exists(
        self,
        key: Key,
        policy: Optional[dict[str, Any]] = None,
    ) -> ExistsResult:
        """Check whether a record exists.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            policy: Optional read policy dict.

        Returns:
            An ``ExistsResult`` NamedTuple with ``key``, ``meta`` fields.
            ``meta`` is ``None`` if the record does not exist.

        Example:
            ```python
            result = client.exists(("test", "demo", "user1"))
            if result.meta is not None:
                print(f"Found, gen={result.meta.gen}")
            ```
        """
        ...

    def remove(
        self,
        key: Key,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Delete a record from the cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            meta: Optional metadata dict for generation check.
            policy: Optional remove policy dict.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            client.remove(("test", "demo", "user1"))

            # With generation check
            import aerospike_py
            client.remove(
                key,
                meta={"gen": 3},
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )
            ```
        """
        ...

    def touch(
        self,
        key: Key,
        val: int = 0,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Reset the TTL of a record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            val: New TTL value in seconds.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            client.touch(("test", "demo", "user1"), val=300)
            ```
        """
        ...

    # -- String / Numeric --

    def append(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append a string to a bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            val: String value to append.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            client.append(("test", "demo", "user1"), "name", "_suffix")
            ```
        """
        ...

    def prepend(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Prepend a string to a bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            val: String value to prepend.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            client.prepend(("test", "demo", "user1"), "name", "prefix_")
            ```
        """
        ...

    def increment(
        self,
        key: Key,
        bin: str,
        offset: Union[int, float],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Increment a numeric bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            offset: Integer or float amount to add (use negative to decrement).
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            client.increment(("test", "demo", "user1"), "age", 1)
            client.increment(("test", "demo", "user1"), "score", 0.5)
            ```
        """
        ...

    def remove_bin(
        self,
        key: Key,
        bin_names: list[str],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove specific bins from a record by setting them to nil.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin_names: List of bin names to remove.
            meta: Optional metadata dict.
            policy: Optional write policy dict.

        Example:
            ```python
            client.remove_bin(("test", "demo", "user1"), ["temp_bin", "debug_bin"])
            ```
        """
        ...

    # -- Multi-operation --

    def operate(
        self,
        key: Key,
        ops: list[dict[str, Any]],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> Record:
        """Execute multiple operations atomically on a single record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            ops: List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Example:
            ```python
            import aerospike_py

            ops = [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
            ]
            record = client.operate(("test", "demo", "key1"), ops)
            print(record.bins)
            ```
        """
        ...

    def operate_ordered(
        self,
        key: Key,
        ops: list[dict[str, Any]],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> OperateOrderedResult:
        """Execute multiple operations with ordered results.

        Like ``operate()`` but returns results as an ordered list preserving
        the operation order.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            ops: List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Returns:
            An ``OperateOrderedResult`` NamedTuple with ``key``, ``meta``,
            ``ordered_bins`` fields.

        Example:
            ```python
            import aerospike_py

            ops = [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
            ]
            result = client.operate_ordered(("test", "demo", "key1"), ops)
            # result.ordered_bins = [BinTuple("counter", 2)]
            ```
        """
        ...

    # -- Batch --

    @overload
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        _dtype: None = None,
    ) -> BatchRecords: ...
    @overload
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        *,
        _dtype: np.dtype,
    ) -> NumpyBatchRecords: ...
    def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        _dtype: Optional[np.dtype] = None,
    ) -> Union[BatchRecords, NumpyBatchRecords]:
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

            batch = client.batch_read(keys)
            for br in batch.batch_records:
                if br.record:
                    print(br.record.bins)

            # Read specific bins
            batch = client.batch_read(keys, bins=["name", "age"])
            ```
        """
        ...

    def batch_operate(
        self,
        keys: list[Key],
        ops: list[dict[str, Any]],
        policy: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """Execute operations on multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            ops: List of operation dicts to apply to each record.
            policy: Optional batch policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            import aerospike_py

            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
            results = client.batch_operate(keys, ops)
            ```
        """
        ...

    def batch_remove(
        self,
        keys: list[Key],
        policy: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """Delete multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            policy: Optional batch policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            results = client.batch_remove(keys)
            ```
        """
        ...

    # -- Query / Scan --

    def query(self, namespace: str, set_name: str) -> "Query":
        """Create a Query object for secondary index queries.

        Args:
            namespace: The namespace to query.
            set_name: The set to query.

        Returns:
            A ``Query`` object. Use ``where()`` to set a predicate filter
            and ``results()`` or ``foreach()`` to execute.

        Example:
            ```python
            query = client.query("test", "demo")
            query.select("name", "age")
            query.where(predicates.between("age", 20, 30))
            records = query.results()
            ```
        """
        ...

    def scan(self, namespace: str, set_name: str) -> "Scan":
        """Create a Scan object for full namespace/set scans.

        Args:
            namespace: The namespace to scan.
            set_name: The set to scan.

        Returns:
            A ``Scan`` object. Use ``results()`` or ``foreach()`` to execute.

        Example:
            ```python
            scan = client.scan("test", "demo")
            scan.select("name", "age")
            records = scan.results()
            ```
        """
        ...

    # -- Index --

    def index_integer_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a numeric secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index.
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Raises:
            IndexFoundError: An index with that name already exists.

        Example:
            ```python
            client.index_integer_create("test", "demo", "age", "age_idx")
            ```
        """
        ...

    def index_string_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a string secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index.
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Raises:
            IndexFoundError: An index with that name already exists.

        Example:
            ```python
            client.index_string_create("test", "demo", "name", "name_idx")
            ```
        """
        ...

    def index_geo2dsphere_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a geospatial secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index (must contain GeoJSON values).
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Raises:
            IndexFoundError: An index with that name already exists.

        Example:
            ```python
            client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
            ```
        """
        ...

    def index_remove(
        self,
        namespace: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove a secondary index.

        Args:
            namespace: Target namespace.
            index_name: Name of the index to remove.
            policy: Optional info policy dict.

        Raises:
            IndexNotFound: The index does not exist.

        Example:
            ```python
            client.index_remove("test", "age_idx")
            ```
        """
        ...

    # -- Truncate --

    def truncate(
        self,
        namespace: str,
        set_name: str,
        nanos: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove all records in a namespace/set.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            nanos: Optional last-update cutoff in nanoseconds.
            policy: Optional info policy dict.

        Example:
            ```python
            client.truncate("test", "demo")
            ```
        """
        ...

    # -- UDF --

    def udf_put(
        self,
        filename: str,
        udf_type: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register a Lua UDF module on the cluster.

        Args:
            filename: Path to the Lua source file.
            udf_type: UDF language type (only Lua ``0`` is supported).
            policy: Optional info policy dict.

        Example:
            ```python
            client.udf_put("my_udf.lua")
            ```
        """
        ...

    def udf_remove(
        self,
        module: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove a registered UDF module.

        Args:
            module: Module name to remove (without ``.lua`` extension).
            policy: Optional info policy dict.

        Example:
            ```python
            client.udf_remove("my_udf")
            ```
        """
        ...

    def apply(
        self,
        key: Key,
        module: str,
        function: str,
        args: Optional[list[Any]] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute a UDF on a single record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            module: Name of the registered UDF module.
            function: Name of the function within the module.
            args: Optional list of arguments to pass to the function.
            policy: Optional apply policy dict.

        Returns:
            The return value of the UDF function.

        Example:
            ```python
            result = client.apply(
                ("test", "demo", "key1"),
                "my_udf",
                "my_function",
                [1, "hello"],
            )
            ```
        """
        ...

    # -- Admin: User --

    def admin_create_user(
        self,
        username: str,
        password: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_drop_user(self, username: str, policy: Optional[dict[str, Any]] = None) -> None: ...
    def admin_change_password(
        self,
        username: str,
        password: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_grant_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_revoke_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_query_user_info(self, username: str, policy: Optional[dict[str, Any]] = None) -> dict[str, Any]: ...
    def admin_query_users_info(self, policy: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]: ...

    # -- Admin: Role --

    def admin_create_role(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
        whitelist: Optional[list[str]] = None,
        read_quota: int = 0,
        write_quota: int = 0,
    ) -> None: ...
    def admin_drop_role(self, role: str, policy: Optional[dict[str, Any]] = None) -> None: ...
    def admin_grant_privileges(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_revoke_privileges(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_query_role(self, role: str, policy: Optional[dict[str, Any]] = None) -> dict[str, Any]: ...
    def admin_query_roles(self, policy: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]: ...
    def admin_set_whitelist(
        self,
        role: str,
        whitelist: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    def admin_set_quotas(
        self,
        role: str,
        read_quota: int = 0,
        write_quota: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...

class AsyncClient:
    """Aerospike client for asynchronous operations.

    All I/O methods are coroutines and must be awaited.
    Provides the same functionality as ``Client`` with an async interface.

    Example:
        ```python
        import aerospike_py

        async def main():
            client = aerospike_py.AsyncClient({
                "hosts": [("127.0.0.1", 3000)],
            })
            await client.connect()

            await client.put(("test", "demo", "key1"), {"name": "Alice"})
            record = await client.get(("test", "demo", "key1"))
            print(record.bins)  # {"name": "Alice"}
            print(record.meta.gen)  # generation number

            await client.close()
        ```
    """

    def __init__(self, config: dict[str, Any]) -> None: ...
    async def __aenter__(self) -> "AsyncClient": ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool: ...

    # -- Connection --

    async def connect(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
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
        ...

    def is_connected(self) -> bool:
        """Check whether the client is connected to the cluster.

        Returns:
            ``True`` if the client has an active cluster connection.

        Example:
            ```python
            if client.is_connected():
                print("Connected")
            ```
        """
        ...

    async def close(self) -> None:
        """Close the connection to the cluster.

        Example:
            ```python
            await client.close()
            ```
        """
        ...

    async def get_node_names(self) -> list[str]:
        """Return the names of all nodes in the cluster.

        Returns:
            A list of node name strings.

        Example:
            ```python
            nodes = await client.get_node_names()
            ```
        """
        ...

    # -- Info --

    async def info_all(
        self,
        command: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> list[InfoNodeResult]:
        """Send an info command to all cluster nodes.

        Args:
            command: The info command string (e.g. ``"namespaces"``).
            policy: Optional info policy dict.

        Returns:
            A list of ``InfoNodeResult(node_name, error_code, response)`` tuples.

        Example:
            ```python
            results = await client.info_all("namespaces")
            for node, err, response in results:
                print(f"{node}: {response}")
            ```
        """
        ...

    async def info_random_node(
        self,
        command: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send an info command to a random cluster node.

        Args:
            command: The info command string.
            policy: Optional info policy dict.

        Returns:
            The info response string.

        Example:
            ```python
            response = await client.info_random_node("build")
            ```
        """
        ...

    # -- CRUD --

    async def put(
        self,
        key: Key,
        bins: Bins,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write a record to the Aerospike cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bins: Dictionary of bin name-value pairs to write.
            meta: Optional metadata dict (e.g. ``{"ttl": 300, "gen": 2}``).
            policy: Optional write policy dict.

        Raises:
            RecordExistsError: Record already exists (with CREATE_ONLY policy).
            RecordTooBig: Record size exceeds the configured write-block-size.

        Example:
            ```python
            key = ("test", "demo", "user1")
            await client.put(key, {"name": "Alice", "age": 30})

            # With TTL (seconds)
            await client.put(key, {"score": 100}, meta={"ttl": 300})
            ```
        """
        ...

    async def get(self, key: Key, policy: Optional[dict[str, Any]] = None) -> Record:
        """Read a record from the cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            policy: Optional read policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            record = await client.get(("test", "demo", "user1"))
            print(record.bins)  # {"name": "Alice", "age": 30}
            ```
        """
        ...

    async def select(
        self,
        key: Key,
        bins: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> Record:
        """Read specific bins from a record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bins: List of bin names to retrieve.
            policy: Optional read policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            record = await client.select(("test", "demo", "user1"), ["name"])
            # record.bins = {"name": "Alice"}
            ```
        """
        ...

    async def exists(
        self,
        key: Key,
        policy: Optional[dict[str, Any]] = None,
    ) -> ExistsResult:
        """Check whether a record exists.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            policy: Optional read policy dict.

        Returns:
            An ``ExistsResult`` NamedTuple with ``key``, ``meta`` fields.
            ``meta`` is ``None`` if the record does not exist.

        Example:
            ```python
            result = await client.exists(("test", "demo", "user1"))
            if result.meta is not None:
                print(f"Found, gen={result.meta.gen}")
            ```
        """
        ...

    async def remove(
        self,
        key: Key,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Delete a record from the cluster.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            meta: Optional metadata dict for generation check.
            policy: Optional remove policy dict.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            await client.remove(("test", "demo", "user1"))
            ```
        """
        ...

    async def touch(
        self,
        key: Key,
        val: int = 0,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Reset the TTL of a record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            val: New TTL value in seconds.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Raises:
            RecordNotFound: The record does not exist.

        Example:
            ```python
            await client.touch(("test", "demo", "user1"), val=300)
            ```
        """
        ...

    # -- String / Numeric --

    async def append(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append a string to a bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            val: String value to append.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            await client.append(("test", "demo", "user1"), "name", "_suffix")
            ```
        """
        ...

    async def prepend(
        self,
        key: Key,
        bin: str,
        val: Any,
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Prepend a string to a bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            val: String value to prepend.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            await client.prepend(("test", "demo", "user1"), "name", "prefix_")
            ```
        """
        ...

    async def increment(
        self,
        key: Key,
        bin: str,
        offset: Union[int, float],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Increment a numeric bin value.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin: Target bin name.
            offset: Integer or float amount to add (use negative to decrement).
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Example:
            ```python
            await client.increment(("test", "demo", "user1"), "age", 1)
            await client.increment(("test", "demo", "user1"), "score", 0.5)
            ```
        """
        ...

    async def remove_bin(
        self,
        key: Key,
        bin_names: list[str],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove specific bins from a record by setting them to nil.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            bin_names: List of bin names to remove.
            meta: Optional metadata dict.
            policy: Optional write policy dict.

        Example:
            ```python
            await client.remove_bin(("test", "demo", "user1"), ["temp_bin"])
            ```
        """
        ...

    # -- Multi-operation --

    async def operate(
        self,
        key: Key,
        ops: list[dict[str, Any]],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> Record:
        """Execute multiple operations atomically on a single record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            ops: List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Returns:
            A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

        Example:
            ```python
            import aerospike_py

            ops = [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
            ]
            record = await client.operate(("test", "demo", "key1"), ops)
            print(record.bins)
            ```
        """
        ...

    async def operate_ordered(
        self,
        key: Key,
        ops: list[dict[str, Any]],
        meta: Optional[WriteMeta] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> OperateOrderedResult:
        """Execute multiple operations with ordered results.

        Like ``operate()`` but returns results as an ordered list preserving
        the operation order.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            ops: List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys.
            meta: Optional metadata dict.
            policy: Optional operate policy dict.

        Returns:
            An ``OperateOrderedResult`` NamedTuple with ``key``, ``meta``,
            ``ordered_bins`` fields.

        Example:
            ```python
            import aerospike_py

            ops = [
                {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
            ]
            result = await client.operate_ordered(
                ("test", "demo", "key1"), ops
            )
            # result.ordered_bins = [BinTuple("counter", 2)]
            ```
        """
        ...

    # -- Batch --

    @overload
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        _dtype: None = None,
    ) -> BatchRecords: ...
    @overload
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        *,
        _dtype: np.dtype,
    ) -> NumpyBatchRecords: ...
    async def batch_read(
        self,
        keys: list[Key],
        bins: Optional[list[str]] = None,
        policy: Optional[dict[str, Any]] = None,
        _dtype: Optional[np.dtype] = None,
    ) -> Union[BatchRecords, NumpyBatchRecords]:
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
                    print(br.record.bins)
            ```
        """
        ...

    async def batch_operate(
        self,
        keys: list[Key],
        ops: list[dict[str, Any]],
        policy: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """Execute operations on multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            ops: List of operation dicts to apply to each record.
            policy: Optional batch policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            import aerospike_py

            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
            results = await client.batch_operate(keys, ops)
            ```
        """
        ...

    async def batch_remove(
        self,
        keys: list[Key],
        policy: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """Delete multiple records in a single batch call.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            policy: Optional batch policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            results = await client.batch_remove(keys)
            ```
        """
        ...

    # -- Scan --

    async def scan(
        self,
        namespace: str,
        set_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """Scan all records in a namespace/set.

        Returns a list of records directly (unlike the sync client which
        returns a ``Scan`` object).

        Args:
            namespace: The namespace to scan.
            set_name: The set to scan.
            policy: Optional scan policy dict. Supports ``"filter_expression"``
                for server-side filtering.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            records = await client.scan("test", "demo")
            for record in records:
                print(record.bins)
            ```
        """
        ...

    # -- Index --

    async def index_integer_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a numeric secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index.
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Example:
            ```python
            await client.index_integer_create("test", "demo", "age", "age_idx")
            ```
        """
        ...

    async def index_string_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a string secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index.
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Example:
            ```python
            await client.index_string_create("test", "demo", "name", "name_idx")
            ```
        """
        ...

    async def index_geo2dsphere_create(
        self,
        namespace: str,
        set_name: str,
        bin_name: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a geospatial secondary index.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            bin_name: Bin to index (must contain GeoJSON values).
            index_name: Name for the new index.
            policy: Optional info policy dict.

        Example:
            ```python
            await client.index_geo2dsphere_create(
                "test", "demo", "location", "geo_idx"
            )
            ```
        """
        ...

    async def index_remove(
        self,
        namespace: str,
        index_name: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove a secondary index.

        Args:
            namespace: Target namespace.
            index_name: Name of the index to remove.
            policy: Optional info policy dict.

        Example:
            ```python
            await client.index_remove("test", "age_idx")
            ```
        """
        ...

    # -- Truncate --

    async def truncate(
        self,
        namespace: str,
        set_name: str,
        nanos: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove all records in a namespace/set.

        Args:
            namespace: Target namespace.
            set_name: Target set.
            nanos: Optional last-update cutoff in nanoseconds.
            policy: Optional info policy dict.

        Example:
            ```python
            await client.truncate("test", "demo")
            ```
        """
        ...

    # -- UDF --

    async def udf_put(
        self,
        filename: str,
        udf_type: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register a Lua UDF module on the cluster.

        Args:
            filename: Path to the Lua source file.
            udf_type: UDF language type (only Lua ``0`` is supported).
            policy: Optional info policy dict.

        Example:
            ```python
            await client.udf_put("my_udf.lua")
            ```
        """
        ...

    async def udf_remove(
        self,
        module: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Remove a registered UDF module.

        Args:
            module: Module name to remove (without ``.lua`` extension).
            policy: Optional info policy dict.

        Example:
            ```python
            await client.udf_remove("my_udf")
            ```
        """
        ...

    async def apply(
        self,
        key: Key,
        module: str,
        function: str,
        args: Optional[list[Any]] = None,
        policy: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute a UDF on a single record.

        Args:
            key: Record key as ``(namespace, set, primary_key)`` tuple.
            module: Name of the registered UDF module.
            function: Name of the function within the module.
            args: Optional list of arguments to pass to the function.
            policy: Optional apply policy dict.

        Returns:
            The return value of the UDF function.

        Example:
            ```python
            result = await client.apply(
                ("test", "demo", "key1"),
                "my_udf",
                "my_function",
                [1, "hello"],
            )
            ```
        """
        ...

    # -- Admin: User --

    async def admin_create_user(
        self,
        username: str,
        password: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_drop_user(self, username: str, policy: Optional[dict[str, Any]] = None) -> None: ...
    async def admin_change_password(
        self,
        username: str,
        password: str,
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_grant_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_revoke_roles(
        self,
        username: str,
        roles: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_query_user_info(self, username: str, policy: Optional[dict[str, Any]] = None) -> dict[str, Any]: ...
    async def admin_query_users_info(self, policy: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]: ...

    # -- Admin: Role --

    async def admin_create_role(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
        whitelist: Optional[list[str]] = None,
        read_quota: int = 0,
        write_quota: int = 0,
    ) -> None: ...
    async def admin_drop_role(self, role: str, policy: Optional[dict[str, Any]] = None) -> None: ...
    async def admin_grant_privileges(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_revoke_privileges(
        self,
        role: str,
        privileges: list[Privilege],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_query_role(self, role: str, policy: Optional[dict[str, Any]] = None) -> dict[str, Any]: ...
    async def admin_query_roles(self, policy: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]: ...
    async def admin_set_whitelist(
        self,
        role: str,
        whitelist: list[str],
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...
    async def admin_set_quotas(
        self,
        role: str,
        read_quota: int = 0,
        write_quota: int = 0,
        policy: Optional[dict[str, Any]] = None,
    ) -> None: ...

class Query:
    """Secondary index query object.

    Created via ``Client.query(namespace, set_name)``. Use ``where()``
    to set a predicate filter, ``select()`` to choose bins, then
    ``results()`` or ``foreach()`` to execute.

    Example:
        ```python
        from aerospike_py import predicates

        query = client.query("test", "demo")
        query.select("name", "age")
        query.where(predicates.between("age", 20, 30))
        records = query.results()
        ```
    """

    def select(self, *bins: str) -> None:
        """Select specific bins to return in query results.

        Args:
            *bins: Bin names to include in the results.

        Example:
            ```python
            query = client.query("test", "demo")
            query.select("name", "age")
            ```
        """
        ...

    def where(self, predicate: tuple[str, ...]) -> None:
        """Set a predicate filter for the query.

        Requires a matching secondary index on the filtered bin.

        Args:
            predicate: A predicate tuple created by ``aerospike_py.predicates``
                helper functions.

        Example:
            ```python
            from aerospike_py import predicates

            query = client.query("test", "demo")
            query.where(predicates.equals("name", "Alice"))
            ```
        """
        ...

    def results(self, policy: Optional[dict[str, Any]] = None) -> list[Record]:
        """Execute the query and return all matching records.

        Args:
            policy: Optional query policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            records = query.results()
            for record in records:
                print(record.bins)
            ```
        """
        ...

    def foreach(
        self,
        callback: Callable[[Record], Optional[bool]],
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Execute the query and invoke a callback for each record.

        The callback receives a ``Record`` NamedTuple. Return ``False``
        from the callback to stop iteration early.

        Args:
            callback: Function called with each record. Return ``False`` to stop.
            policy: Optional query policy dict.

        Example:
            ```python
            def process(record):
                print(record.bins)

            query.foreach(process)
            ```
        """
        ...

class Scan:
    """Full namespace/set scan object.

    Created via ``Client.scan(namespace, set_name)``. Use ``select()``
    to choose bins, then ``results()`` or ``foreach()`` to execute.

    Example:
        ```python
        scan = client.scan("test", "demo")
        scan.select("name", "age")
        records = scan.results()
        ```
    """

    def select(self, *bins: str) -> None:
        """Select specific bins to return in scan results.

        Args:
            *bins: Bin names to include in the results.

        Example:
            ```python
            scan = client.scan("test", "demo")
            scan.select("name", "age")
            ```
        """
        ...

    def results(self, policy: Optional[dict[str, Any]] = None) -> list[Record]:
        """Execute the scan and return all records.

        Args:
            policy: Optional scan policy dict.

        Returns:
            A list of ``Record`` NamedTuples.

        Example:
            ```python
            records = scan.results()
            for record in records:
                print(record.bins)
            ```
        """
        ...

    def foreach(
        self,
        callback: Callable[[Record], Optional[bool]],
        policy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Execute the scan and invoke a callback for each record.

        The callback receives a ``Record`` NamedTuple. Return ``False``
        from the callback to stop iteration early.

        Args:
            callback: Function called with each record. Return ``False`` to stop.
            policy: Optional scan policy dict.

        Example:
            ```python
            def process(record):
                print(record.bins)

            scan.foreach(process)
            ```
        """
        ...

# -- Factory functions ---------------------------------------------------

def client(config: dict[str, Any]) -> Client:
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
    ...

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
    ...

def get_metrics() -> str:
    """Return collected metrics in Prometheus text format.

    Returns:
        A string in Prometheus exposition format.

    Example:
        ```python
        print(aerospike_py.get_metrics())
        ```
    """
    ...

def start_metrics_server(port: int = 9464) -> None:
    """Start a background HTTP server serving ``/metrics`` for Prometheus.

    Args:
        port: TCP port to listen on (default ``9464``).

    Example:
        ```python
        aerospike_py.start_metrics_server(port=9464)
        ```
    """
    ...

def stop_metrics_server() -> None:
    """Stop the background metrics HTTP server.

    Example:
        ```python
        aerospike_py.stop_metrics_server()
        ```
    """
    ...

def init_tracing() -> None:
    """Initialize OpenTelemetry tracing.

    Reads standard ``OTEL_*`` environment variables for configuration.

    Example:
        ```python
        aerospike_py.init_tracing()
        ```
    """
    ...

def shutdown_tracing() -> None:
    """Shut down the tracer provider, flushing pending spans.

    Call before process exit to ensure all spans are exported.

    Example:
        ```python
        aerospike_py.shutdown_tracing()
        ```
    """
    ...

# -- Exceptions ----------------------------------------------------------

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

# -- Constants -----------------------------------------------------------

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
