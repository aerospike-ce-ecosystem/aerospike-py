#!/usr/bin/env bash
# Bench the same scenario against both clients back-to-back.
#
# Starts a uvicorn process per CLIENT, waits for /healthz, runs oha, kills.
# Does NOT touch Aerospike — bring it up with `make up` first.
#
# Usage:
#   loadtest/bench_matrix.sh <scenario> <concurrency> <duration> <batch_size>

set -euo pipefail

SCENARIO="${1:-s1}"
CONCURRENCY="${2:-10}"
DURATION="${3:-30s}"
BATCH_SIZE="${4:-50}"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

WARMUP_SECS=3

for CLIENT in py official; do
  echo "==> starting uvicorn with CLIENT=$CLIENT"
  CLIENT=$CLIENT uv run uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1 \
    > "/tmp/bench_${CLIENT}.log" 2>&1 &
  SERVER_PID=$!

  # Wait for /healthz to respond.
  for i in $(seq 1 30); do
    if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done

  if ! curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
    echo "Server did not become healthy. Logs:"
    cat "/tmp/bench_${CLIENT}.log"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
  fi

  echo "==> warmup ${WARMUP_SECS}s"
  sleep $WARMUP_SECS

  HOST="$HOST" PORT="$PORT" \
    bash loadtest/run_oha.sh "$SCENARIO" "$CLIENT" "$CONCURRENCY" "$DURATION" "$BATCH_SIZE"

  echo "==> stopping uvicorn (pid $SERVER_PID)"
  kill $SERVER_PID 2>/dev/null || true
  wait $SERVER_PID 2>/dev/null || true
done

echo
echo "==> all runs done. render report:"
echo "    make report"
