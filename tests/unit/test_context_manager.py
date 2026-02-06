"""Unit tests for context manager support (no server required)."""

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
