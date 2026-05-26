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
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

for CLIENT in py official; do
  echo "==> starting uvicorn with CLIENT=$CLIENT"
  CLIENT=$CLIENT uv run uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1 \
    > "/tmp/bench_${CLIENT}.log" 2>&1 &
  SERVER_PID=$!

  # Wait for /healthz, but fail fast if the server process dies.
  HEALTHY=0
  for _ in $(seq 1 30); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "Server process (CLIENT=$CLIENT) died during startup. Logs:"
      cat "/tmp/bench_${CLIENT}.log"
      exit 1
    fi
    if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
      HEALTHY=1
      break
    fi
    sleep 0.5
  done

  if [[ "$HEALTHY" -ne 1 ]]; then
    echo "Server did not become healthy in 15s (CLIENT=$CLIENT). Logs:"
    cat "/tmp/bench_${CLIENT}.log"
    exit 1
  fi

  echo "==> warmup ${WARMUP_SECS}s"
  sleep "$WARMUP_SECS"

  HOST="$HOST" PORT="$PORT" \
    bash loadtest/run_oha.sh "$SCENARIO" "$CLIENT" "$CONCURRENCY" "$DURATION" "$BATCH_SIZE"

  echo "==> stopping uvicorn (pid $SERVER_PID)"
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
done

echo
echo "==> all runs done. render report:"
echo "    make report"
