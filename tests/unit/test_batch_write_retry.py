"""Unit tests for batch_write_numpy retry parameter."""

import aerospike_py


class TestBatchWriteRetryParameter:
    """Test that the retry parameter is accepted by batch_write_numpy."""

    def test_sync_client_accepts_retry_kwarg(self):
        """Client.batch_write_numpy should accept retry as keyword argument."""
        # Verify the method signature accepts retry parameter
        import inspect

        sig = inspect.signature(aerospike_py.Client.batch_write_numpy)
        assert "retry" in sig.parameters, "retry parameter missing from Client.batch_write_numpy"

    def test_async_client_accepts_retry_kwarg(self):
        """AsyncClient.batch_write_numpy should accept retry as keyword argument."""
        import inspect

        sig = inspect.signature(aerospike_py.AsyncClient.batch_write_numpy)
        assert "retry" in sig.parameters, "retry parameter missing from AsyncClient.batch_write_numpy"

    def test_sync_client_retry_default_is_zero(self):
        """Default retry value should be 0 (no retry)."""
        import inspect

        sig = inspect.signature(aerospike_py.Client.batch_write_numpy)
        param = sig.parameters["retry"]
        assert param.default == 0, f"Expected default retry=0, got {param.default}"

    def test_async_client_retry_default_is_zero(self):
        """Default retry value should be 0 for async client."""
        import inspect

        sig = inspect.signature(aerospike_py.AsyncClient.batch_write_numpy)
        param = sig.parameters["retry"]
        assert param.default == 0, f"Expected default retry=0, got {param.default}"
