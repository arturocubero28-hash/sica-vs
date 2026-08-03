import { useState, useEffect, useRef } from "react";
import { misCuotas, subirComprobante, subirComprobanteAbono, urlReciboPDF,
  type CuotaDTO, type AbonoArregloDTO, type PagoHistorialDTO } from "../../api/client";
import { AlertTriangle, Paperclip, Handshake, Receipt } from "lucide-react";
import { comprimirImagenWebp } from "../../utils/comprimirImagen";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";

const estadoLabel: Record<string, string> = {
  pendiente: "Pendiente", en_revision: "En revisión", pagada: "Pagada", vencida: "Vencida",
};
const estadoColor: Record<string, string> = {
  pendiente: "amber", en_revision: "amber", pagada: "green", vencida: "red",
};

export function CuotasResidente() {
  const [cuotas, setCuotas] = useState<CuotaDTO[]>([]);
  const [arreglo, setArreglo] = useState<{ id: string; saldo_pendiente: number; abonos: AbonoArregloDTO[] } | null>(null);
  const [historial, setHistorial] = useState<PagoHistorialDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [tab, setTab] = useState<"pendientes" | "historial">("pendientes");
  const [cuotaPago, setCuotaPago] = useState<CuotaDTO | null>(null);
  const [abonoPago, setAbonoPago] = useState<AbonoArregloDTO | null>(null);
  // Día 51 — niveles de plan: si la residencial no tiene esta función
  // incluida, el backend responde con un mensaje claro (402) en vez de
  // la lista de cuotas. Antes el .catch(() => {}) se lo comía en
  // silencio, dejando la pantalla vacía como si no hubiera cuotas
  // pendientes — engañoso, parece que está todo pagado cuando en
  // realidad la función ni está disponible.
  const [errorPlan, setErrorPlan] = useState("");

  function recargar() {
    misCuotas().then(d => {
      setCuotas(d.cuotas); setArreglo(d.arreglo); setHistorial(d.historial || []);
    }).catch(() => {});
  }
  useEffect(() => {
    misCuotas().then(d => {
      setCuotas(d.cuotas); setArreglo(d.arreglo); setHistorial(d.historial || []);
    }).catch((e) => setErrorPlan(e?.message || "No se pudo cargar tus cuotas"))
      .finally(() => setCargando(false));
  }, []);

  function onPagoSubido() {
    setCuotaPago(null);
    setAbonoPago(null);
    recargar();
  }

  if (cargando) return <p className="muted">Cargando cuotas…</p>;
  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;

  const pendientes = cuotas.filter(c => c.estado !== "pagada" && c.estado !== "en_arreglo");
  const abonosPend = arreglo ? arreglo.abonos.filter(a => a.estado !== "pagado") : [];
  const totalPend = pendientes.length + abonosPend.length;
  // Orden cronológico obligatorio (Día 36): solo se puede pagar la cuota
  // pendiente más antigua primero. pendientes viene ordenado desc. desde
  // el backend, así que el período más antiguo es el mínimo del array.
  const periodoMasAntiguoPendiente = pendientes.length > 0
    ? pendientes.reduce((min, c) => c.periodo < min ? c.periodo : min, pendientes[0].periodo)
    : null;

  return (
    <div className="cuotas-wrap">
      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "pendientes" ? "on" : ""}`} onClick={() => setTab("pendientes")}>
          Cuotas pendientes ({totalPend})
        </button>
        <button className={`hist-tab ${tab === "historial" ? "on" : ""}`} onClick={() => setTab("historial")}>
          Historial de pagos ({historial.length})
        </button>
      </div>

      {tab === "pendientes" && (
        <>
          {totalPend === 0 && (
            <div className="cuota-vacia">
              <div className="cuota-vacia-icon">✓</div>
              <p>No tenés cuotas pendientes.</p>
              <p className="muted small">Las cuotas se generan automáticamente el 1° de cada mes.</p>
            </div>
          )}

          {/* Cuotas del arreglo de pago, agrupadas */}
          {arreglo && abonosPend.length > 0 && (
            <section>
              <h3 className="cuotas-seccion"><Handshake size={18} /> Arreglo de pago</h3>
              <p className="muted small" style={{ margin: "0 0 10px" }}>
                Saldo pendiente: <b>L {arreglo.saldo_pendiente.toFixed(2)}</b>. Pagá cada abono subiendo tu comprobante.
              </p>
              <div className="cuota-list">
                {abonosPend.map(a => (
                  <AbonoCard key={a.abono_id} abono={a} onPagar={() => setAbonoPago(a)} />
                ))}
              </div>
            </section>
          )}

          {/* Cuotas de mensualidad normales, agrupadas */}
          {pendientes.length > 0 && (
            <section>
              <h3 className="cuotas-seccion" style={{ marginTop: (arreglo && abonosPend.length > 0) ? 24 : 0 }}>
                Cuotas de mensualidad
              </h3>
              <p className="muted small" style={{ margin: "0 0 10px" }}>
                Pagá en orden: primero la más antigua pendiente.
              </p>
              <div className="cuota-list">
                {pendientes.map(c => (
                  <CuotaCard key={c.id} cuota={c} onPagar={() => setCuotaPago(c)}
                    esLaMasAntigua={c.periodo === periodoMasAntiguoPendiente} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {tab === "historial" && (
        <>
          {historial.length === 0 ? (
            <div className="cuota-vacia">
              <div className="cuota-vacia-icon">🧾</div>
              <p>Todavía no hay pagos registrados.</p>
              <p className="muted small">Acá vas a ver todos tus pagos aprobados con su recibo.</p>
            </div>
          ) : (
            <div className="cuota-list">
              {historial.map(p => <PagoHistorialCard key={p.id} pago={p} />)}
            </div>
          )}
        </>
      )}

      {cuotaPago && (
        <FormPago cuota={cuotaPago} onCerrar={() => setCuotaPago(null)} onExito={onPagoSubido} />
      )}
      {abonoPago && (
        <FormPagoAbono abono={abonoPago} onCerrar={() => setAbonoPago(null)} onExito={onPagoSubido} />
      )}
    </div>
  );
}

function PagoHistorialCard({ pago }: { pago: PagoHistorialDTO }) {
  const metodoLabel: Record<string, string> = {
    efectivo: "Efectivo", tarjeta_pos: "Tarjeta POS", transferencia: "Transferencia", linea: "En línea",
  };
  return (
    <div className="cuota-card">
      <div className="cuota-card-top">
        <div>
          <div className="cuota-mes">{pago.etiqueta}</div>
          <div className="cuota-monto">L {pago.monto.toFixed(2)}</div>
        </div>
        <span className="pill green">Pagado</span>
      </div>
      <div className="cuota-vence">
        {new Date(pago.fecha).toLocaleDateString("es-HN")} · {metodoLabel[pago.metodo] || pago.metodo}
      </div>
      <a className="cuota-btn-recibo" href={urlReciboPDF(pago.id)} target="_blank" rel="noreferrer">
        <Receipt size={16} /> Ver recibo{pago.numero_recibo ? ` REC-${String(pago.numero_recibo).padStart(6, "0")}` : ""}
      </a>
    </div>
  );
}

function AbonoCard({ abono, onPagar }: { abono: AbonoArregloDTO; onPagar: () => void }) {
  const vencido = abono.estado === "vencido" ||
    (new Date(abono.fecha_pactada) < new Date() && abono.estado === "pendiente");
  return (
    <div className={`cuota-card ${vencido ? "vencida" : ""}`}>
      <div className="cuota-card-top">
        <div>
          <div className="cuota-mes">Abono {abono.numero} de {abono.total_abonos}</div>
          <div className="cuota-monto">L {abono.monto.toFixed(2)}</div>
        </div>
        <span className={`pill ${vencido ? "red" : "amber"}`}>{vencido ? "Vencido" : "Pendiente"}</span>
      </div>
      <div className="cuota-vence">
        Vence: {new Date(abono.fecha_pactada).toLocaleDateString("es-HN")}
      </div>
      <button className="cuota-btn-pagar" onClick={onPagar}>Subir comprobante de pago</button>
    </div>
  );
}

function CuotaCard({ cuota, onPagar, esLaMasAntigua = true }: {
  cuota: CuotaDTO; onPagar?: () => void; esLaMasAntigua?: boolean;
}) {
  const vencida = new Date(cuota.fecha_vencimiento) < new Date() && cuota.estado !== "pagada";
  const puedeSubir = (cuota.estado === "pendiente" || cuota.estado === "vencida") && !cuota.en_revision;
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
        {vencida && cuota.estado !== "en_revision" && <span className="mora-tag"><AlertTriangle size={16} /> En mora</span>}
      </div>
      {cuota.pago_rechazado && (cuota.estado === "pendiente" || cuota.estado === "vencida") && (
        <div className="cuota-rechazo">
          <b>Tu comprobante anterior fue rechazado.</b>
          {cuota.nota_rechazo ? <span> Motivo: {cuota.nota_rechazo}</span> : null}
          <span> Podés subir un nuevo comprobante.</span>
        </div>
      )}
      {puedeSubir && !esLaMasAntigua && (
        <div className="cuota-rechazo" style={{ background: "#eef2fb", borderColor: "#c7d3ef", color: "#2c4a8f" }}>
          Tenés una cuota más antigua sin pagar. Pagá esa primero.
        </div>
      )}
      {puedeSubir && onPagar && (
        <button className="cuota-btn-pagar" onClick={onPagar} disabled={!esLaMasAntigua}
          style={!esLaMasAntigua ? { opacity: 0.5, cursor: "not-allowed" } : undefined}>
          {cuota.pago_rechazado ? "Subir nuevo comprobante" : "Subir comprobante de pago"}
        </button>
      )}
      {(cuota.estado === "en_revision" || cuota.en_revision) && (
        <div className="cuota-revision">
          ⏳ <b>Comprobante recibido.</b> La administración lo está revisando.
          No necesitás subirlo de nuevo — te avisaremos cuando se apruebe.
        </div>
      )}
      {cuota.estado === "pagada" && (
        <div className="cuota-pagada-info">
          <div className="cuota-ok" style={{ marginBottom: cuota.pago ? 8 : 0 }}>
            ✓ Pago aprobado
            {cuota.pago?.revisado_en && (
              <span className="muted small"> · {new Date(cuota.pago.revisado_en).toLocaleDateString("es-HN")}</span>
            )}
          </div>
          {cuota.pago?.id && (
            <a className="cuota-btn-recibo" href={urlReciboPDF(cuota.pago.id)}
              target="_blank" rel="noreferrer">
              <Receipt size={16} /> Ver recibo
              {cuota.pago.numero_recibo ? ` REC-${String(cuota.pago.numero_recibo).padStart(6, "0")}` : ""}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function FormPago({ cuota, onCerrar, onExito }: {
  cuota: CuotaDTO; onCerrar: () => void; onExito: () => void;
}) {
  const [archivos, setArchivos] = useState<File[]>([]);
  const [previews, setPrevius] = useState<string[]>([]);
  const [monto, setMonto] = useState(String(cuota.monto));
  const [referencia, setReferencia] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function onArchivos(e: React.ChangeEvent<HTMLInputElement>) {
    const nuevos = Array.from(e.target.files || []);
    if (nuevos.length === 0) return;
    if (archivos.length + nuevos.length > 5) {
      setError("Máximo 5 comprobantes por pago");
      return;
    }
    setError("");
    const comprimidos = await Promise.all(nuevos.map(f => comprimirImagenWebp(f)));
    setArchivos(prev => [...prev, ...comprimidos]);
    setPrevius(prev => [...prev, ...comprimidos.map(f =>
      f.type.startsWith("image/") ? URL.createObjectURL(f) : "")]);
  }

  function quitarArchivo(i: number) {
    setArchivos(prev => prev.filter((_, idx) => idx !== i));
    setPrevius(prev => prev.filter((_, idx) => idx !== i));
  }

  async function enviar() {
    if (archivos.length === 0) { setError("Adjuntá al menos un comprobante"); return; }
    const m = parseFloat(monto);
    if (!m || m <= 0) { setError("Ingresá un monto válido"); return; }
    setError(""); setSubiendo(true);
    try {
      await subirComprobante(cuota.id, archivos, m, referencia);
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
            <label>Comprobante(s) — foto o PDF</label>
            <p className="muted small" style={{ marginBottom: 6 }}>
              ¿Depositaste en varias partes? Adjuntá todos los comprobantes acá — la
              administración los revisa juntos y aprueba el pago completo.
            </p>

            {archivos.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                {archivos.map((a, i) => (
                  <div key={i} style={{ position: "relative", width: 72, height: 72 }}>
                    {previews[i]
                      ? <img src={previews[i]} alt={a.name} className="preview-img"
                          style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8 }} />
                      : <div style={{ width: 72, height: 72, borderRadius: 8, background: "var(--fondo)",
                          border: "1px solid var(--borde)", display: "flex", alignItems: "center",
                          justifyContent: "center", fontSize: 10, textAlign: "center", padding: 4 }}>
                          {a.name}
                        </div>}
                    <button onClick={() => quitarArchivo(i)}
                      style={{ position: "absolute", top: -6, right: -6, width: 20, height: 20,
                        borderRadius: "50%", background: "#c0392b", color: "#fff", border: "none",
                        fontSize: 12, cursor: "pointer", lineHeight: 1 }}>
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}

            {archivos.length < 5 && (
              <div className="upload-area" onClick={() => inputRef.current?.click()}>
                <div className="upload-placeholder">
                  <span className="upload-icon"><Paperclip size={16} /></span>
                  <span>{archivos.length > 0 ? "Agregar otro comprobante" : "Toca para adjuntar"}</span>
                  <span className="muted small">PNG, JPG o PDF · hasta 5</span>
                </div>
              </div>
            )}
            <input ref={inputRef} type="file" accept="image/*,.pdf" multiple
              style={{ display: "none" }} onChange={onArchivos} />
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

function FormPagoAbono({ abono, onCerrar, onExito }: {
  abono: AbonoArregloDTO; onCerrar: () => void; onExito: () => void;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [monto, setMonto] = useState(String(abono.monto));
  const [referencia, setReferencia] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    comprimirImagenWebp(f).then(comprimido => {
      setArchivo(comprimido);
      setPreview(comprimido.type.startsWith("image/") ? URL.createObjectURL(comprimido) : null);
    });
  }

  async function enviar() {
    if (subiendo) return;
    if (!archivo) { setError("Seleccioná el comprobante"); return; }
    const m = parseFloat(monto);
    if (!m || m <= 0) { setError("Ingresá un monto válido"); return; }
    setError(""); setSubiendo(true);
    try {
      await subirComprobanteAbono(abono.abono_id, archivo, m, referencia);
      onExito();
    } catch (e) { setError((e as Error).message); }
    finally { setSubiendo(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-pago">
          <div className="modal-pago-header">
            <h3>Pagar abono {abono.numero} de {abono.total_abonos}</h3>
            <button className="ghost mini" onClick={onCerrar}>✕</button>
          </div>
          <p className="muted small">Monto del abono: L {abono.monto.toFixed(2)}</p>

          <label className="campo-label">Monto a pagar</label>
          <input type="number" value={monto} onChange={e => setMonto(e.target.value)} />

          <label className="campo-label">Referencia (opcional)</label>
          <input type="text" value={referencia} onChange={e => setReferencia(e.target.value)}
            placeholder="N° de transferencia, banco, etc." />

          <div className="dropzone" onClick={() => inputRef.current?.click()}>
            {preview
              ? <img src={preview} alt="comprobante" className="dropzone-preview" />
              : <div className="dropzone-empty">
                  <Paperclip size={20} />
                  <span>{archivo ? archivo.name : "Tocá para adjuntar el comprobante"}</span>
                </div>}
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
