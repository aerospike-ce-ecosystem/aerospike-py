"""Unit tests for OpenTelemetry tracing support (no Aerospike server required)."""

import threading

import aerospike_py

# ---------------------------------------------------------------------------
# Export & API surface tests
# ---------------------------------------------------------------------------


class TestTracingExports:
    """Verify that tracing functions are properly exported."""

    def test_init_tracing_in_all(self):
        assert "init_tracing" in aerospike_py.__all__

    def test_shutdown_tracing_in_all(self):
        assert "shutdown_tracing" in aerospike_py.__all__

    def test_init_tracing_callable(self):
        assert callable(aerospike_py.init_tracing)

    def test_shutdown_tracing_callable(self):
        assert callable(aerospike_py.shutdown_tracing)

    def test_init_tracing_importable_from_module(self):
        from aerospike_py import init_tracing

        assert callable(init_tracing)

    def test_shutdown_tracing_importable_from_module(self):
        from aerospike_py import shutdown_tracing

        assert callable(shutdown_tracing)

    def test_init_tracing_available_on_native_module(self):
        """init_tracing should be available on the native _aerospike module."""
        from aerospike_py._aerospike import init_tracing

        assert callable(init_tracing)

    def test_shutdown_tracing_available_on_native_module(self):
        """shutdown_tracing should be available on the native _aerospike module."""
        from aerospike_py._aerospike import shutdown_tracing

        assert callable(shutdown_tracing)


# ---------------------------------------------------------------------------
# Disabled / no-op mode tests
# ---------------------------------------------------------------------------


class TestTracingDisabledMode:
    """Test tracing when OTEL_SDK_DISABLED=true or OTEL_TRACES_EXPORTER=none."""

    def test_init_with_sdk_disabled(self, monkeypatch):
        """init_tracing() should succeed silently when SDK is disabled."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()

    def test_init_with_exporter_none(self, monkeypatch):
        """init_tracing() should succeed silently when exporter is 'none'."""
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()

    def test_shutdown_without_init(self):
        """shutdown_tracing() should be safe to call without init."""
        aerospike_py.shutdown_tracing()

    def test_double_shutdown(self, monkeypatch):
        """Calling shutdown_tracing() twice should not raise."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()
        aerospike_py.shutdown_tracing()

    def test_double_init(self, monkeypatch):
        """Calling init_tracing() twice should not raise."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()

    def test_init_shutdown_cycle(self, monkeypatch):
        """Full init → shutdown → init → shutdown cycle should work."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()


# ---------------------------------------------------------------------------
# Thread-safety tests
# ---------------------------------------------------------------------------


class TestTracingThreadSafety:
    """Verify tracing functions are safe to call from multiple threads."""

    def test_concurrent_init_shutdown(self, monkeypatch):
        """Concurrent init/shutdown calls should not crash."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        errors = []

        def worker(i):
            try:
                if i % 2 == 0:
                    aerospike_py.init_tracing()
                else:
                    aerospike_py.shutdown_tracing()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent tracing errors: {errors}"
        aerospike_py.shutdown_tracing()


# ---------------------------------------------------------------------------
# Tracing does not affect client behaviour
# ---------------------------------------------------------------------------


class TestTracingDoesNotAffectClient:
    """Tracing should never break normal client operations."""

    def test_unconnected_client_put_raises_client_error(self, monkeypatch):
        """ClientError for unconnected client should still work with tracing enabled."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
            try:
                c.put(("test", "demo", "key1"), {"a": 1})
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    def test_unconnected_client_get_raises_client_error(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
            try:
                c.get(("test", "demo", "key1"))
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    def test_unconnected_client_exists_raises_client_error(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
            try:
                c.exists(("test", "demo", "key1"))
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    def test_unconnected_client_remove_raises_client_error(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
            try:
                c.remove(("test", "demo", "key1"))
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    def test_unconnected_client_batch_read_raises_client_error(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
            try:
                c.batch_read([("test", "demo", "k1"), ("test", "demo", "k2")])
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    def test_metrics_still_work_with_tracing(self, monkeypatch):
        """Prometheus metrics should still function when tracing is enabled."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            text = aerospike_py.get_metrics()
            assert isinstance(text, str)
            assert "db_client_operation_duration_seconds" in text
        finally:
            aerospike_py.shutdown_tracing()


# ---------------------------------------------------------------------------
# Environment variable handling tests
# ---------------------------------------------------------------------------


class TestTracingEnvVars:
    """Test that environment variables are properly respected."""

    def test_sdk_disabled_case_insensitive(self, monkeypatch):
        """OTEL_SDK_DISABLED should be case-insensitive."""
        for val in ["true", "True", "TRUE", "tRuE"]:
            monkeypatch.setenv("OTEL_SDK_DISABLED", val)
            aerospike_py.init_tracing()
            aerospike_py.shutdown_tracing()

    def test_traces_exporter_none_case_insensitive(self, monkeypatch):
        """OTEL_TRACES_EXPORTER=none should be case-insensitive."""
        for val in ["none", "None", "NONE"]:
            monkeypatch.setenv("OTEL_TRACES_EXPORTER", val)
            aerospike_py.init_tracing()
            aerospike_py.shutdown_tracing()

    def test_invalid_endpoint_does_not_crash_init(self, monkeypatch):
        """init_tracing() with an unreachable endpoint should not crash.

        The OTLP exporter uses batch processing; export failures happen
        asynchronously and should not affect init.
        """
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://192.0.2.1:4317")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "test-aerospike")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()

    def test_custom_service_name_does_not_crash(self, monkeypatch):
        """Custom OTEL_SERVICE_NAME should be accepted."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "my-custom-service")
        aerospike_py.init_tracing()
        aerospike_py.shutdown_tracing()


# ---------------------------------------------------------------------------
# Async client tracing tests
# ---------------------------------------------------------------------------


class TestAsyncClientTracing:
    """Verify async client operations don't crash with tracing enabled."""

    async def test_unconnected_async_put_raises(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
            try:
                await c.put(("test", "demo", "key1"), {"a": 1})
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    async def test_unconnected_async_get_raises(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
            try:
                await c.get(("test", "demo", "key1"))
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()

    async def test_unconnected_async_exists_raises(self, monkeypatch):
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        aerospike_py.init_tracing()
        try:
            c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
            try:
                await c.exists(("test", "demo", "key1"))
                assert False, "Should have raised ClientError"
            except aerospike_py.ClientError:
                pass
        finally:
            aerospike_py.shutdown_tracing()
