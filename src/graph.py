"""Grafos LangGraph del orquestador.

  · build_inicio_graph()  → rutina de la mañana (docker up → recolecta en
                            paralelo → briefing → abre navegador → VS Code)
  · build_fin_graph()     → cierre de jornada (apaga contenedores)
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes import (
    OrquestadorState,
    node_docker_down,
    node_docker_up,
    node_github,
    node_gmail,
    node_notion,
    node_notion_web,
    node_resumen,
    node_vscode,
    node_whatsapp,
)


def _fanout_colectar(state: OrquestadorState):
    """Despacha en paralelo los agentes de recolección (GitHub y Notion)."""
    return [
        Send("github", state),
        Send("notion", state),
    ]


def _fanout_navegador(state: OrquestadorState):
    """Despacha en paralelo los lanzadores de navegador
    (WhatsApp, Gmail y Notion)."""
    return [
        Send("whatsapp", state),
        Send("gmail", state),
        Send("notion_web", state),
    ]


def build_inicio_graph():
    g = StateGraph(OrquestadorState)

    g.add_node("docker_up", node_docker_up)
    g.add_node("github", node_github)
    g.add_node("notion", node_notion)
    g.add_node("resumen", node_resumen)
    g.add_node("whatsapp", node_whatsapp)
    g.add_node("gmail", node_gmail)
    g.add_node("notion_web", node_notion_web)
    g.add_node("vscode", node_vscode)

    g.add_edge(START, "docker_up")
    # Fan-out paralelo: el nodo que devuelve Send se conecta con
    # add_conditional_edges (no con add_edge).
    g.add_conditional_edges("docker_up", _fanout_colectar, ["github", "notion"])
    g.add_edge("github", "resumen")
    g.add_edge("notion", "resumen")
    g.add_conditional_edges(
        "resumen", _fanout_navegador, ["whatsapp", "gmail", "notion_web"]
    )
    g.add_edge("whatsapp", "vscode")
    g.add_edge("gmail", "vscode")
    g.add_edge("notion_web", "vscode")
    g.add_edge("vscode", END)

    return g.compile()


def build_fin_graph():
    g = StateGraph(OrquestadorState)

    g.add_node("docker_down", node_docker_down)

    g.add_edge(START, "docker_down")
    g.add_edge("docker_down", END)

    return g.compile()
