# Orquestador — reglas para escribir en Notion

## Regla fija: orden y formato de lo nuevo

**Todo lo que se agregue a la página "Memoria" ya queda automáticamente
arriba de lo anterior, con fecha/hora en rojo y negrita delante.** Esto lo
hace `write_notion_memory` (en `src/nodes.py`) por sí sola — tanto si se
llama desde las tools MCP (`notion_escribir_pendiente`,
`notion_escribir_reporte`) como desde el CLI (`python main.py nota/pendiente`).
**No hace falta que la IA agregue la fecha a mano en el texto** — el sistema
ya la antepone en color fuerte automáticamente.

Excepción conocida: bloques especiales (subpáginas, bases de datos, o
cualquier bloque con contenido anidado) NO se reordenan — se dejan
intactos donde están, porque la API de Notion no permite recrearlos igual
si se borran (ver comentario en `_prepend_blocks`, `src/nodes.py`). Si la
página tiene una subpágina fija (p. ej. "COMMITS EN VIVO"), lo nuevo queda
arriba del resto del contenido pero no puede saltar por encima de esa
subpágina — es una limitación real de la API, no un bug a "arreglar" de
nuevo sin cuidado (intentarlo mandó la subpágina a la papelera una vez).

## Regla fija: los pendientes SIEMPRE van como checkbox

Cualquier cosa que quede pendiente (una tarea, algo por hacer, algo por
verificar) se escribe con `notion_escribir_pendiente` / `python main.py
pendiente`, que la crea como **checkbox sin marcar** (`to_do`), nunca como
párrafo de texto plano. Esto aplica siempre, sin importar qué IA o qué
computadora esté escribiendo — es una regla del formato de la página, no
una preferencia de una sesión puntual. `notion_escribir_reporte` / `nota`
es solo para resúmenes de lo YA hecho, no para tareas que faltan; si algo
es "hecho" pero con una parte pendiente, van dos llamadas: una `reporte`
para lo hecho y una `pendiente` (checkbox) por cada cosa que falta.

## Uso de las herramientas MCP

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
