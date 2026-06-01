import { useState, useEffect, useRef } from "react";
import { misCuotas, subirComprobante, detalleCuota, type CuotaDTO } from "../../api/client";

const estadoLabel: Record<string, string> = {
  pendiente: "Pendiente", en_revision: "En revisión", pagada: "Pagada", vencida: "Vencida",
};
const estadoColor: Record<string, string> = {
  pendiente: "amber", en_revision: "amber", pagada: "green", vencida: "red",
};

export function CuotasResidente() {
  const [cuotas, setCuotas] = useState<CuotaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [cuotaPago, setCuotaPago] = useState<CuotaDTO | null>(null);

  useEffect(() => {
    misCuotas().then(setCuotas).catch(() => {}).finally(() => setCargando(false));
  }, []);

  function onPagoSubido() {
    setCuotaPago(null);
    misCuotas().then(setCuotas).catch(() => {});
  }

  if (cargando) return <p className="muted">Cargando cuotas…</p>;

  const pendientes = cuotas.filter(c => c.estado !== "pagada");
  const pagadas = cuotas.filter(c => c.estado === "pagada");

  return (
    <div className="cuotas-wrap">
      {pendientes.length === 0 && pagadas.length === 0 && (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon">✓</div>
          <p>No tenés cuotas registradas.</p>
          <p className="muted small">Las cuotas se generan automáticamente el 1° de cada mes.</p>
        </div>
      )}

      {pendientes.length > 0 && (
        <section>
          <h3 className="cuotas-seccion">Cuotas pendientes</h3>
          <div className="cuota-list">
            {pendientes.map(c => (
              <CuotaCard key={c.id} cuota={c} onPagar={() => setCuotaPago(c)} />
            ))}
          </div>
        </section>
      )}

      {pagadas.length > 0 && (
        <section>
          <h3 className="cuotas-seccion" style={{ marginTop: 24 }}>Historial de pagos</h3>
          <div className="cuota-list">
            {pagadas.map(c => (
              <CuotaCard key={c.id} cuota={c} />
            ))}
          </div>
        </section>
      )}

      {cuotaPago && (
        <FormPago cuota={cuotaPago} onCerrar={() => setCuotaPago(null)} onExito={onPagoSubido} />
      )}
    </div>
  );
}

function CuotaCard({ cuota, onPagar }: { cuota: CuotaDTO; onPagar?: () => void }) {
  const vencida = new Date(cuota.fecha_vencimiento) < new Date() && cuota.estado !== "pagada";
  return (
    <div className={`cuota-card ${vencida ? "vencida" : ""}`}>
      <div className="cuota-card-top">
        <div>
          <div className="cuota-mes">{cuota.mes_label}</div>
          <div className="cuota-monto">L {cuota.monto.toFixed(2)}</div>
        </div>
        <span className={`pill ${estadoColor[cuota.estado] || ""}`}>
          {estadoLabel[cuota.estado] || cuota.estado}
        </span>
      </div>
      <div className="cuota-vence">
        Vence: {new Date(cuota.fecha_vencimiento).toLocaleDateString("es-HN")}
        {vencida && cuota.estado !== "en_revision" && <span className="mora-tag">⚠ En mora</span>}
      </div>
      {cuota.pago_rechazado && (cuota.estado === "pendiente" || cuota.estado === "vencida") && (
        <div className="cuota-rechazo">
          <b>Tu comprobante anterior fue rechazado.</b>
          {cuota.nota_rechazo ? <span> Motivo: {cuota.nota_rechazo}</span> : null}
          <span> Podés subir un nuevo comprobante.</span>
        </div>
      )}
      {(cuota.estado === "pendiente" || cuota.estado === "vencida") && onPagar && (
        <button className="cuota-btn-pagar" onClick={onPagar}>
          {cuota.pago_rechazado ? "Subir nuevo comprobante" : "Subir comprobante de pago"}
        </button>
      )}
      {cuota.estado === "en_revision" && (
        <div className="cuota-revision">
          Tu comprobante está siendo revisado por la administración. Te notificaremos pronto.
        </div>
      )}
      {cuota.estado === "pagada" && (
        <div className="cuota-ok">✓ Pago aprobado por la administración</div>
      )}
    </div>
  );
}

function FormPago({ cuota, onCerrar, onExito }: {
  cuota: CuotaDTO; onCerrar: () => void; onExito: () => void;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [monto, setMonto] = useState(String(cuota.monto));
  const [referencia, setReferencia] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setArchivo(f);
    if (f.type.startsWith("image/")) {
      const url = URL.createObjectURL(f);
      setPreview(url);
    } else {
      setPreview(null);
    }
  }

  async function enviar() {
    if (!archivo) { setError("Seleccioná el comprobante"); return; }
    const m = parseFloat(monto);
    if (!m || m <= 0) { setError("Ingresá un monto válido"); return; }
    setError(""); setSubiendo(true);
    try {
      await subirComprobante(cuota.id, archivo, m, referencia);
      onExito();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Pagar cuota — {cuota.mes_label}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        <div className="form-pago">
          <div className="form-field">
            <label>Monto transferido (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)}
              placeholder={String(cuota.monto)} step="0.01" />
          </div>
          <div className="form-field">
            <label>Referencia / N° de transacción</label>
            <input type="text" value={referencia} onChange={e => setReferencia(e.target.value)}
              placeholder="Ej. TRN-2026-001234" />
          </div>
          <div className="form-field">
            <label>Comprobante (foto o PDF)</label>
            <div className="upload-area" onClick={() => inputRef.current?.click()}>
              {preview
                ? <img src={preview} alt="Comprobante" className="preview-img" />
                : <div className="upload-placeholder">
                    <span className="upload-icon">📎</span>
                    <span>{archivo ? archivo.name : "Toca para adjuntar"}</span>
                    <span className="muted small">PNG, JPG o PDF</span>
                  </div>
              }
            </div>
            <input ref={inputRef} type="file" accept="image/*,.pdf"
              style={{ display: "none" }} onChange={onArchivo} />
          </div>

          {error && <div className="error">{error}</div>}

          <button className="cuota-btn-pagar full" onClick={enviar} disabled={subiendo}>
            {subiendo ? "Subiendo…" : "Enviar comprobante"}
          </button>
          <p className="muted small" style={{ textAlign: "center" }}>
            La administración revisará tu comprobante y aprobará el pago.
          </p>
        </div>
      </div>
    </div>
  );
}
