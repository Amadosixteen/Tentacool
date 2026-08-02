"""Watcher de cambios: detecta commits nuevos y los registra en Notion.

Diseñado para correr cada X minutos (cron) SIN gastar tokens cuando no
hay novedades:
  · Consulta GitHub en paralelo (Go: tentacool-io fetch-commits).
  · Compara los SHAs con el estado anterior (archivo local) → solo los nuevos.
  · Si no hay novedades → 0 tokens, no escribe nada.
  · Si hay novedades → resume con IA (commit · autor · hora) y lo escribe
    en la página "Watcher" de Notion (NOTION_WATCHER_PAGE_ID).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional

from notion_client import Client

from .config import settings
from .nodes import write_notion_memory

STATE_DIR = os.path.join(os.path.expanduser("~"), ".local", "state", "tentacool")
STATE_FILE = os.path.join(STATE_DIR, "watcher.json")


# ── Estado local ──────────────────────────────────────────────────
def _cargar_estado() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"vistos": {}}


def _guardar_estado(estado: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2)


# ── Fetch (Go en paralelo) ────────────────────────────────────────
def _fetch_json() -> Optional[dict]:
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
        return json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None


def _nuevos_commits(data: dict, estado: dict) -> list:
    """Commits cuyos SHAs no estaban en el estado anterior."""
    vistos = estado.get("vistos", {})
    nuevos = []
    for repo in data.get("repos", []):
        for c in repo.get("commits") or []:
            prev = vistos.get(repo["repo"], [])
            if c["sha"] not in prev:
                nuevos.append({
                    "repo": repo["repo"],
                    "sha": c["sha"],
                    "msg": c["msg"],
                    "autor": c["autor"],
                    "fecha": c["fecha"],
                })
    return nuevos


# ── Resúmenes ─────────────────────────────────────────────────────
def _resumen_plano(nuevos: list) -> str:
    lineas = [f"🔔 Watcher · {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    for c in nuevos:
        lineas.append(
            f"· {c['repo']}: {c['msg']} — {c['autor']} ({c['fecha']}) [{c['sha']}]"
        )
    return "\n".join(lineas)


def _resumen_llm(nuevos: list) -> str:
    from openai import OpenAI

    datos = "\n".join(
        f"- [{c['repo']}] {c['msg']} | autor: {c['autor']} | fecha: {c['fecha']} "
        f"| sha: {c['sha']}"
        for c in nuevos
    )
    client = OpenAI(
        api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
    )
    resp = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un watcher de repositorios. Resume con PRECISIÓN los "
                    "commits nuevos: por cada uno indica repositorio, qué se "
                    "hizo, quién (autor) y cuándo (fecha/hora). Breve, en español."
                ),
            },
            {"role": "user", "content": f"Commits nuevos detectados:\n{datos}"},
        ],
        max_tokens=400,
        temperature=0.2,
    )
    contenido = resp.choices[0].message.content.strip()
    return f"🔔 Watcher · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{contenido}"


# ── Orquestación ──────────────────────────────────────────────────
def run_watcher() -> int:
    data = _fetch_json()
    if data is None:
        print("⚠️  No se pudo consultar GitHub (binario Go o token no disponibles).")
        return 1

    estado = _cargar_estado()
    nuevos = _nuevos_commits(data, estado)

    if not nuevos:
        print("📡 Sin novedades — 0 tokens, no se escribe en Notion.")
        return 0

    resumen = (
        _resumen_llm(nuevos) if settings.watcher_llm_resumen else _resumen_plano(nuevos)
    )

    # Escribir en la página Watcher de Notion
    escrito = "⏭  Sin NOTION_WATCHER_PAGE_ID: no se escribió en Notion"
    if settings.notion_token and settings.notion_watcher_page_id:
        try:
            n = write_notion_memory(
                Client(auth=settings.notion_token),
                settings.notion_watcher_page_id,
                reportes=[resumen],
            )
            escrito = f"✅ Escrito en Notion (+{n} bloque)"
        except Exception as e:  # noqa: BLE001
            escrito = f"❌ Error al escribir en Notion: {type(e).__name__}: {e}"

    # Actualizar estado (últimos 3 SHAs por repo)
    for nc in nuevos:
        repo = estado.setdefault("vistos", {}).setdefault(nc["repo"], [])
        repo.append(nc["sha"])
        estado["vistos"][nc["repo"]] = repo[-3:]
    _guardar_estado(estado)

    print(f"🔔 {len(nuevos)} commit(s) nuevo(s) detectado(s).")
    print(resumen)
    print(escrito)
    return 0
