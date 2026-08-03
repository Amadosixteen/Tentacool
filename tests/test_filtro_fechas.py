"""Tests del filtro desde → hasta y del parseo de entradas.

El caso que motiva todo esto: cuando la página lleva meses, encontrar "lo
de julio" a mano es inviable. El filtro se apoya en que cada entrada
empieza por una cabecera con sello de tiempo, así que lo que se prueba
aquí es sobre todo que esas cabeceras se reconozcan — incluidas las del
formato antiguo, que no llevaban día de la semana ni origen.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.nodes import (
    filtrar_entradas,
    leer_notion,
    parsear_entradas,
    parsear_fecha,
)
from src.notion_db import _titulo, consultar


# ── parseo de cabeceras ─────────────────────────────────────────────
def test_reconoce_el_formato_actual_con_dia_y_origen():
    [e] = parsear_entradas(["🕐 lunes 03/08/2026 09:51  ·  📁 tentacool (main)", "algo"])
    assert e.fecha == datetime(2026, 8, 3, 9, 51)
    assert e.origen == "tentacool (main)"
    assert e.lineas == ["algo"]


def test_reconoce_el_formato_antiguo_sin_dia_ni_origen():
    [e] = parsear_entradas(["🕐 01/08/2026 16:31", "briefing viejo"])
    assert e.fecha == datetime(2026, 8, 1, 16, 31)
    assert e.origen == ""


def test_cabecera_dentro_de_un_bloque_multilinea():
    # la versión antigua escribía cabecera y cuerpo en un mismo párrafo:
    # mirando bloque a bloque esas entradas se perdían
    [e] = parsear_entradas(["🕐 03/08/2026 08:01\n\n- actividad reciente"])
    assert e.fecha == datetime(2026, 8, 3, 8, 1)
    assert "- actividad reciente" in e.lineas


def test_contenido_sin_cabecera_queda_sin_fecha():
    [e] = parsear_entradas(["credenciales escritas a mano"])
    assert e.fecha is None
    assert e.lineas == ["credenciales escritas a mano"]


def test_varias_entradas_se_separan_por_cabecera():
    entradas = parsear_entradas(
        ["suelto", "🕐 03/08/2026 09:00", "a", "🕐 02/08/2026 09:00", "b"]
    )
    assert [e.fecha for e in entradas] == [
        None,
        datetime(2026, 8, 3, 9, 0),
        datetime(2026, 8, 2, 9, 0),
    ]


# ── parseo de la fecha que escribe el usuario ───────────────────────
@pytest.mark.parametrize(
    "texto", ["2026-07-01", "01/07/2026", "01-07-2026", "2026/07/01"]
)
def test_acepta_los_formatos_habituales(texto):
    assert parsear_fecha(texto) == datetime(2026, 7, 1)


def test_hasta_llega_al_final_del_dia():
    # si 'hasta' se quedara a las 00:00, un rango "hasta el 31" perdería
    # todo lo escrito ese día
    assert parsear_fecha("2026-07-31", fin_de_dia=True) == datetime(2026, 7, 31, 23, 59)


def test_hoy_y_ayer_se_resuelven_contra_la_zona_configurada():
    with patch("src.nodes._ahora", return_value=datetime(2026, 8, 3, 15, 30)):
        assert parsear_fecha("hoy") == datetime(2026, 8, 3)
        assert parsear_fecha("ayer") == datetime(2026, 8, 2)


def test_fecha_vacia_no_filtra():
    assert parsear_fecha("") is None


def test_fecha_ilegible_avisa_en_vez_de_devolver_nada():
    with pytest.raises(ValueError, match="no reconocida"):
        parsear_fecha("el martes pasado")


# ── filtrado ────────────────────────────────────────────────────────
def _entradas():
    return parsear_entradas(
        [
            "sin cabecera",
            "🕐 03/08/2026 09:00", "hoy",
            "🕐 15/07/2026 09:00", "julio",
            "🕐 02/06/2026 09:00", "junio",
        ]
    )


def test_el_texto_suelto_tras_una_cabecera_pertenece_a_esa_entrada():
    # Caso real de la migración: al insertar lo nuevo arriba, el contenido
    # antiguo sin sello queda por debajo de la última cabecera y se absorbe
    # en ella. Solo el texto anterior a la PRIMERA cabecera queda suelto.
    entradas = parsear_entradas(["🕐 03/08/2026 09:00", "nuevo", "credenciales viejas"])
    assert len(entradas) == 1
    assert entradas[0].lineas == ["nuevo", "credenciales viejas"]


def test_filtra_por_rango_inclusive():
    dentro = filtrar_entradas(
        _entradas(), parsear_fecha("2026-07-01"), parsear_fecha("2026-07-31", True)
    )
    assert [e.lineas for e in dentro] == [["julio"]]


def test_solo_desde_deja_todo_lo_posterior():
    dentro = filtrar_entradas(_entradas(), desde=parsear_fecha("2026-07-01"))
    assert [e.lineas for e in dentro] == [["hoy"], ["julio"]]


def test_sin_rango_devuelve_todo_incluido_lo_sin_fecha():
    assert len(filtrar_entradas(_entradas())) == 4


def test_las_entradas_sin_fecha_no_se_cuelan_en_un_rango():
    # no se puede afirmar que estén dentro, así que se descartan en vez de
    # asumirles una fecha
    dentro = filtrar_entradas(_entradas(), desde=parsear_fecha("2020-01-01"))
    assert all(e.fecha is not None for e in dentro)
    assert len(dentro) == 3


# ── consulta a la base de datos ─────────────────────────────────────
def test_el_filtro_de_fechas_lo_aplica_notion_no_nosotros():
    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1", desde=datetime(2026, 7, 1), hasta=datetime(2026, 7, 31))
    filtro = client.data_sources.query.call_args.kwargs["filter"]
    assert filtro["and"][0]["date"]["on_or_after"].startswith("2026-07-01")
    assert filtro["and"][1]["date"]["on_or_before"].startswith("2026-07-31")


def test_las_filas_llegan_de_la_mas_reciente_a_la_mas_antigua():
    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1")
    sorts = client.data_sources.query.call_args.kwargs["sorts"]
    assert sorts == [{"property": "Fecha", "direction": "descending"}]


def test_sin_rango_no_se_manda_filtro():
    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1")
    assert "filter" not in client.data_sources.query.call_args.kwargs


def test_leer_notion_usa_la_base_cuando_esta_configurada():
    client = MagicMock()
    with patch("src.notion_db.consultar", return_value=[]) as consulta, patch(
        "src.nodes.leer_notion_filtrado"
    ) as bloques:
        leer_notion(client, "page-1", "ds-1", desde="2026-07-01")
    bloques.assert_not_called()
    assert consulta.call_args.kwargs["desde"] == datetime(2026, 7, 1)


def test_leer_notion_cae_a_los_bloques_sin_base():
    client = MagicMock()
    with patch("src.nodes.leer_notion_filtrado", return_value="ok") as bloques:
        assert leer_notion(client, "page-1", "") == "ok"
    bloques.assert_called_once()


def test_rango_invertido_se_corrige_en_vez_de_no_devolver_nada():
    client = MagicMock()
    with patch("src.notion_db.consultar", return_value=[]) as consulta:
        leer_notion(client, "p", "ds-1", desde="2026-07-31", hasta="2026-07-01")
    assert consulta.call_args.kwargs["desde"] < consulta.call_args.kwargs["hasta"]


# ── título de las filas ─────────────────────────────────────────────
def test_el_titulo_salta_los_encabezados_de_seccion():
    assert _titulo("## Pendientes\nsaas_clinic: revisar el cron") == (
        "saas_clinic: revisar el cron"
    )


def test_el_titulo_no_lleva_markdown():
    assert _titulo("**Briefing diario — 03/08/2026**") == "Briefing diario — 03/08/2026"


def test_el_titulo_conserva_los_guiones_bajos_de_los_nombres():
    # `saas_clinic` no puede quedar como `saasclinic`
    assert _titulo("- **saas_clinic:** actualizar .env") == "saas_clinic: actualizar .env"
