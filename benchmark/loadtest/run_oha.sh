#!/usr/bin/env bash
# Run a single oha measurement against a serving FastAPI process.
#
# Usage:
#   loadtest/run_oha.sh <scenario> <client> <concurrency> <duration> <batch_size>
#
# Output:
#   results/<scenario>_<client>_<pyver>_<timestamp>/oha.json
#   results/<scenario>_<client>_<pyver>_<timestamp>/meta.json
#
# The server is assumed to be running already on $HOST:$PORT with the
# matching CLIENT env var. Use loadtest/bench_matrix.sh to orchestrate
# start/stop across clients.

set -euo pipefail

SCENARIO="${1:-s1}"
CLIENT="${2:-py}"
CONCURRENCY="${3:-10}"
DURATION="${4:-30s}"
BATCH_SIZE="${5:-50}"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

PYVER=$(uv run python -c 'import sys; v=sys.version_info; t="t" if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled() else ""; print(f"{v.major}.{v.minor}{t}")')
TS=$(date +%Y%m%d_%H%M%S)
OUT_DIR="results/${SCENARIO}_${CLIENT}_py${PYVER}_${TS}"
mkdir -p "$OUT_DIR"

case "$SCENARIO" in
  s1)
    URL="http://${HOST}:${PORT}/s1/read"
    BODY="{\"offset\":0,\"batch_size\":${BATCH_SIZE}}"
    ;;
  s2)
    URL="http://${HOST}:${PORT}/s2/predict"
    BODY="{\"offset\":0,\"batch_size\":${BATCH_SIZE}}"
    ;;
  s3)
    URL="http://${HOST}:${PORT}/s3/predict"
    BODY="{\"offset\":0,\"batch_size\":${BATCH_SIZE}}"
    ;;
  s4_gather)
    # 4 fan-out groups of BATCH_SIZE keys each = 4×BATCH_SIZE total.
    URL="http://${HOST}:${PORT}/s4/gather"
    BODY="{\"offset\":0,\"n_groups\":4,\"per_group\":${BATCH_SIZE}}"
    ;;
  s4_single)
    URL="http://${HOST}:${PORT}/s4/single"
    BODY="{\"offset\":0,\"n_groups\":4,\"per_group\":${BATCH_SIZE}}"
    ;;
  s5)
    URL="http://${HOST}:${PORT}/s5/subset"
    BODY="{\"offset\":0,\"batch_size\":${BATCH_SIZE}}"
    ;;
  *)
    echo "Unknown scenario: $SCENARIO" >&2
    echo "Valid: s1 s2 s3 s4_gather s4_single s5" >&2
    exit 2
    ;;
esac

echo "[oha] scenario=$SCENARIO client=$CLIENT py=$PYVER c=$CONCURRENCY z=$DURATION batch=$BATCH_SIZE"
echo "[oha] -> $OUT_DIR"

# Save run metadata so report.py can correlate without re-parsing oha JSON.
cat > "$OUT_DIR/meta.json" <<EOF
{
  "scenario": "$SCENARIO",
  "client": "$CLIENT",
  "python": "$PYVER",
  "concurrency": $CONCURRENCY,
  "duration": "$DURATION",
  "batch_size": $BATCH_SIZE,
  "url": "$URL",
  "timestamp": "$TS"
}
EOF

oha \
  --no-tui \
  --output-format json \
  -c "$CONCURRENCY" \
  -z "$DURATION" \
  -m POST \
  -T application/json \
  -d "$BODY" \
  "$URL" > "$OUT_DIR/oha.json"

echo "[oha] done."
