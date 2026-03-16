"""Unit tests for backpressure (operation concurrency limiter)."""

import aerospike_py


class TestBackpressureConfig:
    """Test that backpressure config parameters are accepted."""

    def test_config_accepts_max_concurrent_operations(self):
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)], "max_concurrent_operations": 64})
        assert not c.is_connected()

    def test_config_accepts_operation_queue_timeout(self):
        c = aerospike_py.client(
            {
                "hosts": [("127.0.0.1", 3000)],
                "max_concurrent_operations": 64,
                "operation_queue_timeout_ms": 5000,
            }
        )
        assert not c.is_connected()

    def test_config_default_no_backpressure(self):
        """Default config should have no backpressure (max_concurrent_operations=0)."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        assert not c.is_connected()

    def test_async_config_accepts_backpressure(self):
        c = aerospike_py.async_client({"hosts": [("127.0.0.1", 3000)], "max_concurrent_operations": 32})
        assert not c.is_connected()


class TestBackpressureError:
    """Test BackpressureError exception hierarchy."""

    def test_backpressure_error_exists(self):
        assert hasattr(aerospike_py, "BackpressureError")

    def test_backpressure_error_is_client_error(self):
        assert issubclass(aerospike_py.BackpressureError, aerospike_py.ClientError)

    def test_backpressure_error_is_aerospike_error(self):
        assert issubclass(aerospike_py.BackpressureError, aerospike_py.AerospikeError)

    def test_backpressure_error_is_exception(self):
        assert issubclass(aerospike_py.BackpressureError, Exception)

    def test_backpressure_error_catchable_as_client_error(self):
        try:
            raise aerospike_py.BackpressureError("test")
        except aerospike_py.ClientError:
            pass

    def test_backpressure_error_in_exception_module(self):
        from aerospike_py.exception import BackpressureError

        assert BackpressureError is aerospike_py.BackpressureError
