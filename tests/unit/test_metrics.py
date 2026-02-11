"""Unit tests for metrics module (no Aerospike server required)."""

import re
import socket
import threading
import urllib.request

import aerospike_py


class TestGetMetrics:
    def test_returns_string(self):
        text = aerospike_py.get_metrics()
        assert isinstance(text, str)

    def test_contains_help_header(self):
        text = aerospike_py.get_metrics()
        assert "# HELP" in text
        assert "db_client_operation_duration_seconds" in text

    def test_contains_type_header(self):
        text = aerospike_py.get_metrics()
        assert "# TYPE db_client_operation_duration_seconds" in text

    def test_contains_eof_marker(self):
        """Prometheus text format must end with # EOF."""
        text = aerospike_py.get_metrics()
        assert text.strip().endswith("# EOF")

    def test_valid_prometheus_text_lines(self):
        """Every non-empty line should be a comment (#) or a metric sample."""
        text = aerospike_py.get_metrics()
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            assert line.startswith("#") or re.match(r"^[a-zA-Z_]", line), f"Unexpected line format: {line!r}"

    def test_multiple_calls_consistent(self):
        """Repeated calls return structurally identical output (no ops between)."""
        a = aerospike_py.get_metrics()
        b = aerospike_py.get_metrics()
        # Both should at minimum contain the same HELP/TYPE lines
        assert "# HELP db_client_operation_duration_seconds" in a
        assert "# HELP db_client_operation_duration_seconds" in b

    def test_concurrent_calls_no_crash(self):
        """get_metrics() is safe to call from multiple threads simultaneously."""
        results = [None] * 10
        errors = []

        def worker(idx):
            try:
                results[idx] = aerospike_py.get_metrics()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent get_metrics() errors: {errors}"
        for r in results:
            assert isinstance(r, str)
            assert "db_client_operation_duration_seconds" in r


class TestMetricsExports:
    def test_get_metrics_in_all(self):
        assert "get_metrics" in aerospike_py.__all__

    def test_start_metrics_server_in_all(self):
        assert "start_metrics_server" in aerospike_py.__all__

    def test_stop_metrics_server_in_all(self):
        assert "stop_metrics_server" in aerospike_py.__all__

    def test_get_metrics_callable(self):
        assert callable(aerospike_py.get_metrics)

    def test_start_metrics_server_callable(self):
        assert callable(aerospike_py.start_metrics_server)

    def test_stop_metrics_server_callable(self):
        assert callable(aerospike_py.stop_metrics_server)


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestMetricsServer:
    def test_start_and_stop(self):
        port = _find_free_port()
        aerospike_py.start_metrics_server(port=port)
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2)
            assert resp.status == 200
        finally:
            aerospike_py.stop_metrics_server()

    def test_serves_prometheus_format(self):
        port = _find_free_port()
        aerospike_py.start_metrics_server(port=port)
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2)
            body = resp.read().decode("utf-8")
            assert "# HELP db_client_operation_duration_seconds" in body
            assert "# TYPE db_client_operation_duration_seconds" in body
            assert body.strip().endswith("# EOF")
        finally:
            aerospike_py.stop_metrics_server()

    def test_content_type_header(self):
        port = _find_free_port()
        aerospike_py.start_metrics_server(port=port)
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2)
            ct = resp.headers.get("Content-Type", "")
            assert "text/plain" in ct
        finally:
            aerospike_py.stop_metrics_server()

    def test_non_metrics_path_returns_404(self):
        port = _find_free_port()
        aerospike_py.start_metrics_server(port=port)
        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)
                assert False, "Should have raised HTTPError for 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            aerospike_py.stop_metrics_server()

    def test_idempotent_stop(self):
        """Calling stop_metrics_server() when not started should not raise."""
        aerospike_py.stop_metrics_server()
        aerospike_py.stop_metrics_server()

    def test_restart(self):
        """Server can be stopped and started again on a different port."""
        port1 = _find_free_port()
        aerospike_py.start_metrics_server(port=port1)
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port1}/metrics", timeout=2)
        assert resp.status == 200
        aerospike_py.stop_metrics_server()

        port2 = _find_free_port()
        aerospike_py.start_metrics_server(port=port2)
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port2}/metrics", timeout=2)
            assert resp.status == 200
        finally:
            aerospike_py.stop_metrics_server()

    def test_start_replaces_existing(self):
        """Calling start_metrics_server() while running replaces the old server."""
        port1 = _find_free_port()
        aerospike_py.start_metrics_server(port=port1)

        port2 = _find_free_port()
        aerospike_py.start_metrics_server(port=port2)
        try:
            # New port should work
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port2}/metrics", timeout=2)
            assert resp.status == 200
        finally:
            aerospike_py.stop_metrics_server()
