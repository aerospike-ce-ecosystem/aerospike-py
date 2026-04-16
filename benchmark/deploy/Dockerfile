# =============================================================================
# 2-Stage Dockerfile — uses pre-built aerospike-py wheel (cross-compiled via zig)
#
# Pre-build step (run on host):
#   maturin build --release --target x86_64-unknown-linux-gnu --zig \
#     -o benchmark/deploy/wheels/ -i python3.11
#
# Build:
#   cd /path/to/aerospike-py
#   podman buildx build --platform linux/amd64 \
#     -t IMAGE -f benchmark/deploy/Dockerfile .
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: python-builder — Install all Python dependencies
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 n3r-namespace-mrad1.n3r.reg.navercorp.com/mona-public/python:3.11.14-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# aerospike-py from pre-built cross-compiled wheel
COPY benchmark/deploy/wheels/*.whl /wheels/
RUN pip install --no-cache-dir /wheels/*.whl

# Core dependencies
RUN pip install --no-cache-dir \
    "numpy>=2.0" \
    "aerospike>=19.0.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.0" \
    "rich>=14.0"

# OTel tracing + metrics
RUN pip install --no-cache-dir \
    "opentelemetry-api>=1.20.0" \
    "opentelemetry-sdk>=1.20.0" \
    "opentelemetry-exporter-otlp-proto-grpc>=1.20.0" \
    "opentelemetry-instrumentation-fastapi>=0.41b0" \
    "prometheus-client>=0.20.0"

# Official aerospike client OTel instrumentation (pre-release, install with --no-deps
# to avoid pulling opentelemetry-instrumentation==0.61b0.dev which is not on PyPI)
RUN pip install --no-cache-dir --no-deps \
    "opentelemetry-instrumentation-aerospike==0.61b0.dev0"

# PyTorch (CPU-only)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# NELO logging (Naver internal artifactory)
RUN pip install --no-cache-dir \
    "pynelo[async]>=1.3.0" \
    --extra-index-url=https://artifactory.navercorp.com/artifactory/api/pypi/pypi-virtual/simple


# ---------------------------------------------------------------------------
# Stage 2: runtime — Minimal production image
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 n3r-namespace-mrad1.n3r.reg.navercorp.com/mona-public/python:3.11.14-slim

# Copy installed packages from builder
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

WORKDIR /app

# Benchmark app source + data
COPY benchmark/src/ src/
COPY benchmark/data/ data/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# 8000: FastAPI HTTP  |  9464: aerospike-py native Prometheus metrics
EXPOSE 8000 9464

CMD ["uvicorn", "serving.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
