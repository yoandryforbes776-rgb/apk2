#!/data/data/com.termux/files/usr/bin/bash
# Instalación de Free AI Router dentro de Termux (Android).
# Uso: bash scripts/termux-setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 Instalando paquetes base"
pkg update -y
pkg install -y python git curl

echo "==> 2/4 Creando entorno virtual"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "==> 3/4 Preparando configuración"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    Creado .env (edítalo con nano .env y pon tus claves y tokens)"
else
  echo "    .env ya existe, no se toca"
fi
chmod 600 .env || true

echo "==> 4/4 Diagnóstico"
python scripts/doctor.py || true

cat <<'MSG'

Listo. Para arrancar el router:

    source .venv/bin/activate
    termux-wake-lock                       # evita que Android suspenda el proceso
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

Abre http://127.0.0.1:8080 en el navegador del móvil para usar la consola.
Si la APK corre en el mismo dispositivo:  http://127.0.0.1:8080/v1
Si corre en el emulador:                  http://10.0.2.2:8080/v1
Si está en otro móvil de la red local:    http://IP-DEL-HOST:8080/v1
MSG
