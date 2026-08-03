"""Tests de la bitácora 'Anotaciones' (src/nodes.py).

Lo que se garantiza aquí: cada entrada lleva su sello de tiempo completo
(día de la semana, fecha, hora y minuto) y el proyecto de origen, que es
justo lo que permite reconstruir después en qué se estaba trabajando.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from src.nodes import (
    _bloque_fecha,
    _contexto_proyecto,
    _sello_tiempo,
    write_notion_anotacion,
)

# lunes 3 de agosto de 2026, 09:51
FECHA = datetime(2026, 8, 3, 9, 51)


def _texto(bloque):
    return "".join(
        f["text"]["content"] for f in bloque["paragraph"]["rich_text"]
    )


# ── sello de tiempo ─────────────────────────────────────────────────
def test_sello_lleva_dia_fecha_hora_y_minuto():
    assert _sello_tiempo(FECHA) == "lunes 03/08/2026 09:51"


def test_dia_de_la_semana_en_espanol_sin_depender_del_locale():
    # bajo cron el locale suele ser C/POSIX y `%A` devolvería inglés
    assert _sello_tiempo(datetime(2026, 8, 9, 0, 0)).startswith("domingo")


# ── cabecera del bloque ─────────────────────────────────────────────
def test_cabecera_incluye_el_origen_cuando_se_pasa():
    bloque = _bloque_fecha(FECHA, "neobusiness (main)")
    assert _texto(bloque) == "🕐 lunes 03/08/2026 09:51  ·  📁 neobusiness (main)"


def test_cabecera_sin_origen_solo_lleva_la_fecha():
    assert _texto(_bloque_fecha(FECHA)) == "🕐 lunes 03/08/2026 09:51"


def test_fecha_y_origen_van_en_fragmentos_distintos_para_colorearlos():
    frags = _bloque_fecha(FECHA, "tentacool (main)")["paragraph"]["rich_text"]
    assert [f["annotations"]["color"] for f in frags] == ["red", "blue"]


# ── contexto del proyecto ───────────────────────────────────────────
def test_contexto_usa_la_raiz_del_repo_y_la_rama():
    with patch("src.nodes._git", side_effect=["/home/x/Projects/neobusiness", "main"]):
        assert _contexto_proyecto("/home/x/Projects/neobusiness/app") == (
            "neobusiness (main)"
        )


def test_contexto_sin_git_cae_al_nombre_de_la_carpeta():
    with patch("src.nodes._git", return_value=""):
        assert _contexto_proyecto("/home/x/sin_repo") == "sin_repo"


# ── escritura ───────────────────────────────────────────────────────
def test_anotacion_escribe_cabecera_y_texto_al_inicio():
    client = MagicMock()
    with patch("src.nodes._prepend_blocks", return_value=2) as prepend:
        n = write_notion_anotacion(
            client, "page-1", "clave del ERP", origen="neobusiness (main)", dt=FECHA
        )
    assert n == 2
    _, _, nuevos = prepend.call_args[0]
    assert _texto(nuevos[0]).endswith("📁 neobusiness (main)")
    assert _texto(nuevos[1]) == "clave del ERP"


def test_anotacion_vacia_no_toca_notion():
    client = MagicMock()
    with patch("src.nodes._prepend_blocks") as prepend:
        assert write_notion_anotacion(client, "page-1", "   ") == 0
    prepend.assert_not_called()


def test_anotacion_detecta_el_origen_si_no_se_pasa():
    client = MagicMock()
    with patch("src.nodes._prepend_blocks", return_value=2) as prepend, patch(
        "src.nodes._contexto_proyecto", return_value="detectado (rama)"
    ):
        write_notion_anotacion(client, "page-1", "algo", dt=FECHA)
    _, _, nuevos = prepend.call_args[0]
    assert "📁 detectado (rama)" in _texto(nuevos[0])
