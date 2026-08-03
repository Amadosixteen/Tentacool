"""Servidor MCP: expone la página 'Memoria' de Notion como herramientas.

Así, Claude Code (u otro agente/IDE con soporte MCP) puede leer y escribir
en tu Notion de forma nativa, reutilizando el token y la página ya
configurados en .env y src/config.py.

Conexión (stdio):
    claude mcp add notion-memoria -- \
        /ruta/a/tentacool/.venv/bin/python \
        /ruta/a/tentacool/src/mcp_server.py

O vía .mcp.json en la raíz del proyecto (ya incluido).
"""
from __future__ import annotations

import os
import sys

# Se invoca como script directo (no como módulo de paquete), así que no hay
# import relativo posible: agregamos la raíz del proyecto al path para poder
# importar `src.config` / `src.nodes` de forma absoluta.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from notion_client import Client

from src.config import settings
from src.nodes import (
    _contexto_proyecto,
    _sello_tiempo,
    read_notion_memory,
    write_notion_anotacion,
    write_notion_memory,
)

mcp = FastMCP("notion-memoria")


def _client() -> Client:
    return Client(auth=settings.notion_token)


@mcp.tool()
def notion_leer_memoria() -> str:
    """Lee TODO el texto de la página 'Memoria' de Notion.

    Devuelve el contexto diario: lo avanzado, lo pendiente y lo siguiente.
    """
    if not settings.notion_token or not settings.notion_page_id:
        return "[Notion no configurado: token o ID de página vacíos]"
    try:
        return read_notion_memory(_client(), settings.notion_page_id) or (
            "(página 'Memoria' vacía)"
        )
    except Exception as e:  # noqa: BLE001
        return f"[Error leyendo Notion: {type(e).__name__}: {e}]"


@mcp.tool()
def notion_escribir_pendiente(texto: str) -> str:
    """Añade un PENDIENTE (checklist sin marcar) a la página 'Memoria'.

    Úsalo cuando pidan anotar algo que falta por hacer o quedó pendiente.
    """
    if not settings.notion_token or not settings.notion_page_id:
        return "[Notion no configurado]"
    try:
        n = write_notion_memory(_client(), settings.notion_page_id, pendientes=[texto])
        return f"✅ Pendiente añadido a Notion (+{n} bloque)."
    except Exception as e:  # noqa: BLE001
        return f"[Error escribiendo en Notion: {type(e).__name__}: {e}]"


@mcp.tool()
def notion_escribir_reporte(texto: str) -> str:
    """Añade un REPORTE o nota (párrafo de texto) a la página 'Memoria'.

    Úsalo cuando pidan resumir lo hecho en la jornada o dejar contexto.
    """
    if not settings.notion_token or not settings.notion_page_id:
        return "[Notion no configurado]"
    try:
        n = write_notion_memory(_client(), settings.notion_page_id, reportes=[texto])
        return f"✅ Reporte escrito en Notion (+{n} bloque)."
    except Exception as e:  # noqa: BLE001
        return f"[Error escribiendo en Notion: {type(e).__name__}: {e}]"


@mcp.tool()
def notion_leer_anotaciones() -> str:
    """Lee TODO el texto de la página 'Anotaciones' de Notion.

    Es la bitácora de recursos del día a día: enlaces, credenciales, cosas
    a mano. Úsalo cuando pregunten por un recurso, un dato o "dónde estaba
    tal cosa". Su contenido es privado: no lo repitas más de lo necesario.
    """
    if not settings.notion_token or not settings.notion_anotaciones_page_id:
        return "[Anotaciones no configurado: falta NOTION_ANOTACIONES_PAGE_ID]"
    try:
        return read_notion_memory(
            _client(), settings.notion_anotaciones_page_id
        ) or "(página 'Anotaciones' vacía)"
    except Exception as e:  # noqa: BLE001
        return f"[Error leyendo Anotaciones: {type(e).__name__}: {e}]"


@mcp.tool()
def notion_escribir_anotacion(texto: str, proyecto: str = "") -> str:
    """Añade una ANOTACIÓN del día a día a la página 'Anotaciones'.

    Úsalo para recursos, enlaces, credenciales o cualquier dato que haya
    que tener a mano — NO para pendientes ni reportes de jornada (esos van
    a 'Memoria' con las otras herramientas).

    La entrada se guarda con día de la semana, fecha, hora y minuto
    exactos, y con el proyecto desde el que se anotó, para poder
    reconstruir después en qué se estaba trabajando en ese momento.

    Args:
        texto: el contenido de la anotación.
        proyecto: de dónde viene. Si se omite, se detecta del directorio
            de trabajo actual (repo git + rama).
    """
    if not settings.notion_token or not settings.notion_anotaciones_page_id:
        return "[Anotaciones no configurado: falta NOTION_ANOTACIONES_PAGE_ID]"
    origen = proyecto.strip() or _contexto_proyecto()
    try:
        n = write_notion_anotacion(
            _client(),
            settings.notion_anotaciones_page_id,
            texto,
            origen=origen,
        )
        if not n:
            return "[No se escribió nada: el texto estaba vacío]"
        return f"✅ Anotación guardada · {_sello_tiempo()} · 📁 {origen}"
    except Exception as e:  # noqa: BLE001
        return f"[Error escribiendo Anotaciones: {type(e).__name__}: {e}]"


if __name__ == "__main__":
    mcp.run()  # transporte stdio por defecto
