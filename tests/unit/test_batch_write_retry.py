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


class TestBatchRetryInfo:
    """``BatchWriteResult.retry`` — the counters that make truncation visible (#425)."""

    def test_defaults_describe_a_single_attempt(self):
        info = aerospike_py.BatchRetryInfo()
        assert info.attempts == 1
        assert info.max_attempts == 1
        assert info.truncated_by_timeout is False
        assert info.unresolved == 0

    def test_batch_write_result_defaults_its_retry_field(self):
        """Constructing without ``retry`` must keep working for existing callers."""
        result = aerospike_py.BatchWriteResult(batch_records=[])
        assert result.retry == aerospike_py.BatchRetryInfo()

    def test_batch_records_remains_the_first_field(self):
        """Positional access to ``batch_records`` is part of the public surface."""
        result = aerospike_py.BatchWriteResult(batch_records=["sentinel"])
        assert result[0] == ["sentinel"]
        assert result.batch_records == ["sentinel"]

    def test_retry_info_is_exported(self):
        assert "BatchRetryInfo" in aerospike_py.__all__
