"""Shared fixtures for feasibility tests (requires Aerospike server)."""

import pytest

from tests.server import skip_or_fail_unreachable


@pytest.fixture(scope="session", autouse=True)
def require_aerospike():
    skip_or_fail_unreachable()
