"""Integration test configuration — adds autouse cleanup."""

import pytest


@pytest.fixture(autouse=True)
def _auto_cleanup(cleanup):
    """Make cleanup autouse for integration tests."""
    yield cleanup
