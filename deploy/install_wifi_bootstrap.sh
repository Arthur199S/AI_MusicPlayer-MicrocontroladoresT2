#!/usr/bin/env bash
# Instala o servico systemd que roda o Wi-Fi bootstrap no boot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/deploy/wifi-bootstrap.service"
UNIT_DST="/etc/systemd/system/wifi-bootstrap.service"
VENV_PY="$ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Crie o venv antes: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable wifi-bootstrap.service
echo "Servico habilitado. Para testar agora:"
echo "  sudo systemctl start wifi-bootstrap.service"
echo "  journalctl -u wifi-bootstrap.service -b --no-pager"
