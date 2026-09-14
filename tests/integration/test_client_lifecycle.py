"""Integration tests: repeated connect/close cycles must not leak resources.

``close()`` is supposed to tear the cluster down completely. Underneath,
``aerospike_core::Client::close()`` delegates to ``Cluster::close()``, which
has to stop the background *tend* task spawned by ``Cluster::new``. A tend
task that keeps running holds an ``Arc<Cluster>`` alive, which holds every
``Node`` and its connection pool alive — so every connect/close cycle would
strand at least one open socket per node plus a task that keeps issuing an
info command every ``tend_interval`` (1 s by default), for the life of the
process.

That is exactly what ``aerospike-core`` 2.0.0 did (``close()`` dropped the
``MutexGuard`` instead of closing the ``Sender``, and the tend loop had no
exit path), and it is what these tests guard against for every future
dependency bump.

The probe is the *process'* own open file descriptor count rather than the
server's ``client_connections`` statistic: it is immune to anything else that
happens to be talking to the same server while the suite runs.
"""

import asyncio
import gc
import os
import time

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.server import skip_or_raise

#: Enough cycles that a one-socket-per-cycle leak dwarfs any incidental churn.
CYCLES = 25

#: Descriptors the process may legitimately gain across the measured window
#: (pytest bookkeeping, lazily opened files). A real leak adds >= CYCLES.
MAX_FD_GROWTH = 8

#: The tend task can sit in its ``tend_interval`` sleep (1 s default) when
#: ``close()`` signals it, so give it time to wake, exit and drop the pools.
SETTLE_SECONDS = 3.0


def _fd_dir() -> str | None:
    """Directory listing this process' open descriptors, if the OS has one."""
    for candidate in ("/proc/self/fd", "/dev/fd"):
        if os.path.isdir(candidate):
            return candidate
    return None


def _open_fds(fd_dir: str) -> int:
    return len(os.listdir(fd_dir))


@pytest.fixture
def fd_dir() -> str:
    directory = _fd_dir()
    if directory is None:
        pytest.skip("no /proc/self/fd or /dev/fd on this platform")
    return directory


def _new_sync_client():
    try:
        return aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception as exc:
        skip_or_raise(exc)


async def _new_async_client():
    client = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
    try:
        await client.connect()
    except Exception as exc:
        skip_or_raise(exc)
    return client


@pytest.mark.slow
def test_sync_connect_close_cycles_do_not_leak_descriptors(fd_dir):
    """``Client.close()`` must release the cluster's sockets, every cycle."""
    # Warm up so one-off allocations (runtime threads, lazy statics) are not
    # counted as growth.
    warmup = _new_sync_client()
    warmup.close()
    del warmup
    gc.collect()
    time.sleep(SETTLE_SECONDS)

    before = _open_fds(fd_dir)
    for _ in range(CYCLES):
        client = _new_sync_client()
        assert client.is_connected()
        client.close()
        assert not client.is_connected()
        del client
    gc.collect()
    time.sleep(SETTLE_SECONDS)
    after = _open_fds(fd_dir)

    assert after - before <= MAX_FD_GROWTH, (
        f"{CYCLES} sync connect/close cycles leaked descriptors: "
        f"{before} -> {after} (+{after - before}); close() is not stopping the cluster tend task"
    )


@pytest.mark.slow
async def test_async_connect_close_cycles_do_not_leak_descriptors(fd_dir):
    """``AsyncClient.close()`` must release the cluster's sockets, every cycle."""
    warmup = await _new_async_client()
    await warmup.close()
    del warmup
    gc.collect()
    await asyncio.sleep(SETTLE_SECONDS)

    before = _open_fds(fd_dir)
    for _ in range(CYCLES):
        client = await _new_async_client()
        assert client.is_connected()
        await client.close()
        assert not client.is_connected()
        del client
    gc.collect()
    await asyncio.sleep(SETTLE_SECONDS)
    after = _open_fds(fd_dir)

    assert after - before <= MAX_FD_GROWTH, (
        f"{CYCLES} async connect/close cycles leaked descriptors: "
        f"{before} -> {after} (+{after - before}); close() is not stopping the cluster tend task"
    )
