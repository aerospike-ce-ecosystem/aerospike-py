"""Transport-level retry coverage for ``batch_write(retry=N)`` — issue #424.

The per-record retry path (server result codes such as ``Timeout`` and
``DeviceOverload``) is covered by ``test_batch.py``. What is covered here is the
case that path never reached: an attempt that fails at the *transport* level —
connection reset, node down, client-side timeout — which used to propagate
immediately and never consume any of the retry budget the caller paid for.

Reproducing that needs the server to actually go away mid-call, so these tests
stop and start the Aerospike container. They are skipped where that is not
possible (CI service containers, a server started by hand), with a reason
distinct from "server not available" so a genuinely unreachable server is still
reported by ``tests/server.py``.

They also carry the ``destructive`` marker, which the default ``addopts``
deselects: stopping the server voids the module-scoped client fixtures and the
cleanup of every other module sharing the session.

Run locally with the Makefile's container:

    make run-aerospike-ce
    uvx --with tox-uv tox -e batch-retry-transport
    # or: uv run pytest tests/integration/test_batch_retry_transport.py -v -m destructive
"""

import os
import shutil
import subprocess
import threading
import time

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG

NS = "test"
SET_NAME = "batch_retry_transport"

CONTAINER = os.environ.get("AEROSPIKE_CONTAINER", "aerospike")
RUNTIME = os.environ.get("RUNTIME", "podman")


def _runtime_available() -> bool:
    """Whether the configured container runtime can control our Aerospike."""
    if shutil.which(RUNTIME) is None:
        return False
    try:
        out = subprocess.run(
            [RUNTIME, "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return CONTAINER in out.stdout.split()


pytestmark = [
    # Deselected from the default run: stopping the server voids the
    # module-scoped client fixtures and the cleanup of every other module in the
    # same session. `tox -e batch-retry-transport` runs this file on its own.
    pytest.mark.destructive,
    pytest.mark.skipif(
        not _runtime_available(),
        reason=(
            f"cannot control the Aerospike server lifecycle: no {RUNTIME!r} container "
            f"named {CONTAINER!r}. This is a capability skip, not an unreachable server."
        ),
    ),
]


def _server(action: str) -> None:
    subprocess.run([RUNTIME, action, CONTAINER], check=True, capture_output=True, timeout=120)


def _wait_until_serving(timeout: float = 90.0) -> None:
    """Block until a fresh client can connect, so the next test is not raced.

    Probes with a real client rather than ``asinfo``: the container reports
    ``status ok`` slightly before the cluster will accept client connections,
    and that gap is long enough to fail the following test's fixture.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            probe = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        except Exception as e:  # cluster not accepting connections yet
            last_error = e
            time.sleep(0.5)
            continue
        probe.close()
        return
    raise RuntimeError(f"{CONTAINER} did not accept a client within {timeout}s: {last_error!r}")


@pytest.fixture
def restartable_client():
    """A connected client, with the server guaranteed back up afterwards."""
    client = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    try:
        yield client
    finally:
        try:
            _server("start")
            _wait_until_serving()
        finally:
            client.close()


def _records(prefix, count=20):
    return [((NS, SET_NAME, f"{prefix}_{i}"), {"v": i}) for i in range(count)]


def test_transport_error_consumes_retry_budget(restartable_client):
    """``retry=N`` must re-drive a batch whose *first* attempt failed in transport.

    Before #424 the first attempt sat outside the retry loop and terminated in
    ``?``, so ``retry=0`` and ``retry=N`` behaved identically here: both raised
    on the first transport error. The retry budget is now spent, which is
    observable as elapsed time (backoff plus the extra attempts).
    """
    records = _records("budget")
    restartable_client.batch_write(records)  # warm the cluster state up

    _server("stop")

    # A downed node surfaces as ClientError or AerospikeTimeoutError depending on
    # whether the socket is refused or the deadline fires first; both are
    # AerospikeError, and which one arrives is not what this test is about.
    unreachable = aerospike_py.AerospikeError

    # Let the client notice the node is gone, so neither measurement below pays
    # the one-off cost of discovering it.
    with pytest.raises(unreachable):
        restartable_client.batch_write(records, policy={"total_timeout": 30000})

    start = time.perf_counter()
    with pytest.raises(unreachable):
        restartable_client.batch_write(records, policy={"total_timeout": 30000}, retry=0)
    no_retry_s = time.perf_counter() - start

    start = time.perf_counter()
    with pytest.raises(unreachable):
        restartable_client.batch_write(records, policy={"total_timeout": 30000}, retry=8)
    with_retry_s = time.perf_counter() - start

    assert with_retry_s > no_retry_s * 3, (
        f"retry=8 took {with_retry_s * 1000:.1f}ms vs retry=0 {no_retry_s * 1000:.1f}ms — "
        "the retry budget was not spent on the transport-error path"
    )


def test_batch_write_survives_a_node_restart(restartable_client):
    """The data-loss case: writes land even though the first attempt found no node.

    This is the whole point of ``retry=N`` for ``batch_write`` (goal 1-5). Before
    #424 this call raised and the records were lost unless the caller had written
    an outer retry of their own.
    """
    records = _records("restart")
    restartable_client.batch_write(records)

    _server("stop")

    def restart_after_a_moment():
        time.sleep(2)
        _server("start")

    restarter = threading.Thread(target=restart_after_a_moment)
    restarter.start()
    try:
        result = restartable_client.batch_write(records, policy={"total_timeout": 120000}, retry=60)
    finally:
        restarter.join()

    assert [br.result for br in result.batch_records] == [0] * len(records)

    # The records really landed, rather than merely being reported as written.
    _wait_until_serving()
    assert restartable_client.get((NS, SET_NAME, "restart_7")).bins == {"v": 7}
