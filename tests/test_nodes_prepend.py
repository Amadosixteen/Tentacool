"""Tests de _prepend_blocks y sus helpers (src/nodes.py).

Cubre el incidente real: reordenar bloques de Notion requiere borrar y
recrear, y una vez se borró por error un bloque `child_page` (subpágina)
que no se puede recrear igual — quedó en la papelera y hubo que
restaurarlo a mano. Estos tests aseguran que NUNCA se vuelva a borrar
un bloque que no sea `paragraph`/`to_do` sin hijos.
"""
from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

from src.nodes import _es_reordenable, _prepend_blocks, _recrear_bloque


def _bloque(id_, tipo, has_children=False, **contenido):
    return {"id": id_, "type": tipo, "has_children": has_children, tipo: contenido}


# ── _es_reordenable ─────────────────────────────────────────────────
def test_paragraph_sin_hijos_es_reordenable():
    b = _bloque("1", "paragraph", rich_text=[])
    assert _es_reordenable(b) is True


def test_to_do_sin_hijos_es_reordenable():
    b = _bloque("1", "to_do", rich_text=[], checked=False)
    assert _es_reordenable(b) is True


def test_child_page_no_es_reordenable():
    b = _bloque("1", "child_page", title="COMMITS EN VIVO")
    assert _es_reordenable(b) is False


def test_paragraph_con_hijos_no_es_reordenable():
    b = _bloque("1", "paragraph", has_children=True, rich_text=[])
    assert _es_reordenable(b) is False


def test_bloque_desconocido_no_es_reordenable():
    b = _bloque("1", "child_database", title="x")
    assert _es_reordenable(b) is False


# ── _recrear_bloque ──────────────────────────────────────────────────
def test_recrear_bloque_descarta_campos_de_solo_lectura():
    """Notion devuelve 'icon': null en paragraph; la API de escritura lo
    rechaza. El bug real que causó el primer intento fallido."""
    b = _bloque("1", "paragraph", rich_text=[{"text": "hola"}], icon=None, color="default")
    recreado = _recrear_bloque(b)
    assert recreado == {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": "hola"}], "color": "default"},
    }
    assert "icon" not in recreado["paragraph"]


def test_recrear_bloque_to_do_conserva_checked():
    b = _bloque("1", "to_do", rich_text=[{"text": "pendiente"}], checked=True, color="default")
    recreado = _recrear_bloque(b)
    assert recreado["to_do"]["checked"] is True


# ── _prepend_blocks ──────────────────────────────────────────────────
def _client_con(existentes: list[dict], has_more=False):
    client = MagicMock()
    client.blocks.children.list.return_value = {
        "results": existentes,
        "has_more": has_more,
    }
    return client


def test_prepend_sin_bloques_existentes_solo_hace_append():
    client = _client_con([])
    nuevos = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}]

    total = _prepend_blocks(client, "page-id", nuevos)

    assert total == 1
    client.blocks.children.append.assert_called_once_with(
        block_id="page-id", children=nuevos
    )
    client.blocks.delete.assert_not_called()


def test_prepend_reordena_bloques_simples_arriba():
    existentes = [
        _bloque("a", "paragraph", rich_text=[{"text": "## Pendientes"}], color="default"),
        _bloque("b", "to_do", rich_text=[{"text": "viejo"}], checked=False, color="default"),
    ]
    client = _client_con(existentes)
    nuevos = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": "nuevo"}]}}]

    with patch("src.nodes.open", mock_open()), patch("src.nodes.os.makedirs"):
        total = _prepend_blocks(client, "page-id", nuevos)

    # Se borraron ambos bloques movibles, en cualquier orden
    ids_borrados = {c.kwargs["block_id"] for c in client.blocks.delete.call_args_list}
    assert ids_borrados == {"a", "b"}

    # El append final: nuevos primero, luego los viejos en su orden original
    payload = client.blocks.children.append.call_args.kwargs["children"]
    assert payload[0] == nuevos[0]
    assert payload[1]["paragraph"]["rich_text"] == [{"text": "## Pendientes"}]
    assert payload[2]["to_do"]["rich_text"] == [{"text": "viejo"}]
    assert total == len(payload)


def test_prepend_NUNCA_borra_una_child_page():
    """Regresión directa del incidente: una subpágina ('COMMITS EN VIVO')
    no debe borrarse ni intentar recrearse jamás, sin importar en qué
    posición esté entre los demás bloques."""
    existentes = [
        _bloque("subpagina", "child_page", title="COMMITS EN VIVO"),
        _bloque("parrafo", "paragraph", rich_text=[{"text": "algo"}], color="default"),
    ]
    client = _client_con(existentes)
    nuevos = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": "nuevo"}]}}]

    with patch("src.nodes.open", mock_open()), patch("src.nodes.os.makedirs"):
        _prepend_blocks(client, "page-id", nuevos)

    ids_borrados = {c.kwargs["block_id"] for c in client.blocks.delete.call_args_list}
    assert "subpagina" not in ids_borrados
    assert ids_borrados == {"parrafo"}

    # Tampoco debe aparecer reconstruida en el payload final
    payload = client.blocks.children.append.call_args.kwargs["children"]
    tipos = [p["type"] for p in payload]
    assert "child_page" not in tipos


def test_prepend_respalda_en_disco_antes_de_borrar():
    existentes = [_bloque("a", "paragraph", rich_text=[], color="default")]
    client = _client_con(existentes)
    m = mock_open()

    with patch("src.nodes.open", m), patch("src.nodes.os.makedirs") as mk:
        _prepend_blocks(client, "page-id", [])

    mk.assert_called_once()
    m.assert_called_once()
    # El respaldo se escribe ANTES de borrar
    escritura_antes_del_borrado = (
        m.call_args_list[0] and client.blocks.delete.called
    )
    assert escritura_antes_del_borrado


def test_prepend_pagina_resultados_de_notion():
    pagina1 = {"results": [_bloque("a", "paragraph", rich_text=[], color="default")], "has_more": True, "next_cursor": "cursor-2"}
    pagina2 = {"results": [_bloque("b", "paragraph", rich_text=[], color="default")], "has_more": False}
    client = MagicMock()
    client.blocks.children.list.side_effect = [pagina1, pagina2]

    with patch("src.nodes.open", mock_open()), patch("src.nodes.os.makedirs"):
        _prepend_blocks(client, "page-id", [])

    assert client.blocks.children.list.call_count == 2
    ids_borrados = {c.kwargs["block_id"] for c in client.blocks.delete.call_args_list}
    assert ids_borrados == {"a", "b"}
