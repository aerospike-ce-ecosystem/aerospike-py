"""``Query.foreach()`` streams rather than buffering — issue #427.

``foreach`` is the API users reach for precisely to *avoid* materialising a large
scan. It used to call ``execute_query_collect`` first, so peak memory was the
whole result set and time-to-first-callback was the whole scan duration, no
matter what the callback did. A caller writing "scan until I find the first
match, then return ``False``" got the entire set fetched and converted before
their callback ran even once.

The load-bearing assertion here is the *ratio* of time-to-first-callback to
whole-scan time. Buffered, the first callback cannot run until the last record
has arrived, so that ratio is the whole fetch phase over fetch-plus-convert —
around 0.5 in practice, since converting records to Python costs roughly what
fetching them does. Streaming interleaves the two, so the ratio collapses to one
record's latency over the whole scan, a few percent. The 0.30 threshold sits
between the two with room on both sides.

Ratios rather than absolute timings, so the test stays meaningful on a slower CI
machine.
"""

import os
import time

import pytest

import aerospike_py
from tests.helpers import invoke

NS = "test"
SET_NAME = "foreach_streaming"

# Large enough that buffering the set is clearly distinguishable from streaming
# it, small enough to seed in about a second.
RECORD_COUNT = int(os.environ.get("AEROSPIKE_FOREACH_TEST_RECORDS", "20000"))
PAD = "x" * 400


@pytest.fixture(scope="module")
def seeded(client):
    """Seed a set big enough for the streaming difference to be measurable."""
    for start in range(0, RECORD_COUNT, 2000):
        client.batch_write(
            [((NS, SET_NAME, f"k{i}"), {"v": i, "pad": PAD}) for i in range(start, min(start + 2000, RECORD_COUNT))]
        )
    yield RECORD_COUNT
    client.truncate(NS, SET_NAME, 0)


def _scan_timings(client, seeded):
    """Return (time-to-first-callback, whole-scan-time) for a full scan."""
    query = client.query(NS, SET_NAME)
    started = time.perf_counter()
    first_callback_at = None
    count = 0

    def callback(_record):
        nonlocal first_callback_at, count
        if first_callback_at is None:
            first_callback_at = time.perf_counter() - started
        count += 1
        return True

    query.foreach(callback)
    total = time.perf_counter() - started
    assert count == seeded, f"scan saw {count} records, expected {seeded}"
    return first_callback_at, total


class TestStreamingContract:
    def test_first_callback_runs_long_before_the_scan_finishes(self, client, seeded):
        """The whole point: the callback must not wait for the last record.

        Measured on this suite's 20k-record set: ~0.47 buffered, ~0.08
        streaming.
        """
        ttfc, total = _scan_timings(client, seeded)

        assert ttfc / total < 0.30, (
            f"time-to-first-callback was {1000 * ttfc:.1f}ms of a {1000 * total:.1f}ms "
            f"scan ({100 * ttfc / total:.0f}%) — the result set is still being "
            "buffered before the first callback"
        )

    def test_returning_false_stops_after_one_callback(self, client, seeded):
        calls = 0

        def stop_immediately(_record):
            nonlocal calls
            calls += 1
            return False

        client.query(NS, SET_NAME).foreach(stop_immediately)

        assert calls == 1

    def test_early_exit_is_far_cheaper_than_a_full_scan(self, client, seeded):
        """Early exit must bound *time*, not just skip an in-memory loop."""
        _, full_scan = _scan_timings(client, seeded)

        started = time.perf_counter()
        client.query(NS, SET_NAME).foreach(lambda _record: False)
        early_exit = time.perf_counter() - started

        assert early_exit < full_scan * 0.30, (
            f"early exit took {1000 * early_exit:.1f}ms vs a {1000 * full_scan:.1f}ms "
            "full scan — the whole set is still being fetched"
        )

    def test_a_full_scan_still_sees_every_record(self, client, seeded):
        seen = set()
        client.query(NS, SET_NAME).foreach(lambda record: seen.add(record.bins["v"]) is None)
        assert len(seen) == seeded

    def test_non_bool_return_values_do_not_stop_iteration(self, client, seeded):
        """Only an explicit ``False`` stops; ``None`` (the usual) must not."""
        calls = 0

        def returns_none(_record):
            nonlocal calls
            calls += 1

        client.query(NS, SET_NAME).foreach(returns_none)

        assert calls == seeded


class TestCallbackEnvironment:
    def test_a_callback_may_call_back_into_the_client(self, client, seeded):
        """Re-entrant client calls from inside the callback keep working.

        This is what stops the streaming loop from being driven inside a single
        ``RUNTIME.block_on``: a nested ``block_on`` from within the Tokio runtime
        panics. Pinning it here so a future refactor cannot quietly break the
        "scan and enrich" pattern.
        """
        looked_up = []

        def enrich(record):
            other = client.get((NS, SET_NAME, "k0"))
            looked_up.append((record.bins["v"], other.bins["v"]))
            return len(looked_up) < 5

        client.query(NS, SET_NAME).foreach(enrich)

        assert len(looked_up) == 5
        assert all(other == 0 for _, other in looked_up)

    def test_an_exception_from_the_callback_propagates(self, client, seeded):
        calls = 0

        def explode(_record):
            nonlocal calls
            calls += 1
            raise ValueError("callback failed")

        with pytest.raises(ValueError, match="callback failed"):
            client.query(NS, SET_NAME).foreach(explode)

        assert calls == 1, "iteration must stop at the raising callback"


class TestAsyncQueryForeach:
    async def test_async_foreach_streams_too(self, async_client, client, seeded):
        """``AsyncQuery.foreach`` runs the same native path via ``to_thread``."""
        query = async_client.query(NS, SET_NAME)
        started = time.perf_counter()
        first_callback_at = None
        count = 0

        def callback(_record):
            nonlocal first_callback_at, count
            if first_callback_at is None:
                first_callback_at = time.perf_counter() - started
            count += 1
            return True

        await query.foreach(callback)
        total = time.perf_counter() - started

        assert count == seeded
        assert first_callback_at / total < 0.30

    async def test_async_early_exit_stops_after_one_callback(self, async_client, seeded):
        calls = 0

        def stop_immediately(_record):
            nonlocal calls
            calls += 1
            return False

        await async_client.query(NS, SET_NAME).foreach(stop_immediately)

        assert calls == 1

    async def test_any_client_foreach_keeps_working(self, any_client, seeded):
        """Sync and async wrappers both still deliver typed records."""
        seen = []

        def collect(record):
            seen.append(record.bins["v"])
            return len(seen) < 10

        query = any_client.query(NS, SET_NAME)
        await invoke(query, "foreach", collect)

        assert len(seen) == 10


class TestQueryErrorsReachTheCaller:
    """A failing query must raise — never read as an empty or short result set.

    These are the streaming loop's error paths. They run in the ordinary suite
    (no server lifecycle control needed), because the mutations they kill —
    swallowing a mid-stream error, and treating a failed query start as an empty
    result — otherwise survive a full CI run.
    """

    def test_a_query_start_failure_propagates_rather_than_looking_empty(self, client, seeded):
        """A query that never starts must raise, not deliver zero records quietly.

        ``partition_filter_by_range(0, 0)`` is the one reachable way to fail
        ``client.query()`` itself from Python: aerospike-py validates the begin
        and begin+count bounds client-side, but a zero count is only rejected
        by ``PartitionTracker::new`` inside aerospike-core, so this exercises the
        query-start error branch rather than the stream one. Without it, a
        mutation that turns that branch into an empty successful scan survives a
        full CI run.
        """
        calls = 0

        def callback(_record):
            nonlocal calls
            calls += 1
            return True

        empty_partition_range = aerospike_py.partition_filter_by_range(0, 0)

        with pytest.raises(aerospike_py.AerospikeError):
            client.query(NS, SET_NAME).foreach(callback, policy={"partition_filter": empty_partition_range})

        assert calls == 0

    def test_an_unknown_namespace_propagates_rather_than_looking_empty(self, client):
        """The stream-level equivalent: no node serves the namespace."""
        calls = 0

        def callback(_record):
            nonlocal calls
            calls += 1
            return True

        with pytest.raises(aerospike_py.AerospikeError):
            client.query("no_such_namespace", "no_such_set").foreach(callback)

        assert calls == 0

    def test_a_mid_stream_failure_raises_after_delivering_a_prefix(self, client, seeded):
        """The behaviour change, pinned executably.

        A query error part-way through now surfaces *after* records have reached
        the callback — buffered, it surfaced before any callback ran. Both halves
        matter: the raise (a swallowed mid-stream error would silently truncate
        the scan and report success) and the non-zero prefix (the semantics this
        PR changes, which callers with side-effecting callbacks must know about).

        The budget is derived from a measured baseline rather than hard-coded, so
        the test tracks machine speed, and it halves on a miss so a fast run
        cannot turn into a flake.
        """
        baseline_ms = _scan_timings(client, seeded)[1] * 1000
        budget_ms = max(15, round(baseline_ms * 0.5))

        for _ in range(5):
            calls = 0

            def callback(_record):
                nonlocal calls
                calls += 1
                return True

            try:
                client.query(NS, SET_NAME).foreach(callback, policy={"total_timeout": budget_ms})
            except aerospike_py.AerospikeError:
                assert calls > 0, (
                    "the query failed before any record was delivered — this test needs a "
                    "failure *during* the scan to pin the partial-delivery semantics"
                )
                assert calls < seeded, "the scan must not have completed"
                return
            budget_ms = max(5, budget_ms // 2)

        pytest.fail(
            f"could not make a {seeded}-record scan time out mid-stream "
            f"(baseline {baseline_ms:.0f}ms); the streaming error path is untested"
        )
