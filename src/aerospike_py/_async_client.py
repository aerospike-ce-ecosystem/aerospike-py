"""Async Client and AsyncQuery wrappers with NamedTuple result conversion."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aerospike_py._aerospike import AsyncClient as _NativeAsyncClient
from aerospike_py._aerospike import Query as _NativeQuery
from aerospike_py._bug_report import catch_unexpected
from aerospike_py._client import _wrap_batch_record, _wrap_exists, _wrap_operate_ordered, _wrap_record
from aerospike_py.types import (
    BatchRecords as BatchRecordsTuple,
    ExistsResult,
    InfoNodeResult,
    OperateOrderedResult,
    Record,
)

logger = logging.getLogger("aerospike_py")


# ---------------------------------------------------------------------------
# AsyncQuery Python wrapper
# ---------------------------------------------------------------------------


class AsyncQuery:
    """Async Python wrapper around the native Query object that returns typed records.

    ``select()`` and ``where()`` are synchronous setup methods.
    ``results()`` and ``foreach()`` are async and run the blocking native
    query in a thread pool to avoid blocking the event loop.
    """

    def __init__(self, inner: _NativeQuery):
        self._inner = inner

    def select(self, *bins: str) -> None:
        self._inner.select(*bins)

    def where(self, predicate) -> None:
        self._inner.where(predicate)

    @catch_unexpected("AsyncQuery.results")
    async def results(self, policy=None) -> list[Record]:
        raw = await asyncio.to_thread(self._inner.results, policy)
        return [_wrap_record(r) for r in raw]

    @catch_unexpected("AsyncQuery.foreach")
    async def foreach(self, callback, policy=None) -> None:
        def _sync_foreach():
            def _cb(raw):
                return callback(_wrap_record(raw))

            self._inner.foreach(_cb, policy)

        await asyncio.to_thread(_sync_foreach)


# ---------------------------------------------------------------------------
# AsyncClient
# ---------------------------------------------------------------------------


class BatchReadHandle:
    """Handle wrapping Rust batch read results with lazy NamedTuple conversion.

    Returned by ``AsyncClient.batch_read()``. The async future completes with
    near-zero GIL cost; actual data conversion is deferred to method calls
    that run in the event loop thread (zero GIL contention).

    Fast path::

        handle = await client.batch_read(keys)
        data = handle.as_dict()  # dict[key, bins_dict]

    Compatibility path::

        handle = await client.batch_read(keys)
        for br in handle.batch_records:
            print(br.record.bins)
    """

    __slots__ = ("_inner", "_cached_batch_records")

    def __init__(self, inner):
        self._inner = inner
        self._cached_batch_records = None

    def __len__(self) -> int:
        return len(self._inner)

    def __iter__(self):
        return iter(self.batch_records)

    def as_dict(self):
        """Fastest access path: returns ``dict[key, bins_dict]`` directly.

        Skips all intermediate objects (BatchRecord wrapper, key tuple, meta dict).
        """
        return self._inner.as_dict()

    @property
    def batch_records(self):
        """Compatibility path: ``list[BatchRecord]`` NamedTuples. Lazy and cached."""
        if self._cached_batch_records is None:
            self._cached_batch_records = [
                _wrap_batch_record(br) for br in self._inner.batch_records
            ]
        return self._cached_batch_records

    def found_count(self) -> int:
        """Count of records with successful result code (no conversion needed)."""
        return self._inner.found_count()

    def keys(self):
        """Extract just the user keys without converting record data."""
        return self._inner.keys()


class AsyncClient:
    """Aerospike async client wrapper with numpy batch_read support.

    Delegates to _NativeAsyncClient (PyO3 type that cannot be subclassed).

    All read methods (``get``, ``select``, ``exists``, ``operate``, etc.)
    return NamedTuple instances (``Record``, ``ExistsResult``, etc.) with
    named field access: ``record.meta.gen``, ``record.bins["name"]``.
    """

    def __init__(self, config: dict):
        self._inner = _NativeAsyncClient(config)

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        await self.close()
        return False

    async def connect(self, username: str | None = None, password: str | None = None) -> "AsyncClient":
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
            client = await aerospike_py.AsyncClient(config).connect()

            # With authentication
            client = await aerospike_py.AsyncClient(config).connect("admin", "admin")
            ```
        """
        logger.info("Async client connecting")
        await self._inner.connect(username, password)
        return self

    async def close(self) -> None:
        """Close the connection to the cluster.

        Example:
            ```python
            await client.close()
            ```
        """
        logger.debug("Async client closing")
        return await self._inner.close()

    @catch_unexpected("AsyncClient.get")
    async def get(self, key, policy=None) -> Record:
        return _wrap_record(await self._inner.get(key, policy))

    @catch_unexpected("AsyncClient.select")
    async def select(self, key, bins, policy=None) -> Record:
        return _wrap_record(await self._inner.select(key, bins, policy))

    @catch_unexpected("AsyncClient.exists")
    async def exists(self, key, policy=None) -> ExistsResult:
        return _wrap_exists(await self._inner.exists(key, policy))

    @catch_unexpected("AsyncClient.operate")
    async def operate(self, key, ops, meta=None, policy=None) -> Record:
        return _wrap_record(await self._inner.operate(key, ops, meta, policy))

    @catch_unexpected("AsyncClient.operate_ordered")
    async def operate_ordered(self, key, ops, meta=None, policy=None) -> OperateOrderedResult:
        return _wrap_operate_ordered(await self._inner.operate_ordered(key, ops, meta, policy))

    @catch_unexpected("AsyncClient.info_all")
    async def info_all(self, command, policy=None) -> list[InfoNodeResult]:
        return [InfoNodeResult(*t) for t in await self._inner.info_all(command, policy)]

    @catch_unexpected("AsyncClient.batch_read")
    async def batch_read(
        self, keys: list, bins: list[str] | None = None, policy: dict[str, Any] | None = None, _dtype: Any = None
    ) -> Any:
        """Read multiple records in a single batch call.

        Returns a :class:`BatchReadHandle` — a zero-conversion handle wrapping
        raw Rust results. The async future completes with near-zero GIL cost.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            bins: Optional list of bin names to read. ``None`` reads all bins;
                an empty list performs an existence check only.
            policy: Optional batch policy dict.
            _dtype: Optional NumPy dtype. When provided, returns
                ``NumpyBatchRecords`` instead of ``BatchReadHandle``.

        Returns:
            ``BatchReadHandle`` (or ``NumpyBatchRecords`` when ``_dtype`` is set).

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            handle = await client.batch_read(keys, bins=["name", "age"])

            # Fast path — dict[key, bins_dict]:
            data = handle.as_dict()

            # Compat path — list[BatchRecord] NamedTuples:
            for br in handle.batch_records:
                if br.result == 0 and br.record is not None:
                    print(br.record.bins)
            ```
        """
        raw = await self._inner.batch_read(keys, bins, policy, _dtype)
        if _dtype is not None:
            return raw  # NumpyBatchRecords path unchanged
        return BatchReadHandle(raw)

    @catch_unexpected("AsyncClient.batch_write_numpy")
    async def batch_write_numpy(
        self, data, namespace: str, set_name: str, _dtype, key_field: str = "_key", policy=None, retry: int = 0
    ) -> BatchRecordsTuple:
        """Write multiple records from a numpy structured array (async).

        Each row of the structured array becomes a separate write operation.
        The dtype must contain a key field (default ``_key``) for the record key.
        Remaining non-underscore-prefixed fields become bins.

        Args:
            data: numpy structured array with record data.
            namespace: Target namespace.
            set_name: Target set.
            _dtype: numpy dtype describing the array layout.
            key_field: Name of the dtype field to use as the user key (default ``"_key"``).
            policy: Optional batch policy dict.
            retry: Maximum number of retries for failed records (default ``0``).
                When > 0, records that fail with transient errors (timeout,
                device overload, key busy) are automatically retried with
                exponential backoff.

        Returns:
            ``BatchRecords`` containing per-record result codes.

        Example:
            ```python
            import numpy as np
            dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
            data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)
            results = await client.batch_write_numpy(data, "test", "demo", dtype, retry=10)
            for br in results.batch_records:
                if br.result != 0:
                    print(f"Failed: {br.key}, code={br.result}")
            ```
        """
        raw = await self._inner.batch_write_numpy(data, namespace, set_name, _dtype, key_field, policy, retry)
        return BatchRecordsTuple(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("AsyncClient.batch_write")
    async def batch_write(self, records, policy=None, retry=0) -> BatchRecordsTuple:
        """Write multiple records with per-record bins in a single batch call (async).

        See :meth:`AsyncClient.batch_write` in ``__init__.pyi`` for full documentation.
        """
        raw = await self._inner.batch_write(records, policy, retry)
        return BatchRecordsTuple(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("AsyncClient.batch_operate")
    async def batch_operate(self, keys, ops, policy=None) -> BatchRecordsTuple:
        raw = await self._inner.batch_operate(keys, ops, policy)
        return BatchRecordsTuple(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("AsyncClient.batch_remove")
    async def batch_remove(self, keys, policy=None) -> BatchRecordsTuple:
        raw = await self._inner.batch_remove(keys, policy)
        return BatchRecordsTuple(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("AsyncClient.ping")
    async def ping(self) -> bool:
        return await self._inner.ping()

    @catch_unexpected("AsyncClient.is_connected")
    def is_connected(self) -> bool:
        return self._inner.is_connected()

    @catch_unexpected("AsyncClient.get_node_names")
    def get_node_names(self) -> list[str]:
        return self._inner.get_node_names()

    @catch_unexpected("AsyncClient.info_random_node")
    async def info_random_node(self, command, policy=None) -> str:
        return await self._inner.info_random_node(command, policy)

    @catch_unexpected("AsyncClient.put")
    async def put(self, key, bins, meta=None, policy=None) -> None:
        return await self._inner.put(key, bins, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.remove")
    async def remove(self, key, meta=None, policy=None) -> None:
        return await self._inner.remove(key, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.touch")
    async def touch(self, key, val=0, meta=None, policy=None) -> None:
        return await self._inner.touch(key, val=val, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.append")
    async def append(self, key, bin, val, meta=None, policy=None) -> None:
        return await self._inner.append(key, bin, val, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.prepend")
    async def prepend(self, key, bin, val, meta=None, policy=None) -> None:
        return await self._inner.prepend(key, bin, val, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.increment")
    async def increment(self, key, bin, offset, meta=None, policy=None) -> None:
        return await self._inner.increment(key, bin, offset, meta=meta, policy=policy)

    @catch_unexpected("AsyncClient.remove_bin")
    async def remove_bin(self, key, bin_names, meta=None, policy=None) -> None:
        return await self._inner.remove_bin(key, bin_names, meta=meta, policy=policy)

    # -- Index --

    @catch_unexpected("AsyncClient.index_integer_create")
    async def index_integer_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return await self._inner.index_integer_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("AsyncClient.index_string_create")
    async def index_string_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return await self._inner.index_string_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("AsyncClient.index_geo2dsphere_create")
    async def index_geo2dsphere_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return await self._inner.index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("AsyncClient.index_remove")
    async def index_remove(self, namespace, index_name, policy=None) -> None:
        return await self._inner.index_remove(namespace, index_name, policy)

    # -- Truncate --

    @catch_unexpected("AsyncClient.truncate")
    async def truncate(self, namespace, set_name, nanos=0, policy=None) -> None:
        return await self._inner.truncate(namespace, set_name, nanos, policy)

    # -- UDF --

    @catch_unexpected("AsyncClient.udf_put")
    async def udf_put(self, filename, udf_type=0, policy=None) -> None:
        return await self._inner.udf_put(filename, udf_type, policy)

    @catch_unexpected("AsyncClient.udf_remove")
    async def udf_remove(self, module, policy=None) -> None:
        return await self._inner.udf_remove(module, policy)

    @catch_unexpected("AsyncClient.apply")
    async def apply(self, key, module, function, args=None, policy=None):
        return await self._inner.apply(key, module, function, args, policy)

    # -- Admin: User --

    @catch_unexpected("AsyncClient.admin_create_user")
    async def admin_create_user(self, username, password, roles, policy=None) -> None:
        return await self._inner.admin_create_user(username, password, roles, policy)

    @catch_unexpected("AsyncClient.admin_drop_user")
    async def admin_drop_user(self, username, policy=None) -> None:
        return await self._inner.admin_drop_user(username, policy)

    @catch_unexpected("AsyncClient.admin_change_password")
    async def admin_change_password(self, username, password, policy=None) -> None:
        return await self._inner.admin_change_password(username, password, policy)

    @catch_unexpected("AsyncClient.admin_grant_roles")
    async def admin_grant_roles(self, username, roles, policy=None) -> None:
        return await self._inner.admin_grant_roles(username, roles, policy)

    @catch_unexpected("AsyncClient.admin_revoke_roles")
    async def admin_revoke_roles(self, username, roles, policy=None) -> None:
        return await self._inner.admin_revoke_roles(username, roles, policy)

    @catch_unexpected("AsyncClient.admin_query_user_info")
    async def admin_query_user_info(self, username, policy=None):
        return await self._inner.admin_query_user_info(username, policy)

    @catch_unexpected("AsyncClient.admin_query_users_info")
    async def admin_query_users_info(self, policy=None):
        return await self._inner.admin_query_users_info(policy)

    # -- Admin: Role --

    @catch_unexpected("AsyncClient.admin_create_role")
    async def admin_create_role(
        self, role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0
    ) -> None:
        return await self._inner.admin_create_role(role, privileges, policy, whitelist, read_quota, write_quota)

    @catch_unexpected("AsyncClient.admin_drop_role")
    async def admin_drop_role(self, role, policy=None) -> None:
        return await self._inner.admin_drop_role(role, policy)

    @catch_unexpected("AsyncClient.admin_grant_privileges")
    async def admin_grant_privileges(self, role, privileges, policy=None) -> None:
        return await self._inner.admin_grant_privileges(role, privileges, policy)

    @catch_unexpected("AsyncClient.admin_revoke_privileges")
    async def admin_revoke_privileges(self, role, privileges, policy=None) -> None:
        return await self._inner.admin_revoke_privileges(role, privileges, policy)

    @catch_unexpected("AsyncClient.admin_query_role")
    async def admin_query_role(self, role, policy=None):
        return await self._inner.admin_query_role(role, policy)

    @catch_unexpected("AsyncClient.admin_query_roles")
    async def admin_query_roles(self, policy=None):
        return await self._inner.admin_query_roles(policy)

    @catch_unexpected("AsyncClient.admin_set_whitelist")
    async def admin_set_whitelist(self, role, whitelist, policy=None) -> None:
        return await self._inner.admin_set_whitelist(role, whitelist, policy)

    @catch_unexpected("AsyncClient.admin_set_quotas")
    async def admin_set_quotas(self, role, read_quota=0, write_quota=0, policy=None) -> None:
        return await self._inner.admin_set_quotas(role, read_quota, write_quota, policy)

    # -- Query --

    def query(self, namespace: str, set_name: str) -> AsyncQuery:
        """Create a query object for the given namespace and set.

        Returns an ``AsyncQuery`` whose ``results()`` and ``foreach()``
        methods are coroutines.

        Args:
            namespace: The namespace to query.
            set_name: The set name to query.

        Returns:
            An ``AsyncQuery`` instance.

        Example:
            ```python
            query = client.query("test", "demo")
            query.where(predicates.between("age", 20, 30))
            records = await query.results()
            ```
        """
        return AsyncQuery(self._inner.query(namespace, set_name))
