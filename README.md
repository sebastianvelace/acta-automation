# Acta automation

Pipeline: sube `.docx` de Gemini → parser + Groq (`llama-3.3`) → plantilla DOCX/PDF del acta.

## Requisitos

- Python 3.12+
- Node 20+
- LibreOffice instalado (`libreoffice --headless` en PATH)
- Clave **`GROQ_API_KEY`** en `.env` en la raíz del repo

## Configuración (una vez)

```bash
cd acta-automation
python -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm install --prefix web
```

## Si `npm run dev` falla con `ENOSPC` (Linux)

Linux limita los **watchers de inotify** (y a veces el **número de instancias**). Muchas herramientas a la vez (IDE, Cursor, Docker, `uvicorn --reload` + Vite) agotan el cupo.

**Qué hace el repo por defecto**

- `npm run dev` arranca la API **sin** `--reload`, para no duplicar miles de watchers con Vite.
- Vite usa **polling** (`web/vite.config.ts` + variables `CHOKIDAR_*` en `web/package.json`) para reducir `fs.watch` / inotify.

**Si aun así ves `ENOSPC`**, sube límites del kernel (hasta reinicio):

```bash
sudo sysctl fs.inotify.max_user_watches=524288
sudo sysctl fs.inotify.max_user_instances=8192
```

Permanente (crea un archivo y aplica):

```bash
sudo tee /etc/sysctl.d/99-inotify-dev.conf << 'EOF'
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=8192
EOF
sudo sysctl -p /etc/sysctl.d/99-inotify-dev.conf
```

**Modo con recarga automática del API** (más watchers; solo si tienes límites holgados):

```bash
npm run dev:watch
```

Tras cambiar `.py` en `api/` o `src/`, sin `dev:watch` tendrás que **parar y volver a levantar** `npm run dev` (o usar `dev:watch`).

## Ejecutar la interfaz web (un solo comando)

Desde la raíz del proyecto:

```bash
npm run dev
```

Abre **`http://localhost:5173`**, arrastra tu `.docx` y descarga PDF / DOCX. La API está en **`http://127.0.0.1:8000`**.

Con **Ctrl+C** se paran API y frontend.

Para recargar el API al editar Python, usa **`npm run dev:watch`** (consume más watchers).

Si prefieres servicios aparte:

```bash
# Terminal 1 (sin --reload; menos ENOSPC)
.venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000

# Terminal 2
cd web && npm run dev
```

## Modo carpeta (`watch`)

Sigue igual:

```bash
.venv/bin/python -m src.main
```

Deja un `.docx` en `input/`; los resultados también se escriben en `output/` (ver la consola).

## Mantenimiento de plantilla

Tras cambios manuales a la DOCX borrador:

```bash
python src/fix_template.py
```

## Railway (deploy del API)

- Imagen en [`Dockerfile.railway`](Dockerfile.railway) (`python:3.11-slim` + LibreOffice).
- Variables de entorno en Railway: **`GROQ_API_KEY`** (obligatorio).
- El contenedor escucha **`${PORT:-8000}`** (Railway inyecta `PORT` automáticamente).
- Pon el SPA (Vercel u otro) apuntando a la URL HTTPS del servicio. El API usa CORS **`allow_origins=["*"]`** por ahora (revísalo para producción).

## Hugging Face Spaces

- El [`Dockerfile`](Dockerfile) en la raíz está pensado para **Spaces** (puerto **7860**, LibreOffice).
- Crea un Space tipo **Docker**, conecta el repo y define **`GROQ_API_KEY`** en Settings → Repository secrets.
- Health: **`GET /api/health`**; proceso: **`POST /api/process`** igual que en local.
# acta-automation
