"""What ``max_concurrent_operations`` counts, and what it deliberately does not.

The limit exists so that callers cannot ask for more connections than the pool
has. A command takes a slot when it is sent and gives it back when its answer
has arrived.

- A single-record UDF call is such a command. ``batch_apply`` has always taken a
  slot; ``apply`` did not, so UDF calls passed the limit that every other
  record command respected.
- A query or scan is not: its stream stays open for as long as the caller reads
  it. If an open stream held a slot, ``max_concurrent_operations`` streams whose
  consumers look something up for each record would wait for one another for
  ever. Streams are therefore not counted; the number of scans running at once
  is the application's to bound.
"""

import asyncio
import time

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.server import skip_or_raise

NS = "test"
SET_NAME = "backpressure_scope"

SLOW_UDF_FILE = "tests/slow_udf.lua"
# Several hundred milliseconds of Lua: long enough for a second caller to give
# up waiting for the only slot.
SPIN_ROUNDS = 30_000_000

ONE_SLOT = {**AEROSPIKE_CONFIG, "max_concurrent_operations": 1, "operation_queue_timeout_ms": 100}


@pytest.fixture(scope="module")
def slow_udf():
    """Register the UDF once; wait until the node serves it."""
    try:
        admin = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception as e:
        skip_or_raise(e)
        raise  # not reached: skip_or_raise() does not return. Static analysis cannot see that.
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
    admin.remove(probe)
    admin.close()


@pytest.fixture
async def one_slot_client():
    try:
        client = await aerospike_py.AsyncClient(ONE_SLOT).connect()
    except Exception as e:
        skip_or_raise(e)
        raise  # not reached: skip_or_raise() does not return. Static analysis cannot see that.
    yield client
    await client.close()


class TestApplyTakesASlot:
    async def test_a_second_udf_call_waits_and_then_gives_up(self, one_slot_client, slow_udf, async_cleanup):
        keys = [(NS, SET_NAME, f"udf_{i}") for i in range(2)]
        async_cleanup.extend(keys)
        for key in keys:
            await one_slot_client.put(key, {"v": 1})

        outcomes = await asyncio.gather(
            *(one_slot_client.apply(key, "slow_udf", "spin", [SPIN_ROUNDS]) for key in keys),
            return_exceptions=True,
        )

        refused = [outcome for outcome in outcomes if isinstance(outcome, aerospike_py.BackpressureError)]
        completed = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        assert (len(completed), len(refused)) == (1, 1), outcomes
        assert "apply" in str(refused[0])

    def test_the_sync_client_counts_it_too(self, slow_udf, cleanup):
        import threading

        key = (NS, SET_NAME, "udf_sync")
        cleanup.append(key)
        client = aerospike_py.client(ONE_SLOT).connect()
        outcomes = []

        def call():
            try:
                outcomes.append(client.apply(key, "slow_udf", "spin", [SPIN_ROUNDS]))
            except aerospike_py.AerospikeError as exc:
                outcomes.append(exc)

        try:
            client.put(key, {"v": 1})
            threads = [threading.Thread(target=call) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        finally:
            client.close()

        refused = [outcome for outcome in outcomes if isinstance(outcome, aerospike_py.BackpressureError)]
        assert (len(outcomes), len(refused)) == (2, 1), outcomes


class TestAnOpenStreamTakesNone:
    async def test_commands_run_while_a_stream_is_open(self, one_slot_client, async_cleanup):
        keys = [(NS, SET_NAME, f"scan_{i}") for i in range(50)]
        async_cleanup.extend(keys)
        await one_slot_client.batch_write([(key, {"n": i}) for i, key in enumerate(keys)])

        looked_up = 0
        async for record in one_slot_client.query(NS, SET_NAME):
            if "n" not in record.bins:
                continue  # another test's record in the same set
            # With the only slot held by the stream, this read would wait
            # 100 ms and raise BackpressureError.
            again = await one_slot_client.get(keys[record.bins["n"]])
            assert again.bins == record.bins
            looked_up += 1

        assert looked_up == len(keys)
