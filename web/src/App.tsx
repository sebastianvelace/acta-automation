import { useCallback, useRef, useState } from "react";

const apiBase = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type ProcessPayload = {
  metadata: Record<string, unknown>;
  acta: Record<string, unknown>;
  output_base_name: string;
  pdf_base64: string;
  docx_base64: string | null;
  drive_web_link?: string | null;
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
  const [dragOver, setDragOver] = useState(false);
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
      const res = await fetch(`${apiBase}/api/process`, { method: "POST", body: fd });
      let body: Record<string, unknown> = {};
      try { body = (await res.json()) as Record<string, unknown>; } catch { /**/ }
      if (!res.ok) {
        const err: ApiErrorPayload = {
          error_code: typeof body.error_code === "string" ? body.error_code : "UNKNOWN",
          user_message: typeof body.user_message === "string" ? body.user_message : `Error ${res.status}`,
          request_id: typeof body.request_id === "string" ? body.request_id : "",
        };
        if (import.meta.env.DEV && typeof body.technical_details === "string")
          err.technical_details = body.technical_details;
        setServerError(err);
        setPhase("error");
        return;
      }
      setPayload(body as unknown as ProcessPayload);
      setPhase("success");
    } catch {
      setServerError({ error_code: "NETWORK", user_message: "Fallo de red. Comprueba tu conexión.", request_id: "" });
      setPhase("error");
    }
  }, []);

  const onInputChange = useCallback(async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (file) { setFileLabel(file.name); await upload(file); }
  }, [upload]);

  const onDrop = useCallback(async (ev: React.DragEvent) => {
    ev.preventDefault();
    setDragOver(false);
    const file = ev.dataTransfer.files?.[0];
    if (!file?.name.endsWith(".docx")) {
      setLocalError("Solo se aceptan archivos .docx");
      setPhase("error");
      return;
    }
    setFileLabel(file.name);
    setLocalError(null);
    await upload(file);
  }, [upload]);

  const retryLast = useCallback(async () => {
    if (lastFileRef.current) await upload(lastFileRef.current);
  }, [upload]);

  const copyRequestId = useCallback(async (rid: string) => {
    if (!rid) return;
    try { await navigator.clipboard.writeText(rid); } catch { /**/ }
  }, []);

  const base = payload?.output_base_name ?? "acta";
  const showError = phase === "error";

  return (
    <div className="page">
      <header className="header">
        <img src="/gorila-logo.png" alt="" className="logo" />
        <div>
          <div className="brand">Gorila Hosting</div>
          <div className="brand-sub">Generador de Actas</div>
        </div>
      </header>

      <main className="main">
        <h1 className="title">Genera tu <em>acta</em></h1>
        <p className="desc">Sube el .docx de Gemini y el sistema genera el PDF y Word automáticamente.</p>

        <input
          ref={inputRef}
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="file-input"
          onChange={onInputChange}
        />

        <div
          className={`drop ${dragOver ? "drag-over" : ""} ${busy ? "busy" : ""}`}
          onDragEnter={() => setDragOver(true)}
          onDragLeave={() => setDragOver(false)}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDrop={onDrop}
          onClick={busy ? undefined : () => inputRef.current?.click()}
        >
          {busy ? (
            <span className="spinner" />
          ) : phase === "success" ? (
            <svg className="icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg className="icon-up" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          )}

          <span className="drop-label">
            {busy
              ? "Procesando con IA…"
              : phase === "success"
              ? fileLabel ?? "Listo"
              : "Arrastra o haz clic para subir el .docx"}
          </span>

          {busy && <span className="drop-hint">~10–20 segundos</span>}
          {!busy && phase !== "success" && <span className="drop-hint">.docx exportado de Gemini</span>}
        </div>

        {showError && (
          <p className="error-line">
            {serverError?.user_message ?? localError}
            {lastFileRef.current && (
              <> — <button className="inline-btn" onClick={retryLast}>reintentar</button></>
            )}
            {serverError?.request_id && (
              <> · <button className="inline-btn" onClick={() => copyRequestId(serverError.request_id)}>copiar ID</button></>
            )}
          </p>
        )}

        {import.meta.env.DEV && serverError?.technical_details && (
          <details className="dev-details">
            <summary>Detalles técnicos</summary>
            <pre>{serverError.technical_details}</pre>
          </details>
        )}

        {payload && phase === "success" && (
          <div className="actions">
            <button
              className="btn-primary"
              onClick={() => downloadBase64(payload.pdf_base64, `${base}.pdf`, "application/pdf")}
            >
              Descargar PDF
            </button>
            {payload.docx_base64 && (
              <button
                className="btn-ghost"
                onClick={() => downloadBase64(
                  payload.docx_base64!,
                  `${base}.docx`,
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )}
              >
                Descargar DOCX
              </button>
            )}
            {payload.drive_web_link && (
              <a className="btn-ghost" href={payload.drive_web_link} target="_blank" rel="noopener noreferrer">
                Abrir en Drive
              </a>
            )}
          </div>
        )}

        {payload && phase === "success" && (
          <details className="meta">
            <summary>Metadatos extraídos</summary>
            <pre>{JSON.stringify(payload.metadata, null, 2)}</pre>
          </details>
        )}
      </main>
    </div>
  );
}
