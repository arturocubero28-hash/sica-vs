import { useState, useEffect } from "react";
import {
  estadoCaja, abrirCaja, saldoApertura, buscarCuentaCaja, registrarPagoCaja, cerrarCaja,
  reportarDescuadre, solicitarSalida, solicitarIngreso, urlConstanciaCaja,
  type SesionCajaDTO, type CuentaCajaDTO,
} from "../../api/client";

function L(n: number) {
  return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function CajaPanel() {
  const [sesion, setSesion] = useState<SesionCajaDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [cerrando, setCerrando] = useState(false);

  function recargar() {
    estadoCaja().then(r => setSesion(r.abierta ? r.sesion! : null)).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  if (cargando) return <p className="muted">Cargando caja…</p>;

  if (!sesion) return <AbrirCaja onAbierta={recargar} />;
  if (cerrando) return <CerrarCaja sesion={sesion} onCancelar={() => setCerrando(false)} onCerrada={() => { setCerrando(false); recargar(); }} />;

  return (
    <div className="caja">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Caja abierta</h2>
          <span className="muted">Cajero: {sesion.cajero}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <a className="ghost mini" href={urlConstanciaCaja(sesion.id)} target="_blank" rel="noreferrer"
            style={{ textDecoration: "none" }}>📄 Constancia</a>
          <button className="btn-baja mini" onClick={() => setCerrando(true)}>Cerrar caja</button>
        </div>
      </div>

      {/* Arqueo en vivo */}
      <div className="metric-grid">
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Fondo inicial</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L(sesion.monto_inicial)}</div>
        </div>
        <div className="metric-card verde">
          <div className="metric-top"><span className="metric-label">Efectivo esperado</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L(sesion.efectivo_esperado)}</div>
        </div>
        <div className="metric-card naranja">
          <div className="metric-top"><span className="metric-label">POS (tarjeta)</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L(sesion.total_pos)}</div>
        </div>
        <div className="metric-card verde">
          <div className="metric-top"><span className="metric-label">Ingresos autorizados</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L((sesion as any).total_ingresos || 0)}</div>
        </div>
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Salidas autorizadas</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L(sesion.total_salidas || 0)}</div>
        </div>
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Pagos registrados</span></div>
          <div className="metric-valor">{sesion.cantidad_pagos}</div>
        </div>
      </div>

      <RegistrarPago onRegistrado={recargar} />
      <SolicitarSalida onRegistrada={recargar} />
      <SolicitarIngreso onRegistrado={recargar} />
      <ReportarDescuadre />

      {/* Pagos de la sesión */}
      <div className="dash-card">
        <h3>Pagos de esta sesión</h3>
        {!sesion.pagos || sesion.pagos.length === 0 ? (
          <p className="muted">Aún no hay pagos registrados.</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Hora</th><th>Monto</th><th>Método</th><th>Referencia</th></tr></thead>
              <tbody>
                {sesion.pagos.map(p => (
                  <tr key={p.id}>
                    <td className="small">{new Date(p.hora).toLocaleTimeString("es-HN")}</td>
                    <td>{L(p.monto)}</td>
                    <td><span className="pill">{p.metodo === "efectivo" ? "Efectivo" : "Tarjeta POS"}</span></td>
                    <td>{p.referencia || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AbrirCaja({ onAbierta }: { onAbierta: () => void }) {
  const [abriendo, setAbriendo] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState<{ saldo_apertura: number; tiene_cierre_anterior: boolean; cerrada_en?: string } | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    saldoApertura().then(setInfo).catch(() => {}).finally(() => setCargando(false));
  }, []);

  async function abrir() {
    setAbriendo(true); setError("");
    try { await abrirCaja(); onAbierta(); }
    catch (e) { setError((e as Error).message); setAbriendo(false); }
  }

  const L = (n: number) => "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="caja-abrir">
      <div className="dash-card" style={{ maxWidth: 460, margin: "0 auto" }}>
        <div className="caja-abrir-icon">🔓</div>
        <h2 style={{ textAlign: "center", color: "var(--marca-azul)" }}>Abrir caja</h2>
        {cargando ? (
          <p className="muted" style={{ textAlign: "center" }}>Calculando fondo de apertura…</p>
        ) : (
          <>
            <p className="muted" style={{ textAlign: "center" }}>
              {info?.tiene_cierre_anterior
                ? "El fondo de apertura es el efectivo con que cerró la caja anterior. No es editable."
                : "Primera apertura: el fondo es el saldo inicial configurado del sistema."}
            </p>
            <div className="caja-fondo-fijo">
              <span className="muted small">Fondo de apertura</span>
              <span className="caja-fondo-monto">{L(info?.saldo_apertura ?? 0)}</span>
              {info?.tiene_cierre_anterior && info.cerrada_en && (
                <span className="muted small">Cierre anterior: {new Date(info.cerrada_en).toLocaleString("es-HN")}</span>
              )}
            </div>
            <p className="muted small" style={{ textAlign: "center", marginTop: 8 }}>
              Verificá que el efectivo físico en caja coincida con este monto antes de abrir.
            </p>
            {error && <div className="error">{error}</div>}
            <button className="cuota-btn-pagar full" onClick={abrir} disabled={abriendo}>
              {abriendo ? "Abriendo…" : `Abrir caja con ${L(info?.saldo_apertura ?? 0)}`}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function RegistrarPago({ onRegistrado }: { onRegistrado: () => void }) {
  const [busqueda, setBusqueda] = useState("");
  const [resultados, setResultados] = useState<CuentaCajaDTO[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [seleccion, setSeleccion] = useState<{ cuotaId: string; label: string; monto: number } | null>(null);
  const [metodo, setMetodo] = useState("efectivo");
  const [referencia, setReferencia] = useState("");
  const [pagaCon, setPagaCon] = useState("");
  const [msg, setMsg] = useState("");

  const montoPagaCon = parseFloat(pagaCon || "0");
  const vuelto = seleccion && montoPagaCon > 0 ? montoPagaCon - seleccion.monto : 0;

  async function buscar() {
    if (!busqueda.trim()) return;
    setBuscando(true);
    try { setResultados(await buscarCuentaCaja(busqueda)); }
    finally { setBuscando(false); }
  }

  async function cobrar() {
    if (!seleccion) return;
    setMsg("");
    try {
      await registrarPagoCaja({ cuota_id: seleccion.cuotaId, metodo, referencia });
      setMsg(`✓ Pago de ${L(seleccion.monto)} registrado`);
      setSeleccion(null); setBusqueda(""); setResultados([]); setReferencia(""); setPagaCon("");
      onRegistrado();
      setTimeout(() => setMsg(""), 4000);
    } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <div className="dash-card">
      <h3>Registrar pago en ventanilla</h3>
      <div className="caja-buscar-row">
        <input placeholder="Buscar por casa o titular…" value={busqueda}
          onChange={e => setBusqueda(e.target.value)} onKeyDown={e => e.key === "Enter" && buscar()} />
        <button className="cuota-btn-pagar" style={{ maxWidth: 110 }} onClick={buscar} disabled={buscando}>
          {buscando ? "…" : "Buscar"}
        </button>
      </div>

      {resultados.map(c => (
        <div key={c.cuenta_id} className="caja-resultado">
          <div className="caja-resultado-head">
            <b>{c.identificador}</b> · {c.titular}
          </div>
          {c.cuotas_pendientes.length === 0 ? (
            <span className="muted small">Sin cuotas pendientes</span>
          ) : (
            <div className="caja-cuotas">
              {c.cuotas_pendientes.map(q => (
                <button key={q.cuota_id}
                  className={`caja-cuota-chip ${seleccion?.cuotaId === q.cuota_id ? "on" : ""}`}
                  onClick={() => setSeleccion({ cuotaId: q.cuota_id, label: `${c.identificador} · ${q.mes_label}`, monto: q.monto })}>
                  {q.mes_label} — {L(q.monto)}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      {seleccion && (
        <div className="caja-cobro">
          <div className="caja-cobro-info">
            Cobrando: <b>{seleccion.label}</b> — <b>{L(seleccion.monto)}</b>
          </div>
          <div className="caja-cobro-metodo">
            <label className={metodo === "efectivo" ? "on" : ""}>
              <input type="radio" checked={metodo === "efectivo"} onChange={() => setMetodo("efectivo")} /> Efectivo
            </label>
            <label className={metodo === "tarjeta_pos" ? "on" : ""}>
              <input type="radio" checked={metodo === "tarjeta_pos"} onChange={() => setMetodo("tarjeta_pos")} /> Tarjeta (POS)
            </label>
          </div>
          {metodo === "tarjeta_pos" && (
            <input placeholder="N° de voucher / referencia POS" value={referencia}
              onChange={e => setReferencia(e.target.value)} />
          )}
          {metodo === "efectivo" && (
            <div className="vuelto-box">
              <div className="form-field" style={{ margin: 0 }}>
                <label>¿Con cuánto paga el residente?</label>
                <input type="number" min="0" value={pagaCon}
                  onChange={e => setPagaCon(e.target.value)}
                  placeholder={`Mínimo ${seleccion.monto}`} />
              </div>
              {montoPagaCon > 0 && (
                vuelto < 0 ? (
                  <div className="vuelto-resultado falta">
                    Falta: <b>{L(Math.abs(vuelto))}</b> (el pago no cubre la cuota)
                  </div>
                ) : (
                  <div className="vuelto-resultado ok">
                    Vuelto a entregar: <b>{L(vuelto)}</b>
                  </div>
                )
              )}
            </div>
          )}
          <button className="cuota-btn-pagar full" onClick={cobrar}
            disabled={metodo === "efectivo" && montoPagaCon > 0 && vuelto < 0}>
            Confirmar pago {L(seleccion.monto)}
          </button>
        </div>
      )}

      {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

function CerrarCaja({ sesion, onCancelar, onCerrada }: {
  sesion: SesionCajaDTO; onCancelar: () => void; onCerrada: () => void;
}) {
  const DENOMINACIONES = [500, 200, 100, 50, 20, 10, 5, 2, 1];
  const [billetes, setBilletes] = useState<Record<number, string>>({});
  const [pos, setPos] = useState("");
  const [nota, setNota] = useState("");
  const [cerrando, setCerrando] = useState(false);
  const [error, setError] = useState("");
  const [confirmarForzar, setConfirmarForzar] = useState(false);

  // El efectivo contado se calcula del desglose de billetes
  const efContado = DENOMINACIONES.reduce((sum, d) => sum + (parseInt(billetes[d] || "0") || 0) * d, 0);
  const posContado = parseFloat(pos || "0");
  const difEf = efContado - sesion.efectivo_esperado;
  const difPos = posContado - sesion.total_pos;

  function setBillete(den: number, cant: string) {
    setBilletes(b => ({ ...b, [den]: cant }));
  }

  async function cerrar(forzar = false) {
    setCerrando(true); setError("");
    try {
      const desglose: Record<string, number> = {};
      DENOMINACIONES.forEach(d => { desglose[String(d)] = parseInt(billetes[d] || "0") || 0; });
      await cerrarCaja({ efectivo_contado: efContado, pos_contado: posContado, nota, forzar,
        desglose_billetes: desglose });
      onCerrada();
    } catch (e: any) {
      const msg = (e as Error).message || "";
      if (msg.includes("pendiente")) {
        setConfirmarForzar(true);
      } else {
        setError(msg);
      }
      setCerrando(false);
    }
  }

  return (
    <div className="caja-cerrar">
      <div className="dash-card" style={{ maxWidth: 520, margin: "0 auto" }}>
        <h2 style={{ color: "var(--marca-azul)" }}>Cierre de caja (arqueo)</h2>
        <p className="muted">Contá el efectivo y los vouchers POS reales. El sistema los compara con lo esperado.</p>

        <div className="arqueo-fila">
          <span>Efectivo esperado</span><b>{L(sesion.efectivo_esperado)}</b>
        </div>

        <div className="form-field">
          <label>Conteo de billetes</label>
          <p className="muted small">Contá cuántos billetes tenés de cada denominación. El total se calcula solo.</p>
          <div className="billetes-grid">
            {DENOMINACIONES.map(den => (
              <div key={den} className="billete-row">
                <span className="billete-den">L {den}</span>
                <input type="number" min="0" className="billete-input"
                  value={billetes[den] || ""} onChange={e => setBillete(den, e.target.value)}
                  placeholder="0" />
                <span className="billete-sub muted small">
                  {(parseInt(billetes[den] || "0") || 0) > 0 ? L((parseInt(billetes[den] || "0") || 0) * den) : ""}
                </span>
              </div>
            ))}
          </div>
          <div className="billetes-total">
            <span>Total efectivo contado</span>
            <b>{L(efContado)}</b>
          </div>
        </div>
        {efContado > 0 && (
          <div className={`arqueo-dif ${Math.abs(difEf) < 0.01 ? "ok" : "alerta"}`}>
            {Math.abs(difEf) < 0.01 ? "✓ Cuadra" : `Diferencia: ${L(difEf)} ${difEf > 0 ? "(sobra)" : "(falta)"}`}
          </div>
        )}

        <div className="arqueo-fila" style={{ marginTop: 14 }}>
          <span>POS esperado</span><b>{L(sesion.total_pos)}</b>
        </div>
        <div className="form-field">
          <label>POS contado / vouchers (L)</label>
          <input type="number" value={pos} onChange={e => setPos(e.target.value)} placeholder="0.00" />
        </div>
        {pos !== "" && (
          <div className={`arqueo-dif ${Math.abs(difPos) < 0.01 ? "ok" : "alerta"}`}>
            {Math.abs(difPos) < 0.01 ? "✓ Cuadra" : `Diferencia: ${L(difPos)} ${difPos > 0 ? "(sobra)" : "(falta)"}`}
          </div>
        )}

        <div className="form-field" style={{ marginTop: 14 }}>
          <label>Nota (opcional)</label>
          <textarea className="comunicado-textarea" rows={2} value={nota}
            onChange={e => setNota(e.target.value)} placeholder="Observaciones del cierre…" />
        </div>

        {error && <div className="error">{error}</div>}

        {sesion.salidas_pendientes && sesion.salidas_pendientes > 0 && (
          <div className="arqueo-dif alerta" style={{ marginBottom: 10 }}>
            ⚠️ Tenés {sesion.salidas_pendientes} salida(s)/ingreso(s) sin autorizar. El arqueo puede no cuadrar.
          </div>
        )}

        {confirmarForzar ? (
          <div className="caja-confirmar-forzar">
            <p className="muted small">
              Hay salidas o ingresos pendientes de autorización. Si cerrás ahora, el arqueo podría
              mostrar una diferencia. ¿Cerrar de todos modos?
            </p>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="ghost" onClick={() => setConfirmarForzar(false)}>Volver</button>
              <button className="cuota-btn-pagar full" onClick={() => cerrar(true)} disabled={cerrando}>
                {cerrando ? "Cerrando…" : "Cerrar de todos modos"}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="ghost" onClick={onCancelar}>Cancelar</button>
            <button className="cuota-btn-pagar full" onClick={() => cerrar(false)} disabled={cerrando}>
              {cerrando ? "Cerrando…" : "Confirmar cierre"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ReportarDescuadre() {
  const [abierto, setAbierto] = useState(false);
  const [tipo, setTipo] = useState("faltante");
  const [monto, setMonto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [msg, setMsg] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function reportar() {
    const m = parseFloat(monto);
    if (isNaN(m) || m <= 0) { setMsg("Ingresá un monto válido"); return; }
    setEnviando(true); setMsg("");
    try {
      await reportarDescuadre({ tipo, monto: m, motivo });
      setMsg("✓ Descuadre reportado. Queda pendiente de aprobación por administración.");
      setMonto(""); setMotivo(""); setAbierto(false);
      setTimeout(() => setMsg(""), 5000);
    } catch (e) { setMsg((e as Error).message); }
    finally { setEnviando(false); }
  }

  return (
    <div className="dash-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Reportar descuadre</h3>
        {!abierto && <button className="mini" onClick={() => setAbierto(true)}>Reportar sobrante / faltante</button>}
      </div>
      {abierto && (
        <div className="form-pago" style={{ marginTop: 12 }}>
          <div className="caja-cobro-metodo">
            <label className={tipo === "faltante" ? "on" : ""}>
              <input type="radio" checked={tipo === "faltante"} onChange={() => setTipo("faltante")} /> Faltante
            </label>
            <label className={tipo === "sobrante" ? "on" : ""}>
              <input type="radio" checked={tipo === "sobrante"} onChange={() => setTipo("sobrante")} /> Sobrante
            </label>
          </div>
          <div className="form-field"><label>Monto (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" /></div>
          <div className="form-field"><label>Motivo</label>
            <input value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="Ej. faltó vuelto, error de conteo…" /></div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="ghost" onClick={() => setAbierto(false)}>Cancelar</button>
            <button className="cuota-btn-pagar full" onClick={reportar} disabled={enviando}>
              {enviando ? "Enviando…" : "Reportar"}
            </button>
          </div>
        </div>
      )}
      {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

function SolicitarSalida({ onRegistrada }: { onRegistrada: () => void }) {
  const [abierto, setAbierto] = useState(false);
  const [monto, setMonto] = useState("");
  const [concepto, setConcepto] = useState("");
  const [msg, setMsg] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function solicitar() {
    const m = parseFloat(monto);
    if (isNaN(m) || m <= 0) { setMsg("Ingresá un monto válido"); return; }
    if (!concepto.trim()) { setMsg("Indicá el concepto (ej. Depósito banco Ficohsa)"); return; }
    setEnviando(true); setMsg("");
    try {
      await solicitarSalida({ monto: m, concepto });
      setMsg("✓ Salida solicitada. Esperando autorización del administrador.");
      setMonto(""); setConcepto(""); setAbierto(false);
      onRegistrada();
      setTimeout(() => setMsg(""), 5000);
    } catch (e) { setMsg((e as Error).message); }
    finally { setEnviando(false); }
  }

  return (
    <div className="dash-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Salida de caja</h3>
        {!abierto && (
          <button className="mini" onClick={() => setAbierto(true)}>
            Solicitar depósito / salida
          </button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        Para registrar cuando se saca efectivo de la caja (depósito al banco, etc.). Requiere autorización del admin.
      </p>
      {abierto && (
        <div className="form-pago" style={{ marginTop: 12 }}>
          <div className="form-field">
            <label>Monto a retirar (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" />
          </div>
          <div className="form-field">
            <label>Concepto</label>
            <input value={concepto} onChange={e => setConcepto(e.target.value)}
              placeholder="Ej. Depósito banco Ficohsa, cheque #12345…" />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="ghost" onClick={() => { setAbierto(false); setMsg(""); }}>Cancelar</button>
            <button className="cuota-btn-pagar full" onClick={solicitar} disabled={enviando}>
              {enviando ? "Enviando…" : "Solicitar salida"}
            </button>
          </div>
        </div>
      )}
      {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

function SolicitarIngreso({ onRegistrado }: { onRegistrado: () => void }) {
  const [abierto, setAbierto] = useState(false);
  const [monto, setMonto] = useState("");
  const [concepto, setConcepto] = useState("");
  const [msg, setMsg] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function solicitar() {
    const m = parseFloat(monto);
    if (isNaN(m) || m <= 0) { setMsg("Ingresá un monto válido"); return; }
    if (!concepto.trim()) { setMsg("Indicá el concepto (ej. Retiro banco Ficohsa)"); return; }
    setEnviando(true); setMsg("");
    try {
      await solicitarIngreso({ monto: m, concepto });
      setMsg("✓ Ingreso solicitado. Esperando autorización del administrador.");
      setMonto(""); setConcepto(""); setAbierto(false);
      onRegistrado();
      setTimeout(() => setMsg(""), 5000);
    } catch (e) { setMsg((e as Error).message); }
    finally { setEnviando(false); }
  }

  return (
    <div className="dash-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Ingreso extraordinario</h3>
        {!abierto && (
          <button className="mini btn-reactivar" onClick={() => setAbierto(true)}>
            Solicitar ingreso de efectivo
          </button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        Para registrar cuando se trae efectivo del banco u otra fuente. Requiere autorización del admin.
      </p>
      {abierto && (
        <div className="form-pago" style={{ marginTop: 12 }}>
          <div className="form-field">
            <label>Monto a ingresar (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" />
          </div>
          <div className="form-field">
            <label>Concepto</label>
            <input value={concepto} onChange={e => setConcepto(e.target.value)}
              placeholder="Ej. Retiro banco Ficohsa, fondo de caja…" />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="ghost" onClick={() => { setAbierto(false); setMsg(""); }}>Cancelar</button>
            <button className="cuota-btn-pagar full" onClick={solicitar} disabled={enviando}>
              {enviando ? "Enviando…" : "Solicitar ingreso"}
            </button>
          </div>
        </div>
      )}
      {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}
