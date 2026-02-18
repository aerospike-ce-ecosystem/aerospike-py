"""Concurrency test configuration — adds autouse cleanup via truncate."""

import pytest

import aerospike_py

CONCURRENCY_SETS = ["conc_thread", "conc_ft"]


@pytest.fixture(autouse=True)
def _auto_cleanup(client):
    """Truncate concurrency test sets after each test module to remove residual data."""
    yield
    for set_name in CONCURRENCY_SETS:
        try:
            client.truncate("test", set_name, 0)
        except aerospike_py.AerospikeError:
            pass
