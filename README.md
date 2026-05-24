# Acta automation

Pipeline automatizado: sube un `.docx` exportado por **Gemini** (notas de reunión) → parser + Groq (`llama-3.3-70b`) → post-proceso determinístico → plantilla DOCX/PDF del acta formal.

## Qué hace el sistema

```text
Gemini DOCX  →  parser  →  Groq (JSON)  →  finalize_acta_after_llm  →  apply_metadata_times  →  Word/PDF
                    ↓              ↓                    ↓
              metadata      objetivo,            compromisos 1:1,
              (fecha,       asuntos, cierre       invitados, cliente
               equipos,     (requiere Groq)       (determinístico)
               emails)
```

Orden en [`src/pipeline.py`](src/pipeline.py):

1. **Parse** ([`src/parser.py`](src/parser.py))
2. **Calendar enrich** opcional ([`src/google_workflow.py`](src/google_workflow.py) — `calendar_enrich_metadata`)
3. **LLM** ([`src/llm.py`](src/llm.py) — `structure_meeting` + `post_process_acta`)
4. **Finalize** ([`src/aliases.py`](src/aliases.py) — `finalize_acta_after_llm`: compromisos + invitados; **sobrescribe** lo que el LLM puso en esas secciones si hay Próximos pasos)
5. **Tiempos** ([`src/google_workflow.py`](src/google_workflow.py) — `apply_metadata_times_to_acta`)
6. **Render** ([`src/generator.py`](src/generator.py) — docxtpl + LibreOffice → PDF)

---

## Funcionalidades implementadas (estado actual)

### Parser (`src/parser.py`)

| Capacidad | Detalle |
|-----------|---------|
| Texto y fecha | Primera línea tipo `may 22, 2026` |
| Bloque Invitado | Correos + equipos Gorila (`Marketing Gorila Hosting`, etc.) |
| Próximos pasos | Regex `[Tag] Título: descripción` → lista para routing |
| Detalles | Conteo de bloques (`count_detalles_blocks`) usado en prompt LLM |
| Hora inicio | Cuerpo del doc, o **nombre del archivo** (`16_01` → `4:01 PM`, `09_00` → `9:00 AM`) |
| Hora fin | Rangos en cuerpo (`9:00 AM – 10:00 AM`) si aparecen |
| Reunión virtual | `_detect_virtual_meeting`: enlace Meet/Zoom o adjunto «Grabación» → `is_virtual=true` |
| URL calendario | Parámetro `eid` para Calendar API opcional |
| Personas Gorila en Detalles | `extract_gorila_person_names` (nombres junto a equipos en notas) |

### LLM (`src/llm.py`)

- Modelo: **Groq `llama-3.3-70b-versatile`**, JSON validado con [`ActaSchema`](src/schemas.py).
- Prompt exige **asuntos solo desde Detalles** (no duplicar el Resumen breve).
- Hint de reunión virtual y conteo de bloques Detalles en el mensaje de usuario.
- **`invitados` del LLM se ignoran** en la práctica: el post-proceso los rellena determinísticamente.
- Truncado inteligente si el doc excede ventana de tokens (preserva Próximos pasos + Detalles).
- Requiere **`GROQ_API_KEY`**; sin tokens Groq el acta queda **incompleta** en objetivo, asuntos y cierre.

### Post-proceso — encabezado y cliente (`src/aliases.py`)

- **`compose_cliente_heading`**: combina título + cuenta (ej. «Seguimiento - Real State»).
- **`client_account_responsable`**: nombre de empresa para columna responsable en compromisos cliente.
- **`apply_metadata_times_to_acta`**: fecha en **español** (`may 22, 2026` → `22 de mayo de 2026`).

### Post-proceso — invitados (`src/aliases.py` + `src/gorila_roster.py`)

| Paso | Función | Comportamiento |
|------|---------|----------------|
| 1 | `build_invitados_from_attendee_emails` | Correos del bloque Invitado |
| 2 | `merge_invitados_from_gorila_teams` | Equipos Gorila del calendario/Gemini como filas propias |
| 3 | `merge_invitados_from_proximos_tags` | Personas internas en tags (ej. Omar Escobedo) |
| 4 | `_enrich_invitados_from_proximos_names` | Nombres cliente desde tags → filas fallback por email |

**Formato equipos Gorila** (alias abreviado):

- **Administración Gorila Hosting** → nombre `Administración`, puesto **Organizador**
- Demás equipos → nombre corto (`Marketing`, `Social Media`, …), puesto **Gorila Hosting**
- Orden: Administración primero, luego `_ROLE_ORDER`

**Enriquecimiento por correo** (sin LLM):

1. [`data/gorila_staff.yaml`](data/gorila_staff.yaml) — roster Gorila (Marco Gonzalez, Martina, David @growfik.com, etc.)
2. [`data/client_contacts.yaml`](data/client_contacts.yaml) — contactos cliente conocidos
3. Fallback legible desde local-part del email

**Contactos cliente en YAML hoy:** Universal (Samuel), Ana Maria, Barrera (2), Real State (Camilo).

### Post-proceso — compromisos (`src/aliases.py` + `src/dates.py`)

**Regla 1:1:** cada línea de Próximos pasos = **una fila** en la tabla (sin fusionar con `"; "`).

| Routing | Destino |
|---------|---------|
| `[El grupo]` / `[The group]` / `[Todos]` | `compromisos_gorila` (responsable inferido del calendario) |
| Equipos / personal Gorila / roster / `@growfik.com` | `compromisos_gorila` |
| Persona del cliente | `compromisos_cliente` (responsable = **cuenta**, no la persona) |
| Tag Gorila pero entrega explícita al cliente | `compromisos_cliente` (`_is_client_deliverable_despite_gorila_tag`) |

- **`reclassify_compromisos`**: corrige filas mal clasificadas por el LLM.
- **`fecha_entrega_for_compromiso`**: «mañana a las 2PM», «5 de la tarde del día de mañana», etc. → prosa española.
- **`normalize_gorila_compromiso_responsable_display`**: texto visible **Growfik → Gorila Hosting** en responsables.

### Post-proceso — tiempos (`src/google_workflow.py` + `src/dates.py`)

- Fecha metadata → prosa española (`format_meeting_date_prose`).
- Hora inicio desde metadata si el LLM dejó placeholder.
- **`hora_fin` inferida = `hora_inicio + 1 hora`** cuando no hay fin explícito (ej. 9:00 AM → 10:00 AM).
- Si el parser extrajo rango explícito en notas, **se respeta** ese fin.
- `is_virtual=true` → `lugar = "Google Meet"`.
- Calendar API (opcional): fecha/horas desde evento + `drive_upload_pdf_if_configured`.

### Roster Gorila (`data/gorila_staff.yaml` + `src/gorila_roster.py`)

- Catálogo fijo: nombres canónicos, emails, roles, aliases.
- Marco Gonzalez (`ads@gorila.hosting`, `ads.gorilahosting@gmail.com`) siempre clasificado como Gorila.
- Personal `@growfik.com` (David, Sebastián) en roster; emails Growfik = equipo interno para routing.
- `format_staff_puesto`: añade « Gorila» al cargo en invitados internos.

### Interfaz y API

| Componente | Uso |
|------------|-----|
| **Web UI** ([`web/`](web/)) | Drag-and-drop, descarga PDF/DOCX, enlace Drive |
| **API** ([`api/app.py`](api/app.py)) | `POST /api/process`, `GET /api/health` |
| **Modo carpeta** (`python -m src.main`) | Watch en `input/` → `output/` |

`npm run dev` arranca API con **`--reload`** en `src/` y `api/` + frontend Vite.

### Scripts de evaluación

| Script | Propósito |
|--------|-----------|
| [`scripts/batch_grade.py`](scripts/batch_grade.py) | Calificación **determinística** (sin Groq) sobre DOCX reales; encabezado / invitados / compromisos |
| [`scripts/eval_acta.py`](scripts/eval_acta.py) | Evaluación con pipeline completo (Groq) sobre fixtures |
| [`scripts/judge_acta.py`](scripts/judge_acta.py) | Juez LLM de calidad del acta |
| [`scripts/alias_metrics_report.py`](scripts/alias_metrics_report.py) | Métricas de aliases post-proceso |

**Clientes en golden batch** (`EXPECTED_COUNTS`):

| Cliente | Gorila | Cliente |
|---------|--------|---------|
| Ana Maria | 1 | 4 |
| Barrera Estrada | 2 | 3 |
| Real State Seguimiento | 2 | 5 |
| Sambal | 3 | 2 |
| Marlon | 2 | 2 |
| Universal Campañas | 8 | 0 |
| Universal Dashboard | 8 | 0 |

---

## Qué queda incompleto o pendiente

Estas partes **no están implementadas** o requieren intervención manual / tokens Groq:

| Área | Estado |
|------|--------|
| **Objetivo, asuntos, cierre** | Solo vía Groq; sin fallback determinístico |
| **Deduplicar asuntos Resumen→Detalles** | Regla en prompt; sin post-proceso que elimine duplicados |
| **Growfik solo en actas Universal** | Hoy Growfik se normaliza a Gorila Hosting en todo el acta; política Universal-only no implementada |
| **`client_account_responsable`** | En títulos sin guión (ej. «Seguimiento Barrera Estrada») puede devolver el título completo en vez del nombre corto de cuenta |
| **Detección virtual ampliada** | Solo Meet/Zoom en texto o «Grabación»; muchas reuniones quedan `lugar = No especificada` |
| **Dedupe invitados por persona** | Mismo integrante puede aparecer dos veces (email roster + tag Próximos) |
| **Contactos cliente** | YAML con 5 entradas; emails como `jaimegchef@gmail.com` siguen con nombre inferido del local-part |
| **Consolidación compromisos** | **Eliminada** a propósito (regla 1:1); actas con muchos próximos pasos son más largas |

---

## Requisitos

- Python 3.12+
- Node 20+
- LibreOffice (`libreoffice --headless` en PATH)
- **`GROQ_API_KEY`** en `.env`

## Variables de entorno

| Variable | Obligatorio | Uso |
| --- | --- | --- |
| `GROQ_API_KEY` | Sí | API Groq para objetivo, asuntos y cierre |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | Cuenta de servicio (Calendar + Drive) |
| `GCAL_CALENDAR_ID` | No | ID del calendario |
| `GCAL_EVENT_ID` | No | ID del evento |
| `DRIVE_UPLOAD_FOLDER_ID` | No | Carpeta destino del PDF en Drive |
| `DEBUG` | No | Detalles técnicos en errores de la API |

Enlace Calendar con `eid` → inferencia de `calendar_id` / `event_id` sin variables extra.

## Configuración (una vez)

```bash
cd acta-automation
python -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm install --prefix web
```

Crea `.env` con al menos `GROQ_API_KEY`.

## Ejecutar la interfaz web

```bash
npm run dev
```

- Frontend: **http://localhost:5173**
- API: **http://127.0.0.1:8000**

Tras cambiar código Python, la API se recarga sola (`dev:api:watch`). Si usas una sesión antigua sin reload, reinicia con Ctrl+C y `npm run dev`.

## Modo carpeta (`watch`)

```bash
.venv/bin/python -m src.main
```

Deja un `.docx` en `input/`; resultados en `output/`.

## Mantenimiento de datos

### Integrantes Gorila — [`data/gorila_staff.yaml`](data/gorila_staff.yaml)

`canonical_name`, `emails`, `role`, `aliases`.

### Contactos cliente — [`data/client_contacts.yaml`](data/client_contacts.yaml)

`email`, `name`, `role` para enriquecer invitados sin LLM.

### Plantilla Word — [`docs/template_variables.md`](docs/template_variables.md)

Tras editar la DOCX manualmente:

```bash
python src/fix_template.py
```

## Google Calendar y Drive (opcional)

Guía: [docs/configuracion-google-empresa.md](docs/configuracion-google-empresa.md).

Sin credenciales Google el pipeline funciona igual (horas desde parser + inferencia +1h).

## Tests

```bash
.venv/bin/pytest tests/ --ignore=tests/test_pipeline_e2e.py
```

~**173 tests** pasando (determinísticos). Incluye:

- `test_six_clients_batch`, `test_real_state_seguimiento`, `test_barrera_estrada`, `test_universal_acta`
- Roster, aliases, fechas, metadata_times, parser invite, invitados enrich

Calificación batch sin Groq:

```bash
.venv/bin/python scripts/batch_grade.py
```

E2E con PDF requiere LibreOffice (`tests/test_pipeline_e2e.py`).

## Estructura del proyecto

```text
src/           pipeline, parser, llm, aliases, roster, dates, generator, google_workflow
api/           FastAPI
web/           React + Vite
data/          gorila_staff.yaml, client_contacts.yaml
templates/     acta_template.docx
scripts/       batch_grade, eval_acta, judge_acta, alias_metrics
tests/         unitarios + batch golden
docs/          template_variables, configuracion-google-empresa
```

## Deploy

- **Railway**: [`Dockerfile.railway`](Dockerfile.railway) — LibreOffice + `GROQ_API_KEY`.
- **Hugging Face Spaces**: [`Dockerfile`](Dockerfile) — puerto 7860.
