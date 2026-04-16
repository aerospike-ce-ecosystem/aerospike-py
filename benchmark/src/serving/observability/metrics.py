"""Prometheus metrics — per-pipeline-stage histograms for bottleneck analysis.

Uses a **custom registry** to avoid conflicts with default collectors.
Rust-side metrics from ``aerospike_py.get_metrics()`` are appended at scrape time.
"""

from __future__ import annotations

import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

import aerospike_py

logger = logging.getLogger("serving.observability")

# ---------------------------------------------------------------------------
# Custom registry (no default platform collectors)
# ---------------------------------------------------------------------------

registry = CollectorRegistry()

# ---------------------------------------------------------------------------
# Histogram bucket definitions
# ---------------------------------------------------------------------------

# 10ms - 2s
_BUCKETS_10ms_2s = (0.010, 0.025, 0.050, 0.075, 0.100, 0.150, 0.200, 0.300, 0.500, 0.750, 1.0, 1.5, 2.0)

# 5ms - 1s
_BUCKETS_5ms_1s = (0.005, 0.010, 0.025, 0.050, 0.075, 0.100, 0.150, 0.200, 0.300, 0.500, 0.750, 1.0)

# 1ms - 100ms
_BUCKETS_1ms_100ms = (0.001, 0.002, 0.005, 0.010, 0.020, 0.030, 0.050, 0.075, 0.100)

# 0.5ms - 50ms
_BUCKETS_05ms_50ms = (0.0005, 0.001, 0.002, 0.005, 0.010, 0.020, 0.030, 0.050)

# 0.5ms - 20ms
_BUCKETS_05ms_20ms = (0.0005, 0.001, 0.002, 0.005, 0.010, 0.015, 0.020)

# ratio 0.0 - 1.0
_BUCKETS_RATIO = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

# ---------------------------------------------------------------------------
# Pipeline-stage histograms
# ---------------------------------------------------------------------------

predict_duration_seconds = Histogram(
    "predict_duration_seconds",
    "Total predict endpoint latency",
    labelnames=["client_type"],
    buckets=_BUCKETS_10ms_2s,
    registry=registry,
)

key_extraction_duration_seconds = Histogram(
    "key_extraction_duration_seconds",
    "Time to extract keys from request payload",
    labelnames=["client_type"],
    buckets=_BUCKETS_05ms_50ms,
    registry=registry,
)

aerospike_batch_read_all_duration_seconds = Histogram(
    "aerospike_batch_read_all_duration_seconds",
    "Total batch-read wall time across all sets",
    labelnames=["client_type"],
    buckets=_BUCKETS_10ms_2s,
    registry=registry,
)

aerospike_batch_read_set_duration_seconds = Histogram(
    "aerospike_batch_read_set_duration_seconds",
    "Batch-read latency per individual set",
    labelnames=["client_type", "set_name"],
    buckets=_BUCKETS_5ms_1s,
    registry=registry,
)

feature_extraction_duration_seconds = Histogram(
    "feature_extraction_duration_seconds",
    "Time to build feature tensors from Aerospike records",
    labelnames=["client_type"],
    buckets=_BUCKETS_1ms_100ms,
    registry=registry,
)

dlrm_inference_duration_seconds = Histogram(
    "dlrm_inference_duration_seconds",
    "DLRM model forward-pass latency",
    labelnames=["client_type"],
    buckets=_BUCKETS_1ms_100ms,
    registry=registry,
)

response_build_duration_seconds = Histogram(
    "response_build_duration_seconds",
    "Time to serialise the prediction response",
    labelnames=["client_type"],
    buckets=_BUCKETS_05ms_20ms,
    registry=registry,
)

aerospike_batch_read_io_duration_seconds = Histogram(
    "aerospike_batch_read_io_duration_seconds",
    "Rust I/O time only (before as_dict conversion), per set",
    labelnames=["client_type", "set_name"],
    buckets=_BUCKETS_1ms_100ms,
    registry=registry,
)

aerospike_dict_conversion_duration_seconds = Histogram(
    "aerospike_dict_conversion_duration_seconds",
    "Python dict conversion time (as_dict + post-processing), per set",
    labelnames=["client_type", "set_name"],
    buckets=_BUCKETS_1ms_100ms,
    registry=registry,
)

aerospike_records_found_ratio = Histogram(
    "aerospike_records_found_ratio",
    "Ratio of records found vs requested in a batch read",
    labelnames=["client_type"],
    buckets=_BUCKETS_RATIO,
    registry=registry,
)

# ---------------------------------------------------------------------------
# Counter & Gauge
# ---------------------------------------------------------------------------

predict_requests_total = Counter(
    "predict_requests_total",
    "Total predict requests",
    labelnames=["client_type", "status"],
    registry=registry,
)

predict_active_requests = Gauge(
    "predict_active_requests",
    "Currently in-flight predict requests",
    labelnames=["client_type"],
    registry=registry,
)


# ---------------------------------------------------------------------------
# Scrape helper
# ---------------------------------------------------------------------------


def get_metrics_text() -> bytes:
    """Return combined Prometheus exposition text.

    Merges Python-side custom registry output with aerospike_py native
    (Rust) metrics. The Rust output may end with ``# EOF\\n`` which must
    be stripped before concatenation so the merged output is valid.
    """
    python_metrics = generate_latest(registry)

    try:
        rust_metrics: str = aerospike_py.get_metrics()
    except Exception:
        logger.debug("aerospike_py.get_metrics() unavailable", exc_info=True)
        rust_metrics = ""

    # Strip trailing ``# EOF`` line from Rust output
    if rust_metrics:
        rust_bytes = rust_metrics.encode("utf-8") if isinstance(rust_metrics, str) else rust_metrics
        rust_bytes = rust_bytes.rstrip()
        if rust_bytes.endswith(b"# EOF"):
            rust_bytes = rust_bytes[: -len(b"# EOF")].rstrip()
        if rust_bytes:
            return python_metrics + b"\n" + rust_bytes + b"\n"

    return python_metrics


def configure_metrics() -> None:
    """Initialise metrics subsystem.

    Metrics are defined at module level so this is currently a no-op.
    Reserved for future use (e.g. starting the aerospike_py native
    Prometheus HTTP server if configured via env).
    """
    logger.info("Metrics ready (custom Prometheus registry)")
