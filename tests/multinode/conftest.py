"""Fixtures for the two-node failure scenarios.

Every test gets a healthy two-node cluster and its own clients, and leaves the
cluster healthy again: the node it stopped is restarted and the test waits
until both nodes agree on the cluster and no partition is still migrating.
"""

import shutil
import subprocess
import time

import pytest

import aerospike_py
from tests.multinode import MULTINODE_CONFIG, SURVIVOR_CONTAINER, VICTIM_CONTAINER
from tests.server import container_runtime

NAMESPACE = "test"


def _running_containers() -> set[str]:
    runtime = container_runtime()
    if shutil.which(runtime) is None:
        return set()
    try:
        listed = subprocess.run([runtime, "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(listed.stdout.split())


def _all_containers() -> set[str]:
    runtime = container_runtime()
    if shutil.which(runtime) is None:
        return set()
    try:
        listed = subprocess.run(
            [runtime, "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(listed.stdout.split())


def pytest_collection_modifyitems(config, items):
    """Skip, with a reason of its own, where the cluster cannot be controlled."""
    known = _all_containers()
    if {VICTIM_CONTAINER, SURVIVOR_CONTAINER} <= known:
        return
    reason = pytest.mark.skip(
        reason=(
            f"cannot control the two-node cluster: no {container_runtime()!r} containers named "
            f"{SURVIVOR_CONTAINER!r} and {VICTIM_CONTAINER!r} (start it with `make run-aerospike-multinode`). "
            "This is a capability skip, not an unreachable server."
        )
    )
    for item in items:
        if "multinode" in str(item.fspath):
            item.add_marker(reason)


def _container(action: str, name: str) -> None:
    subprocess.run([container_runtime(), action, name], check=True, capture_output=True, timeout=120)


def _info(client, command: str) -> dict[str, dict[str, str]]:
    """``{node: {stat: value}}`` for a ``key=value;...`` info command."""
    out: dict[str, dict[str, str]] = {}
    for node, error, response in client.info_all(command):
        if error != 0:
            continue
        out[node] = dict(pair.split("=", 1) for pair in response.strip().split(";") if "=" in pair)
    return out


def wait_for_cluster(size: int, timeout: float = 120.0) -> None:
    """Block until `size` nodes form the cluster and nothing is migrating."""
    deadline = time.monotonic() + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            probe = aerospike_py.client(MULTINODE_CONFIG).connect()
        except Exception as e:  # not accepting clients yet
            last = e
            time.sleep(0.5)
            continue
        try:
            stats = _info(probe, "statistics")
            namespace = _info(probe, f"namespace/{NAMESPACE}")
        except aerospike_py.AerospikeError as e:
            last = e
            time.sleep(0.5)
            continue
        finally:
            probe.close()
        sizes = {node: values.get("cluster_size") for node, values in stats.items()}
        migrating = {
            node: (values.get("migrate_tx_partitions_remaining"), values.get("migrate_rx_partitions_remaining"))
            for node, values in namespace.items()
        }
        last = (sizes, migrating)
        settled = (
            len(sizes) == size
            and set(sizes.values()) == {str(size)}
            and len(migrating) == size
            and set(migrating.values()) == {("0", "0")}
        )
        if settled:
            return
        time.sleep(0.5)
    raise RuntimeError(f"the cluster did not settle at {size} node(s) within {timeout}s: {last!r}")


class Cluster:
    """Handle a test uses to take the second node away."""

    def stop_victim(self) -> None:
        """Kill node 2 without warning, as a crash would."""
        _container("kill", VICTIM_CONTAINER)

    def wait_for_survivor_alone(self) -> None:
        wait_for_cluster(1)


@pytest.fixture
def cluster():
    if VICTIM_CONTAINER not in _running_containers():
        _container("start", VICTIM_CONTAINER)
    wait_for_cluster(2)
    try:
        yield Cluster()
    finally:
        if VICTIM_CONTAINER not in _running_containers():
            _container("start", VICTIM_CONTAINER)
        wait_for_cluster(2)


@pytest.fixture
def client(cluster):
    """A sync client connected while both nodes are up."""
    c = aerospike_py.client(MULTINODE_CONFIG).connect()
    yield c
    c.close()


@pytest.fixture
async def async_client(cluster):
    """An async client connected while both nodes are up."""
    c = aerospike_py.AsyncClient(MULTINODE_CONFIG)
    await c.connect()
    yield c
    await c.close()


@pytest.fixture
def observer(cluster):
    """A second sync client, used only to look at what the cluster holds."""
    c = aerospike_py.client(MULTINODE_CONFIG).connect()
    yield c
    c.close()
