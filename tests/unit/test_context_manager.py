"""Unit tests for context manager support (no server required)."""

import pytest

import aerospike_py


class TestContextManager:
    def test_client_has_enter_exit(self):
        """Test that Client has __enter__ and __exit__ methods."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        assert hasattr(c, "__enter__")
        assert hasattr(c, "__exit__")

    def test_async_client_has_aenter_aexit(self):
        """Test that AsyncClient has __aenter__ and __aexit__ methods."""
        c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
        assert hasattr(c, "__aenter__")
        assert hasattr(c, "__aexit__")

    def test_async_client_aenter_defined_on_class(self):
        """Test that __aenter__/__aexit__ are defined on the class itself, not via __getattr__."""
        assert "__aenter__" in aerospike_py.AsyncClient.__dict__
        assert "__aexit__" in aerospike_py.AsyncClient.__dict__

    async def test_async_client_aenter_returns_self(self):
        """Test that AsyncClient.__aenter__ returns self."""
        c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
        result = await c.__aenter__()
        assert result is c

    def test_client_enter_returns_self(self):
        """Test that Client.__enter__ returns self."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        result = c.__enter__()
        assert result is c

    def test_client_exit_returns_false(self):
        """Test that Client.__exit__ returns False (doesn't suppress exceptions)."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        result = c.__exit__(None, None, None)
        assert result is False


class TestAsyncClientInitFailure:
    def test_getattr_after_bad_init_no_recursion(self):
        """_inner 미설정 시 RecursionError 대신 AttributeError 발생 확인."""
        client = object.__new__(aerospike_py.AsyncClient)
        # _inner가 설정되지 않은 상태에서 속성 접근
        with pytest.raises(AttributeError, match="not be fully initialized"):
            _ = client.some_attribute
