"""Structured errors for the acta pipeline and API."""


class ActaError(Exception):
    """Base error with API-safe fields (never include raw model output in ``user_message``)."""

    error_code: str = "ACTA_ERROR"
    http_status: int = 500
    user_message: str = "No pudimos completar la operación. Si el problema continúa, contacta a soporte."

    def __init__(self, *, technical_details: str | None = None):
        self.technical_details = technical_details
        super().__init__(type(self).user_message)


class DocxParseError(ActaError):
    error_code = "DOCX_PARSE_FAILED"
    http_status = 422
    user_message = (
        "No pudimos leer el archivo Word. Comprueba que sea un .docx válido de las notas de la reunión."
    )


class LLMExtractionError(ActaError):
    error_code = "LLM_EXTRACTION_FAILED"
    http_status = 502
    user_message = (
        "No pudimos extraer la estructura de la reunión. Esto suele resolverse reintentando."
    )


class SchemaValidationError(ActaError):
    error_code = "SCHEMA_VALIDATION_FAILED"
    http_status = 502
    user_message = (
        "La respuesta del modelo no encajó en el formato esperado del acta. Prueba de nuevo en unos segundos."
    )


class RenderError(ActaError):
    error_code = "RENDER_FAILED"
    http_status = 500
    user_message = "No pudimos generar el documento final (PDF/Word). Si persiste, contacta a soporte."


class InvalidFileTypeError(ActaError):
    error_code = "INVALID_FILE_TYPE"
    http_status = 422
    user_message = "Sube un archivo .docx (notas Gemini)."


class FileTooLargeError(ActaError):
    error_code = "FILE_TOO_LARGE"
    http_status = 422

    def __init__(self, *, max_mb: int, technical_details: str | None = None):
        self.max_mb = max_mb
        um = f"El archivo supera el tamaño máximo permitido ({max_mb} MB)."
        self.technical_details = technical_details
        self.user_message = um
        Exception.__init__(self, um)
