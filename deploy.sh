#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.production.yml)
HOST_STATIC=0
if [[ -f docker-compose.server.yml && -f /etc/caddy/Caddyfile ]]; then
  COMPOSE+=(-f docker-compose.server.yml)
  HOST_STATIC=1
fi

python3 scripts/check_vps_handoff.py

if [[ ! -f .env ]]; then
  echo "ERROR: .env is missing. Copy .env.example and configure production values." >&2
  exit 1
fi

echo "[1/6] Pulling latest code..."
git pull --ff-only

echo "[2/6] Validating production Compose configuration..."
"${COMPOSE[@]}" config --quiet

echo "[3/6] Building images..."
"${COMPOSE[@]}" build

echo "[4/6] Applying database migrations..."
"${COMPOSE[@]}" run --rm app alembic upgrade head

echo "[5/6] Starting services and waiting for health checks..."
"${COMPOSE[@]}" up -d --wait --wait-timeout 180

echo "[6/6] Publishing frontend assets..."
if [[ "$HOST_STATIC" == "1" ]]; then
  # The Arvan host's Caddy serves web/dist directly, while the frontend image
  # writes the same build to its Docker volume. Copy the verified container
  # output to Caddy's host path so deployments cannot leave stale UI behind.
  mkdir -p web/dist
  "${COMPOSE[@]}" exec -T frontend tar -C /usr/share/nginx/html -cf - . | tar -C web/dist -xf -
fi

"${COMPOSE[@]}" ps
echo "Production deployment is healthy."
