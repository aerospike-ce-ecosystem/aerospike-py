"""Logging, metrics, and tracing utilities."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aerospike_py._aerospike import get_metrics_text as _get_metrics_text
from aerospike_py._aerospike import init_tracing as _init_tracing
from aerospike_py._aerospike import is_metrics_enabled as _is_metrics_enabled
from aerospike_py._aerospike import set_metrics_enabled as _set_metrics_enabled
from aerospike_py._aerospike import shutdown_tracing as _shutdown_tracing

logger = logging.getLogger("aerospike_py")


_LEVEL_MAP: dict[int, int] = {
    -1: logging.CRITICAL + 1,  # OFF
    0: logging.ERROR,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG,
    4: 5,  # TRACE
}
"""Map aerospike LOG_LEVEL_* constants to Python logging levels."""


def set_log_level(level: int) -> None:
    """Set the aerospike_py log level.

    Accepts ``LOG_LEVEL_*`` constants. Controls both Rust-internal
    and Python-side logging.

    Args:
        level: One of ``LOG_LEVEL_OFF`` (-1), ``LOG_LEVEL_ERROR`` (0),
            ``LOG_LEVEL_WARN`` (1), ``LOG_LEVEL_INFO`` (2),
            ``LOG_LEVEL_DEBUG`` (3), ``LOG_LEVEL_TRACE`` (4).

    Example:
        ```python
        import aerospike_py

        aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
        ```
    """
    py_level = _LEVEL_MAP.get(level, level)
    logging.getLogger("aerospike_py").setLevel(py_level)
    logging.getLogger("_aerospike").setLevel(py_level)
    logging.getLogger("aerospike_core").setLevel(py_level)
    logging.getLogger("aerospike").setLevel(py_level)


def get_metrics() -> str:
    """Return collected metrics in Prometheus text format."""
    return _get_metrics_text()


def set_metrics_enabled(enabled: bool) -> None:
    """Enable or disable Prometheus metrics collection.

    When disabled, operation timers are skipped entirely (~1ns atomic check).
    Useful for benchmarking without metrics overhead.

    Args:
        enabled: ``True`` to enable (default), ``False`` to disable.

    Example:
        ```python
        aerospike_py.set_metrics_enabled(False)   # disable metrics
        # ... run benchmark ...
        aerospike_py.set_metrics_enabled(True)     # re-enable
        ```
    """
    _set_metrics_enabled(enabled)


def is_metrics_enabled() -> bool:
    """Check if Prometheus metrics collection is currently enabled.

    Returns:
        ``True`` if metrics are enabled (default), ``False`` otherwise.
    """
    return _is_metrics_enabled()


_metrics_server = None
_metrics_server_thread = None
_metrics_lock = threading.Lock()


class _MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            body = _get_metrics_text().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_metrics_server(port: int = 9464) -> None:
    """Start a background HTTP server serving /metrics for Prometheus scraping.

    If a metrics server is already running on a different port, it is shut down
    before the new one starts. If the new port fails to bind, the old server is
    preserved and the OSError propagates.
    """
    global _metrics_server, _metrics_server_thread

    with _metrics_lock:
        # Bind the new socket first — if this raises (e.g. port in use),
        # the old server is preserved unchanged.
        new_server = HTTPServer(("", port), _MetricsHandler)

        # New server bound successfully — shut down old one if present.
        if _metrics_server is not None:
            _metrics_server.shutdown()
            if _metrics_server_thread is not None:
                _metrics_server_thread.join(timeout=5)
                if _metrics_server_thread.is_alive():
                    logger.warning(
                        "Old metrics server thread did not stop within 5 seconds; "
                        "replacing reference — thread is daemonic"
                    )

        _metrics_server = new_server
        _metrics_server_thread = threading.Thread(target=_metrics_server.serve_forever, daemon=True)
        _metrics_server_thread.start()


def stop_metrics_server() -> None:
    """Stop the background metrics HTTP server."""
    global _metrics_server, _metrics_server_thread

    with _metrics_lock:
        if _metrics_server is not None:
            try:
                _metrics_server.shutdown()
                if _metrics_server_thread is not None:
                    _metrics_server_thread.join(timeout=5)
                    if _metrics_server_thread.is_alive():
                        logger.warning(
                            "Metrics server thread did not stop within 5 seconds; "
                            "thread is daemonic and will be terminated at interpreter exit"
                        )
            finally:
                _metrics_server = None
                _metrics_server_thread = None


def init_tracing() -> None:
    """Initialize OpenTelemetry tracing.

    Reads standard OTEL_* environment variables for configuration.
    Key variables:
        OTEL_EXPORTER_OTLP_ENDPOINT  - gRPC endpoint (default: http://localhost:4317)
        OTEL_SERVICE_NAME            - service name (default: aerospike-py)
        OTEL_SDK_DISABLED=true       - disable tracing entirely
        OTEL_TRACES_EXPORTER=none    - disable trace export
    """
    _init_tracing()


def shutdown_tracing() -> None:
    """Shut down the tracer provider, flushing pending spans.

    Call before process exit to ensure all spans are exported.
    """
    _shutdown_tracing()
