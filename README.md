# Tentacool

**El copiloto agéntico de tu jornada.** Un grafo de agentes en paralelo
(LangGraph) que arranca tu día: junta contexto de tus repos y de Notion,
genera un briefing, abre tus herramientas, y mantiene tu memoria viva —
todo orquestado con LangGraph + Golang.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Go](https://img.shields.io/badge/Go-1.22+-00ADD8?logo=go&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multiagente%20paralelo-8A2BE2)
![MCP](https://img.shields.io/badge/MCP-Claude%20Code-D97757)
![License](https://img.shields.io/badge/license-MIT-3DA639)

---

## WORKFLOW

- **Multiagente real, no un script secuencial** — LangGraph orquesta un
  grafo donde varios agentes (GitHub, Notion, navegador...) corren **en
  paralelo** vía fan-out dinámico (`Send()`), y convergen en un supervisor
  que fusiona el estado.
- **Go para el trabajo pesado** — el I/O concurrente (descubrir repos,
  traer commits, levantar contenedores Docker) corre en un CLI propio escrito en
  Go (`tentacool-io`, goroutines, solo stdlib), que le entrega a la IA
  JSON limpio en vez de texto crudo: menos tokens, menos, ruido, latencia. Si no está compilado, cae fallback en Python.
- **MCP nativo** — memoria de Notion u obsidian queda expuesta
  Agentes pueden Gestionar Base de datos CRUDS , sin copiar y pegar
  contexto entre apps.
- **Cualquier LLM, tu propia key** — compatible con la API de OpenAI entre otros 
  (DeepSeek por defecto, si orquestara 10 + Api keys distintos Provedores, Modelos, Provedores, entornos Docker, Multiples cuentas Notion, Gmail entre otros mas).
.
- **Libre** — código abierto, cada integración es un nodo aislado. Sin GitHub/Notion/Docker configurados, esos nodos se
  omiten solos y el resto sigue funcionando. Lo moldeas a tu jornada, no
  al revés.

---

## Compatibilidad

**Corre en Linux nativo.** la
automatización central (disparo por horario, apertura de apps del
escritorio) se apoya en herramientas que solo existen en Linux:
`cron` y convenciones de escritorio Linux cualquier Distribucion.

- **WSL2**: funciona para todo lo manual (`inicio`, `fin`, `leer`, `nota`,
  `pendiente`). El disparo automático por `cron` no se recomienda. 20% potencial.
- **macOS / Windows nativo**: no soportado tal cual hoy. Macos se trabaja aparte otro Proyecto similar TentaCoolMACIntegration, diferente filosofia

---

## INICIAR

```bash
git clone <tu-repo> tentacool && cd tentacool
bash setup.sh               # crea .venv, instala deps, genera .env y .mcp.json
nano .env                   # rellena tus claves (todas opcionales)
./.venv/bin/python main.py inicio    # prueba la rutina de la mañana
```

La única clave con la que vale la pena empezar es `LLM_API_KEY` (o
`DEEPSEEK_API_KEY`). Todo lo demás — Notion, GitHub, Docker, MCP, tu
horario por cron — está documentado y explicado en `.env.example` y
`CLAUDE.md`(si usa claude para construir/moldear encima); la estructura del código (`src/nodes.py`, un nodo por
integración) se explica sola.

---
## Seguridad

`.env` y `.mcp.json` están en `.gitignore` — nunca se suben a git. Tus
tokens y tu página de Notion son tuyos y nunca salen

---

Licencia MIT — ver [`LICENSE`](LICENSE).
