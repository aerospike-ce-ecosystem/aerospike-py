"""Shared test utilities used across integration, concurrency, and compatibility suites."""

import asyncio
import functools
import inspect
import time

import pytest

import aerospike_py
from aerospike_py import predicates as p


async def invoke(client, method_name, *args, **kwargs):
    """Call a method on either sync or async client transparently.

    If the result is a coroutine, awaits it. Otherwise returns directly.
    This avoids the need to duplicate test bodies for sync vs async clients.
    """
    method = getattr(client, method_name)
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def wait_for_index(client, ns, set_name, bin_name, timeout=5.0, interval=0.2):
    """Poll until a secondary index query on *bin_name* returns without error."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            q = client.query(ns, set_name)
            q.where(p.equals(bin_name, 0))
            q.results()
            return
        except aerospike_py.AerospikeError:
            if time.monotonic() >= deadline:
                return  # best-effort; let the real test fail if needed
            time.sleep(interval)


def skip_if_no_security(func):
    """Decorator to skip tests if security is not enabled on the server.

    Works for both sync and async test functions.
    """
    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except aerospike_py.AerospikeError as e:
                if "security" in str(e).lower() or "not supported" in str(e).lower():
                    pytest.skip("Security not enabled on this server")
                raise

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

    return wrapper
