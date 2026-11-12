#!/usr/bin/env bash
# Arranca Free AI Router en Android (Termux / Linux proot) o en cualquier Linux,
# y muestra exactamente qué pegar en el harness o la APK.
#
#   bash scripts/android.sh              # puerto 8080
#   PORT=9000 bash scripts/android.sh    # otro puerto
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

if [ ! -d .venv ]; then
  echo "==> Creando entorno virtual e instalando dependencias"
  python -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env || true
  echo "==> He creado .env. Edítalo con 'nano .env' para poner tus claves."
  echo "    (El router arranca igual, pero sin claves no puede responder.)"
fi

TOKEN="$(grep -E '^[[:space:]]*ROUTER_TOKEN=' .env | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
if [ -z "$TOKEN" ]; then
  TOKEN="(vacío: cualquier API key vale)"
fi

IP=""
if command -v ip >/dev/null 2>&1; then
  IP="$(ip -4 addr show 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | grep -v '^127\.' | head -1 || true)"
fi
if [ -z "$IP" ] && command -v ifconfig >/dev/null 2>&1; then
  IP="$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '^127\.' | head -1 || true)"
fi

cat <<EOF

  ┌───────────────────────────────────────────────────────────────────┐
  │  Pega esto en tu harness / APK (proveedor "OpenAI compatible")    │
  ├───────────────────────────────────────────────────────────────────┤
  │  Base URL  :  http://127.0.0.1:${PORT}/v1
  │  API Key   :  ${TOKEN}
  │  Modelo    :  auto
  ├───────────────────────────────────────────────────────────────────┤
  │  Desde otro dispositivo de la red Wi-Fi:
  │  Base URL  :  http://${IP:-IP_DEL_MOVIL}:${PORT}/v1
  │  Consola   :  http://127.0.0.1:${PORT}/
  └───────────────────────────────────────────────────────────────────┘

  Ctrl+C para detener el router.

EOF

exec ./.venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1
