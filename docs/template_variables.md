# Plantilla `templates/acta_template.docx` (docxtpl / Jinja2)

Los datos provienen del JSON del acta (mismos nombres de clave). Aplica los cambios **a mano** en Word según las condiciones indicadas.

## Variables escalares (raíz del contexto)

| Placeholder | Origen |
|-------------|--------|
| `{{ titulo }}` | Título descriptivo del acta |
| `{{ fecha }}` | Fecha en prosa |
| `{{ hora_inicio }}` | Hora inicio |
| `{{ hora_fin }}` | Hora fin (puede ser `No especificada`) |
| `{{ hora_final }}` | Duplicado de `hora_fin` si la plantilla lo usa (el generador lo rellena) |
| `{{ lugar }}` | Lugar (suele ser vacío o `No especificada` en notas Gemini) |
| `{{ cliente }}` | Nombre completo de la reunión / cliente |
| `{{ objetivo }}` | Objetivo (uno o más enunciados) |
| `{{ cierre }}` | Resumen de cierre: acuerdos y conclusiones finales |

## Listas (bucles típicos)

- **`asistentes`**: cada item `nombre`, `puesto`. Tras el post-proceso por alias, equipos tipo "Marketing Gorila Hosting" quedan canónicos.
- **`asuntos_tratados`**: `titulo`, `descripcion`.
- **`compromisos_gorila`**: `tarea`, `responsable`, `fecha_entrega`.
- **`compromisos_cliente`**: `tarea`, `responsable`, `fecha_entrega`.

## Condicionales recomendados (editar en la .docx)

### Fila o bloque de **hora_fin**

Ocultar cuando no hay hora útil:

```jinja2
{% if hora_fin and hora_fin != "No especificada" %}
… fila o párrafo con {{ hora_fin }} …
{% endif %}
```

### **lugar**

```jinja2
{% if lugar and lugar != "No especificada" %}
… {{ lugar }} …
{% endif %}
```

### Sección completa **compromisos_cliente** (cabecera + tabla)

Si la lista está vacía, no mostrar nada de esa sección:

```jinja2
{% if compromisos_cliente %}
## Compromisos cliente
{% for row in compromisos_cliente %}
…
{% endfor %}
{% endif %}
```

En tablas Word con `docxtpl`, envuelve la fila de caberca extra y las filas `{% tr for … %}` dentro del mismo `{% if compromisos_cliente %}…{% endif %}`.

## Notas

- `No especificada` / `No especificado` son valores legales del modelo; usa comparación exacta en Jinja como arriba.
- Tras normalizar asistentes, `puesto` de alias de equipo deja de ser ambiguo ("Gorila Hosting", "Equipo", etc.).
