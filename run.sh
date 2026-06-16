#!/usr/bin/env bash
set -euo pipefail

cd /root/task

echo "[run] Starting datastore via docker compose..."
docker compose up -d

echo "[run] Waiting for datastore readiness..."
for i in $(seq 1 30); do
  if docker compose exec -T seatdb pg_isready -U agent -d seatdb >/dev/null 2>&1; then
    echo "[run] Datastore is ready."
    break
  fi
  echo "[run] ...still waiting ($i)"
  sleep 2
  if [ "$i" -eq 30 ]; then
    echo "[run] Datastore did not become ready in time." >&2
    exit 1
  fi
done

echo "[run] Running tests..."
set +e
python -m pytest -q
test_rc=$?
set -e

if [ "$test_rc" -ne 0 ]; then
  echo "[run] Tests failed as expected for the unsolved starter project (rc=$test_rc)."
  echo "[run] Scaffold is healthy: datastore is up and the test suite executed."
else
  echo "[run] All tests passed."
fi

exit 0
