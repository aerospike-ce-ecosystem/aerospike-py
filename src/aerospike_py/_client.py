"""Sync Client and Query wrappers with NamedTuple result conversion."""

from __future__ import annotations

import logging

from aerospike_py._aerospike import Client as _NativeClient
from aerospike_py._aerospike import Query as _NativeQuery
from aerospike_py._bug_report import catch_unexpected
from aerospike_py.types import (
    AerospikeKey,
    BatchRecord as BatchRecordTuple,
    BatchWriteResult,
    BinTuple,
    ExistsResult,
    InfoNodeResult,
    OperateOrderedResult,
    Record,
    RecordMetadata,
)

logger = logging.getLogger("aerospike_py")


# ---------------------------------------------------------------------------
# Wrapping helpers
# ---------------------------------------------------------------------------


def _wrap_key(raw: tuple | None) -> AerospikeKey | None:
    if raw is None:
        return None
    return AerospikeKey(raw[0], raw[1], raw[2], raw[3])


def _wrap_meta(raw: dict | None) -> RecordMetadata | None:
    if raw is None:
        return None
    return RecordMetadata(gen=raw["gen"], ttl=raw["ttl"])


def _wrap_record(raw: tuple) -> Record:
    return Record(key=_wrap_key(raw[0]), meta=_wrap_meta(raw[1]), bins=raw[2])


def _wrap_exists(raw: tuple) -> ExistsResult:
    return ExistsResult(key=_wrap_key(raw[0]), meta=_wrap_meta(raw[1]))


def _wrap_operate_ordered(raw: tuple) -> OperateOrderedResult:
    return OperateOrderedResult(
        key=_wrap_key(raw[0]),
        meta=_wrap_meta(raw[1]),
        ordered_bins=[BinTuple(n, v) for n, v in raw[2]],
    )


def _wrap_batch_record(br) -> BatchRecordTuple:
    key = _wrap_key(br.key)
    record = _wrap_record(br.record) if br.record is not None else None
    return BatchRecordTuple(key=key, result=br.result, record=record, in_doubt=br.in_doubt)


# ---------------------------------------------------------------------------
# Query Python wrapper
# ---------------------------------------------------------------------------


class Query:
    """Python wrapper around the native Query object that returns typed records."""

    def __init__(self, inner: _NativeQuery):
        self._inner = inner

    def select(self, *bins: str) -> None:
        self._inner.select(*bins)

    def where(self, predicate) -> None:
        self._inner.where(predicate)

    @catch_unexpected("Query.results")
    def results(self, policy=None) -> list[Record]:
        return [_wrap_record(r) for r in self._inner.results(policy)]

    @catch_unexpected("Query.foreach")
    def foreach(self, callback, policy=None) -> None:
        def _cb(raw):
            return callback(_wrap_record(raw))

        self._inner.foreach(_cb, policy)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class Client(_NativeClient):
    """Aerospike client wrapper that supports method chaining on connect().

    All read methods (``get``, ``select``, ``exists``, ``operate``, etc.)
    return NamedTuple instances (``Record``, ``ExistsResult``, etc.) with
    named field access: ``record.meta.gen``, ``record.bins["name"]``.
    """

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

    @catch_unexpected("Client.get")
    def get(self, key, policy=None) -> Record:
        return _wrap_record(super().get(key, policy))

    @catch_unexpected("Client.select")
    def select(self, key, bins, policy=None) -> Record:
        return _wrap_record(super().select(key, bins, policy))

    @catch_unexpected("Client.exists")
    def exists(self, key, policy=None) -> ExistsResult:
        return _wrap_exists(super().exists(key, policy))

    @catch_unexpected("Client.operate")
    def operate(self, key, ops, meta=None, policy=None) -> Record:
        return _wrap_record(super().operate(key, ops, meta, policy))

    @catch_unexpected("Client.operate_ordered")
    def operate_ordered(self, key, ops, meta=None, policy=None) -> OperateOrderedResult:
        return _wrap_operate_ordered(super().operate_ordered(key, ops, meta, policy))

    @catch_unexpected("Client.info_all")
    def info_all(self, command, policy=None) -> list[InfoNodeResult]:
        return [InfoNodeResult(*t) for t in super().info_all(command, policy)]

    @catch_unexpected("Client.batch_read")
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
            ``BatchRecords`` (``dict[Key, AerospikeRecord]``) or
            ``NumpyBatchRecords`` when ``_dtype`` is set.

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            result = client.batch_read(keys, bins=["name", "age"])
            for user_key, bins_dict in result.items():
                print(user_key, bins_dict)
            ```
        """
        raw = super().batch_read(keys, bins, policy, _dtype)
        if _dtype is not None:
            return raw  # NumpyBatchRecords path unchanged
        return raw.as_dict()

    @catch_unexpected("Client.batch_write_numpy")
    def batch_write_numpy(self, data, namespace, set_name, _dtype, key_field="_key", policy=None, retry=0):
        """Write multiple records from a numpy structured array.

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
            results = client.batch_write_numpy(data, "test", "demo", dtype, retry=10)
            for br in results.batch_records:
                if br.result != 0:
                    print(f"Failed: {br.key}, code={br.result}")
            ```
        """
        raw = super().batch_write_numpy(data, namespace, set_name, _dtype, key_field, policy, retry)
        return BatchWriteResult(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("Client.batch_write")
    def batch_write(self, records, policy=None, retry=0) -> BatchWriteResult:
        """Write multiple records with per-record bins in a single batch call.

        See :meth:`Client.batch_write` in ``__init__.pyi`` for full documentation.
        """
        raw = super().batch_write(records, policy, retry)
        return BatchWriteResult(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("Client.batch_operate")
    def batch_operate(self, keys, ops, policy=None) -> BatchWriteResult:
        raw = super().batch_operate(keys, ops, policy)
        return BatchWriteResult(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("Client.batch_remove")
    def batch_remove(self, keys, policy=None) -> BatchWriteResult:
        raw = super().batch_remove(keys, policy)
        return BatchWriteResult(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

    @catch_unexpected("Client.put")
    def put(self, key, bins, meta=None, policy=None) -> None:
        return super().put(key, bins, meta=meta, policy=policy)

    @catch_unexpected("Client.remove")
    def remove(self, key, meta=None, policy=None) -> None:
        return super().remove(key, meta=meta, policy=policy)

    @catch_unexpected("Client.touch")
    def touch(self, key, val=0, meta=None, policy=None) -> None:
        return super().touch(key, val=val, meta=meta, policy=policy)

    @catch_unexpected("Client.append")
    def append(self, key, bin, val, meta=None, policy=None) -> None:
        return super().append(key, bin, val, meta=meta, policy=policy)

    @catch_unexpected("Client.prepend")
    def prepend(self, key, bin, val, meta=None, policy=None) -> None:
        return super().prepend(key, bin, val, meta=meta, policy=policy)

    @catch_unexpected("Client.increment")
    def increment(self, key, bin, offset, meta=None, policy=None) -> None:
        return super().increment(key, bin, offset, meta=meta, policy=policy)

    @catch_unexpected("Client.remove_bin")
    def remove_bin(self, key, bin_names, meta=None, policy=None) -> None:
        return super().remove_bin(key, bin_names, meta=meta, policy=policy)

    # -- Index --

    @catch_unexpected("Client.index_integer_create")
    def index_integer_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return super().index_integer_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("Client.index_string_create")
    def index_string_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return super().index_string_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("Client.index_geo2dsphere_create")
    def index_geo2dsphere_create(self, namespace, set_name, bin_name, index_name, policy=None) -> None:
        return super().index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy)

    @catch_unexpected("Client.index_remove")
    def index_remove(self, namespace, index_name, policy=None) -> None:
        return super().index_remove(namespace, index_name, policy)

    # -- Truncate --

    @catch_unexpected("Client.truncate")
    def truncate(self, namespace, set_name, nanos=0, policy=None) -> None:
        return super().truncate(namespace, set_name, nanos, policy)

    # -- UDF --

    @catch_unexpected("Client.udf_put")
    def udf_put(self, filename, udf_type=0, policy=None) -> None:
        return super().udf_put(filename, udf_type, policy)

    @catch_unexpected("Client.udf_remove")
    def udf_remove(self, module, policy=None) -> None:
        return super().udf_remove(module, policy)

    @catch_unexpected("Client.apply")
    def apply(self, key, module, function, args=None, policy=None):
        return super().apply(key, module, function, args, policy)

    # -- Admin: User --

    @catch_unexpected("Client.admin_create_user")
    def admin_create_user(self, username, password, roles, policy=None) -> None:
        return super().admin_create_user(username, password, roles, policy)

    @catch_unexpected("Client.admin_drop_user")
    def admin_drop_user(self, username, policy=None) -> None:
        return super().admin_drop_user(username, policy)

    @catch_unexpected("Client.admin_change_password")
    def admin_change_password(self, username, password, policy=None) -> None:
        return super().admin_change_password(username, password, policy)

    @catch_unexpected("Client.admin_grant_roles")
    def admin_grant_roles(self, username, roles, policy=None) -> None:
        return super().admin_grant_roles(username, roles, policy)

    @catch_unexpected("Client.admin_revoke_roles")
    def admin_revoke_roles(self, username, roles, policy=None) -> None:
        return super().admin_revoke_roles(username, roles, policy)

    @catch_unexpected("Client.admin_query_user_info")
    def admin_query_user_info(self, username, policy=None):
        return super().admin_query_user_info(username, policy)

    @catch_unexpected("Client.admin_query_users_info")
    def admin_query_users_info(self, policy=None):
        return super().admin_query_users_info(policy)

    # -- Admin: Role --

    @catch_unexpected("Client.admin_create_role")
    def admin_create_role(self, role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0) -> None:
        return super().admin_create_role(role, privileges, policy, whitelist, read_quota, write_quota)

    @catch_unexpected("Client.admin_drop_role")
    def admin_drop_role(self, role, policy=None) -> None:
        return super().admin_drop_role(role, policy)

    @catch_unexpected("Client.admin_grant_privileges")
    def admin_grant_privileges(self, role, privileges, policy=None) -> None:
        return super().admin_grant_privileges(role, privileges, policy)

    @catch_unexpected("Client.admin_revoke_privileges")
    def admin_revoke_privileges(self, role, privileges, policy=None) -> None:
        return super().admin_revoke_privileges(role, privileges, policy)

    @catch_unexpected("Client.admin_query_role")
    def admin_query_role(self, role, policy=None):
        return super().admin_query_role(role, policy)

    @catch_unexpected("Client.admin_query_roles")
    def admin_query_roles(self, policy=None):
        return super().admin_query_roles(policy)

    @catch_unexpected("Client.admin_set_whitelist")
    def admin_set_whitelist(self, role, whitelist, policy=None) -> None:
        return super().admin_set_whitelist(role, whitelist, policy)

    @catch_unexpected("Client.admin_set_quotas")
    def admin_set_quotas(self, role, read_quota=0, write_quota=0, policy=None) -> None:
        return super().admin_set_quotas(role, read_quota, write_quota, policy)

    # -- Utility --

    @catch_unexpected("Client.ping")
    def ping(self) -> bool:
        return super().ping()

    @catch_unexpected("Client.is_connected")
    def is_connected(self) -> bool:
        return super().is_connected()

    @catch_unexpected("Client.get_node_names")
    def get_node_names(self) -> list[str]:
        return super().get_node_names()

    # -- Query --

    def query(self, namespace, set_name) -> Query:
        return Query(super().query(namespace, set_name))

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        logger.debug("Closing client connection")
        self.close()
        return False
