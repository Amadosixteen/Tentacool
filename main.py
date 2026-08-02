#!/usr/bin/env python3
"""Punto de entrada del orquestador de jornada.

Uso:
    source .venv/bin/activate
    python main.py inicio     # rutina de la mañana (8 AM)
    python main.py fin        # cierre de jornada (apaga contenedores)
"""
from __future__ import annotations

import asyncio
import sys

from notion_client import Client

from src.config import settings
from src.graph import build_fin_graph, build_inicio_graph
from src.nodes import read_notion_memory, write_notion_memory


def _imprimir(titulo: str, contenido: str) -> None:
    print(f"\n─── {titulo} ───")
    print(contenido)


async def _correr(grafo, estado: dict) -> dict:
    return await grafo.ainvoke(estado)


def main() -> int:
    comando = sys.argv[1] if len(sys.argv) > 1 else "inicio"

    if comando == "inicio":
        grafo = build_inicio_graph()
        print("🚀 Orquestador de INICIO de jornada…")
        resultado = asyncio.run(_correr(grafo, {}))
        for r in resultado.get("proyectos_docker", []):
            _imprimir("Docker", r)
        _imprimir("GitHub", resultado.get("github_resumen", "(vacío)"))
        _imprimir("Notion (memoria)", resultado.get("notion_context", "(vacío)"))
        _imprimir("Briefing DeepSeek", resultado.get("briefing", "(vacío)"))
        _imprimir("Escritura en Notion", resultado.get("notion_escrito", ""))
        _imprimir("WhatsApp", resultado.get("whatsapp", ""))
        _imprimir("Gmail", resultado.get("gmail", ""))
        _imprimir("Notion (web)", resultado.get("notion_web", ""))
        _imprimir("VS Code", resultado.get("vscode", ""))
        return 0

    if comando == "fin":
        grafo = build_fin_graph()
        print("🌙 Orquestador de FIN de jornada (apagando contenedores)…")
        resultado = asyncio.run(_correr(grafo, {}))
        for r in resultado.get("proyectos_docker", []):
            _imprimir("Docker", r)
        print("\n✅ Contenedores apagados. La PC queda encendida (AnyDesk OK).")
        return 0

    if comando in ("leer", "nota", "pendiente"):
        return _notion_cli(comando, sys.argv[2:])

    print(
        "Comando desconocido. Usa:\n"
        "  inicio      rutina de la mañana\n"
        "  fin         apagar contenedores\n"
        "  leer        mostrar la página Memoria de Notion\n"
        "  nota \"...\"  escribir un reporte/párrafo en Notion\n"
        "  pendiente \"...\"  añadir un checklist pendiente en Notion"
    )
    return 2


def _notion_cli(comando: str, args: list) -> int:
    """Comandos directos sobre la página 'Memoria' de Notion."""
    if not settings.notion_token or not settings.notion_page_id:
        print("❌ Notion no configurado (token o ID de página vacíos en .env).")
        return 1
    client = Client(auth=settings.notion_token)
    try:
        if comando == "leer":
            print(read_notion_memory(client, settings.notion_page_id) or "(vacía)")
            return 0
        texto = " ".join(args).strip()
        if not texto:
            print(f"❌ Falta el texto. Uso: python main.py {comando} \"...\"")
            return 2
        if comando == "nota":
            n = write_notion_memory(client, settings.notion_page_id, reportes=[texto])
            print(f"✅ Reporte escrito en Notion (+{n} bloque).")
        else:  # pendiente
            n = write_notion_memory(client, settings.notion_page_id, pendientes=[texto])
            print(f"✅ Pendiente añadido a Notion (+{n} bloque).")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
