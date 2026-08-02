#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  Instalador universal del orquestador de jornada
#
#  Uso:   bash setup.sh
#  Hace:  crea .venv, instala dependencias y genera .env si no existe
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Creando entorno virtual (.venv)"
python3 -m venv .venv

echo "==> Instalando dependencias"
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    echo "==> Creando .env a partir de .env.example"
    cp .env.example .env
    echo "    ⚠️  Edita .env y rellena tus claves (LLM, GitHub, Notion...)"
else
    echo "==> .env ya existe, no se toca"
fi

echo
echo "✔ Instalación terminada. Siguientes pasos:"
echo "  1. Edita .env con tus claves."
echo "  2. Prueba:        python main.py inicio"
echo "  3. Lee memoria:   python main.py leer"
echo "  4. Crontab 8:00 (lun-vie): crontab -e y añade:"
echo "     0 8 * * 1-5 DISPLAY=:0 $PWD/.venv/bin/python $PWD/main.py inicio >> $PWD/cron-inicio.log 2>&1"
