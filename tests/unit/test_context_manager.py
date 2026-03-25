"""Unit tests for context manager support (no server required)."""

import pytest

import aerospike_py
from tests import DUMMY_CONFIG


class TestContextManager:
    def test_client_has_enter_exit(self):
        """Test that Client has __enter__ and __exit__ methods."""
        c = aerospike_py.client(DUMMY_CONFIG)
        assert hasattr(c, "__enter__")
        assert hasattr(c, "__exit__")

    def test_async_client_has_aenter_aexit(self):
        """Test that AsyncClient has __aenter__ and __aexit__ methods."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        assert hasattr(c, "__aenter__")
        assert hasattr(c, "__aexit__")

    def test_async_client_aenter_defined_on_class(self):
        """Test that __aenter__/__aexit__ are defined on the class itself, not via __getattr__."""
        assert "__aenter__" in aerospike_py.AsyncClient.__dict__
        assert "__aexit__" in aerospike_py.AsyncClient.__dict__

    async def test_async_client_aenter_returns_self(self):
        """Test that AsyncClient.__aenter__ returns self."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        result = await c.__aenter__()
        assert result is c

    def test_client_enter_returns_self(self):
        """Test that Client.__enter__ returns self."""
        c = aerospike_py.client(DUMMY_CONFIG)
        result = c.__enter__()
        assert result is c

    def test_client_exit_returns_false(self):
        """Test that Client.__exit__ returns False (doesn't suppress exceptions)."""
        c = aerospike_py.client(DUMMY_CONFIG)
        result = c.__exit__(None, None, None)
        assert result is False


class TestAsyncClientInitFailure:
    def test_getattr_after_bad_init_no_recursion(self):
        """Verify AttributeError is raised instead of RecursionError when _inner is not set."""
        client = object.__new__(aerospike_py.AsyncClient)
        # Accessing an attribute when _inner is not set — raises normal AttributeError after __getattr__ removal
        with pytest.raises(AttributeError):
            _ = client.some_attribute


class TestAsyncContextManagerProtocol:
    """Test AsyncClient async context manager protocol without a server."""

    async def test_async_with_statement_aenter(self):
        """Verify 'async with' calls __aenter__ and returns the client."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        # __aenter__ should return self
        entered = await c.__aenter__()
        assert entered is c

    async def test_async_with_statement_aexit_signature(self):
        """Verify __aexit__ accepts the standard 3 args and returns bool."""
        # We just verify the method is callable with the right signature
        import inspect

        sig = inspect.signature(aerospike_py.AsyncClient.__aexit__)
        params = list(sig.parameters.keys())
        # Should have: self, exc_type, exc_val, exc_tb
        assert len(params) == 4

    async def test_async_client_is_connected_false_after_init(self):
        """An unconnected AsyncClient should report is_connected() == False."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        assert not c.is_connected()

    async def test_async_client_aenter_does_not_connect(self):
        """__aenter__ should return self but NOT connect to the cluster."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        entered = await c.__aenter__()
        assert entered is c
        assert not c.is_connected()


class TestSyncContextManagerProtocol:
    """Additional tests for sync Client context manager protocol."""

    def test_sync_with_statement_enter(self):
        """Verify 'with' statement calls __enter__ and returns the client."""
        c = aerospike_py.client(DUMMY_CONFIG)
        entered = c.__enter__()
        assert entered is c

    def test_sync_client_enter_does_not_connect(self):
        """__enter__ should return self but NOT connect to the cluster."""
        c = aerospike_py.client(DUMMY_CONFIG)
        entered = c.__enter__()
        assert entered is c
        assert not c.is_connected()

    def test_sync_exit_with_exception_info(self):
        """__exit__ should handle exception info parameters without crashing."""
        c = aerospike_py.client(DUMMY_CONFIG)
        try:
            raise ValueError("test")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
            result = c.__exit__(*exc_info)
            assert result is False
