import { useState, useEffect } from "react";
import {
  listarArreglos, detalleArreglo, crearArreglo, cobrarAbono, cancelarArreglo,
  listarCuentas, cuotasPendientesCuenta,
  type ArregloDTO, type Cuenta, type CuotaDTO,
} from "../../api/client";

function L(n: number) {
  return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const ESTADO_PILL: Record<string, string> = {
  activo: "green", completado: "", incumplido: "red", cancelado: "amber",
};
const ESTADO_LABEL: Record<string, string> = {
  activo: "Activo", completado: "Completado", incumplido: "Incumplido", cancelado: "Cancelado",
};

export function ArreglosPanel() {
  const [tab, setTab] = useState<"lista" | "crear">("lista");
  const [filtro, setFiltro] = useState("");
  const [arreglos, setArreglos] = useState<ArregloDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [detalle, setDetalle] = useState<ArregloDTO | null>(null);

  function cargar() {
    setCargando(true);
    listarArreglos(filtro || undefined).then(setArreglos).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, [filtro]);

  return (
    <div className="reporteria">
      <div className="historial-tabs" style={{ marginBottom: 14 }}>
        <button className={`htab ${tab === "lista" ? "activo" : ""}`} onClick={() => setTab("lista")}>
          Arreglos
        </button>
        <button className={`htab ${tab === "crear" ? "activo" : ""}`} onClick={() => setTab("crear")}>
          + Nuevo arreglo
        </button>
      </div>

      {tab === "crear" ? (
        <CrearArreglo onCreado={() => { setTab("lista"); cargar(); }} />
      ) : (
        <>
          <div className="dash-header-pro">
            <div>
              <h2 className="dash-titulo">Arreglos de pago</h2>
              <span className="muted">Planes de pago para cuentas morosas</span>
            </div>
            <select className="periodo-select" value={filtro} onChange={e => setFiltro(e.target.value)}>
              <option value="">Todos</option>
              <option value="activo">Activos</option>
              <option value="completado">Completados</option>
              <option value="incumplido">Incumplidos</option>
              <option value="cancelado">Cancelados</option>
            </select>
          </div>

          {cargando ? <p className="muted">Cargando…</p>
            : arreglos.length === 0 ? (
              <div className="dash-card"><p className="muted">No hay arreglos {filtro ? `en estado "${filtro}"` : ""}.</p></div>
            ) : (
              <div className="mora-lista">
                {arreglos.map(a => (
                  <div key={a.id} className="mora-casa">
                    <div className="mora-casa-head" onClick={() => detalleArreglo(a.id).then(setDetalle)}>
                      <div className="mora-casa-info">
                        <span className="mora-unidad">{a.unidad}</span>
                        <span className="muted small">{a.titular}</span>
                      </div>
                      <div className="mora-casa-resumen">
                        <span className={`pill ${ESTADO_PILL[a.estado]}`}>{ESTADO_LABEL[a.estado]}</span>
                        <span className="muted small">{a.abonos_pagados}/{a.num_abonos} abonos</span>
                        <span className="mora-total">{L(a.saldo_pendiente)}</span>
                        <button className="mini">Ver →</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </>
      )}

      {detalle && (
        <DetalleArreglo
          arreglo={detalle}
          onCerrar={() => setDetalle(null)}
          onCambio={(a) => { setDetalle(a); cargar(); }}
        />
      )}
    </div>
  );
}

// ─── Crear arreglo ───────────────────────────────────────────────────────────
function CrearArreglo({ onCreado }: { onCreado: () => void }) {
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [cuentaId, setCuentaId] = useState("");
  const [cuotas, setCuotas] = useState<CuotaDTO[]>([]);
  const [seleccionadas, setSeleccionadas] = useState<string[]>([]);
  const [abonoInicial, setAbonoInicial] = useState(0);
  const [numAbonos, setNumAbonos] = useState(3);
  const [diasGracia, setDiasGracia] = useState(15);
  const [primerVenc, setPrimerVenc] = useState("");
  const [nota, setNota] = useState("");
  const [msg, setMsg] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => { listarCuentas().then(setCuentas).catch(() => {}); }, []);

  useEffect(() => {
    if (cuentaId) {
      cuotasPendientesCuenta(cuentaId).then(c => { setCuotas(c); setSeleccionadas([]); }).catch(() => setCuotas([]));
    } else { setCuotas([]); }
  }, [cuentaId]);

  function toggleCuota(id: string) {
    setSeleccionadas(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  }

  // Cálculos en vivo
  const deudaTotal = cuotas.filter(c => seleccionadas.includes(c.id)).reduce((s, c) => s + c.monto, 0);
  const saldoFinanciado = Math.max(0, deudaTotal - abonoInicial);
  const montoPorAbono = numAbonos > 0 ? saldoFinanciado / numAbonos : 0;

  async function crear() {
    setMsg("");
    if (!cuentaId) return setMsg("Seleccioná una cuenta");
    if (seleccionadas.length === 0) return setMsg("Seleccioná al menos una cuota");
    if (saldoFinanciado <= 0) return setMsg("El abono inicial no puede cubrir toda la deuda (cobrá las cuotas directamente)");
    setGuardando(true);
    try {
      await crearArreglo({
        cuenta_id: cuentaId, cuotas: seleccionadas, abono_inicial: abonoInicial,
        num_abonos: numAbonos, dias_gracia: diasGracia,
        primer_vencimiento: primerVenc || undefined, nota,
      });
      onCreado();
    } catch (e) { setMsg((e as Error).message); }
    finally { setGuardando(false); }
  }

  return (
    <div className="dash-card">
      <h3>Crear nuevo arreglo de pago</h3>
      <p className="muted small">Negociá un plan de pago para una cuenta morosa. Las cuotas incluidas
        dejan de generar mora y el acceso se reactiva mientras el arreglo esté al día.</p>

      <div className="campo-grupo" style={{ marginTop: 12 }}>
        <label className="campo-label">1. Cuenta morosa</label>
        <select className="periodo-select" value={cuentaId} onChange={e => setCuentaId(e.target.value)} style={{ width: "100%" }}>
          <option value="">Seleccionar cuenta…</option>
          {cuentas.map(c => (
            <option key={c.id} value={c.id}>
              {c.identificador || c.apartamento || "Cuenta"} — {c.titular?.nombre || "sin titular"}
            </option>
          ))}
        </select>
      </div>

      {cuentaId && (
        <div className="campo-grupo" style={{ marginTop: 14 }}>
          <label className="campo-label">2. Cuotas a incluir en el arreglo</label>
          {cuotas.length === 0 ? (
            <p className="muted small">Esta cuenta no tiene cuotas pendientes elegibles.</p>
          ) : (
            <div className="cuotas-check-list">
              {cuotas.map(c => (
                <label key={c.id} className="cuota-check">
                  <input type="checkbox" checked={seleccionadas.includes(c.id)} onChange={() => toggleCuota(c.id)} />
                  <span>{c.mes_label}</span>
                  <span className="muted small">{L(c.monto)}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {seleccionadas.length > 0 && (
        <>
          <div className="campo-grupo" style={{ marginTop: 14 }}>
            <label className="campo-label">3. Condiciones del plan</label>
            <div className="row">
              <div style={{ flex: 1 }}>
                <span className="muted small">Abono inicial (prima)</span>
                <input type="number" min={0} value={abonoInicial}
                  onChange={e => setAbonoInicial(Number(e.target.value))} />
              </div>
              <div style={{ flex: 1 }}>
                <span className="muted small">Número de abonos</span>
                <input type="number" min={1} max={36} value={numAbonos}
                  onChange={e => setNumAbonos(Number(e.target.value))} />
              </div>
            </div>
            <div className="row">
              <div style={{ flex: 1 }}>
                <span className="muted small">Días de gracia por abono</span>
                <input type="number" min={1} max={90} value={diasGracia}
                  onChange={e => setDiasGracia(Number(e.target.value))} />
              </div>
              <div style={{ flex: 1 }}>
                <span className="muted small">Primer vencimiento (opcional)</span>
                <input type="date" value={primerVenc} onChange={e => setPrimerVenc(e.target.value)} />
              </div>
            </div>
            <input placeholder="Nota / observación (opcional)" value={nota}
              onChange={e => setNota(e.target.value)} style={{ marginTop: 8 }} />
          </div>

          {/* Resumen financiero en vivo */}
          <div className="arreglo-resumen">
            <div className="arreglo-resumen-row"><span>Deuda total</span><b>{L(deudaTotal)}</b></div>
            <div className="arreglo-resumen-row"><span>Abono inicial</span><b>− {L(abonoInicial)}</b></div>
            <div className="arreglo-resumen-row total"><span>Saldo a financiar</span><b>{L(saldoFinanciado)}</b></div>
            <div className="arreglo-resumen-row destacado">
              <span>{numAbonos} abonos de</span><b>{L(montoPorAbono)}</b>
            </div>
            <p className="muted small" style={{ marginTop: 6 }}>
              Sin recargo: solo se difiere la deuda. El último abono ajusta el redondeo.
            </p>
          </div>
        </>
      )}

      {msg && <div className="error" style={{ marginTop: 10 }}>{msg}</div>}
      <button className="agregar-miembro-btn" onClick={crear} disabled={guardando} style={{ marginTop: 14 }}>
        {guardando ? "Creando…" : "Crear arreglo de pago"}
      </button>
    </div>
  );
}

// ─── Detalle del arreglo (con cobro de abonos) ───────────────────────────────
function DetalleArreglo({ arreglo, onCerrar, onCambio }: {
  arreglo: ArregloDTO; onCerrar: () => void; onCambio: (a: ArregloDTO) => void;
}) {
  const [cobrando, setCobrando] = useState<string | null>(null);
  const [metodo, setMetodo] = useState("efectivo");
  const [msg, setMsg] = useState("");

  async function cobrar(abonoId: string) {
    setCobrando(abonoId); setMsg("");
    try {
      const actualizado = await cobrarAbono(arreglo.id, abonoId, metodo);
      onCambio(actualizado);
    } catch (e) { setMsg((e as Error).message); }
    finally { setCobrando(null); }
  }

  async function cancelar() {
    const motivo = prompt("Motivo de la cancelación del arreglo:");
    if (motivo === null) return;
    try {
      const actualizado = await cancelarArreglo(arreglo.id, motivo);
      onCambio(actualizado);
    } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-head">
          <h3>Arreglo — {arreglo.unidad}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        <div className="arreglo-resumen" style={{ marginTop: 4 }}>
          <div className="arreglo-resumen-row"><span>Titular</span><b>{arreglo.titular}</b></div>
          <div className="arreglo-resumen-row"><span>Estado</span>
            <b><span className={`pill ${ESTADO_PILL[arreglo.estado]}`}>{ESTADO_LABEL[arreglo.estado]}</span></b></div>
          <div className="arreglo-resumen-row"><span>Deuda total</span><b>{L(arreglo.deuda_total)}</b></div>
          <div className="arreglo-resumen-row"><span>Abonado</span><b>{L(arreglo.total_abonado)}</b></div>
          <div className="arreglo-resumen-row total"><span>Saldo pendiente</span><b>{L(arreglo.saldo_pendiente)}</b></div>
        </div>

        {arreglo.meses_incluidos && arreglo.meses_incluidos.length > 0 && (
          <p className="muted small" style={{ marginTop: 8 }}>
            Meses incluidos: {arreglo.meses_incluidos.map(m => m.mes_label).join(", ")}
          </p>
        )}

        {arreglo.estado === "incumplido" && (
          <div className="nota" style={{ background: "#fff0f0", borderColor: "#f5a3a3", marginTop: 8 }}>
            ⚠ {arreglo.motivo_cierre}. Las cuotas volvieron a mora y la cuenta fue bloqueada.
            Lo abonado ({L(arreglo.total_abonado)}) quedó acreditado.
          </div>
        )}

        {/* Calendario de abonos */}
        <div className="sub" style={{ marginTop: 12 }}>Calendario de abonos</div>
        {arreglo.estado === "activo" && (
          <div className="row" style={{ alignItems: "center", margin: "6px 0" }}>
            <span className="muted small">Cobrar con:</span>
            <select className="periodo-select" value={metodo} onChange={e => setMetodo(e.target.value)}>
              <option value="efectivo">Efectivo</option>
              <option value="tarjeta_pos">Tarjeta POS</option>
            </select>
          </div>
        )}
        <div className="scroll-x">
          <table className="data">
            <thead><tr><th>#</th><th>Vence</th><th>Monto</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {(arreglo.abonos || []).map(ab => (
                <tr key={ab.id}>
                  <td>{ab.numero}</td>
                  <td className="small">{new Date(ab.fecha_pactada).toLocaleDateString("es-HN")}</td>
                  <td>{L(ab.monto)}</td>
                  <td>
                    {ab.estado === "pagado" ? <span className="pill green">Pagado</span>
                      : ab.estado === "vencido" ? <span className="pill red">Vencido</span>
                      : <span className="pill amber">Pendiente</span>}
                  </td>
                  <td>
                    {arreglo.estado === "activo" && ab.estado !== "pagado" && (
                      <button className="mini" onClick={() => cobrar(ab.id)} disabled={cobrando === ab.id}>
                        {cobrando === ab.id ? "…" : "Cobrar"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {msg && <div className="error" style={{ marginTop: 8 }}>{msg}</div>}

        {arreglo.estado === "activo" && (
          <button className="ghost mini" style={{ marginTop: 12, color: "#c81e1e" }} onClick={cancelar}>
            Cancelar arreglo
          </button>
        )}
      </div>
    </div>
  );
}
