"""Tests del contexto que recibe el briefing (src/nodes.py, src/notion_db.py).

Bug real que motiva este archivo: el usuario marcaba un pendiente como
hecho con el checkbox y a la mañana siguiente el briefing se lo seguía
reportando como pendiente, con una cuenta de días que crecía sola
("arrastrados 4 días", "arrastrados 5 días").

La causa no era el checkbox: los briefings anteriores entraban en el
contexto del briefing de hoy, así que el LLM releía su propia prosa del día
anterior —donde los pendientes están escritos como texto, sin estado— y la
copiaba. El estado real vive en las filas `Pendiente`, que sí se leen.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.nodes import _TIPOS_FUERA_DEL_CONTEXTO, leer_notion, node_notion
from src.notion_db import consultar, formatear


def _fila(tipo, hecho=False, titulo="algo"):
    return {
        "id": "fila-1",
        "properties": {
            "Tipo": {"select": {"name": tipo}},
            "Hecho": {"checkbox": hecho},
            "Fecha": {"date": {"start": "2026-08-03T09:00:00"}},
            "Contenido": {"title": [{"plain_text": titulo}]},
            "Origen": {"rich_text": []},
        },
    }


# ── el briefing no debe leerse a sí mismo ───────────────────────────
def test_los_briefings_anteriores_quedan_fuera_del_contexto():
    client = MagicMock()
    with patch("src.nodes.settings") as s, patch("src.nodes.Client"), patch(
        "src.nodes.leer_notion", return_value="contexto"
    ) as leer:
        s.notion_token, s.notion_page_id = "token", "page"
        s.notion_memoria_ds_id = "ds-1"
        node_notion({})
    assert "Briefing" in leer.call_args.kwargs["tipos_excluidos"]


def test_la_exclusion_la_aplica_notion_en_el_filtro():
    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1", tipos_excluidos=("Briefing",))
    filtro = client.data_sources.query.call_args.kwargs["filter"]
    assert filtro == {"property": "Tipo", "select": {"does_not_equal": "Briefing"}}


def test_excluir_se_combina_con_el_rango_de_fechas():
    from datetime import datetime

    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1", desde=datetime(2026, 7, 1), tipos_excluidos=("Briefing",))
    condiciones = client.data_sources.query.call_args.kwargs["filter"]["and"]
    assert any("does_not_equal" in c.get("select", {}) for c in condiciones)
    assert any("on_or_after" in c.get("date", {}) for c in condiciones)


def test_leer_notion_propaga_la_exclusion():
    client = MagicMock()
    with patch("src.notion_db.consultar", return_value=[]) as consulta:
        leer_notion(client, "page", "ds-1", tipos_excluidos=("Briefing",))
    assert consulta.call_args.kwargs["tipos_excluidos"] == ("Briefing",)


def test_sin_exclusiones_no_se_filtra_por_tipo():
    client = MagicMock()
    client.data_sources.query.return_value = {"results": [], "has_more": False}
    consultar(client, "ds-1")
    assert "filter" not in client.data_sources.query.call_args.kwargs


# ── el estado tiene que ser legible para el LLM ─────────────────────
def test_un_pendiente_hecho_se_marca_con_palabras_no_solo_con_emoji():
    # un "✅" suelto se le pasaba por alto al modelo
    texto = formatear([_fila("Pendiente", hecho=True)])
    assert "[HECHO ✅]" in texto


def test_un_pendiente_abierto_se_marca_como_tal():
    texto = formatear([_fila("Pendiente", hecho=False)])
    assert "[PENDIENTE ⬜]" in texto


def test_los_reportes_no_llevan_marca_de_estado():
    # el checkbox solo significa algo en los pendientes
    texto = formatear([_fila("Reporte")])
    assert "[PENDIENTE ⬜]" not in texto and "[HECHO ✅]" not in texto


def test_la_constante_documenta_que_briefing_queda_fuera():
    assert _TIPOS_FUERA_DEL_CONTEXTO == ("Briefing",)
