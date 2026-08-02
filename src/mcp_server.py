"""Servidor MCP: expone la página 'Memoria' de Notion como herramientas.

Así, Claude Code (u otro agente/IDE con soporte MCP) puede leer y escribir
en tu Notion de forma nativa, reutilizando el token y la página ya
configurados en .env y src/config.py.

Conexión (stdio):
    claude mcp add notion-memoria -- \
        /home/desarrollo/tentacool/.venv/bin/python \
        /home/desarrollo/tentacool/src/mcp_server.py

O vía .mcp.json en la raíz del proyecto (ya incluido).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from notion_client import Client

from .config import settings
from .nodes import read_notion_memory, write_notion_memory

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


if __name__ == "__main__":
    mcp.run()  # transporte stdio por defecto
