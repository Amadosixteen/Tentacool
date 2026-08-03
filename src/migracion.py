"""Migración de las páginas de bloques a las bases de datos filtrables.

Lee las entradas que ya hay en una página (cada una identificada por su
cabecera con sello de tiempo) y crea una fila por entrada, conservando
fecha y origen. Lo que no tiene sello de tiempo también se migra, pero sin
fecha: no se inventa una, porque falsearía cualquier filtro posterior.

La página original NO se toca: queda como archivo histórico. Así la
migración se puede repetir o revisar sin haber perdido nada.
"""
from __future__ import annotations

from typing import Optional

from notion_client import Client

from .nodes import Entrada, _leer_bloques_recursivo, parsear_entradas
from .notion_db import crear_fila


def _clasificar(entrada: Entrada, por_defecto: str) -> tuple[str, bool]:
    """Deduce el Tipo de la entrada por sus encabezados, y si está hecha.

    Las páginas mezclan reportes, pendientes y briefings bajo cabeceras
    como "## Pendientes" o "## Reporte IA"; se usan como pista para no
    volcarlo todo en un mismo tipo genérico.
    """
    texto = entrada.texto().lower()
    if "pendiente" in texto[:200]:
        return "Pendiente", texto.lstrip().startswith("[x]")
    if "briefing" in texto[:200]:
        return "Briefing", False
    if "reporte" in texto[:200]:
        return "Reporte", False
    return por_defecto, False


def migrar_pagina(
    client: Client,
    page_id: str,
    data_source_id: str,
    tipo_por_defecto: str = "Anotación",
    dry_run: bool = False,
) -> dict:
    """Migra una página a su base de datos.

    Con `dry_run` no escribe nada: solo informa de qué haría, que es la
    forma sensata de comprobar la clasificación antes de tocar Notion.
    """
    entradas = parsear_entradas(_leer_bloques_recursivo(client, page_id))
    resumen = {"total": len(entradas), "migradas": 0, "sin_fecha": 0, "errores": []}
    detalle = []

    for entrada in entradas:
        texto = entrada.texto()
        # La cabecera es metadato: fecha y origen ya viajan en las
        # propiedades de la fila, repetirla en el cuerpo sería ruido.
        cuerpo = "\n".join(entrada.lineas).strip() or texto.strip()
        if not cuerpo:
            continue
        tipo, hecho = _clasificar(entrada, tipo_por_defecto)
        if entrada.fecha is None:
            resumen["sin_fecha"] += 1
        detalle.append((entrada.fecha, tipo, cuerpo[:60].replace("\n", " ")))
        if dry_run:
            continue
        try:
            crear_fila(
                client,
                data_source_id,
                cuerpo,
                tipo=tipo,
                fecha=entrada.fecha,
                origen=entrada.origen,
                hecho=hecho,
            )
            resumen["migradas"] += 1
        except Exception as e:  # noqa: BLE001
            resumen["errores"].append(f"{type(e).__name__}: {e}")

    resumen["detalle"] = detalle
    return resumen
