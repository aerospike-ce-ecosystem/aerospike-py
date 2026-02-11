"""Integration test configuration — adds autouse cleanup."""

import pytest


@pytest.fixture(autouse=True)
def _auto_cleanup(cleanup):
    """Make cleanup autouse for integration tests."""
    yield cleanup


@pytest.fixture(autouse=True)
async def _async_cleanup_teardown(async_cleanup, request):
    """Automatically clean up keys collected via async_cleanup after each async test."""
    yield
    if not async_cleanup:
        return
    try:
        ac = request.getfixturevalue("async_client")
    except pytest.FixtureLookupError:
        return
    for key in async_cleanup:
        try:
            await ac.remove(key)
        except Exception:
            pass
