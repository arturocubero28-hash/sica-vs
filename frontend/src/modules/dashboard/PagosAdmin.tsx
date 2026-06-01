import { useState, useEffect } from "react";
import { cuotasPendientesAdmin, revisarPago, type PagoAdminDTO } from "../../api/client";

export function PagosAdmin() {
  const [pagos, setPagos] = useState<PagoAdminDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState<string | null>(null);
  const [nota, setNota] = useState("");
  const [pagoDetalle, setPagoDetalle] = useState<PagoAdminDTO | null>(null);

  useEffect(() => {
    cuotasPendientesAdmin().then(setPagos).catch(() => {}).finally(() => setCargando(false));
  }, []);

  async function revisar(pago: PagoAdminDTO, accion: "aprobar" | "rechazar") {
    setProcesando(pago.id);
    try {
      await revisarPago(pago.id, accion, nota);
      setPagos(prev => prev.filter(p => p.id !== pago.id));
      setPagoDetalle(null);
      setNota("");
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setProcesando(null);
    }
  }

  if (cargando) return <p className="muted">Cargando pagos pendientes…</p>;

  return (
    <div className="pagos-admin">
      <div className="dash-head">
        <h2>Revisión de pagos</h2>
        {pagos.length > 0 && <span className="pill amber big">{pagos.length} pendiente{pagos.length > 1 ? "s" : ""}</span>}
      </div>

      {pagos.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon">✓</div>
          <p>No hay comprobantes pendientes de revisión.</p>
        </div>
      ) : (
        <div className="pagos-list">
          {pagos.map(p => (
            <div key={p.id} className="pago-card" onClick={() => { setPagoDetalle(p); setNota(""); }}>
              <div className="pago-card-top">
                <div>
                  <div className="pago-unidad">{p.unidad}</div>
                  <div className="muted small">{p.mes_label}</div>
                </div>
                <div className="pago-monto">L {p.monto.toFixed(2)}</div>
              </div>
              {p.referencia && <div className="muted small">Ref: {p.referencia}</div>}
              <div className="muted small">
                Recibido: {new Date(p.created_at).toLocaleString("es-HN")}
              </div>
              <div className="pago-ver">Ver comprobante →</div>
            </div>
          ))}
        </div>
      )}

      {pagoDetalle && (
        <div className="modal" onClick={() => setPagoDetalle(null)}>
          <div className="modal-body" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Comprobante — {pagoDetalle.unidad}</h3>
              <button className="ghost mini" onClick={() => setPagoDetalle(null)}>✕</button>
            </div>

            <div className="detalle-grid" style={{ marginBottom: 14 }}>
              <Dato label="Cuota" valor={pagoDetalle.mes_label} />
              <Dato label="Monto declarado" valor={`L ${pagoDetalle.monto.toFixed(2)}`} />
              {pagoDetalle.referencia && <Dato label="Referencia" valor={pagoDetalle.referencia} />}
              <Dato label="Recibido" valor={new Date(pagoDetalle.created_at).toLocaleString("es-HN")} />
            </div>

            {pagoDetalle.comprobante_archivo && (
              <div className="comprobante-preview">
                <div className="sub">Comprobante adjunto</div>
                {pagoDetalle.comprobante_archivo.endsWith(".pdf") ? (
                  <a
                    href={`/api/v1/cuotas/comprobantes/${pagoDetalle.comprobante_archivo}`}
                    target="_blank" rel="noreferrer"
                    className="cuota-btn-pagar"
                    style={{ display: "inline-block", textDecoration: "none", marginBottom: 12 }}
                  >
                    Ver PDF →
                  </a>
                ) : (
                  <img
                    src={`/api/v1/cuotas/comprobantes/${pagoDetalle.comprobante_archivo}`}
                    alt="Comprobante"
                    className="comprobante-img"
                  />
                )}
              </div>
            )}

            <div className="form-field" style={{ marginTop: 12 }}>
              <label>Nota para el residente (opcional)</label>
              <input
                type="text" placeholder="Ej. Monto correcto, aprobado"
                value={nota} onChange={e => setNota(e.target.value)}
              />
            </div>

            <div className="row-btns" style={{ marginTop: 16 }}>
              <button
                className="cuota-btn-pagar"
                style={{ background: "#1d8a4a" }}
                onClick={() => revisar(pagoDetalle, "aprobar")}
                disabled={procesando === pagoDetalle.id}
              >
                {procesando === pagoDetalle.id ? "Procesando…" : "✓ Aprobar pago"}
              </button>
              <button
                className="ghost"
                style={{ color: "#c81e1e", borderColor: "#f3c2c2" }}
                onClick={() => revisar(pagoDetalle, "rechazar")}
                disabled={procesando === pagoDetalle.id}
              >
                ✕ Rechazar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Dato({ label, valor }: { label: string; valor: string }) {
  return (
    <div className="dato">
      <span className="muted small">{label}</span>
      <b>{valor}</b>
    </div>
  );
}
