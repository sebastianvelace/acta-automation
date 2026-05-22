# Acta automation

Pipeline automatizado: sube un `.docx` exportado por **Gemini** (notas de reunión) → parser + Groq (`llama-3.3-70b`) → plantilla DOCX/PDF del acta formal.

## Qué hace el sistema

```text
Gemini DOCX  →  parser  →  Groq (JSON)  →  post-proceso  →  plantilla Word  →  PDF
                    ↓                           ↓
              metadata                  roster + Próximos pasos
              (fecha, emails)           (compromisos + invitados)
```

1. **Parse** ([`src/parser.py`](src/parser.py)): extrae texto, fecha, correos del bloque Invitado, equipos Gorila, Próximos pasos, URL de calendario y hora desde el nombre del archivo Gemini.
2. **LLM** ([`src/llm.py`](src/llm.py)): Groq `llama-3.3-70b-versatile` genera JSON validado con [`ActaSchema`](src/schemas.py). El prompt exige cobertura completa de **Detalles** y cierre estructurado. Si el documento es muy largo, se trunca preservando **Próximos pasos** y **Detalles**.
3. **Post-proceso** ([`src/aliases.py`](src/aliases.py)):
   - `compose_cliente_heading` — campo Cliente del acta (ej. «Revisión Pauta - Real State»).
   - `finalize_acta_after_llm` — compromisos determinísticos desde Próximos pasos + invitados enriquecidos.
4. **Google opcional** ([`src/google_workflow.py`](src/google_workflow.py)): enriquece horas desde Calendar y sube el PDF a Drive.
5. **Render** ([`src/generator.py`](src/generator.py)): rellena [`templates/acta_template.docx`](templates/acta_template.docx) y convierte a PDF vía LibreOffice.

## Funcionalidades implementadas

### Roster Gorila / Growfik

- Catálogo en [`data/gorila_staff.yaml`](data/gorila_staff.yaml) (integrantes Gorila + equipo Growfik).
- Módulo [`src/gorila_roster.py`](src/gorila_roster.py): lookup por email o nombre para clasificar compromisos e invitados **sin llamadas extra al LLM**.
- Correos `@growfik.com` y personal Growfik se tratan como **equipo interno** (compromisos Gorila, no cliente).
- Marco Gonzalez siempre va a `compromisos_gorila`, aunque la reunión sea con un cliente.

### Invitados

- Solo correos del bloque **Invitado** del `.docx` Gemini, con asistencia **Confirmado**.
- Enriquecimiento: roster Gorila → [`data/client_contacts.yaml`](data/client_contacts.yaml) → fallback al correo.
- Personas internas que aparecen en tags de **Próximos pasos** pero no fueron invitadas (ej. Omar Escobedo) se añaden automáticamente a la lista.
- Plantilla: columnas **Nombre | Puesto | Asistencia**.

### Compromisos

- Parsing determinístico de `[Tag] Título: descripción` desde **Próximos pasos** (tiene prioridad sobre el JSON del LLM).
- Routing: equipos/personal Gorila-Growfik → `compromisos_gorila`; obligaciones del cliente → `compromisos_cliente`.
- En compromisos cliente, columna **responsable** = nombre de **cuenta/empresa** (ej. «Universal»), no persona.
- Fechas relativas en descripciones (ej. «mañana a las 2PM») se convierten usando la fecha de la reunión.
- Texto visible normaliza marcas legacy Growfik → **Gorila Hosting**.

### Interfaz y API

- **Web UI** ([`web/`](web/)): drag-and-drop, descarga PDF/DOCX, enlace «Abrir en Drive» si está configurado.
- **API REST** ([`api/app.py`](api/app.py)): `POST /api/process`, `GET /api/health`.
- **Modo carpeta**: `python -m src.main` — deja `.docx` en `input/`, resultados en `output/`.

## Requisitos

- Python 3.12+
- Node 20+
- LibreOffice instalado (`libreoffice --headless` en PATH)
- Clave **`GROQ_API_KEY`** en `.env` en la raíz del repo

## Variables de entorno

| Variable | Obligatorio | Uso |
| --- | --- | --- |
| `GROQ_API_KEY` | Sí | API Groq para estructurar el acta |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | Ruta al JSON de cuenta de servicio (Calendar + Drive) |
| `GCAL_CALENDAR_ID` | No | ID del calendario para leer evento |
| `GCAL_EVENT_ID` | No | ID del evento en Calendar |
| `DRIVE_UPLOAD_FOLDER_ID` | No | Carpeta destino del PDF en Drive |
| `DEBUG` | No | Incluye detalles técnicos en errores de la API |

Si el `.docx` incluye un enlace de Google Calendar con parámetro `eid`, se pueden inferir `calendar_id` y `event_id` sin las variables anteriores.

## Configuración (una vez)

```bash
cd acta-automation
python -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm install --prefix web
```

Copia `.env.example` o crea `.env` con al menos `GROQ_API_KEY`.

## Ejecutar la interfaz web

```bash
npm run dev
```

Abre **`http://localhost:5173`**, arrastra tu `.docx` y descarga PDF / DOCX. La API está en **`http://127.0.0.1:8000`**.

Con **Ctrl+C** se paran API y frontend. Para recarga automática del API: **`npm run dev:watch`**.

## Modo carpeta (`watch`)

```bash
.venv/bin/python -m src.main
```

Deja un `.docx` en `input/`; los resultados se escriben en `output/`.

## Mantenimiento de datos y plantilla

### Alta/baja de integrantes Gorila

Edita [`data/gorila_staff.yaml`](data/gorila_staff.yaml): `canonical_name`, `emails`, `role`, `aliases`.

### Contactos cliente conocidos

Edita [`data/client_contacts.yaml`](data/client_contacts.yaml) para mapear correos de clientes a nombre y cargo.

### Plantilla Word

Variables Jinja2 documentadas en [`docs/template_variables.md`](docs/template_variables.md).

Tras cambios manuales a la DOCX:

```bash
python src/fix_template.py
```

## Google Calendar y Drive (opcional)

Sin estas variables el pipeline funciona igual. Sirven para enriquecer fecha/horas desde un evento y subir el PDF a Drive.

**Guía paso a paso para cuentas de empresa (Workspace + GCP):** [docs/configuracion-google-empresa.md](docs/configuracion-google-empresa.md).

La cuenta de servicio necesita acceso de lectura al calendario (compartir el calendario con el correo `...@...gserviceaccount.com`) y permisos en la carpeta de Drive.

## Si `npm run dev` falla con `ENOSPC` (Linux)

Linux limita los **watchers de inotify**. Muchas herramientas a la vez (IDE, Cursor, Docker, Vite) agotan el cupo.

**Qué hace el repo por defecto**

- `npm run dev` arranca la API **sin** `--reload`.
- Vite usa **polling** para reducir `fs.watch`.

**Si aun así ves `ENOSPC`**, sube límites del kernel:

```bash
sudo sysctl fs.inotify.max_user_watches=524288
sudo sysctl fs.inotify.max_user_instances=8192
```

Permanente:

```bash
sudo tee /etc/sysctl.d/99-inotify-dev.conf << 'EOF'
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=8192
EOF
sudo sysctl -p /etc/sysctl.d/99-inotify-dev.conf
```

## Estructura del proyecto

```text
src/           pipeline, parser, llm, aliases, roster, dates, generator
api/           FastAPI (POST /api/process)
web/           React + Vite
data/          gorila_staff.yaml, client_contacts.yaml
templates/     acta_template.docx
tests/         unitarios + fixtures
docs/          guías (plantilla, Google)
```

## Tests

```bash
.venv/bin/pytest
```

Incluye tests de roster, compromisos, invitados, fechas relativas y caso Universal (post-proceso sin Groq). Los e2e que generan PDF requieren LibreOffice funcional en el entorno.

## Railway (deploy del API)

- Imagen en [`Dockerfile.railway`](Dockerfile.railway) (`python:3.11-slim` + LibreOffice).
- Variables: **`GROQ_API_KEY`** (obligatorio).
- Escucha **`${PORT:-8000}`**.
- CORS **`allow_origins=["*"]`** — revisar para producción.

## Hugging Face Spaces

- [`Dockerfile`](Dockerfile) en la raíz (puerto **7860**, LibreOffice).
- Space tipo **Docker**; define **`GROQ_API_KEY`** en Settings → Repository secrets.
- Health: **`GET /api/health`**; proceso: **`POST /api/process`**.
