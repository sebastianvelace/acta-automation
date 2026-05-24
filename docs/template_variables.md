# Plantilla `templates/acta_template.docx` (docxtpl / Jinja2)

Los datos provienen del JSON del acta (mismos nombres de clave). Aplica los cambios **a mano** en Word según las condiciones indicadas.

## Variables escalares (raíz del contexto)

| Placeholder | Origen |
|-------------|--------|
| `{{ titulo }}` | Título descriptivo del acta |
| `{{ fecha }}` | Fecha en prosa |
| `{{ hora_inicio }}` | Hora inicio |
| `{{ hora_fin }}` | Hora fin; si falta en notas, el pipeline infiere **hora_inicio + 1 h** |
| `{{ hora_final }}` | Duplicado de `hora_fin` si la plantilla lo usa (el generador lo rellena) |
| `{{ lugar }}` | Lugar; `Google Meet` si reunión virtual detectada; si no, `No especificada` |
| `{{ cliente }}` | Nombre completo de la reunión / cliente |
| `{{ objetivo }}` | Objetivo (uno o más enunciados) |
| `{{ cierre }}` | Resumen de cierre: acuerdos y conclusiones finales |

## Listas (bucles típicos)

- **`invitados`**: equipos Gorila del bloque Invitado (Administración → puesto «Organizador»; demás → «Gorila Hosting») más correos enriquecidos. Campos: `correo`, `nombre`, `puesto`, `asistencia` (`Confirmado`). Fuentes: alias de equipos, [`data/gorila_staff.yaml`](../data/gorila_staff.yaml), [`data/client_contacts.yaml`](../data/client_contacts.yaml), tags de Próximos pasos. Sin LLM.
- **`asuntos_tratados`**: `titulo`, `descripcion` (solo vía Groq; deben salir de **Detalles**, no del Resumen).
- **`compromisos_gorila`** / **`compromisos_cliente`**: `tarea`, `responsable`, `fecha_entrega`. **Una fila por ítem de Próximos pasos** (post-proceso determinístico; prioridad sobre JSON del LLM).

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
- Tras el post-proceso, `invitados` se rellena por correos del bloque Invitado del documento.
- El roster de integrantes Gorila (`data/gorila_staff.yaml`) define quién es personal interno para **compromisos**; editar ese YAML para altas/bajas.
