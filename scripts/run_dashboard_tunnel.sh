#!/usr/bin/env bash
# Expoe o dashboard local via ngrok.
# Requisitos: ngrok no PATH e authtoken configurado
#   ngrok config add-authtoken SEU_TOKEN
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${DASHBOARD_PORT:-8080}"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  # carrega so DASHBOARD_PORT se estiver no .env
  PORT_FROM_ENV="$(grep -E '^[[:space:]]*DASHBOARD_PORT=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)"
  set +a
  if [[ -n "${PORT_FROM_ENV}" ]]; then
    PORT="$PORT_FROM_ENV"
  fi
fi

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok nao encontrado no PATH. Instale: https://ngrok.com/download" >&2
  exit 1
fi

echo "Tunelando http://127.0.0.1:${PORT} ..."
echo "Abra a URL https do ngrok e use ?token=SEU_DASHBOARD_TOKEN"
exec ngrok http "127.0.0.1:${PORT}"
