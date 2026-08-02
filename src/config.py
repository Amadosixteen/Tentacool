"""Configuración central del orquestador.

Carga las variables del .env (nunca se imprime su valor) y expone las
rutas y parámetros de los nodos.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Carga el .env de la raíz del proyecto (../.env respecto a este archivo)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

HOME = os.path.expanduser("~")


def _normalize_page_id(raw: str) -> str:
    """Convierte el ID copiado de una URL de Notion a UUID canónico.

    Acepta el formato pegado de la URL (32 hex + posible '?' o fragmentos)
    y lo deja en el formato 8-4-4-4-12 que exige la API de Notion.
    """
    if not raw:
        return ""
    hex_digits = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(hex_digits) == 32:
        return (
            f"{hex_digits[0:8]}-{hex_digits[8:12]}-{hex_digits[12:16]}"
            f"-{hex_digits[16:20]}-{hex_digits[20:32]}"
        )
    return raw.strip().strip('"')


def _env_bool(name: str, default: bool = False) -> bool:
    """Lee una variable de entorno como booleano (1/true/yes/on)."""
    return os.getenv(name, str(default)).strip().lower() in (
        "1", "true", "yes", "on",
    )


def _env_list(name: str, default: list) -> list:
    """Lee una variable de entorno como lista separada por comas."""
    raw = os.getenv(name, "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(default)


@dataclass
class Settings:
    """Parámetros del orquestador — 100% configurables por entorno.

    Todo se lee de variables de entorno / .env con valores por defecto
    sensatos, de modo que cualquier persona pueda usarlo rellenando
    solo sus claves. Compatible hacia atrás con las claves originales.
    """

    # ── LLM (agnóstico de proveedor; DeepSeek por defecto) ──
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY", "")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL", "https://api.deepseek.com"
        )
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat")
    )

    # ── GitHub ──
    github_token: str = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", "")
    )
    github_user: str = field(
        default_factory=lambda: os.getenv("GITHUB_USER", "")
    )

    # ── Notion (página libre "Memoria") ──
    notion_token: str = field(
        default_factory=lambda: os.getenv("NOTION_TOKEN", "")
    )
    notion_page_id: str = field(
        default_factory=lambda: _normalize_page_id(
            os.getenv("NOTION_PAGE_ID") or os.getenv("NOTION_DATABASE_ID", "")
        )
    )
    notion_page_url: str = field(
        default_factory=lambda: os.getenv("NOTION_PAGE_URL", "")
    )

    # ── Navegador (abrir pestañas; Brave por defecto, xdg-open fallback) ──
    brave_bin: str = field(
        default_factory=lambda: os.getenv("BROWSER_CMD", "brave-browser")
    )
    brave_profile: str = field(
        default_factory=lambda: os.getenv("BROWSER_PROFILE", "Default")
    )
    whatsapp_url: str = field(
        default_factory=lambda: os.getenv(
            "WHATSAPP_URL", "https://web.whatsapp.com"
        )
    )
    gmail_url: str = field(
        default_factory=lambda: os.getenv(
            "GMAIL_URL", "https://mail.google.com"
        )
    )

    # ── Proyectos / VS Code ──
    _projects_dir: str = field(
        default_factory=lambda: os.getenv(
            "PROJECTS_DIR", os.path.join(HOME, "Projects")
        )
    )
    proyectos_docker: list = field(
        default_factory=lambda: _env_list("PROJECTS_DOCKER", [])
    )
    proyecto_vscode: str = field(
        default_factory=lambda: os.getenv("VSCODE_PROJECT", "")
    )

    # ── Feature flags (cada integración es opcional) ──
    docker_habilitado: bool = _env_bool("DOCKER_ENABLED", False)
    navegador_habilitado: bool = _env_bool("BROWSER_ENABLED", True)
    vscode_habilitado: bool = _env_bool("VSCODE_ENABLED", True)


settings = Settings()
