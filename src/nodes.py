"""Nodos del orquestador de jornada (LangGraph).

Cada función es un nodo del grafo: recibe el estado y devuelve un dict
parcial con las claves que actualiza. Nodos clave:

  · node_notion  → página libre "Memoria" (texto plano):
        LEER   : client.blocks.children.list   (recursivo, todo el texto)
        ESCRIBIR: client.blocks.children.append (párrafos + checklists to_do)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta
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
# ─────────────────────────────────────────────────────────────────────
def node_github(state: dict) -> dict:
    if not settings.github_token:
        return {"github_resumen": "[GitHub: falta GITHUB_TOKEN en .env]"}
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    since = (datetime.now() - timedelta(days=1)).isoformat()
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


def _bloque_parrafo(texto: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": texto}}]
        },
    }


def _bloque_todo(texto: str, checked: bool = False) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": texto}}],
            "checked": checked,
        },
    }


def write_notion_memory(
    client: Client,
    page_id: str,
    pendientes: Optional[list[str]] = None,
    reportes: Optional[list[str]] = None,
) -> int:
    """ESCRIBE (append) pendientes y reportes como bloques de texto.

    · pendientes → checklists (to_do, sin marcar)
    · reportes   → párrafos libres
    Devuelve cuántos bloques se añadieron.
    """
    children: list[dict[str, Any]] = []
    if pendientes:
        children.append(_bloque_parrafo("## Pendientes"))
        children.extend(_bloque_todo(p) for p in pendientes if p.strip())
    if reportes:
        children.append(_bloque_parrafo("## Reporte IA"))
        children.extend(_bloque_parrafo(r) for r in reportes if r.strip())
    if not children:
        return 0
    # Notion limita a 100 bloques por petición
    for i in range(0, len(children), 100):
        client.blocks.children.append(
            block_id=page_id, children=children[i : i + 100]
        )
    return len(children)


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
    mensajes = [
        {
            "role": "system",
            "content": (
                "Eres el asistente de inicio de jornada de un desarrollador. "
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
