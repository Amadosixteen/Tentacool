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
from src.nodes import (
    _contexto_proyecto,
    _sello_tiempo,
    leer_notion,
    write_notion_anotacion,
    write_notion_memory,
)


def _rango(args: list) -> tuple[list, str, str]:
    """Separa `--desde X` / `--hasta Y` del resto de argumentos.

    Se hace a mano en vez de con argparse porque los comandos toman texto
    libre ("anotacion la clave es --algo") y argparse se lo comería.
    """
    resto, desde, hasta = [], "", ""
    i = 0
    while i < len(args):
        if args[i] in ("--desde", "--hasta") and i + 1 < len(args):
            if args[i] == "--desde":
                desde = args[i + 1]
            else:
                hasta = args[i + 1]
            i += 2
            continue
        resto.append(args[i])
        i += 1
    return resto, desde, hasta


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

    if comando == "anotacion":
        return _anotacion_cli(sys.argv[2:])

    if comando == "anotaciones":
        return _anotaciones_leer_cli(sys.argv[2:])

    if comando == "crear-bases":
        return _crear_bases_cli()

    if comando == "migrar":
        return _migrar_cli("--dry-run" in sys.argv[2:])

    print(
        "Comando desconocido. Usa:\n"
        "  inicio      rutina de la mañana\n"
        "  fin         apagar contenedores\n"
        "  leer        mostrar Memoria (admite --desde / --hasta)\n"
        "  nota \"...\"  escribir un reporte/párrafo en Notion\n"
        "  pendiente \"...\"  añadir un checklist pendiente en Notion\n"
        "  anotacion \"...\"  anotar un recurso del día a día\n"
        "                   (página Anotaciones, con fecha y proyecto)\n"
        "  anotaciones      mostrar Anotaciones (admite --desde / --hasta)\n"
        "\n"
        "Bases de datos (filtro por fechas dentro de Notion):\n"
        "  crear-bases      crear una base en cada página y mostrar sus IDs\n"
        "  migrar           pasar los bloques existentes a filas\n"
        "                   (usa --dry-run para revisar antes)\n"
        "\n"
        "Filtro por fechas (AAAA-MM-DD, DD/MM/AAAA, 'hoy' o 'ayer'):\n"
        "  python main.py leer --desde 2026-07-01 --hasta 2026-07-31\n"
        "  python main.py anotaciones --desde ayer"
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
            args, desde, hasta = _rango(args)
            print(
                leer_notion(
                    client,
                    settings.notion_page_id,
                    settings.notion_memoria_ds_id,
                    desde,
                    hasta,
                )
                or "(vacía)"
            )
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


def _anotacion_cli(args: list) -> int:
    """Anota en la página 'Anotaciones' con sello de tiempo y proyecto.

    El origen se detecta del directorio actual, así que conviene lanzarlo
    desde la carpeta del proyecto en el que estás trabajando.
    """
    if not settings.notion_token or not settings.notion_anotaciones_page_id:
        print(
            "❌ Falta NOTION_TOKEN o NOTION_ANOTACIONES_PAGE_ID en .env.\n"
            "   Recuerda compartir la página con la integración de Notion."
        )
        return 1
    texto = " ".join(args).strip()
    if not texto:
        print('❌ Falta el texto. Uso: python main.py anotacion "..."')
        return 2
    origen = _contexto_proyecto()
    try:
        n = write_notion_anotacion(
            Client(auth=settings.notion_token),
            settings.notion_anotaciones_page_id,
            texto,
            origen=origen,
        )
        print(f"✅ Anotación guardada (+{n} bloques) · {_sello_tiempo()} · 📁 {origen}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error: {type(e).__name__}: {e}")
        return 1


def _anotaciones_leer_cli(args: list) -> int:
    """Muestra 'Anotaciones' por terminal (nunca pasa por el LLM).

    Acepta `--desde` / `--hasta` para acotar el rango.
    """
    if not settings.notion_token or not settings.notion_anotaciones_page_id:
        print("❌ Falta NOTION_TOKEN o NOTION_ANOTACIONES_PAGE_ID en .env.")
        return 1
    _, desde, hasta = _rango(args)
    try:
        client = Client(auth=settings.notion_token)
        texto = leer_notion(
            client,
            settings.notion_anotaciones_page_id,
            settings.notion_anotaciones_ds_id,
            desde,
            hasta,
        )
        print(texto or "(página 'Anotaciones' vacía)")
        return 0
    except ValueError as e:  # fecha mal escrita: es error del usuario, no un fallo
        print(f"❌ {e}")
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error: {type(e).__name__}: {e}")
        return 1


#  Páginas a migrar: (nombre, page_id, ds_id, título de la base, tipo por
#  defecto de las entradas que no se puedan clasificar).
def _paginas() -> list[tuple]:
    return [
        (
            "MEMORIA",
            settings.notion_page_id,
            settings.notion_memoria_ds_id,
            "Registro de jornada",
            "Reporte",
        ),
        (
            "ANOTACIONES",
            settings.notion_anotaciones_page_id,
            settings.notion_anotaciones_ds_id,
            "Registro de recursos",
            "Anotación",
        ),
    ]


def _crear_bases_cli() -> int:
    """Crea una base de datos dentro de cada página y muestra sus IDs.

    No escribe en el .env por su cuenta: se imprimen para pegarlos, porque
    volver a ejecutarlo crearía bases duplicadas y sobrescribir el .env sin
    avisar sería la peor forma de descubrirlo.
    """
    if not settings.notion_token:
        print("❌ Falta NOTION_TOKEN en .env.")
        return 1
    from src.notion_db import crear_base

    client = Client(auth=settings.notion_token)
    creadas = []
    for nombre, page_id, ds_id, titulo, _ in _paginas():
        if not page_id:
            print(f"⏭  {nombre}: sin ID de página en .env, se omite.")
            continue
        if ds_id:
            print(f"⏭  {nombre}: ya tiene base configurada ({ds_id}), se omite.")
            continue
        try:
            db_id, nuevo_ds = crear_base(client, page_id, titulo)
            creadas.append((nombre, db_id, nuevo_ds))
            print(f"✅ {nombre}: base creada.")
        except Exception as e:  # noqa: BLE001
            print(f"❌ {nombre}: {type(e).__name__}: {e}")
            return 1
    if creadas:
        print("\nAñade esto a tu .env:")
        for nombre, _, ds in creadas:
            clave = "NOTION_MEMORIA_DS_ID" if nombre == "MEMORIA" else (
                "NOTION_ANOTACIONES_DS_ID"
            )
            print(f'{clave}="{ds}"')
        print("\nDespués: python main.py migrar --dry-run")
    return 0


def _migrar_cli(dry_run: bool) -> int:
    """Lleva a las bases lo que ya está escrito como bloques en las páginas.

    Las páginas NO se tocan: quedan como archivo histórico, así que la
    migración se puede revisar (y repetir) sin haber perdido nada.
    """
    if not settings.notion_token:
        print("❌ Falta NOTION_TOKEN en .env.")
        return 1
    from src.migracion import migrar_pagina

    client = Client(auth=settings.notion_token)
    if dry_run:
        print("🔍 Simulación: no se escribe nada en Notion.\n")
    for nombre, page_id, ds_id, _, defecto in _paginas():
        if not page_id or not ds_id:
            print(f"⏭  {nombre}: falta page_id o data source, se omite.")
            continue
        r = migrar_pagina(client, page_id, ds_id, defecto, dry_run=dry_run)
        print(f"=== {nombre}: {r['total']} entradas ({r['sin_fecha']} sin fecha) ===")
        for fecha, tipo, muestra in r["detalle"]:
            sello = f"{fecha:%d/%m/%Y %H:%M}" if fecha else "   sin fecha  "
            print(f"  {sello} | {tipo:10} | {muestra}")
        if not dry_run:
            print(f"  → {r['migradas']} migradas · {r['errores'] or 'sin errores'}")
        print()
    if dry_run:
        print("Si la clasificación te cuadra: python main.py migrar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
