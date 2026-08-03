# Orquestador — reglas para escribir en Notion

## Dos páginas, dos propósitos — no mezclarlas

| Página | Para qué | Herramientas |
|---|---|---|
| **Memoria** | Jornada: reportes de lo hecho y pendientes | `notion_leer_memoria`, `notion_escribir_reporte`, `notion_escribir_pendiente` |
| **Anotaciones** | Día a día: recursos, enlaces, credenciales, datos a mano | `notion_leer_anotaciones`, `notion_escribir_anotacion` |

Si es una tarea o un resumen de jornada → **Memoria**. Si es un dato que
hay que tener a mano (una URL, un usuario, una clave, un comando) →
**Anotaciones**.

**Anotaciones es privada**: su contenido nunca entra en el briefing de la
mañana ni se manda al LLM del orquestador. Solo se lee bajo petición
explícita. Al leerla, no repitas credenciales más allá de lo que se te
pregunte.

## Filtrar por fechas

Las dos páginas guardan su contenido en **bases de datos de Notion** con
una propiedad `Fecha`, así que se puede acotar cualquier periodo — desde
Notion (filtro nativo `Desde → Hasta`) o desde las tools:

- `notion_leer_memoria(desde, hasta)`
- `notion_leer_anotaciones(desde, hasta)`

Formatos aceptados: `AAAA-MM-DD`, `DD/MM/AAAA`, `hoy`, `ayer`. Ambos son
opcionales e inclusive (`hasta` cubre el día entero). Cuando el usuario
pregunte por un periodo ("lo del mes pasado", "qué hice la semana del 10"),
**usa el rango** en vez de leerlo todo y filtrar tú: el filtro lo aplica
Notion y evita traerse meses de historial.

Columnas de cada fila:

| Columna | Qué lleva |
|---|---|
| `Contenido` | título: primera línea con sentido, sin markdown |
| `Descripción` | el texto completo, visible en la tabla sin abrir la fila |
| `Fecha` | día y hora exactos (lo que hace posible el filtro) |
| `Tipo` | Anotación · Reporte · Pendiente · Briefing |
| `Origen` | proyecto y rama desde donde se escribió |
| `Hecho` | checkbox de los pendientes |

**Todo lo nuevo va a la base, no a los bloques de la hoja.** El texto suelto
que hay en las páginas es el archivo anterior a la migración: no lo
actualices ni escribas ahí a mano desde las tools.

## Regla fija: orden y formato de lo nuevo

**La fecha y la hora las pone el sistema, nunca la IA a mano.** Cada
escritura guarda su sello de tiempo por su cuenta — como propiedad `Fecha`
de la fila (modo base de datos) o como cabecera en rojo sobre el bloque
(modo página). Vale igual desde las tools MCP que desde el CLI. Si escribes
la fecha dentro del texto, saldrá duplicada.

Lo más reciente queda siempre primero: la base se ordena por `Fecha`
descendente, y en modo página lo nuevo se inserta arriba.

Excepción del modo página: bloques especiales (subpáginas, bases de datos,
o cualquier bloque con contenido anidado) NO se reordenan — se dejan
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

Y para la bitácora de recursos:

- `notion_leer_anotaciones()` → lee la página "Anotaciones" (recursos,
  enlaces, credenciales). Úsalo cuando pregunten "dónde estaba tal cosa".
- `notion_escribir_anotacion(texto, proyecto="")` → guarda un recurso del
  día a día. Cada entrada queda con **día de la semana, fecha, hora y
  minuto exactos** más el **proyecto de origen**, para reconstruir después
  en qué se estaba trabajando. Si omites `proyecto`, se detecta solo del
  directorio de trabajo (repo git + rama) — normalmente eso es lo correcto;
  pásalo a mano solo si el recurso viene de otro sitio.

## Flujo recomendado al cerrar la jornada
1. `notion_leer_memoria()` para ver el contexto del día.
2. `notion_escribir_reporte(...)` con un resumen de lo avanzado hoy.
3. `notion_escribir_pendiente(...)` una vez por cada pendiente que quede.

## Alternativa por terminal (si el MCP no está conectado)
```bash
python main.py nota "resumen de lo hecho..."
python main.py pendiente "pendiente..."
python main.py leer

python main.py anotacion "credenciales del ERP local: ..."   # → Anotaciones
python main.py anotaciones                                    # leerla

python main.py leer --desde 2026-07-01 --hasta 2026-07-31     # filtrar
python main.py anotaciones --desde ayer
```
El origen del `anotacion` sale del directorio desde el que lo lances, así
que conviene ejecutarlo dentro de la carpeta del proyecto en curso.
