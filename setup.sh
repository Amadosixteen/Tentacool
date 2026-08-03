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

echo "==> Generando .mcp.json con la ruta real de este clon"
sed "s#__TENTACOOL_ROOT__#$PWD#g" .mcp.json.example > .mcp.json

echo
echo "✔ Instalación terminada. Siguientes pasos:"
echo "  1. Edita .env con tus claves."
echo "  2. Prueba:        python main.py inicio"
echo "  3. Lee memoria:   python main.py leer"
echo "  4. (Notion) Historial filtrable por fechas:"
echo "     python main.py crear-bases   # crea las bases y muestra los IDs"
echo "     # pega los IDs en .env, y luego:"
echo "     python main.py migrar --dry-run && python main.py migrar"
echo "     python main.py fijar-base    # deja la tabla arriba de la página"
echo "  5. Crontab 8:00 (lun-vie): crontab -e y añade:"
echo "     0 8 * * 1-5 DISPLAY=:0 $PWD/.venv/bin/python $PWD/main.py inicio >> $PWD/cron-inicio.log 2>&1"
