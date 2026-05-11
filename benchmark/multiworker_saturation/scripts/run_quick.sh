#!/usr/bin/env bash
# Short VU 100-only cell — captures CPU%/latency at the saturation point
# in ~2 minutes (warmup 15s + VU 100 plateau 90s + container spin-up overhead).
#
# Used after the full saturation curve is captured to refine the CPU%
# measurement (the run-wide CPU average is dominated by lower-VU plateaus).

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
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[[ -z "${CLIENT_KIND}" ]] && { echo "--client required" >&2; exit 2; }

DATE_DIR="$(date +%Y%m%d)"
TS="$(date +%H%M%S)"
LABEL="${LABEL:-quick_${CLIENT_KIND}_py${PYTHON_VERSION//./_}_${TS}}"
RUN_DIR="${ROOT_DIR}/results/saturation_${DATE_DIR}/${LABEL}"
mkdir -p "${RUN_DIR}"

IMAGE_TAG="py${PYTHON_VERSION//./_}"
IMAGE_NAME="aerospike-py-saturation:${IMAGE_TAG}"

echo "── Quick cell: client=${CLIENT_KIND} python=${PYTHON_VERSION} → ${RUN_DIR}"

# Reuse existing image (already built by full run).
IMAGE_TAG="${IMAGE_TAG}" CLIENT_KIND="${CLIENT_KIND}" podman compose \
    -f "${ROOT_DIR}/compose.saturation.yaml" up -d

for i in {1..30}; do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
    sleep 2
done
podman exec saturation-app python -m app.seed >/dev/null

# k6 + stats in parallel for ~110s
uv run python "${ROOT_DIR}/scripts/collect_metrics.py" \
    --container saturation-app \
    --duration 120 \
    --interval 1.0 \
    --out "${RUN_DIR}/container_stats.json" &
STATS_PID=$!

k6 run \
    --summary-export "${RUN_DIR}/k6_summary.json" \
    --out "json=${RUN_DIR}/k6_raw.json" \
    "${ROOT_DIR}/loadtest/k6_vu100_only.js" \
    || true

wait "${STATS_PID}" || true

cat > "${RUN_DIR}/meta.json" <<EOF
{
    "client": "${CLIENT_KIND}",
    "python_version": "${PYTHON_VERSION}",
    "mode": "quick_vu100_only",
    "started_at": "${DATE_DIR}_${TS}"
}
EOF

podman compose -f "${ROOT_DIR}/compose.saturation.yaml" down

echo "── Done: ${RUN_DIR}"
