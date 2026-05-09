import { useCallback, useRef, useState } from "react";

const apiBase = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type ProcessPayload = {
  metadata: Record<string, unknown>;
  acta: Record<string, unknown>;
  output_base_name: string;
  pdf_base64: string;
  docx_base64: string | null;
};

type ApiErrorPayload = {
  error_code: string;
  user_message: string;
  request_id: string;
  technical_details?: string;
};

type UiPhase = "idle" | "uploading" | "processing" | "success" | "error";

function downloadBase64(b64: string, filename: string, mime: string) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const lastFileRef = useRef<File | null>(null);
  const [dragFocus, setDragFocus] = useState(false);
  const [phase, setPhase] = useState<UiPhase>("idle");
  const [serverError, setServerError] = useState<ApiErrorPayload | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ProcessPayload | null>(null);
  const [fileLabel, setFileLabel] = useState<string | null>(null);

  const busy = phase === "uploading" || phase === "processing";

  const upload = useCallback(async (file: File) => {
    lastFileRef.current = file;
    setServerError(null);
    setLocalError(null);
    setPayload(null);
    setPhase("uploading");
    try {
      const fd = new FormData();
      fd.append("file", file);
      setPhase("processing");
      const res = await fetch(`${apiBase}/api/process`, {
        method: "POST",
        body: fd,
      });
      let body: Record<string, unknown> = {};
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        /* ignore */
      }
      if (!res.ok) {
        const userMessage =
          typeof body.user_message === "string"
            ? body.user_message
            : `Error ${res.status}`;
        const requestId = typeof body.request_id === "string" ? body.request_id : "";
        const err: ApiErrorPayload = {
          error_code: typeof body.error_code === "string" ? body.error_code : "UNKNOWN",
          user_message: userMessage,
          request_id: requestId,
        };
        if (import.meta.env.DEV && typeof body.technical_details === "string") {
          err.technical_details = body.technical_details;
        }
        setServerError(err);
        setPhase("error");
        return;
      }
      setPayload(body as unknown as ProcessPayload);
      setPhase("success");
    } catch {
      setServerError({
        error_code: "NETWORK",
        user_message: "Fallo de red. Comprueba tu conexión.",
        request_id: "",
      });
      setPhase("error");
    }
  }, []);

  const pick = () => inputRef.current?.click();

  const onInputChange = useCallback(
    async (ev: React.ChangeEvent<HTMLInputElement>) => {
      const file = ev.target.files?.[0];
      ev.target.value = "";
      if (file) {
        setFileLabel(file.name);
        setLocalError(null);
        await upload(file);
      }
    },
    [upload],
  );

  const onDrop = useCallback(
    async (ev: React.DragEvent) => {
      ev.preventDefault();
      setDragFocus(false);
      const file = ev.dataTransfer.files?.[0];
      if (!file?.name.endsWith(".docx")) {
        setLocalError("Solo archivos .docx");
        setPhase("error");
        return;
      }
      setFileLabel(file.name);
      setLocalError(null);
      await upload(file);
    },
    [upload],
  );

  const retryLast = useCallback(async () => {
    const f = lastFileRef.current;
    if (!f) return;
    await upload(f);
  }, [upload]);

  const copyRequestId = useCallback(async (rid: string) => {
    if (!rid) return;
    try {
      await navigator.clipboard.writeText(rid);
    } catch {
      /* ignore */
    }
  }, []);

  const baseForDownloads = payload?.output_base_name ?? "acta";
  const showErrorCard = (serverError && phase === "error") || (localError && phase === "error");

  return (
    <div className="app">
      <h1>Generar acta</h1>
      <p className="sub">Sube el .docx de Gemini. Se generan PDF y Word en tu navegador.</p>

      <div
        className={`drop ${dragFocus ? "focus" : ""}`}
        onDragEnter={() => setDragFocus(true)}
        onDragLeave={() => setDragFocus(false)}
        onDragOver={(e) => {
          e.preventDefault();
          setDragFocus(true);
        }}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="file-input"
          onChange={onInputChange}
        />
        <p>
          <strong>Suelta el archivo aquí</strong> o elige desde tu equipo.
        </p>
        <div className="actions row">
          <button type="button" onClick={pick} disabled={busy}>
            Elegir .docx
          </button>
        </div>
      </div>

      {phase === "uploading" && (
        <p className="status working">Subiendo archivo…</p>
      )}
      {phase === "processing" && (
        <p className="status working">Estructurando con IA, ~10–20s</p>
      )}

      {phase === "success" && fileLabel && (
        <p className="status">
          Listo — <strong>{fileLabel}</strong>
        </p>
      )}

      {showErrorCard && (
        <div className="warn-banner" role="alert">
          <p className="warn-banner-text">{serverError?.user_message ?? localError}</p>
          {serverError?.request_id ? (
            <div className="warn-banner-row">
              <span className="warn-meta">ID: {serverError.request_id}</span>
              <button
                type="button"
                className="secondary small"
                onClick={() => copyRequestId(serverError.request_id)}
              >
                Copiar request_id
              </button>
              <button type="button" className="secondary small" onClick={retryLast}>
                Reintentar
              </button>
            </div>
          ) : null}
          {import.meta.env.DEV && serverError?.technical_details ? (
            <details className="dev-technical">
              <summary>technical_details (solo desarrollo)</summary>
              <pre>{serverError.technical_details}</pre>
            </details>
          ) : null}
        </div>
      )}

      {payload && phase === "success" && (
        <div className="row actions" style={{ marginTop: "1.25rem" }}>
          <button
            type="button"
            onClick={() =>
              downloadBase64(payload.pdf_base64, `${baseForDownloads}.pdf`, "application/pdf")
            }
          >
            Descargar PDF
          </button>
          {payload.docx_base64 && (
            <button
              type="button"
              className="secondary"
              onClick={() =>
                downloadBase64(
                  payload.docx_base64!,
                  `${baseForDownloads}.docx`,
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
              }
            >
              Descargar DOCX
            </button>
          )}
        </div>
      )}

      {payload && phase === "success" && (
        <section className="meta">
          <details>
            <summary>Metadatos extraídos</summary>
            <pre>{JSON.stringify(payload.metadata, null, 2)}</pre>
          </details>
        </section>
      )}
    </div>
  );
}
