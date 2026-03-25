"""Sync Client and Query wrappers with NamedTuple result conversion."""

from __future__ import annotations

import logging
import time

from aerospike_py._aerospike import Client as _NativeClient
from aerospike_py._aerospike import Query as _NativeQuery
from aerospike_py._bug_report import catch_unexpected
from aerospike_py.types import (
    AerospikeKey,
    BatchRecord as BatchRecordTuple,
    BatchRecords as BatchRecordsTuple,
    BinTuple,
    ExistsResult,
    InfoNodeResult,
    OperateOrderedResult,
    Record,
    RecordMetadata,
)

# Transient error types eligible for batch_write retry.
_RETRIABLE_ERRORS: tuple[str, ...] = ("BackpressureError", "AerospikeTimeoutError", "ClusterError")

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
    return BatchRecordTuple(key=key, result=br.result, record=record)


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

    @catch_unexpected("Client.info_random_node")
    def info_random_node(self, command, policy=None) -> str:
        return super().info_random_node(command, policy)

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
            ``BatchRecords`` (or ``NumpyBatchRecords`` when ``_dtype`` is set).

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            batch = client.batch_read(keys, bins=["name", "age"])
            for br in batch.batch_records:
                if br.result == 0 and br.record is not None:
                    print(br.record.bins)
            ```
        """
        raw = super().batch_read(keys, bins, policy, _dtype)
        if _dtype is not None:
            return raw  # NumpyBatchRecords path unchanged
        return BatchRecordsTuple(batch_records=[_wrap_batch_record(br) for br in raw.batch_records])

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
            retry: Number of retry attempts for transient errors (default ``0``).
                Uses exponential backoff (base 100ms, max 5s) between attempts.
                Retries on BackpressureError, AerospikeTimeoutError, and ClusterError.

        Returns:
            A list of ``Record`` NamedTuples with write results.

        Example:
            ```python
            import numpy as np
            dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
            data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)
            results = client.batch_write_numpy(data, "test", "demo", dtype, retry=3)
            ```
        """
        retry = max(retry, 0)
        last_err: Exception | None = None
        for attempt in range(1 + retry):
            try:
                return [
                    _wrap_record(r)
                    for r in super().batch_write_numpy(data, namespace, set_name, _dtype, key_field, policy)
                ]
            except Exception as e:
                if attempt < retry and type(e).__name__ in _RETRIABLE_ERRORS:
                    last_err = e
                    delay = min(0.1 * (2**attempt), 5.0)
                    logger.warning(
                        "batch_write_numpy attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt + 1,
                        1 + retry,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise
        raise last_err  # pragma: no cover

    @catch_unexpected("Client.batch_operate")
    def batch_operate(self, keys, ops, policy=None) -> list[Record]:
        return [_wrap_record(r) for r in super().batch_operate(keys, ops, policy)]

    @catch_unexpected("Client.batch_remove")
    def batch_remove(self, keys, policy=None) -> list[Record]:
        return [_wrap_record(r) for r in super().batch_remove(keys, policy)]

    def query(self, namespace, set_name) -> Query:
        return Query(super().query(namespace, set_name))

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        logger.debug("Closing client connection")
        self.close()
        return False
