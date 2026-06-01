import { useState, useEffect, useRef } from "react";
import {
  listarComunicados, crearComunicado, eliminarComunicado,
  urlImagenComunicado, type ComunicadoDTO,
} from "../../api/client";

export function ComunicadosAdmin() {
  const [lista, setLista] = useState<ComunicadoDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [creando, setCreando] = useState(false);

  function recargar() {
    listarComunicados().then(setLista).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  async function borrar(c: ComunicadoDTO) {
    if (!confirm(`¿Eliminar el comunicado "${c.titulo}"?`)) return;
    await eliminarComunicado(c.id);
    recargar();
  }

  return (
    <div className="comunicados-admin">
      <div className="dash-head">
        <h2>Comunicados</h2>
        <button className="cuota-btn-pagar" style={{ maxWidth: 180 }} onClick={() => setCreando(true)}>
          + Nuevo comunicado
        </button>
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : lista.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon">📣</div>
          <p>No hay comunicados publicados.</p>
        </div>
      ) : (
        <div className="comunicado-admin-list">
          {lista.map(c => (
            <div key={c.id} className="comunicado-admin-item">
              {c.imagen && (
                <img className="comunicado-admin-thumb" src={urlImagenComunicado(c.imagen)} alt="" />
              )}
              <div className="comunicado-admin-info">
                <div className="comunicado-admin-titulo">{c.titulo}</div>
                <div className="muted small">
                  {new Date(c.created_at).toLocaleDateString("es-HN", { day: "numeric", month: "long", year: "numeric" })}
                </div>
                <div className="comunicado-admin-preview muted small">{c.cuerpo.slice(0, 120)}{c.cuerpo.length > 120 ? "…" : ""}</div>
              </div>
              <button className="ghost mini" style={{ color: "#c81e1e", flexShrink: 0 }} onClick={() => borrar(c)}>
                Eliminar
              </button>
            </div>
          ))}
        </div>
      )}

      {creando && (
        <FormComunicado onCerrar={() => setCreando(false)} onCreado={() => { setCreando(false); recargar(); }} />
      )}
    </div>
  );
}

function FormComunicado({ onCerrar, onCreado }: { onCerrar: () => void; onCreado: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [imagen, setImagen] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setImagen(f);
    setPreview(URL.createObjectURL(f));
  }

  async function publicar() {
    if (!titulo.trim() || !cuerpo.trim()) { setError("Título y contenido son obligatorios"); return; }
    setError(""); setGuardando(true);
    try {
      await crearComunicado(titulo, cuerpo, imagen);
      onCreado();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Nuevo comunicado</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        <div className="form-pago">
          <div className="form-field">
            <label>Título</label>
            <input value={titulo} onChange={e => setTitulo(e.target.value)}
              placeholder="Ej. Corte de agua programado" />
          </div>
          <div className="form-field">
            <label>Contenido</label>
            <textarea
              className="comunicado-textarea"
              value={cuerpo}
              onChange={e => setCuerpo(e.target.value)}
              placeholder="Escribe aquí el comunicado completo…"
              rows={7}
            />
          </div>
          <div className="form-field">
            <label>Imagen (opcional)</label>
            <div className="upload-area" onClick={() => inputRef.current?.click()}>
              {preview
                ? <img src={preview} alt="Vista previa" className="preview-img" />
                : <div className="upload-placeholder">
                    <span className="upload-icon">🖼️</span>
                    <span>{imagen ? imagen.name : "Toca para adjuntar imagen"}</span>
                    <span className="muted small">PNG, JPG, WEBP o GIF</span>
                  </div>
              }
            </div>
            <input ref={inputRef} type="file" accept="image/*"
              style={{ display: "none" }} onChange={onArchivo} />
          </div>

          {error && <div className="error">{error}</div>}

          <button className="cuota-btn-pagar full" onClick={publicar} disabled={guardando}>
            {guardando ? "Publicando…" : "Publicar comunicado"}
          </button>
        </div>
      </div>
    </div>
  );
}
