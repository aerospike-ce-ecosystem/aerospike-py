"""What a mid-scan server failure does to ``Query.foreach()`` — issue #427.

Streaming changes one thing no signature reveals, and this module pins it.

**Before**, ``foreach`` fetched the entire result set before invoking the
callback, so the scan was over by the time the first callback ran. Whether the
cluster stayed healthy *during callback processing* was irrelevant: you got
either zero callbacks plus an exception (the fetch failed), or a complete
iteration.

**After**, the scan stays open for as long as the callback takes, so a cluster
fault during processing surfaces mid-iteration — a prefix of records has already
been handed to the callback, and then the exception is raised. Partial delivery
plus an exception is a new outcome.

That is inherent to streaming: bounded memory and all-or-nothing delivery cannot
both hold. Callers who need all-or-nothing should use ``results()``, which is
unchanged and still materialises everything before returning.

Measured on this file's own scenario (20k records, ~0.5 ms callback, server
stopped 1.5 s in):

    buffered   -> completed normally, 20000 callbacks, no exception
    streaming  -> ClientError after 13697 callbacks

These stop and start the container, so they carry the ``destructive`` marker and
are deselected by default. Run them with:

    uvx --with tox-uv tox -e query-foreach-interruption
    # or: uv run pytest tests/integration/test_query_foreach_interruption.py -v -m destructive
"""

import threading
import time

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.server import can_control_server, control_server, wait_until_serving

NS = "test"
SET_NAME = "foreach_interrupt"
RECORD_COUNT = 20000
PAD = "x" * 400

pytestmark = [
    pytest.mark.destructive,
    pytest.mark.skipif(
        not can_control_server(),
        reason=("cannot control the Aerospike server lifecycle. This is a capability skip, not an unreachable server."),
    ),
]


@pytest.fixture
def restartable_client():
    """A connected client, with the server guaranteed back up afterwards."""
    client = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    try:
        yield client
    finally:
        try:
            control_server("start")
            wait_until_serving(AEROSPIKE_CONFIG)
        finally:
            client.close()


@pytest.fixture
def seeded(restartable_client):
    for start in range(0, RECORD_COUNT, 2000):
        restartable_client.batch_write(
            [((NS, SET_NAME, f"k{i}"), {"v": i, "pad": PAD}) for i in range(start, min(start + 2000, RECORD_COUNT))]
        )
    return RECORD_COUNT


def test_a_mid_scan_failure_surfaces_after_a_prefix_of_callbacks(restartable_client, seeded):
    """The documented behaviour change: partial delivery, then the exception.

    The callback sleeps so the scan is still open when the server goes away.
    Buffered, the fetch would already have completed and the call would succeed;
    streaming, the fault interrupts an iteration that is genuinely still running.
    """
    calls = 0

    def slow_callback(_record):
        nonlocal calls
        calls += 1
        time.sleep(0.0005)
        return True

    def stop_the_server():
        time.sleep(1.5)
        control_server("stop")

    stopper = threading.Thread(target=stop_the_server)
    stopper.start()
    try:
        with pytest.raises(aerospike_py.AerospikeError):
            restartable_client.query(NS, SET_NAME).foreach(slow_callback)
    finally:
        stopper.join()

    assert calls > 0, "records delivered before the fault must reach the callback"
    assert calls < seeded, "the scan must not have completed — the server was stopped"


def test_results_still_delivers_all_or_nothing(restartable_client, seeded):
    """`results()` is the unchanged escape hatch for callers who need atomicity.

    It materialises the whole set before returning, so a fault during the fetch
    raises with nothing delivered — there is no partial state to observe.
    """

    def stop_the_server():
        time.sleep(0.2)
        control_server("stop")

    stopper = threading.Thread(target=stop_the_server)
    stopper.start()
    try:
        try:
            records = restartable_client.query(NS, SET_NAME).results()
        except aerospike_py.AerospikeError:
            # Fault landed during the fetch: nothing was delivered at all.
            return
    finally:
        stopper.join()

    # Or the fetch beat the stop, in which case the result set is complete.
    assert len(records) == seeded
