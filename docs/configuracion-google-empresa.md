# Configuración de Google (Calendar + Drive) para la empresa

Esta guía asume **Google Workspace** (cuentas `@tuempresa.com`) y que quien configura tiene permisos de **administrador de Google Cloud** o puede coordinar con **IT / seguridad**.

El código usa una **cuenta de servicio**: no es un login de persona; es una identidad técnica a la que la empresa comparte solo lo necesario (un calendario y/o una carpeta de Drive).

---

## 1. Acuerdos internos antes de tocar nada

- **Quién es dueño del proyecto de GCP**: mismo equipo que otros integraciones, o un proyecto nuevo solo para este flujo.
- **Política de claves JSON**: el archivo de la cuenta de servicio es una **credencial sensible**. No se sube al repo, no va a Slack ni email. Rotación si se filtra.
- **Alcance mínimo**: en lugar de dar acceso a todo Drive de la empresa, se usa **una carpeta concreta** compartida con la cuenta de servicio. Igual con el calendario: compartir solo el calendario de reuniones que corresponda (o el del recurso o sala).
- **Workspace puede restringir** cuentas de servicio o el uso de APIs; si algo falla, IT debe revisar restricciones de acceso a APIs o políticas de seguridad.

---

## 2. Proyecto en Google Cloud Platform

1. Entra a [Google Cloud Console](https://console.cloud.google.com/) con una cuenta autorizada de la empresa.
2. Crea un proyecto nuevo (por ejemplo `acta-automation-prod`) o usa uno existente aprobado por IT.
3. Anota el **ID del proyecto**.

### Habilitar APIs

En **APIs y servicios → Biblioteca**, habilita:

- **Google Calendar API**
- **Google Drive API**

Sin esto, las llamadas devolverán error (en logs verás `403` o API not enabled).

---

## 3. Crear la cuenta de servicio

1. Ve a **IAM y administración → Cuentas de servicio**.
2. **Crear cuenta de servicio**. Nombre claro: por ejemplo `acta-automation-calendar-drive`.
3. Sobre **roles en el proyecto**: para Calendar y Drive el acceso real sale de **compartir** calendario y carpeta; a nivel proyecto, sigue la política de tu empresa (a veces un rol mínimo o ninguno extra). Consulta con IT si la consola exige algo específico.
4. **Claves → Agregar clave → JSON**. Se descargará un archivo `.json`.

**Importante:** ese JSON contiene una clave privada. Guárdalo en la caja fuerte de secretos de la empresa (1Password, Vault, Secret Manager, etc.). En servidores: variable de entorno o **montaje de secreto**, nunca en Git.

El correo de la cuenta tendrá forma:

`acta-automation-calendar-drive@TU-PROYECTO.iam.gserviceaccount.com`

**Cópialo:** lo usarás al compartir calendario y carpeta.

---

## 4. Calendario: dar lectura al acta

La aplicación solo **lee** el evento (fecha y hora de inicio y fin).

### 4.1 Compartir el calendario

1. En Google Calendar (web), en la lista de calendarios a la izquierda, elige el calendario correcto (por ejemplo el de reuniones internas o con clientes).
2. Abre **Configuración y uso compartido** de ese calendario.
3. **Añadir personas**: pega el correo `…@….iam.gserviceaccount.com`.
4. Permiso recomendado: **Ver todos los detalles de los eventos** (suficiente para leer horarios).

Si la empresa usa calendarios de **recurso o sala**, a veces el ID del calendario es un email terminado en `@resource.calendar.google.com`; es válido.

### 4.2 Cómo rellenar `GCAL_CALENDAR_ID` y `GCAL_EVENT_ID`

**Opción A — Variables de entorno**

- **Calendar ID:** en muchos casos es el **correo del calendario** que ves en configuración (por ejemplo `reuniones@tuempresa.com`). En calendarios secundarios puede ser un ID largo; usa el que Google muestra como ID de calendario.
- **Event ID:** identificador del evento concreto. Quien gestione Calendar puede obtenerlo desde la API o desde herramientas internas; en la práctica, suele ser más fácil la opción B.

**Opción B — Enlace del evento en el `.docx` (`calendar_url`)**

Si el documento incluye en metadatos un enlace de Google Calendar con el parámetro **`eid`**, el código puede extraer `calendar_id` y `event_id` solo. Entonces puedes **omitir** `GCAL_CALENDAR_ID` y `GCAL_EVENT_ID` en `.env`.

---

## 5. Drive: carpeta para subir PDFs

La aplicación **crea** archivos dentro de una carpeta concreta.

### 5.1 Carpeta y permisos

1. En Drive, crea (o elige) una carpeta; por ejemplo `Actas automáticas`.
2. **Comparte** la carpeta con el correo `…@….iam.gserviceaccount.com`.
3. Permiso: **Editor** (debe poder **subir** archivos).

### 5.2 `DRIVE_UPLOAD_FOLDER_ID`

Abre la carpeta en el navegador. La URL suele ser:

`https://drive.google.com/drive/folders/ESTÁ_ES_LA_ID`

Copia solo el tramo **después de** `/folders/`. Ese valor es `DRIVE_UPLOAD_FOLDER_ID`.

**Buena práctica:** usa una carpeta en un **Drive compartido** de la empresa si IT lo permite, con políticas de retención y propiedad claras, en lugar de “Mi unidad” personal.

---

## 6. Variables en `.env` (local o servidor)

En la raíz del repositorio (junto a `GROQ_API_KEY`):

```bash
# Ya existente
GROQ_API_KEY=gsk_...

# Ruta al JSON de la cuenta de servicio (el archivo no debe estar en Git)
GOOGLE_SERVICE_ACCOUNT_JSON=/ruta/segura/acta-automation-sa.json

# Opción 1: calendario por IDs (omite ambas si el .docx trae calendar_url con eid)
GCAL_CALENDAR_ID=reuniones@tuempresa.com
GCAL_EVENT_ID=id_del_evento

# Opcional: sube el PDF y la API puede devolver drive_web_link
DRIVE_UPLOAD_FOLDER_ID=xxxxxxxxxxxxxxxxxxxxx
```

Reinicia la API después de cambiar `.env`.

### Producción (Railway, VM, Kubernetes)

El código usa **ruta de archivo** en `GOOGLE_SERVICE_ACCOUNT_JSON`, no el JSON pegado en una sola variable.

- Monta el secreto como archivo (volumen o “secret file” de la plataforma) y apunta la variable a esa ruta, **o**
- En el arranque del contenedor, escribe el contenido del secreto a un archivo y usa esa ruta.

---

## 7. Comprobar que funciona

1. **Sin Google:** renombra temporalmente `GOOGLE_SERVICE_ACCOUNT_JSON` en `.env` — el acta debe generarse igual que antes.
2. **Con Google:** procesa un `.docx` de prueba con permisos y IDs correctos:
   - Si Calendar está bien: fecha y horas del acta deberían coincidir con el evento.
   - Si Drive está bien: la respuesta de `POST /api/process` puede incluir `drive_web_link` y en la web aparece **Abrir en Drive**.

Los fallos de Google suelen verse como **warnings** en logs (permiso no concedido, API deshabilitada, ID incorrecto).

---

## 8. Resumen de responsabilidades

| Rol | Qué hace |
| --- | --- |
| Cloud / IT | Proyecto GCP, APIs, cuenta de servicio, custodia del JSON, política de secretos. |
| Workspace admin (si aplica) | Aprobar uso de APIs, unidades compartidas, restricciones. |
| Equipo operativo | Carpeta de actas, compartir con la cuenta de servicio, elegir calendario. |
| Desarrollo | `.env` por entorno, nunca commitear credenciales. |

---

## 9. Nota sobre permisos en código

Actualmente se usan los scopes `calendar.readonly` y `drive` (este último es amplio). Si en el futuro seguridad exige algo más acotado, habría que revisar el código y las opciones de la API de Drive.

[← Volver al README principal](../README.md)
