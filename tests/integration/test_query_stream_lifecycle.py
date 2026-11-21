"""A query that is no longer wanted stops, on the client and on the server.

``AsyncQuery`` reads the query's record stream by awaiting it: ``results()``,
``foreach()`` and ``async for record in query``. Up to 0.14.x the first two ran
the blocking query in a worker thread, so cancelling the awaiting task raised
``CancelledError`` at once while the thread went on fetching records and calling
callbacks to the end of the scan.

What these tests pin:

- every way of reading delivers every record once, also when the client has
  to fetch part of the set again because a node's connection failed, and when
  several tasks read the same stream;
- every way of leaving early — ``break``, ``close()``, ``async with``, a
  callback returning ``False`` or raising, cancelling the task — stops the query
  **on the server**, within a moment and not when the server's socket timeout
  (30 seconds) runs out;
- once a cancelled ``foreach()`` has raised, no callback is running and none
  starts;
- a consumer that pauses does not make the client fetch the whole set.

"Stopped on the server" is read from the server's own job list (``query-show``).
The set is large enough that the server cannot have finished the scan by itself
when a test stops reading: with the consumer paused, the server gets rid of
about 14 MB before the client's bounded queue and the socket buffers are full.
"""

import asyncio
import gc
import logging
import os
import threading
import time
from typing import ClassVar

import pytest

import aerospike_py
from aerospike_py import _async_client, exp
from tests.helpers import invoke

NS = "test"
SET_NAME = "query_stream_lifecycle"

RECORD_COUNT = int(os.environ.get("AEROSPIKE_STREAM_TEST_RECORDS", "100000"))
PAD = "x" * 400

# Stopping takes the time of one hand-over between a node reader and the record
# queue. Two seconds is generous, and far from the 30 seconds it took before.
STOPS_WITHIN = 2.0


@pytest.fixture(scope="module")
def seeded(client):
    for start in range(0, RECORD_COUNT, 5000):
        client.batch_write([((NS, SET_NAME, i), {"v": i, "pad": PAD}) for i in range(start, start + 5000)])
    yield RECORD_COUNT
    client.truncate(NS, SET_NAME, 0)


# Any rate limit makes the server hold its first block of records back for
# seconds, which is the one way to have a read that is certainly still waiting.
THROTTLED = {"records_per_second": 50}


@pytest.fixture(autouse=True)
def no_query_outlives_its_test(client):
    """A query one test left running must not be what the next one observes."""
    yield
    client.info_all("query-abort-all")
    deadline = time.monotonic() + 5
    while _jobs(client) and time.monotonic() < deadline:
        time.sleep(0.05)


def _jobs(observer) -> list[dict[str, str]]:
    """The server's running queries on this module's set."""
    jobs = []
    for _node, _err, text in observer.info_all("query-show"):
        for job in (text or "").split(";"):
            fields = dict(item.split("=", 1) for item in job.split(":") if "=" in item)
            if fields.get("set") == SET_NAME and fields.get("status", "").startswith("active"):
                jobs.append(fields)
    return jobs


async def _wait_until_no_job(observer, within: float = STOPS_WITHIN) -> None:
    deadline = time.monotonic() + within
    while _jobs(observer):
        assert time.monotonic() < deadline, f"the server still runs the query {within}s after it was stopped"
        await asyncio.sleep(0.05)


async def _wait_for(predicate, within: float = 5.0) -> None:
    deadline = time.monotonic() + within
    while not predicate():
        assert time.monotonic() < deadline, "the condition this test waits for never came true"
        await asyncio.sleep(0.001)


def _query_count(error_type: str = "") -> int:
    """How many queries on this module's set the metrics count under ``error_type``."""
    wanted = (f'db_collection_name="{SET_NAME}"', 'db_operation_name="query"', f'error_type="{error_type}"')
    for line in aerospike_py.get_metrics().splitlines():
        if line.startswith("db_client_operation_duration_seconds_count") and all(part in line for part in wanted):
            return int(float(line.rsplit(" ", 1)[1]))
    return 0


class TestEveryRecordOnce:
    async def test_async_for_over_the_query(self, async_client, seeded):
        seen = set()
        async for record in async_client.query(NS, SET_NAME):
            assert isinstance(record, aerospike_py.Record)
            seen.add(record.bins["v"])

        assert seen == set(range(seeded))

    async def test_stream_with_selected_bins(self, async_client, seeded):
        query = async_client.query(NS, SET_NAME)
        query.select("v")
        total = 0

        async with query.stream() as records:
            async for record in records:
                assert list(record.bins) == ["v"]
                total += 1

        assert total == seeded

    async def test_results(self, async_client, seeded):
        records = await async_client.query(NS, SET_NAME).results()

        assert {record.bins["v"] for record in records} == set(range(seeded))
        assert len(records) == seeded

    @pytest.mark.parametrize("wanted", [0, 1, 256, 257, 1023, 1024, 1025, 3000])
    async def test_results_of_every_size(self, async_client, seeded, wanted):
        """A small result is converted when it is taken, a larger one in chunks on the way."""
        query = async_client.query(NS, SET_NAME)
        query.select("v")

        records = await query.results({"filter_expression": exp.lt(exp.int_bin("v"), exp.int_val(wanted))})

        assert all(type(record) is aerospike_py.Record for record in records)
        assert sorted(record.bins["v"] for record in records) == list(range(wanted))

    async def test_several_results_at_once_each_get_every_record(self, async_client, seeded):
        """Their chunks take turns being converted; none may end up in another call's list."""

        async def read() -> list:
            query = async_client.query(NS, SET_NAME)
            query.select("v")
            return await query.results()

        for records in await asyncio.gather(*(read() for _ in range(4))):
            assert len(records) == seeded
            assert {record.bins["v"] for record in records} == set(range(seeded))
            assert all(type(record) is aerospike_py.Record for record in records[:100])

    @pytest.mark.parametrize("wanted", [200, 3000], ids=["converted_when_taken", "converted_in_chunks"])
    async def test_a_panic_while_records_are_converted_is_raised(self, async_client, seeded, wanted, monkeypatch):
        """A panic in the conversion reaches the caller as ``RustPanicError``, whatever the size of the result.

        PyO3 resumes a panic when Python code it called raises its
        ``PanicException``, so a ``Record`` constructor that raises it makes
        the conversion panic. A small result used to be converted after the
        awaited call was over, where nothing caught the panic and the
        ``await`` stayed pending for ever.
        """
        try:
            await async_client.get((NS, SET_NAME, object()))  # an error makes PyO3 create the class
        except Exception:
            pass
        # One class per PyO3 extension in the process; another extension's is
        # an ordinary exception to this one.
        candidates = [cls for cls in BaseException.__subclasses__() if cls.__name__ == "PanicException"]
        assert candidates, "PyO3 has made no PanicException in this process"
        original = _async_client._wrap_record
        outcomes = []

        for panic in candidates:
            calls = 0

            def panicking(raw, panic=panic):
                nonlocal calls
                calls += 1
                if calls == 100:
                    raise panic("a panic in the Record constructor")
                return original(raw)

            monkeypatch.setattr(_async_client, "_wrap_record", panicking)
            query = async_client.query(NS, SET_NAME)
            query.select("v")
            try:
                await asyncio.wait_for(
                    query.results({"filter_expression": exp.lt(exp.int_bin("v"), exp.int_val(wanted))}), 10
                )
                outcomes.append("returned")
            except BaseException as exc:  # PanicException is no Exception
                outcomes.append(type(exc).__name__)
            finally:
                monkeypatch.setattr(_async_client, "_wrap_record", original)

        assert "RustPanicError" in outcomes, outcomes
        assert set(outcomes) <= {"RustPanicError", "PanicException"}, outcomes
        # And no turn in the conversion line went with it.
        assert len(await asyncio.wait_for(async_client.query(NS, SET_NAME).results(), 30)) == seeded

    @pytest.mark.parametrize("wanted", [5, 3000])
    async def test_the_result_is_the_callers_alone(self, async_client, seeded, wanted):
        """Dropping the list frees the records: nothing else refers to it.

        asyncio keeps the result of an awaited future alive until the task that
        awaited it next goes through the event loop. When the list itself was
        that result, a whole query's records outlived the caller's ``del``.
        """
        query = async_client.query(NS, SET_NAME)
        query.select("v")

        records = await query.results({"filter_expression": exp.lt(exp.int_bin("v"), exp.int_val(wanted))})

        assert len(records) == wanted
        keepers = [type(holder).__name__ for holder in gc.get_referrers(records) if isinstance(holder, asyncio.Future)]
        assert keepers == []

    async def test_foreach(self, async_client, seeded):
        seen = []

        await async_client.query(NS, SET_NAME).foreach(lambda record: seen.append(record.bins["v"]))

        assert len(seen) == seeded
        assert set(seen) == set(range(seeded))

    async def test_two_streams_at_once(self, async_client, seeded):
        async def count() -> int:
            total = 0
            async for _ in async_client.query(NS, SET_NAME):
                total += 1
            return total

        assert await asyncio.gather(count(), count()) == [seeded, seeded]


class TestARoundTheClientHasToFetchAgain:
    """A node's connection failing in the middle of a scan must not repeat a record.

    The client then asks for the rest again. The record stream of Rust client
    3.0 resumes from the last record its consumer took, so everything that was
    buffered at that moment is fetched and handed out a second time: about a
    thousand records too many in 40,000 when this was measured. 0.14.x did not
    do that, and neither may this.

    The connection is made to fail by a consumer that pauses for longer than
    the query's socket timeout, which makes the server give up on it, or by a
    socket timeout too short for the scan.
    """

    IMPATIENT_SERVER: ClassVar[dict] = {"socket_timeout": 1000}
    PAUSE_AT = 2000
    PAUSE = 2.5

    def _assert_every_record_once(self, seen: list[int], expected: int) -> None:
        assert len(seen) - len(set(seen)) == 0, f"{len(seen) - len(set(seen))} records were delivered twice"
        assert set(seen) == set(range(expected))

    def test_sync_foreach_with_a_callback_that_pauses(self, client, seeded):
        seen: list[int] = []

        def callback(record):
            seen.append(record.bins["v"])
            if len(seen) == self.PAUSE_AT:
                time.sleep(self.PAUSE)

        client.query(NS, SET_NAME).foreach(callback, self.IMPATIENT_SERVER)

        self._assert_every_record_once(seen, seeded)

    async def test_async_foreach_with_a_callback_that_pauses(self, async_client, seeded):
        seen: list[int] = []

        def callback(record):
            seen.append(record.bins["v"])
            if len(seen) == self.PAUSE_AT:
                time.sleep(self.PAUSE)

        await async_client.query(NS, SET_NAME).foreach(callback, self.IMPATIENT_SERVER)

        self._assert_every_record_once(seen, seeded)

    async def test_async_for_with_a_consumer_that_pauses(self, async_client, seeded):
        seen: list[int] = []

        async for record in async_client.query(NS, SET_NAME).stream(self.IMPATIENT_SERVER):
            seen.append(record.bins["v"])
            if len(seen) == self.PAUSE_AT:
                await asyncio.sleep(self.PAUSE)

        self._assert_every_record_once(seen, seeded)

    @pytest.mark.parametrize("socket_timeout", [2, 4, 6])
    async def test_results_under_a_socket_timeout_too_short_for_the_scan(self, any_client, seeded, socket_timeout):
        """``results()`` is all or nothing: the whole set once, or an error."""
        try:
            records = await invoke(any_client.query(NS, SET_NAME), "results", {"socket_timeout": socket_timeout})
        except aerospike_py.AerospikeError:
            return  # the scan could not be completed under this timeout, and said so

        self._assert_every_record_once([record.bins["v"] for record in records], seeded)


class TestSeveralTasksOnOneStream:
    async def test_each_record_goes_to_one_of_them(self, async_client, seeded):
        stream = async_client.query(NS, SET_NAME).stream()

        async def take() -> list[int]:
            taken = []
            async for record in stream:
                taken.append(record.bins["v"])
                # Let another task in while this one is in the middle of a
                # batch: that task fetching the next batch once replaced the
                # one this task had not finished.
                await asyncio.sleep(0)
            return taken

        parts = await asyncio.gather(*(take() for _ in range(4)))

        seen = [value for part in parts for value in part]
        assert len(seen) == seeded, "tasks reading the same stream lost or repeated records"
        assert set(seen) == set(range(seeded))


class TestNothingIsSentBeforeTheFirstRead:
    async def test_an_unread_stream_costs_nothing(self, async_client, client, seeded):
        before = _query_count()

        stream = async_client.query(NS, SET_NAME).stream()
        await asyncio.sleep(0.2)
        assert _jobs(client) == []
        stream.close()

        assert stream.closed
        assert _query_count() == before, "a query that was never sent is not an operation"
        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()


class TestLeavingEarlyStopsTheQuery:
    async def test_break(self, async_client, client, seeded):
        taken = 0
        async for _ in async_client.query(NS, SET_NAME):
            taken += 1
            if taken == 10:
                break

        await _wait_until_no_job(client)

    async def test_close(self, async_client, client, seeded):
        stream = async_client.query(NS, SET_NAME).stream()
        await stream.__anext__()
        assert len(_jobs(client)) == 1, "the scan must still be running for this test to mean anything"

        stream.close()
        stream.close()

        await _wait_until_no_job(client)
        assert stream.closed
        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()

    async def test_leaving_async_with(self, async_client, client, seeded):
        with pytest.raises(RuntimeError, match="found it"):
            async with async_client.query(NS, SET_NAME).stream() as records:
                async for _ in records:
                    raise RuntimeError("found it")

        assert records.closed
        await _wait_until_no_job(client)

    async def test_cancelling_results(self, async_client, client, seeded):
        task = asyncio.ensure_future(async_client.query(NS, SET_NAME).results())
        await _wait_for(lambda: len(_jobs(client)) == 1)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        await _wait_until_no_job(client)

    async def test_cancelling_a_waiting_read_closes_the_stream(self, async_client, client, seeded):
        """A cancelled read may have taken records that cannot be put back, so the stream ends there.

        And it does not end quietly. ``asyncio.wait_for(anext(stream), ...)``
        cancels the read when it times out; if the next read simply ended the
        iteration, a loop around it would finish with records missing and no
        sign of it.
        """
        stream = async_client.query(NS, SET_NAME).stream(THROTTLED)
        reader = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.2)
        assert not reader.done(), "the throttled scan delivered at once; this test needs a read that waits"

        reader.cancel()

        with pytest.raises(asyncio.CancelledError):
            await reader
        assert stream.closed
        with pytest.raises(RuntimeError, match="a read on it was cancelled"):
            await stream.__anext__()

    async def test_a_stream_the_caller_closed_ends_quietly(self, async_client, seeded):
        stream = async_client.query(NS, SET_NAME).stream()
        await stream.__anext__()

        stream.close()

        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()

    async def test_closing_under_a_waiting_read_ends_it(self, async_client, client, seeded):
        stream = async_client.query(NS, SET_NAME).stream(THROTTLED)
        reader = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.2)
        assert not reader.done(), "the throttled scan delivered at once; this test needs a read that waits"

        stream.close()

        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(reader, timeout=STOPS_WITHIN)

    async def test_many_abandoned_streams_leave_nothing_behind(self, async_client, client, seeded):
        for _ in range(30):
            async for _record in async_client.query(NS, SET_NAME):
                break

        await _wait_until_no_job(client)
        key = (NS, SET_NAME, 0)
        assert (await async_client.get(key)).bins["v"] == 0

    def test_sync_foreach_returning_false(self, client, seeded):
        client.query(NS, SET_NAME).foreach(lambda _record: False)

        deadline = time.monotonic() + STOPS_WITHIN
        while _jobs(client):
            assert time.monotonic() < deadline, "the server still runs a scan whose callback said stop"
            time.sleep(0.05)

    def test_sync_foreach_callback_raising(self, client, seeded):
        def explode(_record):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            client.query(NS, SET_NAME).foreach(explode)

        deadline = time.monotonic() + STOPS_WITHIN
        while _jobs(client):
            assert time.monotonic() < deadline, "the server still runs a scan whose callback raised"
            time.sleep(0.05)


class TestForeach:
    async def test_returning_false_stops_after_that_callback(self, async_client, client, seeded):
        calls = 0

        def stop_at_three(_record):
            nonlocal calls
            calls += 1
            return calls < 3

        await async_client.query(NS, SET_NAME).foreach(stop_at_three)

        assert calls == 3
        await _wait_until_no_job(client)

    async def test_an_exception_from_the_callback_propagates_and_stops(self, async_client, client, seeded):
        calls = 0

        def explode(_record):
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await async_client.query(NS, SET_NAME).foreach(explode)

        assert calls == 1
        await _wait_until_no_job(client)

    async def test_an_exception_from_the_callback_is_not_reported_as_a_bug(self, any_client, seeded, caplog):
        """The caller's callback raised; that says nothing about this library (issue #445)."""

        def explode(_record):
            raise RuntimeError("boom")

        with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError, match="boom"):
            await invoke(any_client.query(NS, SET_NAME), "foreach", explode)

        assert [r.getMessage()[:120] for r in caplog.records if "may be a bug in aerospike-py" in r.getMessage()] == []

    async def test_a_callback_raising_stop_iteration_neither_hangs_nor_is_reported(self, async_client, seeded, caplog):
        """A future cannot carry ``StopIteration``; the exception is carried to the caller another way.

        Leaving a coroutine it becomes ``RuntimeError``, as Python does for every
        ``StopIteration`` that escapes one.
        """

        def callback(_record):
            raise StopIteration

        with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError, match="StopIteration"):
            await asyncio.wait_for(async_client.query(NS, SET_NAME).foreach(callback), timeout=10)

        assert [r.getMessage()[:120] for r in caplog.records if "may be a bug in aerospike-py" in r.getMessage()] == []

    async def test_numpy_false_stops_like_false(self, any_client, seeded):
        """A comparison on a NumPy scalar returns ``numpy.bool``; both clients read it as a bool."""
        np = pytest.importorskip("numpy")
        calls = 0

        def never(_record):
            nonlocal calls
            calls += 1
            return np.int64(1) > np.int64(2)

        await invoke(any_client.query(NS, SET_NAME), "foreach", never)

        assert calls == 1

    async def test_only_a_bool_stops(self, any_client, seeded):
        calls = 0

        def falsy_but_not_false(_record):
            nonlocal calls
            calls += 1
            return 0 if calls < 5 else False

        await invoke(any_client.query(NS, SET_NAME), "foreach", falsy_but_not_false)

        assert calls == 5

    async def test_a_coroutine_callback_is_refused(self, async_client, seeded):
        async def callback(_record):
            return True

        with pytest.raises(TypeError, match="async for"):
            await async_client.query(NS, SET_NAME).foreach(callback)

    async def test_callbacks_run_off_the_event_loop(self, async_client, seeded):
        """A callback may block — it always could — without stalling the loop."""
        loop_thread = threading.get_ident()
        callback_threads = set()
        ticks = 0

        def slow(_record):
            callback_threads.add(threading.get_ident())
            time.sleep(0.3)
            return False

        async def heartbeat():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        beating = asyncio.ensure_future(heartbeat())
        try:
            await async_client.query(NS, SET_NAME).foreach(slow)
        finally:
            beating.cancel()

        assert callback_threads and loop_thread not in callback_threads
        assert ticks >= 10, f"the loop ran {ticks} times in 0.3s; the callback blocked it"


class TestCancellingForeach:
    async def test_no_callback_starts_once_the_cancellation_is_raised(self, async_client, client, seeded):
        calls = 0

        def callback(_record):
            nonlocal calls
            calls += 1

        task = asyncio.ensure_future(async_client.query(NS, SET_NAME).foreach(callback))
        await _wait_for(lambda: calls >= 100)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        at_cancellation = calls
        assert at_cancellation < seeded, "the scan must not have finished for this test to mean anything"
        await asyncio.sleep(0.3)
        assert calls == at_cancellation
        await _wait_until_no_job(client)

    async def test_a_running_callback_finishes_before_the_cancellation_is_raised(self, async_client, client, seeded):
        entered = threading.Event()
        release = threading.Event()
        started = 0
        finished = 0

        def callback(_record):
            nonlocal started, finished
            started += 1
            entered.set()
            release.wait(10)
            finished += 1

        task = asyncio.ensure_future(async_client.query(NS, SET_NAME).foreach(callback))
        await _wait_for(entered.is_set)

        task.cancel()
        await asyncio.sleep(0.1)
        assert not task.done(), "the cancellation was raised while a callback was still running"
        task.cancel()  # a second request changes nothing
        await asyncio.sleep(0.05)
        assert not task.done()

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (started, finished) == (1, 1)
        await asyncio.sleep(0.2)
        assert started == 1, "a callback started after the cancellation had been raised"
        await _wait_until_no_job(client)

    async def test_cancelling_every_task_of_the_loop_still_waits_for_the_callback(self, async_client, client, seeded):
        """What ``asyncio.run()`` does on its way out, and what shutdown code usually does.

        The worker that runs the callback must not be a task: cancelled along
        with everything else, it would report itself done while its thread was
        still inside the callback.
        """
        entered = threading.Event()
        release = threading.Event()
        finished = 0

        def callback(_record):
            nonlocal finished
            entered.set()
            release.wait(10)
            finished += 1

        task = asyncio.ensure_future(async_client.query(NS, SET_NAME).foreach(callback))
        await _wait_for(entered.is_set)

        for other in asyncio.all_tasks() - {asyncio.current_task()}:
            other.cancel()
        await asyncio.sleep(0.1)
        still_running = not task.done()
        release.set()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert still_running, "the cancellation was raised while a callback was still running"
        assert finished == 1
        await _wait_until_no_job(client)


class TestASlowConsumer:
    async def test_a_paused_consumer_bounds_what_is_fetched_and_loses_nothing(self, async_client, client, seeded):
        seen = set()
        stream = async_client.query(NS, SET_NAME).stream()
        seen.add((await stream.__anext__()).bins["v"])

        await asyncio.sleep(0.5)
        (job,) = _jobs(client)
        sent_then = int(job["recs-succeeded"])
        await asyncio.sleep(0.5)
        (job,) = _jobs(client)
        sent_later = int(job["recs-succeeded"])

        assert sent_later == sent_then, "the server went on sending to a consumer that had stopped reading"
        assert sent_then < seeded, "the whole set was fetched for a consumer that took one record"

        async for record in stream:
            seen.add(record.bins["v"])
        assert seen == set(range(seeded))


class TestFailures:
    async def test_a_query_that_cannot_start_raises_from_every_way_of_reading(self, async_client):
        query = async_client.query("no_such_namespace", "no_such_set")

        with pytest.raises(aerospike_py.AerospikeError):
            await query.results()
        with pytest.raises(aerospike_py.AerospikeError):
            await query.foreach(lambda _record: None)
        with pytest.raises(aerospike_py.AerospikeError):
            async for _ in query:
                pass

    async def test_a_bad_policy_is_refused_before_anything_is_sent(self, async_client, seeded):
        with pytest.raises(TypeError, match="partition_filter"):
            async_client.query(NS, SET_NAME).stream({"partition_filter": "not a partition filter"})


class TestTelemetry:
    async def test_a_stream_is_one_query_however_it_ends(self, async_client, seeded):
        before = _query_count()

        async for _ in async_client.query(NS, SET_NAME):
            pass
        assert _query_count() == before + 1

        async for _ in async_client.query(NS, SET_NAME):
            break
        assert _query_count() == before + 2, "a query its caller stopped is an operation, and not a failed one"

    async def test_a_callback_that_raises_is_no_outcome_of_the_query(self, any_client, seeded):
        """The caller's code failed, not the query: nothing is recorded, by either client."""

        def explode(_record):
            raise RuntimeError("boom")

        before = _query_count()

        with pytest.raises(RuntimeError, match="boom"):
            await invoke(any_client.query(NS, SET_NAME), "foreach", explode)

        assert _query_count() == before

    async def test_a_failed_start_is_counted_under_its_error_type(self, async_client):
        wanted = ('db_namespace="no_such_namespace"', 'db_operation_name="query"')

        def failures() -> list[str]:
            return [
                line
                for line in aerospike_py.get_metrics().splitlines()
                if line.startswith("db_client_operation_duration_seconds_count")
                and all(part in line for part in wanted)
                and 'error_type=""' not in line
            ]

        with pytest.raises(aerospike_py.AerospikeError) as excinfo:
            await async_client.query("no_such_namespace", "no_such_set").results()

        assert any(f'error_type="{excinfo.value.error_type}"' in line for line in failures())
