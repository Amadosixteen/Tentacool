# Orquestador — reglas para escribir en Notion

Cuando el usuario te pida anotar en su Notion, por ejemplo
"escribe todo lo que hemos hecho y lo pendiente en mi Notion" (típico ~16:00),
usa las herramientas MCP `notion_*` que ya están disponibles:

- `notion_leer_memoria()` → lee el contexto actual de la página "Memoria"
  (úsalo primero para no duplicar ni pisar lo ya escrito).
- `notion_escribir_pendiente(texto)` → para CADA cosa que quedó pendiente
  (la añade como checklist).
- `notion_escribir_reporte(texto)` → para el resumen de lo hecho en la jornada
  (la añade como párrafo).

## Flujo recomendado al cerrar la jornada
1. `notion_leer_memoria()` para ver el contexto del día.
2. `notion_escribir_reporte(...)` con un resumen de lo avanzado hoy.
3. `notion_escribir_pendiente(...)` una vez por cada pendiente que quede.

## Alternativa por terminal (si el MCP no está conectado)
```bash
python main.py nota "resumen de lo hecho..."
python main.py pendiente "pendiente..."
python main.py leer
```
