"""What an exception says about the failure, and that the metrics say the same.

Every ``AerospikeError`` carries three attributes besides its message:

- ``result_code``: the server's result code, or ``-1`` when no server answered;
- ``error_type``: a name for the kind of failure, which is what tells the
  ``-1`` cases apart;
- ``in_doubt``: whether a write that failed may have been applied anyway.

The Prometheus ``error_type`` label is derived from the same classification,
so a dashboard and an ``except`` clause cannot disagree about what happened.

Failures that happen to a correct client — a record that is not there, a node
that cannot be reached, an argument the caller got wrong, a UDF that fails —
must not be logged as a possible bug in the client (issue #445).
"""

import logging

import pytest

import aerospike_py
from aerospike_py import exp
from tests.helpers import invoke

NS = "test"
SET_NAME = "error_attrs"

BUG_REPORT_MARKER = "may be a bug in aerospike-py"


def _error_count(operation: str, set_name: str, error_type: str) -> int:
    """How many ``operation`` calls on ``set_name`` the metrics count under ``error_type``."""
    wanted = (
        f'db_collection_name="{set_name}"',
        f'db_operation_name="{operation}"',
        f'error_type="{error_type}"',
    )
    for line in aerospike_py.get_metrics().splitlines():
        if line.startswith("db_client_operation_duration_seconds_count") and all(part in line for part in wanted):
            return int(float(line.rsplit(" ", 1)[1]))
    return 0


class TestServerAnsweredWithAFailure:
    """The server's code is the ``result_code``; nothing is in doubt, because the server answered."""

    async def test_record_not_found(self, any_client):
        with pytest.raises(aerospike_py.RecordNotFound) as excinfo:
            await invoke(any_client, "get", (NS, SET_NAME, "never_written"))

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (2, "KeyNotFoundError", False)
        assert exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND

    async def test_record_exists(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "exists")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        with pytest.raises(aerospike_py.RecordExistsError) as excinfo:
            await invoke(any_client, "put", key, {"v": 2}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (5, "KeyExistsError", False)

    async def test_generation_mismatch(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "generation")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        with pytest.raises(aerospike_py.RecordGenerationError) as excinfo:
            await invoke(any_client, "put", key, {"v": 2}, meta={"gen": 99}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (3, "GenerationError", False)

    async def test_filtered_out(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "filtered")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        never = {"filter_expression": exp.eq(exp.int_bin("v"), exp.int_val(99))}
        with pytest.raises(aerospike_py.FilteredOut) as excinfo:
            await invoke(any_client, "get", key, policy=never)

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (27, "FilteredOut", False)

    async def test_bin_type_error(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "bin_type")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"s": "text"})

        with pytest.raises(aerospike_py.BinTypeError) as excinfo:
            await invoke(any_client, "increment", key, "s", 1)

        exc = excinfo.value
        assert (exc.result_code, exc.error_type) == (12, "BinTypeError")

    async def test_udf_failure(self, any_client, any_cleanup):
        """A UDF the server cannot run is the server's answer, code 100, and a ``UDFError``.

        Up to 0.14.x this surfaced as a plain ``ClientError`` with ``-1`` and was
        logged as a possible bug.
        """
        key = (NS, SET_NAME, "udf")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        with pytest.raises(aerospike_py.UDFError) as excinfo:
            await invoke(any_client, "apply", key, "no_such_module", "no_such_function", [])

        exc = excinfo.value
        assert (exc.result_code, exc.error_type) == (aerospike_py.AEROSPIKE_ERR_UDF, "UdfBadResponse")
        assert isinstance(exc, aerospike_py.ServerError)


class TestNoServerAnswered:
    """``result_code`` is ``-1``; ``error_type`` says which kind of ``-1``."""

    async def test_invalid_policy_value(self, any_client):
        with pytest.raises(aerospike_py.InvalidArgError) as excinfo:
            await invoke(any_client, "put", (NS, SET_NAME, "k"), {"v": 1}, policy={"exists": 99})

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (-1, "InvalidArgument", False)

    async def test_unknown_namespace(self, any_client):
        with pytest.raises(aerospike_py.InvalidArgError) as excinfo:
            await invoke(any_client, "get", ("no_such_namespace", SET_NAME, "k"))

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (-1, "InvalidArgument", False)

    def test_no_node_reachable(self):
        unreachable = aerospike_py.client({"hosts": [("127.0.0.1", 19999)], "timeout": 1000})

        with pytest.raises(aerospike_py.ClusterError) as excinfo:
            unreachable.connect()

        exc = excinfo.value
        assert (exc.result_code, exc.error_type, exc.in_doubt) == (-1, "Connection", False)


class TestAMissIsNotAnErrorForExists:
    async def test_exists_returns_none_meta_and_counts_no_error(self, any_client):
        before = _error_count("exists", SET_NAME, "KeyNotFoundError")

        _, meta = await invoke(any_client, "exists", (NS, SET_NAME, "never_written"))

        assert meta is None
        assert _error_count("exists", SET_NAME, "KeyNotFoundError") == before, (
            "asking whether a record exists and hearing no is an answer, not a failed operation"
        )


class TestMetricsUseTheSameName:
    async def test_the_label_is_the_exception_error_type(self, any_client, any_cleanup):
        key = (NS, SET_NAME, "metric")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})
        create_only = {"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}

        cases = [
            ("get", ((NS, SET_NAME, "never_written"),), {}),
            ("put", (key, {"v": 2}), {"policy": create_only}),
        ]
        for operation, args, kwargs in cases:
            with pytest.raises(aerospike_py.AerospikeError) as excinfo:
                await invoke(any_client, operation, *args, **kwargs)
            error_type = excinfo.value.error_type
            before = _error_count(operation, SET_NAME, error_type)

            with pytest.raises(aerospike_py.AerospikeError):
                await invoke(any_client, operation, *args, **kwargs)

            assert _error_count(operation, SET_NAME, error_type) == before + 1, (
                f"{operation}: the metrics did not count the failure under {error_type!r}"
            )


class TestExpectedFailuresAreNotBugReports:
    async def test_nothing_asks_the_user_to_file_an_issue(self, any_client, any_cleanup, caplog):
        key = (NS, SET_NAME, "no_bug_report")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        expected_failures = [
            ("get", ((NS, SET_NAME, "never_written"),), {}),
            ("get", (("no_such_namespace", SET_NAME, "k"),), {}),
            ("put", (key, {"v": 2}), {"policy": {"exists": 99}}),
            ("apply", (key, "no_such_module", "no_such_function", []), {}),
            ("batch_read", ([("no_such_namespace", SET_NAME, "k")],), {}),
        ]
        with caplog.at_level(logging.DEBUG):
            for method, args, kwargs in expected_failures:
                with pytest.raises(aerospike_py.AerospikeError):
                    await invoke(any_client, method, *args, **kwargs)

            unreachable = aerospike_py.client({"hosts": [("127.0.0.1", 19999)], "timeout": 1000})
            with pytest.raises(aerospike_py.ClusterError):
                unreachable.connect()

        offending = [record.getMessage()[:160] for record in caplog.records if BUG_REPORT_MARKER in record.getMessage()]
        assert offending == [], "a failure a correct client runs into was logged as a possible bug"

    async def test_a_refused_argument_does_not_either(self, any_client, caplog):
        """A key the server cannot store and a policy of the wrong type are the caller's to fix."""
        refused = [
            (ValueError, "get", ((NS, SET_NAME, None),), {}),
            (ValueError, "put", ((NS, SET_NAME, 1.5), {"v": 1}), {}),
            (TypeError, "get", ((NS, SET_NAME, "k"),), {"policy": "not a dict"}),
        ]
        with caplog.at_level(logging.DEBUG):
            for kind, method, args, kwargs in refused:
                with pytest.raises(kind):
                    await invoke(any_client, method, *args, **kwargs)

        offending = [record.getMessage()[:160] for record in caplog.records if BUG_REPORT_MARKER in record.getMessage()]
        assert offending == [], "a refused argument was logged as a possible bug"
