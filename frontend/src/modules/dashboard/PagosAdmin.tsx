import { useState, useEffect } from "react";
import { cuotasPendientesAdmin, revisarPago, generarCuotasManual, urlComprobante, type PagoAdminDTO } from "../../api/client";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";

export function PagosAdmin() {
  const [pagos, setPagos] = useState<PagoAdminDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState<string | null>(null);
  const [nota, setNota] = useState("");
  const [pagoDetalle, setPagoDetalle] = useState<PagoAdminDTO | null>(null);
  // Día 51 — niveles de plan: mismo criterio que CuotasResidente, mostrar
  // el mensaje real del backend (ej. "tu plan no incluye esta función")
  // en vez de dejar la pantalla vacía como si no hubiera nada pendiente.
  const [errorPlan, setErrorPlan] = useState("");

  useEffect(() => {
    cuotasPendientesAdmin().then(setPagos)
      .catch((e) => setErrorPlan(e?.message || "No se pudo cargar los pagos pendientes"))
      .finally(() => setCargando(false));
  }, []);

  async function revisar(pago: PagoAdminDTO, accion: "aprobar" | "rechazar") {
    if (accion === "rechazar" && !nota.trim()) {
      alert("Indicá el motivo del rechazo para que el residente sepa por qué.");
      return;
    }
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
  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;

  return (
    <div className="pagos-admin">
      <div className="dash-head">
        <h2>Revisión de pagos</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {pagos.length > 0 && <span className="pill amber big">{pagos.length} pendiente{pagos.length > 1 ? "s" : ""}</span>}
          <BotonGenerarCuotas />
        </div>
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

            {((pagoDetalle.comprobantes && pagoDetalle.comprobantes.length > 0)
              ? pagoDetalle.comprobantes
              : (pagoDetalle.comprobante_archivo ? [pagoDetalle.comprobante_archivo] : [])
            ).length > 0 && (
              <div className="comprobante-preview">
                <div className="sub">
                  {(pagoDetalle.comprobantes?.length ?? 1) > 1
                    ? `Comprobantes adjuntos (${pagoDetalle.comprobantes!.length})`
                    : "Comprobante adjunto"}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {(pagoDetalle.comprobantes && pagoDetalle.comprobantes.length > 0
                    ? pagoDetalle.comprobantes
                    : [pagoDetalle.comprobante_archivo!]
                  ).map((archivo, i) => (
                    archivo.endsWith(".pdf") ? (
                      <a key={i}
                        href={urlComprobante(archivo)}
                        target="_blank" rel="noreferrer"
                        className="cuota-btn-pagar"
                        style={{ display: "inline-block", textDecoration: "none", marginBottom: 12 }}
                      >
                        Ver PDF {i + 1} →
                      </a>
                    ) : (
                      <img
                        key={i}
                        src={urlComprobante(archivo)}
                        alt={`Comprobante ${i + 1}`}
                        className="comprobante-img"
                        style={{ maxWidth: 220, cursor: "pointer" }}
                        onClick={() => window.open(urlComprobante(archivo), "_blank")}
                      />
                    )
                  ))}
                </div>
              </div>
            )}

            <div className="form-field" style={{ marginTop: 12 }}>
              <label>Nota para el residente <span className="muted small">(obligatoria si rechazás)</span></label>
              <input
                type="text" placeholder="Ej. El comprobante no es legible / el monto no coincide"
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

function BotonGenerarCuotas() {
  const [estado, setEstado] = useState<"idle" | "generando" | "ok">("idle");
  const [msg, setMsg] = useState("");

  async function generar() {
    if (!confirm("¿Generar las cuotas del mes en curso para todas las cuentas que aún no la tengan?")) return;
    setEstado("generando");
    try {
      const r = await generarCuotasManual();
      setMsg(r.generadas > 0 ? `${r.generadas} cuota(s) generada(s)` : "Ya estaban todas generadas");
      setEstado("ok");
      setTimeout(() => setEstado("idle"), 4000);
    } catch (e) {
      alert((e as Error).message);
      setEstado("idle");
    }
  }

  return (
    <button className="ghost mini" onClick={generar} disabled={estado === "generando"}>
      {estado === "generando" ? "Generando…" : estado === "ok" ? `✓ ${msg}` : "⟳ Generar cuotas del mes"}
    </button>
  );
}
