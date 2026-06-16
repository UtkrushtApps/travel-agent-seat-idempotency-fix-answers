#!/usr/bin/env bash
set +e

echo "[kill] Starting cleanup..."

cd /root/task 2>/dev/null

echo "[kill] Stopping docker compose services..."
docker compose down --remove-orphans || true

echo "[kill] Removing docker compose volumes..."
docker compose down -v --remove-orphans || true

echo "[kill] Removing task-specific named volume..."
docker volume rm travel_seat_idem_data || true

echo "[kill] Removing task-specific network..."
docker network rm travel_seat_idem_net || true

echo "[kill] Removing task-specific images (if any)..."
docker rmi -f travel-agent-seat-idempotency-fix || true

echo "[kill] Pruning docker resources..."
docker system prune -a --volumes -f || true

echo "[kill] Removing task directory..."
rm -rf /root/task || true

echo "Cleanup completed successfully!"
