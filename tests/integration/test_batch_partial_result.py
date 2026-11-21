"""What a batch call reports per record, and what it reports when it fails as a whole.

Two things are pinned here, on both clients.

**Rows.** ``BatchRecord.result`` is ``0`` only when a server said the record
succeeded. A server failure carries the server's code (``2`` not found, ``20``
unknown namespace, ``27`` filtered out). A record no server answered for
carries ``-1``, and ``error_type`` says which kind of ``-1`` it is.

**Exceptions.** A batch call that fails as a whole raises the exception the
failure always raised. The rows are not thrown away: ``exc.partial_result`` is a
``BatchWriteResult`` with one entry per requested record, in request order.

A whole-call failure needs a node to fail. Two are reachable on one healthy
node without racing it: a namespace no node serves (nothing can be routed), and
a UDF that is still running when the client's deadline passes. A node that
stops while the others keep answering is covered by ``tests/multinode``.
"""

import pytest

import aerospike_py
from aerospike_py import exp
from aerospike_py.types import BatchRetryInfo, BatchWriteResult
from tests import AEROSPIKE_CONFIG
from tests.helpers import invoke
from tests.server import skip_or_raise

NS = "test"
SET_NAME = "batch_partial"
NO_SUCH_NS = "no_such_namespace"

# ``slow_udf.spin`` loops this many times before it returns. The Lua
# interpreter needs several hundred milliseconds for it, and no machine runs
# it inside 50 ms, so the client always stops waiting first.
#
# The wait is cut short by ``socket_timeout`` alone. With a ``total_timeout``
# the client also tells the server how long it will wait, and the server
# aborts the UDF at that very moment: which of the two is noticed first would
# be a race. With ``total_timeout = 0`` the server applies its own limit
# (one second by default), far beyond the client's 50 ms.
SLOW_UDF_FILE = "tests/slow_udf.lua"
SPIN_ROUNDS = 60_000_000
SHORT_DEADLINE = {"total_timeout": 0, "socket_timeout": 50}


@pytest.fixture(scope="module")
def slow_udf():
    """Register the UDF once; wait until the node serves it."""
    import time

    try:
        admin = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception as e:
        skip_or_raise(e)
    admin.udf_put(SLOW_UDF_FILE)
    probe = (NS, SET_NAME, "udf_probe")
    admin.put(probe, {"v": 1})
    deadline = time.monotonic() + 10
    while True:
        try:
            admin.apply(probe, "slow_udf", "spin", [1])
            break
        except aerospike_py.AerospikeError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)
    yield
    # A timed-out call leaves its UDF running on the server; removing the
    # module underneath it would only turn the leftover work into errors.
    admin.remove(probe)
    admin.close()


async def _rows_of_batch_read(any_client, keys, **kwargs):
    lazy = await invoke(any_client, "batch_read", keys, **kwargs)
    return lazy.batch_records


class TestRowsOfACallThatReturns:
    async def test_read_tells_found_missing_and_unroutable_apart(self, any_client, any_cleanup):
        present = (NS, SET_NAME, "present")
        missing = (NS, SET_NAME, "missing")
        unroutable = (NO_SUCH_NS, SET_NAME, "anything")
        any_cleanup.append(present)
        await invoke(any_client, "put", present, {"v": 1})

        rows = await _rows_of_batch_read(any_client, [present, missing, unroutable])

        assert [br.result for br in rows] == [
            aerospike_py.AEROSPIKE_OK,
            aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND,
            20,  # the server-side code for a namespace it does not have
        ]
        assert [br.error_type for br in rows] == [None, "KeyNotFoundError", "InvalidNamespace"]
        assert [br.in_doubt for br in rows] == [False, False, False]
        assert rows[0].record is not None
        assert rows[1].record is None and rows[2].record is None

    async def test_read_reports_a_filtered_out_record(self, any_client, any_cleanup):
        kept = (NS, SET_NAME, "kept")
        dropped = (NS, SET_NAME, "dropped")
        any_cleanup.extend([kept, dropped])
        await invoke(any_client, "put", kept, {"v": 1})
        await invoke(any_client, "put", dropped, {"v": 2})

        only_v1 = {"filter_expression": exp.eq(exp.int_bin("v"), exp.int_val(1))}
        rows = await _rows_of_batch_read(any_client, [kept, dropped], policy=only_v1)

        assert [br.result for br in rows] == [0, aerospike_py.AEROSPIKE_ERR_FILTERED_OUT]
        assert [br.error_type for br in rows] == [None, "FilteredOut"]

    async def test_write_tells_written_and_unroutable_apart(self, any_client, any_cleanup):
        good = (NS, SET_NAME, "written")
        any_cleanup.append(good)

        result = await invoke(
            any_client,
            "batch_write",
            [(good, {"v": 7}), ((NO_SUCH_NS, SET_NAME, "nowhere"), {"v": 7})],
        )

        assert [br.result for br in result.batch_records] == [0, 20]
        assert [br.error_type for br in result.batch_records] == [None, "InvalidNamespace"]
        assert (await invoke(any_client, "get", good)).bins == {"v": 7}

    async def test_write_reports_a_record_that_already_exists(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "exists")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        result = await invoke(
            any_client,
            "batch_write",
            [(key, {"v": 2})],
            policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
        )

        (row,) = result.batch_records
        assert row.result == aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS
        assert row.error_type == "KeyExistsError"
        assert row.in_doubt is False, "the server answered, so nothing is in doubt"
        assert (await invoke(any_client, "get", key)).bins == {"v": 1}

    async def test_a_successful_row_has_no_error_type(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "fine")
        any_cleanup.append(key)

        result = await invoke(any_client, "batch_write", [(key, {"v": 1})])

        (row,) = result.batch_records
        assert (row.result, row.error_type, row.in_doubt) == (0, None, False)


class TestNothingCouldBeRouted:
    """Every key names a namespace no node serves: the call fails before it sends anything."""

    @pytest.mark.parametrize("method", ["batch_read", "batch_write", "batch_remove", "batch_operate"])
    async def test_the_exception_carries_one_row_per_requested_key(self, any_client, method):
        keys = [(NO_SUCH_NS, SET_NAME, f"k{i}") for i in range(3)]
        args = {
            "batch_read": (keys,),
            "batch_write": ([(key, {"v": 1}) for key in keys],),
            "batch_remove": (keys,),
            "batch_operate": (keys, [{"op": aerospike_py.OPERATOR_INCR, "bin": "v", "val": 1}]),
        }[method]

        with pytest.raises(aerospike_py.InvalidArgError, match=NO_SUCH_NS) as excinfo:
            await invoke(any_client, method, *args)

        exc = excinfo.value
        assert exc.result_code == -1
        assert exc.error_type == "InvalidArgument"
        partial = exc.partial_result
        assert isinstance(partial, BatchWriteResult)
        assert [br.key[:3] for br in partial.batch_records] == keys, (
            "the rows name the requested keys, in request order"
        )
        assert {(br.result, br.error_type, br.in_doubt) for br in partial.batch_records} == {(-1, "NoResponse", False)}
        assert all(br.record is None for br in partial.batch_records)


class TestDeadlineExpires:
    """The request was sent, and the client stopped waiting before the answer came."""

    async def test_batch_apply_raises_the_timeout_and_marks_every_row_in_doubt(self, any_client, any_cleanup, slow_udf):
        keys = [(NS, SET_NAME, f"slow_{i}") for i in range(2)]
        any_cleanup.extend(keys)
        await invoke(any_client, "batch_write", [(key, {"v": 1}) for key in keys])

        with pytest.raises(aerospike_py.AerospikeTimeoutError) as excinfo:
            await invoke(any_client, "batch_apply", keys, "slow_udf", "spin", [SPIN_ROUNDS], policy=SHORT_DEADLINE)

        exc = excinfo.value
        assert (exc.result_code, exc.error_type) == (-1, "Timeout")
        assert exc.in_doubt is True, "the UDF call reached the server; it may have run"
        partial = exc.partial_result
        assert isinstance(partial, BatchWriteResult)
        assert [br.key[:3] for br in partial.batch_records] == keys
        assert {(br.result, br.error_type, br.in_doubt) for br in partial.batch_records} == {(-1, "Timeout", True)}
        assert partial.retry == BatchRetryInfo(), "batch_apply has no retry loop"

    async def test_a_single_record_write_reports_the_same_way(self, any_client, any_cleanup, slow_udf):
        key = (NS, SET_NAME, "slow_single")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        with pytest.raises(aerospike_py.AerospikeTimeoutError) as excinfo:
            await invoke(any_client, "apply", key, "slow_udf", "spin", [SPIN_ROUNDS], policy=SHORT_DEADLINE)

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (-1, "Timeout", True)
        assert exc.partial_result is None, "not a batch call"


class TestRetryCountersOnAFailedCall:
    async def test_they_travel_with_the_exception(self, any_client):
        """A call that raised used to lose its counters: only the log knew how many attempts ran."""
        records = [((NO_SUCH_NS, SET_NAME, f"k{i}"), {"v": 1}) for i in range(3)]

        with pytest.raises(aerospike_py.InvalidArgError) as excinfo:
            await invoke(any_client, "batch_write", records, retry=3)

        retry = excinfo.value.partial_result.retry
        assert retry.max_attempts == 4
        assert retry.attempts == 1, "an unknown namespace fails the same way again, so it is not re-sent"
        assert retry.unresolved == 0, "no record is left that another attempt could help"
        assert retry.truncated_by_timeout is False


class TestOtherFailuresHaveNoPartialResult:
    async def test_a_single_record_failure(self, any_client):
        with pytest.raises(aerospike_py.RecordNotFound) as excinfo:
            await invoke(any_client, "get", (NS, SET_NAME, "never_written"))

        assert excinfo.value.partial_result is None

    async def test_a_rejected_argument(self, any_client):
        with pytest.raises(aerospike_py.InvalidArgError) as excinfo:
            await invoke(any_client, "batch_write", [((NS, SET_NAME, "k"), {"v": 1})], policy={"exists": 99})

        assert excinfo.value.partial_result is None, "nothing was attempted"
