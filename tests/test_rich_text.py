"""Tests de _rich_text (src/nodes.py).

Cubre el bug real: el briefing del LLM llega en markdown y se escribía en
Notion como texto plano, así que los `**` y los `##` se veían literales en
la página en vez de renderizarse como negrita/título.
"""
from __future__ import annotations

from src.nodes import _MAX_RICH_TEXT, _bloque_parrafo, _bloque_todo, _rich_text


def _plano(fragmentos):
    return "".join(f["text"]["content"] for f in fragmentos)


# ── negrita ─────────────────────────────────────────────────────────
def test_negrita_se_convierte_en_anotacion_y_pierde_los_asteriscos():
    frags = _rich_text("- **Actividad reciente:** solo Tentacool")
    assert _plano(frags) == "- Actividad reciente: solo Tentacool"
    negritas = [f for f in frags if f.get("annotations", {}).get("bold")]
    assert len(negritas) == 1
    assert negritas[0]["text"]["content"] == "Actividad reciente:"


def test_negrita_con_guiones_bajos():
    frags = _rich_text("__importante__")
    assert frags[0]["text"]["content"] == "importante"
    assert frags[0]["annotations"]["bold"] is True


def test_varias_negritas_en_la_misma_linea():
    frags = _rich_text("**uno** y **dos**")
    assert _plano(frags) == "uno y dos"
    assert [f["text"]["content"] for f in frags if f.get("annotations")] == [
        "uno",
        "dos",
    ]


# ── código inline ───────────────────────────────────────────────────
def test_codigo_inline_se_anota_como_code():
    frags = _rich_text("ejecutar `php artisan optimize:clear` ya")
    assert _plano(frags) == "ejecutar php artisan optimize:clear ya"
    codigo = [f for f in frags if f.get("annotations", {}).get("code")]
    assert codigo[0]["text"]["content"] == "php artisan optimize:clear"


# ── títulos markdown ────────────────────────────────────────────────
def test_titulo_markdown_pierde_las_almohadillas_y_queda_en_negrita():
    frags = _rich_text("## Reporte IA")
    assert _plano(frags) == "Reporte IA"
    assert frags[0]["annotations"]["bold"] is True


def test_titulo_solo_al_inicio_de_linea():
    frags = _rich_text("issue #12 pendiente")
    assert _plano(frags) == "issue #12 pendiente"
    assert not any(f.get("annotations") for f in frags)


# ── texto sin markdown ──────────────────────────────────────────────
def test_texto_plano_queda_en_un_solo_fragmento_sin_anotaciones():
    frags = _rich_text("sin nada especial")
    assert frags == [
        {"type": "text", "text": {"content": "sin nada especial"}}
    ]


def test_texto_vacio_no_genera_fragmentos():
    assert _rich_text("") == []


def test_multilinea_conserva_los_saltos():
    frags = _rich_text("**Briefing**\n- uno\n- dos")
    assert _plano(frags) == "Briefing\n- uno\n- dos"


# ── límite de 2000 caracteres de la API ─────────────────────────────
def test_fragmento_largo_se_parte_para_no_exceder_el_limite_de_notion():
    frags = _rich_text("x" * (_MAX_RICH_TEXT + 50))
    assert len(frags) == 2
    assert all(len(f["text"]["content"]) <= _MAX_RICH_TEXT for f in frags)
    assert _plano(frags) == "x" * (_MAX_RICH_TEXT + 50)


# ── los bloques usan el parser ──────────────────────────────────────
def test_bloque_parrafo_usa_rich_text():
    bloque = _bloque_parrafo("**hola**")
    assert bloque["paragraph"]["rich_text"][0]["text"]["content"] == "hola"


def test_bloque_todo_usa_rich_text():
    bloque = _bloque_todo("revisar `main`")
    frags = bloque["to_do"]["rich_text"]
    assert _plano(frags) == "revisar main"
    assert bloque["to_do"]["checked"] is False
