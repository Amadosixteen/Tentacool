"""Nodos del orquestador de jornada (LangGraph).

Cada función es un nodo del grafo: recibe el estado y devuelve un dict
parcial con las claves que actualiza. Nodos clave:

  · node_notion  → página libre "Memoria" (texto plano):
        LEER    : client.blocks.children.list (recursivo, todo el texto)
        ESCRIBIR: inserta AL INICIO de la página (lo nuevo siempre arriba),
                  con timestamp en negrita/rojo antes de cada bloque nuevo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Optional, TypedDict

import requests
from notion_client import Client

from .config import settings


# ─────────────────────────────────────────────────────────────────────
#  Estado compartido del grafo
# ─────────────────────────────────────────────────────────────────────
class OrquestadorState(TypedDict, total=False):
    proyectos_docker: list[str]
    github_resumen: str
    notion_context: str          # texto leído de la página "Memoria"
    notion_pendientes: list[str] # pendientes a ESCRIBIR en Notion
    notion_reportes: list[str]   # reportes de la IA a ESCRIBIR en Notion
    notion_escrito: str          # resultado de escribir el briefing en Notion
    notion_web: str
    briefing: str
    whatsapp: str
    gmail: str
    vscode: str
    errores: list[str]


# ─────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────
def _registrar_error(state: dict, msg: str) -> dict:
    errores = list(state.get("errores", []))
    errores.append(msg)
    return {"errores": errores}


def _abrir_en_brave(url: str) -> str:
    """Abre una URL en Brave (perfil de sesión iniciada). Sin auth, sin leer."""
    brave = shutil.which(settings.brave_bin)
    if brave:
        subprocess.Popen(
            [brave, f"--profile-directory={settings.brave_profile}", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"Abierto en Brave ({settings.brave_profile}): {url}"
    subprocess.Popen(["xdg-open", url], start_new_session=True)
    return f"Abierto (xdg-open): {url}"


def _docker_via_go(accion: str) -> Optional[list]:
    """Delega en tentacool-io (Go): opera docker compose de varios proyectos
    EN PARALELO. Devuelve la lista de resultados o None si no se puede."""
    binario = shutil.which(settings.tentacool_io_bin)
    if not binario:
        return None
    env = {
        **os.environ,
        "PROJECTS_DOCKER": ",".join(settings.proyectos_docker),
    }
    try:
        r = subprocess.run(
            [binario, "docker", accion],
            capture_output=True, text=True, timeout=300, env=env,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None
    resultados = []
    for item in data:
        if item.get("ok"):
            resultados.append(f"✅ {item['proyecto']}: {accion} OK")
        else:
            resultados.append(
                f"❌ {item['proyecto']}: {item.get('error', 'error')}"
            )
    return resultados or ["(sin proyectos con docker-compose)"]


def _docker_proyecto(accion: str, state: dict) -> dict:
    """Ejecuta `docker compose <accion>` en cada proyecto configurado."""
    if not settings.docker_habilitado:
        return {
            "proyectos_docker": [
                "⏸ Docker deshabilitado en config.py "
                "(docker_habilitado = False). "
                "Actívalo cuando tengas los entornos construidos."
            ]
        }

    via_go = _docker_via_go(accion)
    if via_go is not None:
        return {"proyectos_docker": via_go}

    # ── Fallback: Python secuencial ──
    resultados = []
    for ruta in settings.proyectos_docker:
        if not os.path.isdir(ruta):
            resultados.append(f"⏭ {ruta}: carpeta no existe")
            continue
        compose = next(
            (
                os.path.join(ruta, f)
                for f in ("docker-compose.yml", "docker-compose.yaml",
                          "compose.yml", "compose.yaml")
                if os.path.exists(os.path.join(ruta, f))
            ),
            None,
        )
        if compose is None:
            resultados.append(f"⏭ {ruta}: sin docker-compose")
            continue
        try:
            r = subprocess.run(
                ["docker", "compose", accion],
                cwd=ruta, capture_output=True, text=True, timeout=240,
            )
            if r.returncode == 0:
                resultados.append(f"✅ {os.path.basename(ruta)}: {accion} OK")
            else:
                resultados.append(
                    f"❌ {os.path.basename(ruta)}: {r.stderr.strip()[:160]}"
                )
        except Exception as e:  # noqa: BLE001
            resultados.append(f"❌ {os.path.basename(ruta)}: {type(e).__name__}")
    return {"proyectos_docker": resultados}


# ─────────────────────────────────────────────────────────────────────
#  NODO: Docker (levantar entornos) — antes de VS Code
# ─────────────────────────────────────────────────────────────────────
def node_docker_up(state: dict) -> dict:
    return _docker_proyecto("up -d", state)


# ─────────────────────────────────────────────────────────────────────
#  NODO: GitHub — repos dinámicos + últimos 3 commits desde ayer
#  Usa el CLI Go (tentacool-io, en paralelo) si está disponible; si no,
#  cae al implementación Python secuencial (fallback).
# ─────────────────────────────────────────────────────────────────────
def _github_via_go() -> Optional[str]:
    """Delega en tentacool-io (Go): fetch de commits EN PARALELO y JSON
    limpio para que la IA no procese basura. Devuelve None si no se puede."""
    binario = shutil.which(settings.tentacool_io_bin)
    if not binario:
        return None
    env = {**os.environ, "GITHUB_TOKEN": settings.github_token or ""}
    try:
        r = subprocess.run(
            [binario, "fetch-commits"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None

    lineas = [
        f"Repos descubiertos: {data.get('repos_descubiertos', 0)} "
        "(fetch en paralelo vía Go)"
    ]
    for repo in data.get("repos", []):
        commits = repo.get("commits") or []
        if not commits:
            lineas.append(f"· {repo['repo']}: sin commits desde ayer")
            continue
        detalle = "; ".join(
            f"{c.get('msg', '')[:55]} ({c.get('fecha', '')})" for c in commits
        )
        lineas.append(f"· {repo['repo']}: {len(commits)} commit(s) → {detalle}")
    return "\n".join(lineas)


def node_github(state: dict) -> dict:
    if not settings.github_token:
        return {"github_resumen": "[GitHub: falta GITHUB_TOKEN en .env]"}

    via_go = _github_via_go()
    if via_go is not None:
        return {"github_resumen": via_go}

    # ── Fallback: Python secuencial ──
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    since = (_ahora() - timedelta(days=1)).isoformat()
    try:
        # Descubrimiento dinámico: TODOS los repos accesibles con el token
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=headers,
            params={"per_page": 100, "sort": "updated"},
            timeout=30,
        )
        r.raise_for_status()
        repos = [x for x in r.json() if not x.get("archived")]
        lineas = [f"Repos descubiertos: {len(repos)}"]
        for repo in repos[:15]:
            owner, name = repo["owner"]["login"], repo["name"]
            try:
                cr = requests.get(
                    f"https://api.github.com/repos/{owner}/{name}/commits",
                    headers=headers,
                    params={"since": since, "per_page": 3},
                    timeout=30,
                )
                cr.raise_for_status()
                commits = cr.json()
                if not commits:
                    lineas.append(f"· {name}: sin commits desde ayer")
                    continue
                detalle = "; ".join(
                    f"{c['commit']['message'].splitlines()[0][:55]}"
                    f" ({c['commit']['author']['date'][:10]})"
                    for c in commits
                )
                lineas.append(f"· {name}: {len(commits)} commit(s) → {detalle}")
            except Exception as e:  # noqa: BLE001
                lineas.append(f"· {name}: error al leer commits ({type(e).__name__})")
        return {"github_resumen": "\n".join(lineas)}
    except Exception as e:  # noqa: BLE001
        return {"github_resumen": f"[GitHub: error al listar repos: {e}]"}


# ─────────────────────────────────────────────────────────────────────
#  NODO: Notion — página libre "Memoria" (texto plano)
#  LEER   → client.blocks.children.list   (recursivo: todo el texto)
#  ESCRIBIR → client.blocks.children.append (párrafos y checklists)
# ─────────────────────────────────────────────────────────────────────
def _rich_text_de_bloque(block: dict) -> str:
    """Extrae el texto plano de un bloque de Notion según su tipo."""
    btype = block.get("type")
    obj = block.get(btype, {}) if btype else {}
    partes = []
    for rt in obj.get("rich_text", []):
        partes.append(rt.get("plain_text") or rt.get("text", {}).get("content", ""))
    return "".join(partes)


def _leer_bloques_recursivo(client: Client, block_id: str) -> list[str]:
    """Recorre TODOS los bloques de la página (con paginación y anidados)."""
    lineas: list[str] = []
    cursor: Optional[str] = None
    while True:
        data = client.blocks.children.list(
            block_id=block_id, start_cursor=cursor, page_size=100
        )
        for b in data.get("results", []):
            texto = _rich_text_de_bloque(b)
            if texto:
                lineas.append(texto)
            if b.get("has_children"):
                lineas.extend(_leer_bloques_recursivo(client, b["id"]))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return lineas


def read_notion_memory(client: Client, page_id: str) -> str:
    """LEE todo el texto plano de la página 'Memoria'."""
    lineas = _leer_bloques_recursivo(client, page_id)
    return "\n".join(lineas)


# El LLM devuelve markdown (**negrita**, `código`, ## títulos). La API de
# Notion no lo interpreta: si se manda como texto plano, los asteriscos y
# almohadillas se ven literales en la página. Hay que traducirlos a las
# anotaciones de rich_text.
_MD_TITULO = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_MD_INLINE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`")

# Notion rechaza cualquier fragmento de rich_text de más de 2000 caracteres.
_MAX_RICH_TEXT = 2000


def _rich_text(texto: str) -> list[dict[str, Any]]:
    """Traduce el markdown inline del LLM a fragmentos rich_text de Notion.

    · `**x**` / `__x__` → negrita   · `` `x` `` → código
    · `## Título`       → la línea entera en negrita
    """
    texto = _MD_TITULO.sub(r"**\1**", texto)

    partes: list[tuple[str, dict[str, bool]]] = []
    pos = 0
    for m in _MD_INLINE.finditer(texto):
        if m.start() > pos:
            partes.append((texto[pos:m.start()], {}))
        negrita, negrita_alt, codigo = m.group(1), m.group(2), m.group(3)
        if codigo is not None:
            partes.append((codigo, {"code": True}))
        else:
            partes.append((negrita or negrita_alt, {"bold": True}))
        pos = m.end()
    if pos < len(texto):
        partes.append((texto[pos:], {}))

    fragmentos: list[dict[str, Any]] = []
    for contenido, anotaciones in partes:
        if not contenido:
            continue
        for i in range(0, len(contenido), _MAX_RICH_TEXT):
            frag: dict[str, Any] = {
                "type": "text",
                "text": {"content": contenido[i : i + _MAX_RICH_TEXT]},
            }
            if anotaciones:
                frag["annotations"] = dict(anotaciones)
            fragmentos.append(frag)
    return fragmentos


def _bloque_parrafo(texto: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(texto)},
    }


def _bloque_todo(texto: str, checked: bool = False) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": _rich_text(texto),
            "checked": checked,
        },
    }


def _ahora() -> datetime:
    """Hora actual en la zona configurada (`TENTACOOL_TZ`, Lima por defecto).

    No se usa `datetime.now()` a secas porque bajo cron la TZ del sistema
    puede no heredarse y las fechas del reporte saldrían corridas.
    """
    try:
        return datetime.now(ZoneInfo(settings.timezone))
    except Exception:  # noqa: BLE001 — zona inválida: mejor hora local que fallar
        return datetime.now()


# `%A` depende del locale del sistema, que bajo cron puede ser C/POSIX y
# devolver los días en inglés. Se fija a mano para que siempre salga igual.
_DIAS = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
)


def _sello_tiempo(dt: Optional[datetime] = None) -> str:
    """Fecha completa con día de la semana, hora y minuto exactos."""
    dt = dt or _ahora()
    return f"{_DIAS[dt.weekday()]} {dt:%d/%m/%Y %H:%M}"


def _contexto_proyecto(ruta: Optional[str] = None) -> str:
    """De dónde sale la anotación: proyecto (repo git o carpeta) y rama.

    Sirve para reconstruir después en qué se estaba trabajando en ese
    momento. Si no hay git, se usa el nombre de la carpeta a secas.
    """
    ruta = ruta or os.getcwd()
    raiz = _git(ruta, "rev-parse", "--show-toplevel") or ruta
    nombre = os.path.basename(os.path.normpath(raiz))
    rama = _git(ruta, "rev-parse", "--abbrev-ref", "HEAD")
    return f"{nombre} ({rama})" if rama else nombre


def _git(ruta: str, *args: str) -> str:
    """Ejecuta git en `ruta` y devuelve su salida, o "" ante cualquier fallo
    (carpeta sin repo, git no instalado, permisos…). Nunca lanza."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=ruta,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _bloque_fecha(
    dt: Optional[datetime] = None, origen: Optional[str] = None
) -> dict[str, Any]:
    """Timestamp de cuándo se agregó el bloque, en color fuerte para que
    resalte de inmediato al abrir la página. Si se pasa `origen`, se añade
    de dónde vino la anotación (proyecto y rama)."""
    fragmentos: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": {"content": f"🕐 {_sello_tiempo(dt)}"},
            "annotations": {"bold": True, "color": "red"},
        }
    ]
    if origen:
        fragmentos.append(
            {
                "type": "text",
                "text": {"content": f"  ·  📁 {origen}"},
                "annotations": {"bold": True, "color": "blue"},
            }
        )
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": fragmentos},
    }


# Tipos de bloque que esta herramienta sabe recrear de forma segura (son
# los únicos que ella misma genera). Cualquier otro tipo —subpáginas,
# bases de datos, bloques con hijos anidados— NUNCA se borra ni se mueve:
# reordenar bloques compuestos requiere borrar+recrear, y para una
# child_page eso significa mandarla a la papelera sin forma de recrearla
# igual (ver incidente: intentarlo trashea la subpágina).
_TIPOS_REORDENABLES = {"paragraph", "to_do"}

# Claves realmente aceptadas por la API al crear cada tipo de bloque.
# `blocks.children.list` devuelve campos de solo-lectura extra (p.ej.
# "icon": null en paragraph) que la API de escritura rechaza tal cual.
_CAMPOS_ESCRIBIBLES = {
    "paragraph": ("rich_text", "color"),
    "to_do": ("rich_text", "checked", "color"),
}


def _es_reordenable(b: dict[str, Any]) -> bool:
    return b.get("type") in _TIPOS_REORDENABLES and not b.get("has_children")


def _recrear_bloque(b: dict[str, Any]) -> dict[str, Any]:
    btype = b["type"]
    obj = b[btype]
    limpio = {k: obj[k] for k in _CAMPOS_ESCRIBIBLES[btype] if k in obj}
    return {"object": "block", "type": btype, btype: limpio}


def _prepend_blocks(client: Client, page_id: str, nuevos: list[dict[str, Any]]) -> int:
    """Inserta `nuevos` bloques AL INICIO de los bloques reordenables de la
    página (lo más nuevo arriba). Bloques especiales (subpáginas, bases de
    datos, cualquier cosa con hijos) se dejan intactos donde están — la API
    de Notion no permite "insertar antes del primero" sin borrar y recrear,
    y esos tipos no se pueden recrear igual, así que no se tocan.
    """
    existentes: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        data = client.blocks.children.list(
            block_id=page_id, start_cursor=cursor, page_size=100
        )
        existentes.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    movibles = [b for b in existentes if _es_reordenable(b)]
    if not movibles:
        client.blocks.children.append(block_id=page_id, children=nuevos)
        return len(nuevos)

    # Respaldo local antes de borrar nada — por si el re-append falla a
    # mitad de camino, el contenido original no se pierde.
    backup_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".notion_backups"
    )
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"memoria_{_ahora():%Y%m%d_%H%M%S}.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(movibles, f, ensure_ascii=False, indent=2)

    recreados = [_recrear_bloque(b) for b in movibles]

    for b in movibles:
        client.blocks.delete(block_id=b["id"])

    payload = nuevos + recreados
    total = 0
    for i in range(0, len(payload), 100):
        lote = payload[i : i + 100]
        client.blocks.children.append(block_id=page_id, children=lote)
        total += len(lote)
    return total


def write_notion_memory(
    client: Client,
    page_id: str,
    pendientes: Optional[list[str]] = None,
    reportes: Optional[list[str]] = None,
) -> int:
    """ESCRIBE pendientes y reportes AL INICIO de la página (lo nuevo arriba),
    precedidos por un timestamp en color fuerte (rojo, negrita).

    · pendientes → checklists (to_do, sin marcar)
    · reportes   → párrafos libres
    Devuelve cuántos bloques se añadieron.
    """
    nuevos: list[dict[str, Any]] = []
    if pendientes:
        nuevos.append(_bloque_fecha())
        nuevos.append(_bloque_parrafo("## Pendientes"))
        nuevos.extend(_bloque_todo(p) for p in pendientes if p.strip())
    if reportes:
        nuevos.append(_bloque_fecha())
        nuevos.append(_bloque_parrafo("## Reporte IA"))
        nuevos.extend(_bloque_parrafo(r) for r in reportes if r.strip())
    if not nuevos:
        return 0
    return _prepend_blocks(client, page_id, nuevos)


def write_notion_anotacion(
    client: Client,
    page_id: str,
    texto: str,
    origen: Optional[str] = None,
    dt: Optional[datetime] = None,
) -> int:
    """Añade una ANOTACIÓN al inicio de la página 'Anotaciones'.

    Cada entrada lleva su cabecera con día de la semana, fecha, hora y
    minuto exactos, más el proyecto desde el que se anotó — así después se
    puede reconstruir en qué se estaba trabajando en ese momento.

    OJO: esta página es solo de ESCRITURA para el orquestador. Su contenido
    no se lee en `node_notion` ni entra en el prompt de `node_resumen`,
    porque aquí se guardan credenciales y recursos privados que no deben
    salir hacia la API del LLM.
    """
    texto = (texto or "").strip()
    if not texto:
        return 0
    nuevos = [
        _bloque_fecha(dt, origen or _contexto_proyecto()),
        _bloque_parrafo(texto),
    ]
    return _prepend_blocks(client, page_id, nuevos)


def node_notion(state: dict) -> dict:
    """Lee el contexto de la página 'Memoria' y, si hay pendientes/reportes
    en el estado, los ESCRIBE (append) en la misma página."""
    if not settings.notion_token or not settings.notion_page_id:
        return {"notion_context": "[Notion: falta NOTION_TOKEN o ID de página]"}
    client = Client(auth=settings.notion_token)
    # 1) LEER todo el texto de la página
    try:
        contexto = read_notion_memory(client, settings.notion_page_id)
    except Exception as e:  # noqa: BLE001
        return {
            "notion_context": f"[Notion: error al leer: {type(e).__name__}: {e}]"
        }
    # 2) ESCRIBIR pendientes / reportes si el estado los trae
    pendientes = state.get("notion_pendientes") or []
    reportes = state.get("notion_reportes") or []
    if pendientes or reportes:
        try:
            n = write_notion_memory(
                client, settings.notion_page_id, pendientes, reportes
            )
            contexto += f"\n\n[+{n} bloques escritos en la página]"
        except Exception as e:  # noqa: BLE001
            contexto += f"\n\n[Notion: error al escribir: {type(e).__name__}: {e}]"
    return {"notion_context": contexto or "(página 'Memoria' vacía)"}


# ─────────────────────────────────────────────────────────────────────
#  NODO: WhatsApp y Gmail — solo abrir en Brave (sin lectura)
# ─────────────────────────────────────────────────────────────────────
def node_whatsapp(state: dict) -> dict:
    if not settings.navegador_habilitado:
        return {"whatsapp": "⏭ Navegador deshabilitado (BROWSER_ENABLED=false)"}
    return {"whatsapp": _abrir_en_brave(settings.whatsapp_url)}


def node_gmail(state: dict) -> dict:
    if not settings.navegador_habilitado:
        return {"gmail": "⏭ Navegador deshabilitado (BROWSER_ENABLED=false)"}
    return {"gmail": _abrir_en_brave(settings.gmail_url)}


def node_notion_web(state: dict) -> dict:
    """Abre la página 'Memoria' de Notion en Brave (URL canónica verificada)."""
    if not settings.navegador_habilitado:
        return {"notion_web": "⏭ Navegador deshabilitado (BROWSER_ENABLED=false)"}
    url = (
        settings.notion_page_url
        or f"https://www.notion.so/{settings.notion_page_id}"
    )
    return {"notion_web": _abrir_en_brave(url)}


# ─────────────────────────────────────────────────────────────────────
#  NODO: Resumen — briefing de la mañana con DeepSeek
# ─────────────────────────────────────────────────────────────────────
def node_resumen(state: dict) -> dict:
    if not settings.deepseek_api_key:
        return {"briefing": "Sin DEEPSEEK_API_KEY en .env"}
    contexto = "\n\n".join(
        p for p in (
            "### Estado de repos (GitHub)",
            state.get("github_resumen", ""),
            "### Memoria de Notion",
            state.get("notion_context", ""),
        ) if p
    )
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    # La fecha va explícita en el prompt: sin ella el modelo la deduce del
    # contexto de la memoria (fechas de días anteriores) y la escribe mal.
    ahora = _ahora()
    mensajes = [
        {
            "role": "system",
            "content": (
                "Eres el asistente de inicio de jornada de un desarrollador. "
                f"HOY es {ahora:%d/%m/%Y} y son las {ahora:%H:%M} "
                f"(zona horaria {settings.timezone}). Si mencionas la fecha, "
                "usa EXACTAMENTE esa; nunca la deduzcas del contexto, que "
                "contiene entradas de días anteriores. "
                "Genera un briefing breve, claro y en español con el estado de "
                "los repos y el contexto de la memoria diaria. Destaca qué hay "
                "pendiente y posibles siguientes pasos. Máximo 12 líneas."
            ),
        },
        {"role": "user", "content": contexto or "Sin contexto disponible."},
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=mensajes,
            max_tokens=700,
            temperature=0.4,
        )
        briefing = resp.choices[0].message.content.strip()
    except Exception as e:  # noqa: BLE001
        return {"briefing": f"[DeepSeek: error: {type(e).__name__}: {e}]"}

    # Escribir el briefing en la página 'Memoria' de Notion para que se vea
    # y quede como parte de la memoria diaria.
    escrito = "⏭ Notion no configurado"
    if settings.notion_token and settings.notion_page_id:
        try:
            n = write_notion_memory(
                Client(auth=settings.notion_token),
                settings.notion_page_id,
                reportes=[briefing],
            )
            escrito = f"✅ Briefing escrito en Notion (+{n} bloque(s))"
        except Exception as e:  # noqa: BLE001
            escrito = f"❌ No se pudo escribir en Notion: {type(e).__name__}: {e}"
    return {"briefing": briefing, "notion_escrito": escrito}


# ─────────────────────────────────────────────────────────────────────
#  NODO: VS Code — abre el proyecto asignado
# ─────────────────────────────────────────────────────────────────────
def node_vscode(state: dict) -> dict:
    if not settings.vscode_habilitado:
        return {"vscode": "⏭ VS Code deshabilitado (VSCODE_ENABLED=false)"}
    ruta = settings.proyecto_vscode
    if not os.path.isdir(ruta):
        return {"vscode": f"⏭ {ruta} no existe (ajusta config.py)"}
    code = shutil.which("code")
    if not code:
        return {"vscode": "⏭ 'code' no está en el PATH"}
    subprocess.Popen([code, ruta], start_new_session=True)
    return {"vscode": f"✅ VS Code abierto en {ruta}"}


# ─────────────────────────────────────────────────────────────────────
#  NODO: Fin de jornada — apagar contenedores (nunca apagar/suspender PC)
# ─────────────────────────────────────────────────────────────────────
def node_docker_down(state: dict) -> dict:
    return _docker_proyecto("down", state)
