"""A node stops while the other keeps answering.

One batch call spans both nodes. When node 2 is killed, part of the batch can
no longer be delivered. What the client reports about each record must then be
true, and what it re-sends must be safe. Each scenario checks the report
against what the cluster actually holds afterwards: the record's value and its
generation, which counts how many times the record was written.

The namespace keeps two copies of every record, so nothing is lost when node 2
goes away and the surviving node can be asked what happened.

Three things can happen to a record whose node is gone, and the scenarios do
not depend on which one does:

- the request never left the client (connection refused): ``result == -1``,
  ``in_doubt`` false — certainly not applied;
- the request left and no answer came back: ``result == -1``, ``in_doubt``
  true — applied or not;
- the surviving node took the write, could not replicate it to the node that
  is gone, and answered ``TIMEOUT``: ``result == 9``, ``in_doubt`` true. The
  write is on the master. Rust client 3.0 does not flag such a batch row;
  the binding does, and the last scenario is what found that.
"""

import time

import pytest

import aerospike_py
from aerospike_py.types import BatchWriteResult
from tests.helpers import invoke

pytestmark = pytest.mark.destructive

NS = "test"
SET_NAME = "node_failure"
RECORDS = 200

# Short enough that a request to the dead node gives up quickly, long enough
# that a healthy node always answers.
IMPATIENT = {"total_timeout": 3_000, "socket_timeout": 500}
PATIENT = {"total_timeout": 30_000, "socket_timeout": 500}


def _keys(prefix: str) -> list[tuple[str, str, str]]:
    return [(NS, SET_NAME, f"{prefix}_{i}") for i in range(RECORDS)]


async def _rows_of(any_client, method, *args, **kwargs):
    """Run a batch call and return ``(rows, retry, exception or None)``.

    The rows are the same thing whether the call returned them or raised with
    them attached.
    """
    try:
        result = await invoke(any_client, method, *args, **kwargs)
    except aerospike_py.AerospikeError as exc:
        partial = exc.partial_result
        assert isinstance(partial, BatchWriteResult), f"{type(exc).__name__} carried no rows: {exc}"
        return partial.batch_records, partial.retry, exc
    return result.batch_records, result.retry, None


def _state(observer, keys, timeout: float = 30.0) -> dict[str, tuple[int, dict] | None]:
    """``{user_key: (generation, bins) | None}`` as the cluster holds it now."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            rows = observer.batch_read(keys, policy=PATIENT).batch_records
        except aerospike_py.AerospikeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
            continue
        if all(br.result in (0, aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND) for br in rows):
            return {br.key[2]: (br.record[1]["gen"], br.record[2]) if br.result == 0 else None for br in rows}
        if time.monotonic() >= deadline:
            raise AssertionError(f"could not read the records back: { {br.result for br in rows} }")
        time.sleep(0.2)


def _assert_rows_are_complete(rows, keys):
    assert [br.key[:3] for br in rows] == keys, "one row per requested record, in request order"
    for br in rows:
        if br.result == 0:
            assert br.error_type is None and br.in_doubt is False
        else:
            assert br.error_type, f"a failed row must say why: {br}"
        if br.result == aerospike_py.AEROSPIKE_ERR_TIMEOUT:
            # The server gave up waiting, usually for the replica that is
            # gone, after the master may already have taken the write.
            assert br.in_doubt is True, f"a write the server timed out is in doubt: {br}"


class TestWithoutRetry:
    async def test_every_row_tells_the_truth_about_its_record(self, any_client, observer, cluster):
        keys = _keys(f"truth_{id(any_client)}")
        try:
            await invoke(any_client, "batch_write", [(key, {"v": 1}) for key in keys], policy=PATIENT)
            before = _state(observer, keys)
            assert all(state is not None for state in before.values())

            cluster.stop_victim()
            rows, _, exc = await _rows_of(
                any_client, "batch_write", [(key, {"v": 2}) for key in keys], policy=IMPATIENT
            )

            assert exc is not None, "half of the batch belongs to a node that is gone"
            assert isinstance(exc, (aerospike_py.ClusterError, aerospike_py.AerospikeTimeoutError))
            _assert_rows_are_complete(rows, keys)
            failed = [br for br in rows if br.result != 0]
            assert failed, "the node that is gone cannot have answered"
            assert {br.result for br in failed} <= {-1, aerospike_py.AEROSPIKE_ERR_TIMEOUT}, (
                "a record either got no answer, or the surviving node gave up waiting for its dead replica"
            )

            cluster.wait_for_survivor_alone()
            after = _state(observer, keys)
            for br in rows:
                user_key = br.key[2]
                gen_before, _ = before[user_key]
                gen_after, bins_after = after[user_key]
                if br.result == 0:
                    assert bins_after == {"v": 2}, f"{user_key}: reported written, holds {bins_after}"
                    assert gen_after == gen_before + 1
                elif not br.in_doubt:
                    assert bins_after == {"v": 1}, f"{user_key}: reported certainly not applied, holds {bins_after}"
                    assert gen_after == gen_before
                else:
                    assert bins_after in ({"v": 1}, {"v": 2})
                    assert gen_after - gen_before == (1 if bins_after == {"v": 2} else 0)
        finally:
            cluster.wait_for_survivor_alone()
            observer.batch_remove(keys, policy=PATIENT)

    async def test_an_increment_is_never_applied_twice(self, any_client, observer, cluster):
        """No automatic re-send for a write batch: a lost answer must not double the count."""
        keys = _keys(f"incr_{id(any_client)}")
        increment = [{"op": aerospike_py.OPERATOR_INCR, "bin": "n", "val": 1}]
        try:
            await invoke(any_client, "batch_write", [(key, {"n": 0}) for key in keys], policy=PATIENT)

            cluster.stop_victim()
            rows, _, _ = await _rows_of(any_client, "batch_operate", keys, increment, policy=IMPATIENT)

            _assert_rows_are_complete(rows, keys)
            cluster.wait_for_survivor_alone()
            after = _state(observer, keys)
            for br in rows:
                user_key = br.key[2]
                _, bins = after[user_key]
                assert bins["n"] in (0, 1), f"{user_key}: incremented {bins['n']} times by one call"
                if br.result == 0:
                    assert bins["n"] == 1
                elif not br.in_doubt:
                    assert bins["n"] == 0
        finally:
            cluster.wait_for_survivor_alone()
            observer.batch_remove(keys, policy=PATIENT)


class TestWithRetry:
    async def test_a_plain_write_is_completed_by_the_retries(self, any_client, observer, cluster):
        keys = _keys(f"plain_{id(any_client)}")
        try:
            await invoke(any_client, "batch_write", [(key, {"v": 1}) for key in keys], policy=PATIENT)
            before = _state(observer, keys)

            cluster.stop_victim()
            rows, retry, exc = await _rows_of(
                any_client, "batch_write", [(key, {"v": 2}) for key in keys], policy=PATIENT, retry=40
            )

            assert exc is None, f"the surviving node can take every record once the cluster has re-formed: {exc}"
            assert [br.result for br in rows] == [0] * RECORDS
            assert retry.attempts > 1, "the first attempt cannot have reached the node that is gone"
            assert retry.unresolved == 0 and retry.truncated_by_timeout is False

            cluster.wait_for_survivor_alone()
            after = _state(observer, keys)
            for user_key, (gen_before, _) in before.items():
                gen_after, bins_after = after[user_key]
                assert bins_after == {"v": 2}
                # Once, or twice when a send whose answer was lost had in fact
                # been applied: a plain put may be repeated.
                assert gen_after - gen_before in (1, 2)
        finally:
            cluster.wait_for_survivor_alone()
            observer.batch_remove(keys, policy=PATIENT)

    async def test_a_write_that_was_applied_is_never_sent_again(self, any_client, observer, cluster):
        """CREATE_ONLY makes a second send visible: it fails with KEY_EXISTS.

        Rust client 2.x reported a failed call without its rows, so the retry
        had to send the whole batch again and every record that had already
        been created came back as a failure.
        """
        keys = _keys(f"create_{id(any_client)}")
        create_only = {**PATIENT, "exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}
        try:
            observer.batch_remove(keys, policy=PATIENT)

            cluster.stop_victim()
            rows, retry, _ = await _rows_of(
                any_client, "batch_write", [(key, {"v": 1}) for key in keys], policy=create_only, retry=40
            )

            _assert_rows_are_complete(rows, keys)
            assert aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS not in {br.result for br in rows}, (
                "a record came back KEY_EXISTS: it was created and then sent again"
            )
            assert any(br.result == 0 for br in rows), "the surviving node's records were created"

            cluster.wait_for_survivor_alone()
            after = _state(observer, keys)
            for br in rows:
                user_key = br.key[2]
                state = after[user_key]
                if br.result == 0:
                    assert state == (1, {"v": 1}), f"{user_key}: reported created, holds {state}"
                elif not br.in_doubt:
                    assert state is None, f"{user_key}: reported certainly not created, holds {state}"
                else:
                    assert state in (None, (1, {"v": 1})), f"{user_key}: in doubt, holds {state}"
            assert retry.max_attempts == 41
        finally:
            cluster.wait_for_survivor_alone()
            observer.batch_remove(keys, policy=PATIENT)
