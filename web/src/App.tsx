import { useCallback, useRef, useState } from "react";

const apiBase = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type ProcessPayload = {
  metadata: Record<string, unknown>;
  acta: Record<string, unknown>;
  output_base_name: string;
  pdf_base64: string;
  docx_base64: string | null;
};

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
  const [dragFocus, setDragFocus] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ProcessPayload | null>(null);
  const [fileLabel, setFileLabel] = useState<string | null>(null);

  const upload = async (file: File) => {
    setError(null);
    setPayload(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${apiBase}/api/process`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        let msg = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (body.detail) {
            msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          }
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      const data = (await res.json()) as ProcessPayload;
      setPayload(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fallo de red.");
    } finally {
      setBusy(false);
    }
  };

  const pick = () => inputRef.current?.click();

  const onInputChange = useCallback(async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (file) {
      setFileLabel(file.name);
      await upload(file);
    }
  }, []);

  const onDrop = useCallback(
    async (ev: React.DragEvent) => {
      ev.preventDefault();
      setDragFocus(false);
      const file = ev.dataTransfer.files?.[0];
      if (!file?.name.endsWith(".docx")) {
        setError("Solo archivos .docx");
        return;
      }
      setFileLabel(file.name);
      await upload(file);
    },
    [],
  );

  const baseForDownloads = payload?.output_base_name ?? "acta";

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

      {busy && (
        <p className="status working">Generando acta… (puede tardar un minuto)</p>
      )}
      {!busy && fileLabel && !error && payload && (
        <p className="status">
          Listo — <strong>{fileLabel}</strong>
        </p>
      )}
      {!busy && error && (
        <p className="status">
          <span className="error" style={{ display: "block", marginTop: "1rem" }}>
            {error}
          </span>
        </p>
      )}

      {payload && (
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

      {payload && (
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
