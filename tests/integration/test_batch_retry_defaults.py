"""``retry=`` and ``policy["max_retries"]`` on batch writes — issue #453.

Two settings re-send a batch write. ``retry=N`` is the binding's own loop: it
re-sends only the records that failed. ``max_retries`` is the Rust client's
loop underneath: it re-sends a node's whole share of the batch. A batch that
writes starts from ``max_retries = 0`` so that a write is not silently applied
twice, and giving both settings at once is rejected because they would
multiply.

What the defaults are is unit-tested next to the parser
(``rust/src/policy/batch_policy.rs``); a healthy server gives no way to observe
an automatic re-send from Python. These tests pin what a caller can see.
"""

import numpy as np
import pytest

import aerospike_py
from tests.helpers import invoke

NS = "test"
SET_NAME = "batch_retry_defaults"

DTYPE = np.dtype([("_key", "i8"), ("v", "i8")])


def _records(prefix, count=3):
    return [((NS, SET_NAME, f"{prefix}_{i}"), {"v": i}) for i in range(count)]


async def _exists(any_client, key) -> bool:
    _, meta = await invoke(any_client, "exists", key)
    return meta is not None


class TestRetryAndMaxRetriesTogether:
    async def test_batch_write_rejects_both(self, any_client, any_cleanup):
        records = _records("both")
        any_cleanup.extend(key for key, _ in records)

        with pytest.raises(aerospike_py.InvalidArgError, match=r"retry=2.*max_retries") as excinfo:
            await invoke(any_client, "batch_write", records, policy={"max_retries": 1}, retry=2)

        assert "6 sends" in str(excinfo.value), "the message says what the two would add up to"
        for key, _ in records:
            assert not await _exists(any_client, key), "a rejected call writes nothing"

    async def test_batch_write_numpy_rejects_both(self, any_client, any_cleanup):
        data = np.array([(9101, 1), (9102, 2)], dtype=DTYPE)
        keys = [(NS, SET_NAME, 9101), (NS, SET_NAME, 9102)]
        any_cleanup.extend(keys)

        with pytest.raises(aerospike_py.InvalidArgError, match=r"retry=1.*max_retries"):
            await invoke(
                any_client,
                "batch_write_numpy",
                data,
                NS,
                SET_NAME,
                policy={"max_retries": 3},
                retry=1,
            )

        for key in keys:
            assert not await _exists(any_client, key)


class TestEitherSettingAlone:
    async def test_retry_alone(self, any_client, any_cleanup):
        records = _records("retry_only")
        any_cleanup.extend(key for key, _ in records)

        result = await invoke(any_client, "batch_write", records, retry=2)

        assert [br.result for br in result.batch_records] == [0, 0, 0]
        assert result.retry.max_attempts == 3
        assert result.retry.attempts == 1, "nothing failed, so nothing was re-sent"

    async def test_max_retries_alone(self, any_client, any_cleanup):
        records = _records("max_retries_only")
        any_cleanup.extend(key for key, _ in records)

        result = await invoke(any_client, "batch_write", records, policy={"max_retries": 2})

        assert [br.result for br in result.batch_records] == [0, 0, 0]
        assert result.retry.max_attempts == 1, "retry= was not given"

    async def test_max_retries_zero_with_retry(self, any_client, any_cleanup):
        """An explicit 0 is the default spelled out, not a second retry setting."""
        records = _records("explicit_zero")
        any_cleanup.extend(key for key, _ in records)

        result = await invoke(any_client, "batch_write", records, policy={"max_retries": 0}, retry=1)

        assert [br.result for br in result.batch_records] == [0, 0, 0]

    @pytest.mark.parametrize("method", ["batch_operate", "batch_remove"])
    async def test_other_write_batches_accept_max_retries(self, any_client, any_cleanup, method):
        """They have no ``retry=``, so ``max_retries`` is the only way to ask for re-sends."""
        records = _records(f"other_{method}")
        any_cleanup.extend(key for key, _ in records)
        await invoke(any_client, "batch_write", records)
        keys = [key for key, _ in records]

        if method == "batch_operate":
            ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "v", "val": 10}]
            result = await invoke(any_client, method, keys, ops, policy={"max_retries": 1})
        else:
            result = await invoke(any_client, method, keys, policy={"max_retries": 1})

        assert [br.result for br in result.batch_records] == [0, 0, 0]


async def test_master_write_retry_is_refused_before_any_record_changes(any_client, any_cleanup):
    key = (NS, SET_NAME, "master_retry_guard")
    any_cleanup.append(key)
    await invoke(any_client, "put", key, {"v": 0})
    policy = {"replica": aerospike_py.POLICY_REPLICA_MASTER, "max_retries": 1}
    with pytest.raises(aerospike_py.InvalidArgError, match="MASTER"):
        await invoke(
            any_client,
            "batch_operate",
            [key],
            [{"op": aerospike_py.OPERATOR_INCR, "bin": "v", "val": 1}],
            policy=policy,
        )
    result = await invoke(
        any_client, "batch_operate", [key], [{"op": aerospike_py.OPERATOR_READ, "bin": "v"}], policy=policy
    )
    assert result.batch_records[0].record.bins["v"] == 0


async def test_batch_operate_enforces_create_only_on_each_write(any_client, any_cleanup):
    existing = (NS, SET_NAME, "operate_create_existing")
    new = (NS, SET_NAME, "operate_create_new")
    any_cleanup.extend([existing, new])
    await invoke(any_client, "put", existing, {"v": 0})
    result = await invoke(
        any_client,
        "batch_operate",
        [existing, new],
        [{"op": aerospike_py.OPERATOR_WRITE, "bin": "v", "val": 9}],
        policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
    )
    assert [br.result for br in result.batch_records] == [5, 0]
    assert (await invoke(any_client, "get", existing)).bins["v"] == 0
    assert (await invoke(any_client, "get", new)).bins["v"] == 9


async def test_unsupported_batch_conditions_are_refused_before_send(any_client, any_cleanup):
    key = (NS, SET_NAME, "unsupported_conditions")
    any_cleanup.append(key)
    await invoke(any_client, "put", key, {"v": 0})
    with pytest.raises(aerospike_py.InvalidArgError, match="gen"):
        await invoke(
            any_client,
            "batch_operate",
            [key],
            [{"op": aerospike_py.OPERATOR_INCR, "bin": "v", "val": 1}],
            policy={"gen": aerospike_py.POLICY_GEN_EQ},
        )
    with pytest.raises(aerospike_py.InvalidArgError, match="exists"):
        await invoke(any_client, "batch_remove", [key], policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
    with pytest.raises(aerospike_py.InvalidArgError, match="exists"):
        await invoke(any_client, "batch_remove", [(key, {"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})])
    assert (await invoke(any_client, "get", key)).bins["v"] == 0
