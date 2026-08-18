"""Shared fixtures for all test suites."""

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.helpers import invoke
from tests.server import server_required, skip_or_raise


@pytest.fixture(scope="module")
def client():
    """Create and connect a sync client for the test module."""
    try:
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception as e:
        skip_or_raise(e)
    yield c
    c.close()


@pytest.fixture
async def async_client():
    """Create and connect an AsyncClient, skip if server is unavailable."""
    try:
        c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await c.connect()
    except Exception as e:
        skip_or_raise(e)
    yield c
    await c.close()


@pytest.fixture(params=["sync", "async"], ids=["sync", "async"])
async def any_client(request, client, async_client):
    """Yield either the sync or async client, parametrized.

    Each test using this fixture runs twice: once with the sync client
    and once with the async client. Use ``invoke()`` from ``tests.helpers``
    to call methods transparently.
    """
    if request.param == "sync":
        yield client
    else:
        yield async_client


@pytest.fixture
async def any_cleanup(any_client):
    """Clean up test keys after each test, works with any_client."""
    keys = []
    yield keys
    for key in keys:
        try:
            await invoke(any_client, "remove", key)
        except Exception:
            pass


@pytest.fixture
def cleanup(client):
    """Clean up test keys after each test.

    Not autouse — integration/concurrency conftest layers add autouse wrappers.
    """
    keys = []
    yield keys
    for key in keys:
        try:
            client.remove(key)
        except Exception:
            pass


@pytest.fixture
async def async_cleanup(async_client):
    """Collect keys to clean up after an async test.

    Depends on async_client explicitly so pytest tears this fixture down
    *before* closing the client connection.

    Usage:
        async def test_something(async_client, async_cleanup):
            key = ("test", "demo", "k1")
            async_cleanup.append(key)
            ...
    """
    keys = []
    yield keys
    for key in keys:
        try:
            await async_client.remove(key)
        except Exception:
            pass


# ── All-skipped guard ───────────────────────────────────────────────────────
# Independent of the fixture change above: if a *new* fixture ever reintroduces
# a bare ``except Exception: pytest.skip(...)``, a suite that skips its way to
# zero passes must still turn the job red rather than exiting 0.

_passed = 0
_skipped = 0


def pytest_runtest_logreport(report):
    """Tally outcomes. Setup-phase skips never reach the ``call`` phase."""
    global _passed, _skipped
    if report.outcome == "skipped":
        _skipped += 1
    elif report.when == "call" and report.outcome == "passed":
        _passed += 1


def pytest_sessionfinish(session, exitstatus):
    """Fail a required-server run that collected tests but passed none of them."""
    if not server_required() or exitstatus != 0:
        return
    if not (session.testscollected and _skipped and _passed == 0):
        return
    session.exitstatus = 1
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    message = (
        f"AEROSPIKE_REQUIRE_SERVER is set, {session.testscollected} test(s) were collected, "
        f"{_skipped} skipped and none passed — treating this run as a failure."
    )
    if reporter is not None:
        reporter.write_sep("=", "all tests skipped", red=True)
        reporter.write_line(message)
    else:  # pragma: no cover - terminalreporter is absent only under -p no:terminal
        print(message)
