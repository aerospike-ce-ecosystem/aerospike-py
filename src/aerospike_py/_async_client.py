"""Async Client and AsyncQuery wrappers with NamedTuple result conversion."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
import threading
from typing import Any

from typing import TYPE_CHECKING

from aerospike_py._aerospike import AerospikeError
from aerospike_py._aerospike import AsyncClient as _NativeAsyncClient
from aerospike_py._aerospike import Query as _NativeQuery
from aerospike_py._bug_report import _maybe_log, catch_unexpected
from aerospike_py._client import (
    _wrap_batch_write_result,
    _wrap_partial_result,
    _wrap_exists,
    _wrap_operate_ordered,
    _wrap_record,
)
from aerospike_py.types import (
    BatchWriteResult,
    ExistsResult,
    InfoNodeResult,
    OperateOrderedResult,
    Record,
)

if TYPE_CHECKING:
    from aerospike_py._aerospike import LazyBatchRecords

logger = logging.getLogger("aerospike_py")


# ---------------------------------------------------------------------------
# AsyncQuery Python wrapper
# ---------------------------------------------------------------------------


def _says_stop(result: Any) -> bool:
    """Whether a ``foreach`` callback's return value asks for the query to stop.

    ``False`` does, and so does NumPy's ``False`` (what a comparison on a NumPy
    scalar returns). Nothing else: ``None``, ``0`` and ``""`` mean "go on", as
    they do for the sync ``Query.foreach``.
    """
    if result is False:
        return True
    kind = type(result)
    return kind.__module__ == "numpy" and kind.__name__ in ("bool", "bool_") and not result


async def _in_thread_to_completion(function, argument, stop: threading.Event):
    """Run ``function(argument)`` in a worker thread; return only once it has returned.

    A thread cannot be interrupted. If the awaiting task is cancelled while the
    worker runs, ``stop`` is set, so that the worker starts nothing new, and the
    cancellation is raised after the worker has finished what it was doing. When
    the ``CancelledError`` reaches the caller, nothing of ``function`` is running
    any more and nothing of it will start.

    ``function`` must look at ``stop`` before it does anything: a call that is
    still waiting for a thread when the cancellation arrives is not waited for.

    The worker is a plain future of the executor and not a task. A task would
    be cancelled together with the caller by anything that cancels every task
    of the loop (``asyncio.run()`` on its way out does), and a cancelled task
    reports itself done while its thread is still running.
    """
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    started = threading.Event()

    def run():
        started.set()
        return context.run(function, argument)

    worker = loop.run_in_executor(None, run)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        stop.set()
        # Not started: when it does start it finds ``stop`` set (it was set
        # before ``started`` was looked at) and returns without doing anything.
        while started.is_set() and not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Cancelled again while waiting. The worker still cannot be
                # interrupted, so keep waiting for it.
                continue
            except BaseException:  # the cancellation outranks whatever the worker raised
                break
        if worker.done() and not worker.cancelled():
            worker.exception()  # retrieved, so asyncio does not log it as unhandled
        raise


class AsyncRecordStream:
    """The records of a running query, one at a time, as they arrive.

    Returned by ``AsyncQuery.stream()``; ``async for record in query`` uses one.
    Nothing is sent to the cluster until the first record is asked for.

    The query stops when the stream ends, when ``close()`` is called, when the
    ``async with`` block is left, or when the stream is garbage collected —
    which, in CPython, is the moment an ``async for`` loop is left with
    ``break`` or by an exception and nothing else refers to the stream.

    Every record is handed out once. Several tasks may iterate the same
    stream: each record goes to one of them.

    Memory stays bounded whatever the pace of the consumer: at most
    ``record_queue_size`` records (default 1024) wait in the client, plus the
    batch being handed out. While they wait the server is not read from. If
    the consumer pauses for longer than the server is willing to wait, the
    server drops the connection and the client fetches the rest again when
    reading resumes, without repeating a record; a query that is dropped more
    often than its ``max_retries`` allows fails.

    Cancelling a task that is waiting for the next record closes the stream:
    a record the read had already taken cannot be put back. A later read on
    that stream raises ``RuntimeError`` instead of ending the iteration, so
    that records lost this way cannot be mistaken for the end of the query.
    ``asyncio.wait_for(anext(stream), ...)`` cancels the read when it times
    out; to bound a wait, put the timeout around the whole loop.
    """

    #: How many records are taken from the client in one go. Records beyond the
    #: first are only taken when they have already arrived, so this bounds the
    #: batch without delaying anything.
    _BATCH = 256

    def __init__(self, inner):
        self._inner = inner
        self._batch: list = []
        self._position = 0
        # Held by the task that fetches the next batch; the others wait for it
        # and then find the batch it fetched.
        self._refill = asyncio.Lock()
        self._read_was_cancelled = False

    def __aiter__(self) -> "AsyncRecordStream":
        return self

    async def __anext__(self) -> Record:
        while self._position >= len(self._batch):
            async with self._refill:
                if self._position < len(self._batch):
                    break  # another task fetched while this one waited
                batch = await self._next_batch()
                if batch is None or self._inner.closed:
                    raise StopAsyncIteration
                self._batch = batch
                self._position = 0
        raw = self._batch[self._position]
        self._position += 1
        return _wrap_record(raw)

    async def _next_batch(self) -> list | None:
        """The records that have arrived (at least one), or ``None`` at the end."""
        if self._read_was_cancelled:
            raise RuntimeError(
                "this stream was closed because a read on it was cancelled, and records may be missing; "
                "open a new stream with query.stream()"
            )
        try:
            return await self._inner.next_batch(self._BATCH)
        except asyncio.CancelledError:
            # A record the read had already taken when the cancellation arrived
            # cannot be put back. Ending the stream here, and refusing later
            # reads, is what keeps a cancelled read from silently skipping
            # records.
            self._read_was_cancelled = True
            self.close()
            raise

    def close(self) -> None:
        """Stop the query and drop the records not yet handed out. Idempotent."""
        self._inner.close()
        self._batch = []
        self._position = 0

    def _abandon(self) -> None:
        """Stop the query without recording a duration for it: the caller's code failed, not the query."""
        self._inner.abandon()
        self._batch = []
        self._position = 0

    async def aclose(self) -> None:
        """Same as ``close()``; for ``contextlib.aclosing`` and similar helpers."""
        self.close()

    @property
    def closed(self) -> bool:
        """Whether ``close()`` has been called."""
        return self._inner.closed

    async def __aenter__(self) -> "AsyncRecordStream":
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        self.close()
        return False


class AsyncQuery:
    """Async Python wrapper around the native Query object that returns typed records.

    ``select()`` and ``where()`` are synchronous setup methods. ``results()``,
    ``foreach()`` and ``async for record in query`` read the query's record
    stream by awaiting it, so cancelling the task that runs them stops the query.
    """

    def __init__(self, inner: _NativeQuery):
        self._inner = inner

    def select(self, *bins: str) -> None:
        self._inner.select(*bins)

    def where(self, predicate) -> None:
        self._inner.where(predicate)

    def stream(self, policy=None) -> AsyncRecordStream:
        """Open the query as an async iterator of records. See ``AsyncRecordStream``."""
        return AsyncRecordStream(self._inner.stream(policy))

    def __aiter__(self) -> AsyncRecordStream:
        return self.stream()

    @catch_unexpected("AsyncQuery.results")
    async def results(self, policy=None) -> list[Record]:
        stream = self.stream(policy)
        records: list[Record] = []
        try:
            while (batch := await stream._next_batch()) is not None:
                records.extend(map(_wrap_record, batch))
        finally:
            stream.close()
        return records

    async def foreach(self, callback, policy=None) -> None:
        if inspect.iscoroutinefunction(callback):
            raise TypeError(
                "foreach() calls its callback from a worker thread and cannot await it; "
                "to await something for each record, use 'async for record in query'"
            )
        stop = threading.Event()
        raised_by_callback: list[BaseException] = []

        def deliver(batch: list) -> bool:
            """Call the callback for each record; False when the query should stop."""
            for raw in batch:
                if stop.is_set():
                    return False
                record = _wrap_record(raw)
                try:
                    result = callback(record)
                except BaseException as exc:
                    # Carried to the awaiting task by hand and raised there. A
                    # future cannot carry every exception: ``StopIteration``
                    # set on one is refused or replaced, depending on the
                    # Python version.
                    raised_by_callback.append(exc)
                    return False
                if _says_stop(result):
                    return False
            return True

        stream = self.stream(policy)
        try:
            while (batch := await stream._next_batch()) is not None:
                goes_on = await _in_thread_to_completion(deliver, batch, stop)
                if raised_by_callback:
                    raise raised_by_callback[0]
                if not goes_on:
                    break
        except Exception as exc:
            # What the caller's own callback raised is the caller's to handle,
            # not a sign of a bug in this library.
            if not raised_by_callback:
                _maybe_log("AsyncQuery.foreach", exc)
            raise
        finally:
            if raised_by_callback:
                stream._abandon()
            else:
                stream.close()


# ---------------------------------------------------------------------------
# AsyncClient
# ---------------------------------------------------------------------------


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
        self,
        keys: list,
        bins: list[str] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> "LazyBatchRecords":
        """Read multiple records in a single batch call.

        Returns a ``LazyBatchRecords`` — a zero-conversion wrapper around
        the raw Rust results. Call one of its methods to materialise:

        * ``lazy_records.to_dict()`` → ``dict[UserKey, AerospikeRecord]``
        * ``lazy_records.to_numpy(dtype)`` → ``NumpyBatchRecords`` (GIL released
          during the structured-array fill — ideal for FastAPI/PyTorch
          inference workers)
        * ``lazy_records.batch_records`` → ``list[BatchRecord]`` (compat)

        The async future itself completes with near-zero GIL cost
        (``Arc::new`` + ``Py::new``), so concurrent ``batch_read`` futures
        release their ``spawn_blocking`` threads almost immediately. The
        heavier dict / numpy conversion happens here in the coroutine on
        the event loop, where there is no GIL contention between
        concurrent callers.

        Args:
            keys: List of ``(namespace, set, primary_key)`` tuples.
            bins: Optional list of bin names to read. ``None`` reads all
                bins; an empty list performs an existence check only.
            policy: Optional batch policy dict.

        Returns:
            ``LazyBatchRecords`` — call ``.to_dict()`` / ``.to_numpy(dtype)``
            to materialise the result.

        Example:
            ```python
            keys = [("test", "demo", f"user_{i}") for i in range(10)]
            lazy_records = await client.batch_read(keys, bins=["name", "age"])
            for user_key, bins_dict in lazy_records.to_dict().items():
                print(user_key, bins_dict)
            ```
        """
        try:
            return await self._inner.batch_read(keys, bins, policy)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise

    @catch_unexpected("AsyncClient.batch_write_numpy")
    async def batch_write_numpy(
        self, data, namespace: str, set_name: str, _dtype=None, key_field: str = "_key", policy=None, retry: int = 0
    ) -> BatchWriteResult:
        """Write multiple records from a numpy structured array (async).

        Each row of the structured array becomes a separate write operation.
        The dtype must contain a key field (default ``_key``) for the record key.
        Remaining non-underscore-prefixed fields become bins.

        Every row is copied out of the array before this coroutine first
        yields, so mutating ``data`` afterwards does not affect the write.

        Args:
            data: numpy structured array with record data. Its own
                ``data.dtype`` defines the layout.
            namespace: Target namespace.
            set_name: Target set.
            _dtype: Optional dtype the array is expected to have. When given
                and different from ``data.dtype``, ``ValueError`` is raised
                before anything is sent.
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
            results = await client.batch_write_numpy(data, "test", "demo", retry=10)
            for br in results.batch_records:
                if br.result != 0:
                    print(f"Failed: {br.key}, code={br.result}")
            ```
        """
        try:
            raw = await self._inner.batch_write_numpy(data, namespace, set_name, _dtype, key_field, policy, retry)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise
        return _wrap_batch_write_result(raw)

    @catch_unexpected("AsyncClient.batch_write")
    async def batch_write(self, records, policy=None, retry=0) -> BatchWriteResult:
        """Write multiple records with per-record bins in a single batch call (async).

        See :meth:`AsyncClient.batch_write` in ``__init__.pyi`` for full documentation.
        """
        try:
            raw = await self._inner.batch_write(records, policy, retry)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise
        return _wrap_batch_write_result(raw)

    @catch_unexpected("AsyncClient.batch_operate")
    async def batch_operate(self, keys, ops, policy=None) -> BatchWriteResult:
        try:
            raw = await self._inner.batch_operate(keys, ops, policy)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise
        return _wrap_batch_write_result(raw)

    @catch_unexpected("AsyncClient.batch_remove")
    async def batch_remove(self, keys, policy=None) -> BatchWriteResult:
        try:
            raw = await self._inner.batch_remove(keys, policy)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise
        return _wrap_batch_write_result(raw)

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

    @catch_unexpected("AsyncClient.batch_apply")
    async def batch_apply(self, keys, module, function, args=None, policy=None) -> BatchWriteResult:
        try:
            raw = await self._inner.batch_apply(keys, module, function, args, policy)
        except AerospikeError as exc:
            _wrap_partial_result(exc)
            raise
        return _wrap_batch_write_result(raw)

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
