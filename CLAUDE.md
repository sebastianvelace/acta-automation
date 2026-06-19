# CLAUDE.md — Acta automation

Contexto y reglas operativas para Claude Code en este repo. **Léelo completo antes de
procesar actas o tocar el pipeline.** El objetivo nº1 al operar: **no gastar tokens de Groq de más.**

---

## Qué es esto

Convierte notas de reunión exportadas por **Gemini** (`.docx`) en un **acta formal** (DOCX + PDF)
con el estilo de Gorila. Una sola llamada a un LLM (Groq) estructura el contenido; **todo lo demás
es determinístico** (sin tokens).

```
Gemini .docx → parser → Groq (JSON)  → finalize_acta_after_llm → apply_metadata_times → render DOCX/PDF
              (det.)   (ÚNICO costo    (det.)                   (det.)                 (det.)
                        de tokens)
```

Entry point: `run_acta_pipeline(input_docx_path, *, source_filename=...)` en `src/pipeline.py`.

---

## REGLAS DE TOKENS (lo más importante)

**El único paso que consume tokens es `structure_meeting` en `src/llm.py` (Groq `llama-3.3-70b-versatile`).**
Parser, overrides de hora, política Growfik, invitados, fechas en español y el render son **100% determinísticos**.

Límite Groq tier gratis: **100.000 tokens/día (TPD)**. Cada acta cuesta ≈ **prompt ~3.500 + los
`max_tokens` reservados se cuentan completos** contra ese límite. Con `max_tokens=4096` (valor actual)
cada llamada pesa ~7.500 ⇒ caben **~13–15 actas/día**.

**Hay caché en disco** (`src/llm.py`, `.cache/llm/`): la primera vez que pasa un `.docx` por el LLM se
guarda el JSON del modelo; reprocesarlo (arreglos de hora/Growfik/plantilla) es **cache hit = 0 tokens
y ni siquiera requiere `GROQ_API_KEY`**. La clave = hash(prompt + modelo + max_tokens + notas), así que
cambiar las notas o el prompt invalida automáticamente. Desactivable con `ACTA_LLM_CACHE=0`.

### Haz / No hagas

- ✅ **Procesa cada `.docx` por el LLM UNA sola vez.** Guarda el resultado.
- ❌ **NUNCA re-corras el pipeline (LLM) para arreglar cosas que NO dependen del LLM:**
  - **Hora equivocada / sello de exportación** → edita `data/meeting_time_overrides.yaml`
    y **parchea el `.docx` ya generado** (celdas «Hora Inicio»/«Hora Fin» de la tabla) + reconvierte el PDF
    con LibreOffice. Cero tokens. (Ver «Horas» abajo.)
  - **Encabezado Growfik / «GORILA & GROWFIK»** → es la variable `encabezado_compromisos_gorila`
    en la plantilla; se decide determinísticamente. Si ya está renderizado mal, parchéalo en el `.docx`.
  - **Plantilla, formato, nombres de invitados, cliente, fecha en español** → todo determinístico,
    no requiere LLM. Re-renderiza desde los datos o parchea el `.docx`.
- ❌ **NUNCA corras el mismo batch dos veces.** Si un batch falla a mitad por rate limit, reanuda
  **solo los archivos que faltan**, no todos.
- ✅ **Para parchear hora en un `.docx` ya generado** sin tocar Groq: abre con `python-docx`, busca la
  celda con label «Hora Inicio»/«Hora Fin» y reescribe la celda siguiente; `libreoffice --headless
  --convert-to pdf --outdir output <docx>`.
- ⚠️ Si ves `RateLimitError 429 ... tokens per day (TPD)`: el día se agotó. El mensaje dice en cuánto
  resetea (p. ej. «try again in 30m»). **No reintentes en bucle** — espera o termina con parches deterministas.

### Costo del rate limit en la práctica
El 429 reporta `Requested = prompt + max_tokens`. Groq reserva el `max_tokens` completo, por eso se bajó
a 4096 (`ACTA_MAX_COMPLETION_TOKENS` para tunearlo). Un acta JSON real ocupa ~1.5k–2.5k tokens de salida.

---

## Cómo correr

`.env` (en la raíz) define `GROQ_API_KEY`; `src/llm.py` hace `load_dotenv()` solo. Intérprete: `./.venv/bin/python`.

**Un archivo (recomendado, una llamada Groq):**
```python
from src.pipeline import run_acta_pipeline
r = run_acta_pipeline("/ruta/al.docx", source_filename="al.docx")
print(r["pdf_path"], r["acta"]["hora_inicio"], r["acta"]["hora_fin"])
```

**Watcher:** `python -m src.main` observa `input/` y mueve a `input/processed/` (cada archivo = 1 llamada Groq).

Salida en `output/`. Nombre: `Acta <cliente/titulo> <día de mes>` (ver `build_output_name`).

**Verificar sin Groq:** `scripts/batch_grade.py` califica de forma determinística (parse → stub → finalize → tiempos), útil para revisar horas/invitados/Growfik sin gastar tokens.

---

## Reglas de negocio que NO se derivan del código

- **Growfik es empresa independiente de Gorila.** Su marca SOLO aparece en actas de **Universal**
  (seguimiento, redes, estrategia, dashboard — todo lo de Universal). En cualquier otra acta NO figura.
  - Detección: `is_universal_acta()` en `src/aliases.py` (match «universal» en cliente/título/archivo
    o correo `@universal.edu.co`).
  - Encabezado de compromisos: variable de plantilla `{{ encabezado_compromisos_gorila }}`, fijada en
    `apply_growfik_visibility_policy` → `"GORILA & GROWFIK"` si Universal, `"GORILA"` si no.
  - Roster (`format_staff_puesto_for_acta`, `_invitado_gorila_fallback_from_email`) y el scrub de texto
    ocultan Growfik en actas no-Universal según el flag `universal`.

- **Horas / sellos de exportación de Gemini.** El nombre del archivo Gemini suele traer un **sello de
  exportación** (`_14_58`, `_11_59`, etc.), NO la hora real de la reunión. `data/meeting_time_overrides.yaml`
  fija la hora real por `match` (título/archivo) + `dates` (lista `YYYY_MM_DD`). Un override **con fecha
  siempre gana** sobre la hora parseada; uno **sin fecha** cede si el parser ya extrajo hora real.
  Para una reunión recurrente nueva: añade su `YYYY_MM_DD` a la serie correspondiente.

- **Invitados por etiqueta de grupo.** Cuando Gemini lista al equipo Gorila por grupo de calendario
  («Marketing Gorila Hosting», «ADS», «Executive») **sin correo**, el roster no puede mapearlos a una
  persona y salen como etiqueta genérica. No es bug del pipeline; es limitación del documento fuente.

---

## Mapa del código

| Archivo | Rol |
|---|---|
| `src/pipeline.py` | Orquesta: parse → LLM → finalize → tiempos → render. |
| `src/parser.py` | `extract_text` → `{raw_text, metadata}`; fecha, correos, equipos, Próximos pasos, Detalles, hora del archivo. |
| `src/llm.py` | **Único costo de tokens.** Prompt + Groq + validación `ActaSchema` + truncado por presupuesto. |
| `src/aliases.py` (1.288 líneas) | Post-proceso determinístico: compromisos desde Próximos pasos, cliente, `is_universal_acta`, política Growfik. |
| `src/gorila_roster.py` | Mapea correos/puestos del staff; marca Growfik solo si `universal`. |
| `src/client_contacts.py` | `data/client_contacts.yaml` → nombres/roles de clientes. |
| `src/meeting_time_overrides.py` | Aplica `data/meeting_time_overrides.yaml` (lru_cache). |
| `src/google_workflow.py` | `apply_metadata_times_to_acta`, enriquecimiento Calendar opcional, subida a Drive opcional. |
| `src/generator.py` | Render docxtpl (`autoescape=True`, clave para «&») + LibreOffice → PDF. |
| `templates/acta_template.docx` | Plantilla Jinja2. Header compromisos = `{{ encabezado_compromisos_gorila }}`. |
| `data/*.yaml` | Contactos, staff, overrides de hora. Editar aquí = sin tokens. |
| `scripts/batch_grade.py` | Calificación/QA determinística sin Groq. |

Tras tocar código: `./.venv/bin/python -m pytest -q` (suite determinística).

---

## Mejoras de tokens

Implementadas (en `src/llm.py`):

1. ✅ **Caché en disco del JSON del modelo** (`.cache/llm/`), clave `hash(prompt + modelo + max_tokens + notas)`.
   Reprocesar el mismo `.docx` cuesta **0 tokens** y no requiere API key. Toggle `ACTA_LLM_CACHE=0`.
2. ✅ **`_MAX_COMPLETION_TOKENS` 6144 → 4096** (env `ACTA_MAX_COMPLETION_TOKENS`). Reduce el `Requested`
   por llamada y deja más presupuesto para las notas (~5.5k tokens de `raw_text`).

Pendiente (menor): la retry de schema reenvía el system prompt completo (~1.576 tok); solo dispara en
error de validación, impacto bajo.
