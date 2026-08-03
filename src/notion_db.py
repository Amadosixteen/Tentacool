"""Bases de datos de Notion: registro filtrable por fechas.

Las páginas de bloques crecen sin límite y Notion no sabe filtrarlas: para
poder acotar "lo de julio" desde la propia interfaz hace falta una base de
datos con una propiedad de tipo fecha. Este módulo crea esas bases, escribe
filas y las consulta por rango.

Nota sobre la API: desde `2025-09-03` una base de datos es un contenedor de
uno o más *data sources*, y son estos los que tienen las propiedades y se
consultan. Por eso casi todo aquí trabaja con `data_source_id`, no con
`database_id` — es un error fácil de cometer y la API devuelve mensajes
poco claros cuando se confunden.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from notion_client import Client

# Título de fila: Notion lo muestra en la tabla, así que va un resumen de
# una línea. El texto íntegro va en el cuerpo de la fila.
_MAX_TITULO = 200

TIPOS = ("Anotación", "Reporte", "Pendiente", "Briefing")

_ESQUEMA: dict[str, Any] = {
    "Contenido": {"title": {}},
    "Fecha": {"date": {}},
    "Origen": {"rich_text": {}},
    "Tipo": {
        "select": {
            "options": [
                {"name": "Anotación", "color": "blue"},
                {"name": "Reporte", "color": "green"},
                {"name": "Pendiente", "color": "orange"},
                {"name": "Briefing", "color": "purple"},
            ]
        }
    },
    # Equivalente de los checkbox de la página: un pendiente sigue siendo
    # algo que se marca como hecho, ahora filtrable y ordenable.
    "Hecho": {"checkbox": {}},
    # El texto completo, como COLUMNA. El cuerpo de la fila también lo
    # lleva, pero eso obliga a abrir cada fila para ver algo: en la tabla
    # solo se veían títulos y la base parecía vacía de información.
    "Descripción": {"rich_text": {}},
}


def asegurar_propiedades(client: Client, data_source_id: str) -> list[str]:
    """Añade a una base ya creada las propiedades del esquema que le falten.

    Evita tener que recrear la base (y perder las filas) cada vez que el
    esquema gana un campo. Devuelve las que ha añadido.
    """
    actual = client.data_sources.retrieve(data_source_id=data_source_id)
    faltan = {k: v for k, v in _ESQUEMA.items() if k not in (actual.get("properties") or {})}
    if faltan:
        client.data_sources.update(data_source_id=data_source_id, properties=faltan)
    return list(faltan)


def crear_base(client: Client, page_id: str, titulo: str) -> tuple[str, str]:
    """Crea una base de datos dentro de la página y devuelve (db_id, ds_id).

    Se crea como hija de la página que ya usas, así que tu contenido actual
    de bloques se queda donde está: la base aparece debajo, no lo sustituye.
    """
    db = client.databases.create(
        parent={"type": "page_id", "page_id": page_id},
        title=[{"type": "text", "text": {"content": titulo}}],
        initial_data_source={"properties": _ESQUEMA},
    )
    fuentes = db.get("data_sources") or []
    if not fuentes:
        raise RuntimeError(
            f"Notion creó la base {db.get('id')} sin data source; "
            "no se puede escribir en ella."
        )
    return db["id"], fuentes[0]["id"]


def data_source_de(client: Client, database_id: str) -> str:
    """Resuelve el data source de una base ya existente."""
    db = client.databases.retrieve(database_id=database_id)
    fuentes = db.get("data_sources") or []
    if not fuentes:
        raise RuntimeError(f"La base {database_id} no tiene data sources.")
    return fuentes[0]["id"]


# El título es lo único que se ve en la tabla, así que tiene que decir algo:
# ni markdown crudo ni encabezados de sección genéricos como "## Pendientes",
# que dejarían la tabla llena de filas indistinguibles.
# `__` es negrita markdown, pero un `_` suelto casi siempre forma parte de un
# nombre (`saas_clinic`): quitarlo destrozaría los identificadores.
_MD_CRUDO = re.compile(r"[*`#]+|__")
_ENCABEZADOS = {
    "pendientes", "pendiente", "reporte ia", "reporte", "reportes",
    "briefing", "briefing diario", "anotacion", "anotaciones", "memoria",
}


def _limpiar(linea: str) -> str:
    return _MD_CRUDO.sub("", linea).strip(" -–—·•\t:")


def _titulo(texto: str) -> str:
    """Primera línea con contenido real, sin markdown — lo que se ve en la tabla."""
    respaldo = ""
    for linea in texto.splitlines():
        limpia = _limpiar(linea)
        if not limpia:
            continue
        respaldo = respaldo or limpia
        if limpia.lower() in _ENCABEZADOS:
            continue
        return limpia[:_MAX_TITULO]
    return (respaldo or "(sin título)")[:_MAX_TITULO]


def crear_fila(
    client: Client,
    data_source_id: str,
    texto: str,
    tipo: str = "Anotación",
    fecha: Optional[datetime] = None,
    origen: str = "",
    hecho: bool = False,
) -> str:
    """Añade una fila. Devuelve su id.

    El título es la primera línea (lo que se ve en la tabla) y el texto
    completo va en el cuerpo de la fila, con el markdown ya convertido a
    formato real de Notion.

    `fecha=None` deja la fila SIN fecha a propósito (contenido antiguo que
    no la tenía). No se rellena con la hora actual: eso la colaría en los
    filtros de hoy y ensuciaría justo lo que la base viene a resolver.
    """
    # Import diferido: nodes importa este módulo para escribir, así que
    # hacerlo arriba crearía un ciclo entre los dos.
    from .nodes import _bloque_parrafo, _rich_text

    texto = (texto or "").strip()
    if not texto:
        raise ValueError("No se puede crear una fila sin texto.")

    propiedades: dict[str, Any] = {
        "Contenido": {"title": [{"type": "text", "text": {"content": _titulo(texto)}}]},
        "Tipo": {"select": {"name": tipo}},
        "Hecho": {"checkbox": hecho},
        # `_rich_text` ya trocea a 2000 caracteres, que es el límite por
        # fragmento que impone la API.
        "Descripción": {"rich_text": _rich_text(texto)},
    }
    if fecha is not None:
        propiedades["Fecha"] = {"date": {"start": fecha.isoformat()}}
    if origen:
        propiedades["Origen"] = {
            "rich_text": [{"type": "text", "text": {"content": origen}}]
        }

    fila = client.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=propiedades,
        children=[_bloque_parrafo(texto)],
    )
    return fila["id"]


def consultar(
    client: Client,
    data_source_id: str,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    tipo: str = "",
    limite: int = 100,
) -> list[dict[str, Any]]:
    """Filas dentro del rango, de la más reciente a la más antigua.

    El filtro lo aplica Notion, no nosotros: no se descarga la base entera
    para tirar la mayoría, que es justo lo que dejaría de escalar cuando
    haya meses de historial.
    """
    condiciones: list[dict[str, Any]] = []
    if desde:
        condiciones.append({"property": "Fecha", "date": {"on_or_after": desde.isoformat()}})
    if hasta:
        condiciones.append({"property": "Fecha", "date": {"on_or_before": hasta.isoformat()}})
    if tipo:
        condiciones.append({"property": "Tipo", "select": {"equals": tipo}})

    consulta: dict[str, Any] = {
        "data_source_id": data_source_id,
        "sorts": [{"property": "Fecha", "direction": "descending"}],
        "page_size": min(limite, 100),
    }
    if condiciones:
        consulta["filter"] = (
            condiciones[0] if len(condiciones) == 1 else {"and": condiciones}
        )

    filas: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    while len(filas) < limite:
        if cursor:
            consulta["start_cursor"] = cursor
        data = client.data_sources.query(**consulta)
        filas.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return filas[:limite]


# ── lectura de las filas devueltas por la API ───────────────────────
def _texto_prop(fila: dict, nombre: str) -> str:
    prop = (fila.get("properties") or {}).get(nombre) or {}
    fragmentos = prop.get("title") or prop.get("rich_text") or []
    return "".join(
        f.get("plain_text") or f.get("text", {}).get("content", "")
        for f in fragmentos
    )


def _fecha_prop(fila: dict) -> Optional[datetime]:
    inicio = ((fila.get("properties") or {}).get("Fecha") or {}).get("date") or {}
    crudo = inicio.get("start")
    if not crudo:
        return None
    try:
        return datetime.fromisoformat(crudo)
    except ValueError:
        return None


def formatear(
    filas: list[dict[str, Any]], client: Optional[Client] = None
) -> str:
    """Convierte las filas en el texto que se muestra por CLI o por MCP.

    El texto íntegro vive en el cuerpo de cada fila, no en sus propiedades
    (el título es solo un resumen de una línea). Pasando `client` se baja
    ese cuerpo — una llamada por fila, así que solo merece la pena cuando
    ya se ha acotado el rango.
    """
    if not filas:
        return "(sin entradas en ese rango)"
    from .nodes import _leer_bloques_recursivo

    lineas = []
    for fila in filas:
        fecha = _fecha_prop(fila)
        sello = f"{fecha:%d/%m/%Y %H:%M}" if fecha else "sin fecha"
        tipo = (
            ((fila.get("properties") or {}).get("Tipo") or {}).get("select") or {}
        ).get("name", "")
        origen = _texto_prop(fila, "Origen")
        cabecera = f"🕐 {sello}"
        if tipo:
            cabecera += f"  ·  {tipo}"
        if origen:
            cabecera += f"  ·  📁 {origen}"
        if ((fila.get("properties") or {}).get("Hecho") or {}).get("checkbox"):
            cabecera += "  ·  ✅"

        cuerpo = ""
        if client is not None:
            try:
                cuerpo = "\n".join(_leer_bloques_recursivo(client, fila["id"]))
            except Exception:  # noqa: BLE001 — sin cuerpo, queda el título
                cuerpo = ""
        lineas.append(f"{cabecera}\n{cuerpo or _texto_prop(fila, 'Contenido')}")
    return "\n\n".join(lineas)
