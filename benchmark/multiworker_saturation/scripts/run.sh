#!/usr/bin/env bash
# Run one cell of the saturation matrix.
#
# Usage:
#   ./scripts/run.sh --client {aerospike-py|legacy} --python {3.11|3.14t} [--label <id>]
#
# Prerequisites (host):
#   - Aerospike CE running at 127.0.0.1:18710 (e.g. `make run-aerospike-ce`)
#   - Seed data loaded (`uv run python -m app.seed`)
#   - podman, k6 installed
#
# Output:
#   results/saturation_<date>/<client>_py<version>_<ts>/
#     ├── k6_summary.json          — k6 metrics (per-phase)
#     ├── k6_raw.json              — k6 detailed stream (gz-able)
#     ├── container_stats.json     — podman stats poll
#     └── meta.json                — cell metadata (client, python, env)

set -euo pipefail

CLIENT_KIND=""
PYTHON_VERSION="3.11"
LABEL=""
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../.." && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --client) CLIENT_KIND="$2"; shift 2 ;;
        --python) PYTHON_VERSION="$2"; shift 2 ;;
        --label) LABEL="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,18p' "$0" && exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "${CLIENT_KIND}" ]]; then
    echo "--client {aerospike-py|legacy} required" >&2
    exit 2
fi

DATE_DIR="$(date +%Y%m%d)"
TS="$(date +%H%M%S)"
LABEL="${LABEL:-${CLIENT_KIND}_py${PYTHON_VERSION//./_}_${TS}}"
RUN_DIR="${ROOT_DIR}/results/saturation_${DATE_DIR}/${LABEL}"
mkdir -p "${RUN_DIR}"

echo "── Cell: client=${CLIENT_KIND} python=${PYTHON_VERSION} → ${RUN_DIR}"

IMAGE_TAG="py${PYTHON_VERSION//./_}"
IMAGE_NAME="aerospike-py-saturation:${IMAGE_TAG}"

# 1. Build image (idempotent — podman cache will skip if unchanged)
echo "── Building image ${IMAGE_NAME}"
(cd "${REPO_ROOT}" && podman build \
    -f benchmark/multiworker_saturation/app/Containerfile \
    --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
    -t "${IMAGE_NAME}" \
    .)

# 2. Bring up app
echo "── Starting saturation-app"
IMAGE_TAG="${IMAGE_TAG}" CLIENT_KIND="${CLIENT_KIND}" podman compose \
    -f "${ROOT_DIR}/compose.saturation.yaml" \
    up -d

# 3. Wait for healthy
echo -n "── Waiting for /health "
for i in {1..30}; do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo " ok"
        break
    fi
    echo -n "."
    sleep 2
done

# 3b. Seed data (idempotent — Aerospike storage-engine memory is reset on
# container recreate, so we always seed fresh).
echo "── Seeding data from inside saturation-app"
podman exec saturation-app python -m app.seed

# 4. k6 + podman stats in parallel.
# k6 total duration = 15 (warmup) + 5 × 90 = 465s + a small tail → poll for 500s.
echo "── Starting podman stats poll (background)"
uv run python "${ROOT_DIR}/scripts/collect_metrics.py" \
    --container saturation-app \
    --duration 500 \
    --interval 1.0 \
    --out "${RUN_DIR}/container_stats.json" &
STATS_PID=$!

echo "── Running k6 saturation script"
k6 run \
    --summary-export "${RUN_DIR}/k6_summary.json" \
    --out "json=${RUN_DIR}/k6_raw.json" \
    "${ROOT_DIR}/loadtest/k6_saturation.js" \
    || echo "(k6 exited non-zero, continuing for analysis)"

wait "${STATS_PID}" || true

# 5. Save metadata
cat > "${RUN_DIR}/meta.json" <<EOF
{
    "client": "${CLIENT_KIND}",
    "python_version": "${PYTHON_VERSION}",
    "image": "${IMAGE_NAME}",
    "host_uname": "$(uname -a | tr -d '"')",
    "podman_version": "$(podman --version)",
    "k6_version": "$(k6 version 2>&1 | head -1)",
    "started_at": "${DATE_DIR}_${TS}",
    "env": {
        "AEROSPIKE_RUNTIME_WORKERS": "1",
        "AEROSPIKE_PY_INTERNAL_METRICS": "1",
        "CPU_BOUND_ENABLED": "1",
        "NUM_FEATURE_VIEWS": "9",
        "KEYS_PER_FV": "80"
    }
}
EOF

# 6. Bring down app
echo "── Stopping saturation-app"
podman compose -f "${ROOT_DIR}/compose.saturation.yaml" down

echo "── Done: ${RUN_DIR}"
