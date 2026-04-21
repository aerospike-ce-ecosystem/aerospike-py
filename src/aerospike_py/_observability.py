"""Logging, metrics, and tracing utilities."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

from aerospike_py._aerospike import dropped_log_count as _dropped_log_count
from aerospike_py._aerospike import get_metrics_text as _get_metrics_text
from aerospike_py._aerospike import init_tracing as _init_tracing
from aerospike_py._aerospike import (
    is_internal_stage_metrics_enabled as _is_internal_stage_metrics_enabled,
)
from aerospike_py._aerospike import is_metrics_enabled as _is_metrics_enabled
from aerospike_py._aerospike import (
    set_internal_stage_metrics_enabled as _set_internal_stage_metrics_enabled,
)
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


def dropped_log_count() -> int:
    """Return the number of log messages dropped because the GIL was unavailable.

    When the Rust logging bridge cannot acquire the Python GIL (e.g. during
    interpreter shutdown), log messages are counted as dropped. WARN and ERROR
    level messages are still emitted to stderr as a fallback.

    Returns:
        Count of dropped messages since process start.
    """
    return _dropped_log_count()


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


def set_internal_stage_metrics_enabled(enabled: bool) -> None:
    """Enable or disable internal stage profiling metrics.

    Controls the ``db_client_internal_stage_seconds`` histogram, which
    captures fine-grained timing for ``batch_read`` stages (``key_parse``,
    ``tokio_schedule_delay``, ``limiter_wait``, ``io``, ``spawn_blocking_delay``,
    ``into_pyobject``, ``event_loop_resume_delay``, ``as_dict``, ``merge_as_dict``,
    ``future_into_py_setup``).

    Disabled by default — enable only for debug/profiling sessions. When
    disabled, every stage timer call site elides its ``Instant::now()`` call
    entirely (~1ns atomic load) so there is no hot-path overhead.

    The ``AEROSPIKE_PY_INTERNAL_METRICS=1`` environment variable sets the
    initial state at process start.

    Args:
        enabled: ``True`` to collect internal stage metrics, ``False`` to skip.

    Example:
        ```python
        aerospike_py.set_internal_stage_metrics_enabled(True)
        handle = await client.batch_read(keys)
        # ... inspect metrics ...
        aerospike_py.set_internal_stage_metrics_enabled(False)
        ```
    """
    _set_internal_stage_metrics_enabled(enabled)


def is_internal_stage_metrics_enabled() -> bool:
    """Check if internal stage profiling metrics are currently enabled.

    Returns:
        ``True`` if stage profiling is on, ``False`` otherwise (default).
    """
    return _is_internal_stage_metrics_enabled()


@contextmanager
def internal_stage_profiling() -> Iterator[None]:
    """Scoped enable of internal stage profiling metrics.

    Restores the previous state on exit, even if an exception propagates.
    Use for short debug windows without affecting global state:

    ```python
    with aerospike_py.internal_stage_profiling():
        handle = await client.batch_read(keys)
        dump = aerospike_py.get_metrics()
    # profiling is back to its previous state here
    ```
    """
    prev = _is_internal_stage_metrics_enabled()
    _set_internal_stage_metrics_enabled(True)
    try:
        yield
    finally:
        _set_internal_stage_metrics_enabled(prev)


_metrics_server = None
_metrics_server_thread = None
_metrics_lock = threading.Lock()


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus /metrics endpoint."""

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
        # Forward HTTP request logs at DEBUG level instead of silently dropping them.
        logger.debug(format, *args)


def start_metrics_server(port: int = 9464) -> None:
    """Start a background HTTP server serving /metrics for Prometheus scraping."""
    global _metrics_server, _metrics_server_thread

    with _metrics_lock:
        old_server = _metrics_server
        old_thread = _metrics_server_thread

        # Same-port restart: shut down and close old server to release the socket.
        if old_server is not None and old_server.server_address[1] == port:
            try:
                old_server.shutdown()
                old_server.server_close()
            except Exception:
                logger.exception("Error shutting down old metrics server during same-port restart")
            if old_thread is not None:
                old_thread.join(timeout=5)
                if old_thread.is_alive():
                    logger.warning(
                        "Old metrics server thread did not stop within 5 seconds "
                        "during same-port restart; proceeding anyway"
                    )
            old_server = None
            old_thread = None

        # Bind the new port — if this raises OSError (port in use by another
        # process), the existing server on a different port remains untouched.
        new_server = HTTPServer(("", port), _MetricsHandler)
        new_thread = threading.Thread(target=new_server.serve_forever, daemon=True)
        new_thread.start()

        # New server is running; tear down the old one if not already done.
        if old_server is not None:
            old_server.shutdown()
            old_server.server_close()
            if old_thread is not None:
                old_thread.join(timeout=5)

        _metrics_server = new_server
        _metrics_server_thread = new_thread


def stop_metrics_server() -> None:
    """Stop the background metrics HTTP server."""
    global _metrics_server, _metrics_server_thread

    with _metrics_lock:
        if _metrics_server is not None:
            try:
                try:
                    _metrics_server.shutdown()
                except Exception:
                    logger.exception("Error shutting down metrics server")
                try:
                    _metrics_server.server_close()
                except Exception:
                    logger.exception("Error closing metrics server socket")
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
