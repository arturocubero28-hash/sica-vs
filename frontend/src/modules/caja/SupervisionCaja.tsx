import { useState, useEffect } from "react";
import {
  listarSesionesCaja, detalleSesionCaja, resumenCaja,
  modificarSaldoInicial, ajustarSaldoConteo, listarDescuadres, resolverDescuadre,
  salidasPendientes, listarSalidas, autorizarSalida,
  type SesionCajaDTO, type ResumenCajaDTO, type DescuadreDTO, type SalidaCajaDTO,
} from "../../api/client";

function L(n: number) {
  return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function SupervisionCaja() {
  const [sesiones, setSesiones] = useState<SesionCajaDTO[]>([]);
  const [resumen, setResumen] = useState<ResumenCajaDTO | null>(null);
  const [descuadres, setDescuadres] = useState<DescuadreDTO[]>([]);
  const [salidas, setSalidas] = useState<SalidaCajaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [detalle, setDetalle] = useState<SesionCajaDTO | null>(null);
  const [editarSaldo, setEditarSaldo] = useState(false);
  const [ajusteConteo, setAjusteConteo] = useState(false);

  function recargar() {
    Promise.all([listarSesionesCaja(), resumenCaja(), listarDescuadres(), listarSalidas()])
      .then(([s, r, d, sl]) => { setSesiones(s); setResumen(r); setDescuadres(d); setSalidas(sl); })
      .catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  if (cargando) return <p className="muted">Cargando…</p>;

  const abiertas = sesiones.filter(s => s.estado === "abierta");
  const totalRecaudadoHoy = sesiones
    .filter(s => new Date(s.abierta_en).toDateString() === new Date().toDateString())
    .reduce((acc, s) => acc + s.total_efectivo + s.total_pos, 0);
  const pendientes = descuadres.filter(d => d.estado === "pendiente");
  const salidasPend = salidas.filter(s => s.estado === "pendiente");

  return (
    <div className="supervision">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Supervisión de caja</h2>
          <span className="muted">Saldos y sesiones de los cajeros</span>
        </div>
      </div>

      {/* Saldo del sistema */}
      {resumen && (
        <div className="saldo-caja-card">
          <div className="saldo-caja-main">
            <span className="saldo-caja-label">Saldo actual de caja</span>
            <span className="saldo-caja-monto">{L(resumen.saldo_actual)}</span>
            <span className="saldo-caja-detalle muted small">
              Saldo inicial {L(resumen.saldo_inicial)} + efectivo recaudado {L(resumen.total_efectivo_historico)}
              {typeof resumen.total_ajustes === "number" && resumen.total_ajustes !== 0 &&
                ` + ajustes ${L(resumen.total_ajustes)}`}
            </span>
            <div className="saldo-botones">
              <button className="saldo-editar-btn" onClick={() => setAjusteConteo(true)}>
                Ajustar saldo de caja
              </button>
              <button className="saldo-editar-btn secundario" onClick={() => setEditarSaldo(true)}>
                Saldo inicial del sistema
              </button>
            </div>
          </div>
          <div className="saldo-caja-side">
            <div className="saldo-side-item">
              <span className="muted small">En cajas abiertas ahora</span>
              <b>{L(resumen.efectivo_en_cajas_abiertas)}</b>
            </div>
            <div className="saldo-side-item">
              <span className="muted small">POS histórico</span>
              <b>{L(resumen.total_pos_historico)}</b>
            </div>
            {typeof resumen.total_salidas_historico === "number" && resumen.total_salidas_historico > 0 && (
              <div className="saldo-side-item">
                <span className="muted small">Salidas / depósitos al banco</span>
                <b style={{ color: "#F48723" }}>- {L(resumen.total_salidas_historico)}</b>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Salidas de caja pendientes de autorización */}
      {salidasPend.length > 0 && (
        <div className="dash-card descuadres-card" style={{ borderColor: "#a9c4e0" }}>
          <h3>Salidas de caja pendientes de autorización ({salidasPend.length})</h3>
          <p className="muted small">El cajero solicita retirar efectivo (depósito al banco u otro concepto). Tu contraseña de admin autoriza.</p>
          <div className="descuadre-lista">
            {salidasPend.map(s => (
              <SalidaItem key={s.id} salida={s} onResuelta={recargar} />
            ))}
          </div>
        </div>
      )}


      <div className="metric-grid">
        <div className="metric-card verde">
          <div className="metric-top"><span className="metric-label">Cajas abiertas ahora</span></div>
          <div className="metric-valor">{abiertas.length}</div>
        </div>
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Recaudado hoy</span></div>
          <div className="metric-valor" style={{ fontSize: 20 }}>{L(totalRecaudadoHoy)}</div>
        </div>
        <div className="metric-card naranja">
          <div className="metric-top"><span className="metric-label">Total de sesiones</span></div>
          <div className="metric-valor">{sesiones.length}</div>
        </div>
      </div>

      {/* Cajas activas: cuánto tiene cada cajero ahora mismo */}
      {abiertas.length > 0 && (
        <div className="dash-card">
          <h3>Cajas activas ahora</h3>
          <p className="muted small">Efectivo que cada cajero tiene en su caja en este momento.</p>
          <div className="cajas-activas-grid">
            {abiertas.map(s => (
              <div key={s.id} className="caja-activa-item">
                <div className="caja-activa-cajero">
                  <span className="caja-activa-dot" />
                  <b>{s.cajero}</b>
                </div>
                <div className="caja-activa-efectivo">{L(s.efectivo_esperado)}</div>
                <div className="caja-activa-detalle muted small">
                  Fondo {L(s.monto_inicial)} · {s.cantidad_pagos} pago{s.cantidad_pagos !== 1 ? "s" : ""}
                  {(s.total_pos || 0) > 0 && ` · POS ${L(s.total_pos)}`}
                </div>
                <button className="mini" onClick={async () => setDetalle(await detalleSesionCaja(s.id))}>
                  Ver detalle
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Descuadres pendientes de aprobación */}
      {pendientes.length > 0 && (
        <div className="dash-card descuadres-card">
          <h3>Descuadres pendientes de aprobación ({pendientes.length})</h3>
          <p className="muted small">Reportados por cajeros. Aprobar requiere la clave del desarrollador y afecta el saldo de caja.</p>
          <div className="descuadre-lista">
            {pendientes.map(d => (
              <DescuadreItem key={d.id} descuadre={d} onResuelto={recargar} />
            ))}
          </div>
        </div>
      )}

      {/* Historial de descuadres resueltos */}
      {descuadres.some(d => d.estado !== "pendiente") && (
        <div className="dash-card">
          <h3>Historial de descuadres</h3>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Tipo</th><th>Monto</th><th>Motivo</th><th>Reportó</th><th>Estado</th><th>Resuelto</th></tr></thead>
              <tbody>
                {descuadres.filter(d => d.estado !== "pendiente").map(d => (
                  <tr key={d.id}>
                    <td><span className={`pill ${d.tipo === "sobrante" ? "green" : "red"}`}>{d.tipo}</span></td>
                    <td>{L(Math.abs(d.monto))}</td>
                    <td className="small">{d.motivo || "—"}</td>
                    <td className="small">{d.reportado_por}</td>
                    <td><span className="pill">{d.estado}</span></td>
                    <td className="small">{d.resuelto_en ? new Date(d.resuelto_en).toLocaleDateString("es-HN") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="dash-card">
        <h3>Historial de sesiones</h3>
        {sesiones.length === 0 ? (
          <p className="muted">No hay sesiones de caja todavía.</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr><th>Cajero</th><th>Apertura</th><th>Estado</th><th>Inicial</th><th>Efectivo</th><th>POS</th><th>Diferencia</th><th></th></tr>
              </thead>
              <tbody>
                {sesiones.map(s => (
                  <tr key={s.id}>
                    <td>{s.cajero}</td>
                    <td className="small">{new Date(s.abierta_en).toLocaleString("es-HN")}</td>
                    <td><span className={s.estado === "abierta" ? "pill green" : "pill"}>{s.estado}</span></td>
                    <td>{L(s.monto_inicial)}</td>
                    <td>{L(s.total_efectivo)}</td>
                    <td>{L(s.total_pos)}</td>
                    <td>
                      {s.estado === "cerrada" && s.diferencia_efectivo !== undefined ? (
                        <span className={Math.abs(s.diferencia_efectivo) < 0.01 ? "pill green" : "pill red"}>
                          {Math.abs(s.diferencia_efectivo) < 0.01 ? "Cuadra" : L(s.diferencia_efectivo)}
                        </span>
                      ) : "—"}
                    </td>
                    <td><button className="mini" onClick={async () => setDetalle(await detalleSesionCaja(s.id))}>Ver</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detalle && (
        <div className="modal" onClick={() => setDetalle(null)}>
          <div className="modal-body" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Sesión de {detalle.cajero}</h3>
              <button className="ghost mini" onClick={() => setDetalle(null)}>✕</button>
            </div>
            <div className="arqueo-fila"><span>Fondo inicial</span><b>{L(detalle.monto_inicial)}</b></div>
            <div className="arqueo-fila"><span>Efectivo esperado</span><b>{L(detalle.efectivo_esperado)}</b></div>
            {detalle.estado === "cerrada" && (
              <>
                <div className="arqueo-fila"><span>Efectivo contado</span><b>{L(detalle.efectivo_contado || 0)}</b></div>
                <div className={`arqueo-dif ${Math.abs(detalle.diferencia_efectivo || 0) < 0.01 ? "ok" : "alerta"}`}>
                  {Math.abs(detalle.diferencia_efectivo || 0) < 0.01 ? "✓ Efectivo cuadra" : `Dif. efectivo: ${L(detalle.diferencia_efectivo || 0)}`}
                </div>
                <div className="arqueo-fila"><span>POS contado</span><b>{L(detalle.pos_contado || 0)}</b></div>
                {detalle.nota_cierre && <p className="muted small">Nota: {detalle.nota_cierre}</p>}
              </>
            )}
            <div className="sub" style={{ marginTop: 12 }}>Pagos ({detalle.pagos?.length || 0})</div>
            {detalle.pagos && detalle.pagos.length > 0 && (
              <div className="scroll-x"><table className="data">
                <thead><tr><th>Hora</th><th>Monto</th><th>Método</th></tr></thead>
                <tbody>
                  {detalle.pagos.map(p => (
                    <tr key={p.id}>
                      <td className="small">{new Date(p.hora).toLocaleTimeString("es-HN")}</td>
                      <td>{L(p.monto)}</td>
                      <td>{p.metodo === "efectivo" ? "Efectivo" : "POS"}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </div>
        </div>
      )}

      {/* Historial de salidas/depósitos al banco */}
      {salidas.filter(s => s.estado === "autorizada").length > 0 && (
        <div className="dash-card">
          <h3>Historial de salidas / depósitos al banco</h3>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Fecha</th><th>Monto</th><th>Concepto</th><th>Solicitó</th><th>Autorizó</th></tr></thead>
              <tbody>
                {salidas.filter(s => s.estado === "autorizada").map(s => (
                  <tr key={s.id}>
                    <td className="small">{new Date(s.created_at).toLocaleString("es-HN")}</td>
                    <td><b>{L(s.monto)}</b></td>
                    <td>{s.concepto}</td>
                    <td className="small">{s.solicitado_por}</td>
                    <td className="small">{s.autorizado_por || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {editarSaldo && resumen && (
        <ModalSaldoInicial saldoActual={resumen.saldo_inicial}
          onCerrar={() => setEditarSaldo(false)}
          onGuardado={() => { setEditarSaldo(false); recargar(); }} />
      )}

      {ajusteConteo && resumen && (
        <ModalAjusteConteo saldoSistema={resumen.saldo_actual}
          onCerrar={() => setAjusteConteo(false)}
          onGuardado={() => { setAjusteConteo(false); recargar(); }} />
      )}
    </div>
  );
}

function DescuadreItem({ descuadre, onResuelto }: { descuadre: DescuadreDTO; onResuelto: () => void }) {
  const [aprobando, setAprobando] = useState(false);
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [procesando, setProcesando] = useState(false);

  async function aprobar() {
    if (!clave) { setError("Ingresá la clave del desarrollador"); return; }
    setProcesando(true); setError("");
    try { await resolverDescuadre(descuadre.id, "aprobar", clave); onResuelto(); }
    catch (e) { setError((e as Error).message); setProcesando(false); }
  }
  async function rechazar() {
    setProcesando(true);
    try { await resolverDescuadre(descuadre.id, "rechazar"); onResuelto(); }
    catch (e) { setError((e as Error).message); setProcesando(false); }
  }

  return (
    <div className="descuadre-item">
      <div className="descuadre-info">
        <span className={`pill ${descuadre.tipo === "sobrante" ? "green" : "red"}`}>{descuadre.tipo}</span>
        <b>{"L " + Math.abs(descuadre.monto).toLocaleString("es-HN", { minimumFractionDigits: 2 })}</b>
        <span className="muted small">· {descuadre.motivo || "Sin motivo"} · {descuadre.reportado_por}</span>
      </div>
      {!aprobando ? (
        <div className="descuadre-acciones">
          <button className="mini btn-reactivar" onClick={() => setAprobando(true)}>Aprobar</button>
          <button className="mini btn-baja" onClick={rechazar} disabled={procesando}>Rechazar</button>
        </div>
      ) : (
        <div className="descuadre-confirmar">
          <input type="password" placeholder="Clave del desarrollador" value={clave}
            onChange={e => setClave(e.target.value)} onKeyDown={e => e.key === "Enter" && aprobar()} />
          <button className="mini btn-reactivar" onClick={aprobar} disabled={procesando}>Confirmar</button>
          <button className="mini" onClick={() => { setAprobando(false); setClave(""); setError(""); }}>Cancelar</button>
        </div>
      )}
      {error && <div className="error" style={{ marginTop: 6 }}>{error}</div>}
    </div>
  );
}

function ModalSaldoInicial({ saldoActual, onCerrar, onGuardado }: {
  saldoActual: number; onCerrar: () => void; onGuardado: () => void;
}) {
  const [monto, setMonto] = useState(String(saldoActual));
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    const m = parseFloat(monto);
    if (isNaN(m) || m < 0) { setError("Monto inválido"); return; }
    if (!clave) { setError("Ingresá la clave del desarrollador"); return; }
    setGuardando(true); setError("");
    try { await modificarSaldoInicial(m, clave); onGuardado(); }
    catch (e) { setError((e as Error).message); setGuardando(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Saldo inicial del sistema</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <p className="muted small">
          <b>Solo para la implementación inicial.</b> Es el dinero que había en caja el día que
          se empezó a usar SICA-VS. En operación normal no se modifica — para corregir el saldo
          por un conteo físico usá "Ajustar saldo de caja". Requiere clave del desarrollador.
        </p>
        <div className="form-field">
          <label>Saldo inicial del sistema (L)</label>
          <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" />
        </div>
        <div className="form-field">
          <label>Clave del desarrollador</label>
          <input type="password" value={clave} onChange={e => setClave(e.target.value)}
            placeholder="••••••••" onKeyDown={e => e.key === "Enter" && guardar()} />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="cuota-btn-pagar full" onClick={guardar} disabled={guardando}>
          {guardando ? "Guardando…" : "Confirmar cambio"}
        </button>
      </div>
    </div>
  );
}

function ModalAjusteConteo({ saldoSistema, onCerrar, onGuardado }: {
  saldoSistema: number; onCerrar: () => void; onGuardado: () => void;
}) {
  const [monto, setMonto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  const L = (n: number) => "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const saldoReal = parseFloat(monto || "");
  const diferencia = !isNaN(saldoReal) ? saldoReal - saldoSistema : null;

  async function guardar() {
    const m = parseFloat(monto);
    if (isNaN(m) || m < 0) { setError("Ingresá el saldo real contado"); return; }
    if (!clave) { setError("Ingresá la clave del desarrollador"); return; }
    setGuardando(true); setError("");
    try { await ajustarSaldoConteo(m, clave, motivo); onGuardado(); }
    catch (e) { setError((e as Error).message); setGuardando(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Ajustar saldo de caja (conteo físico)</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <p className="muted small">
          Contá el efectivo real total en caja e ingresá el monto. El sistema calculará la
          diferencia con lo registrado y dejará el saldo igual al conteo real. Queda registrado
          con la clave del desarrollador.
        </p>

        <div className="conteo-comparativo">
          <div className="conteo-fila">
            <span className="muted small">Saldo registrado por el sistema</span>
            <b>{L(saldoSistema)}</b>
          </div>
          {diferencia !== null && (
            <div className="conteo-fila">
              <span className="muted small">Diferencia que se ajustará</span>
              <b style={{ color: Math.abs(diferencia) < 0.01 ? "#1d8a4a" : diferencia > 0 ? "#1d8a4a" : "#c81e1e" }}>
                {diferencia > 0 ? "+" : ""}{L(diferencia)} {Math.abs(diferencia) < 0.01 ? "(cuadra)" : diferencia > 0 ? "(sobrante)" : "(faltante)"}
              </b>
            </div>
          )}
        </div>

        <div className="form-field">
          <label>Saldo real contado (L)</label>
          <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" autoFocus />
        </div>
        <div className="form-field">
          <label>Motivo (opcional)</label>
          <input value={motivo} onChange={e => setMotivo(e.target.value)}
            placeholder="Ej. Arqueo mensual, corrección por error acumulado…" />
        </div>
        <div className="form-field">
          <label>Clave del desarrollador</label>
          <input type="password" value={clave} onChange={e => setClave(e.target.value)}
            placeholder="••••••••" onKeyDown={e => e.key === "Enter" && guardar()} />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="cuota-btn-pagar full" onClick={guardar} disabled={guardando}>
          {guardando ? "Ajustando…" : "Confirmar ajuste"}
        </button>
      </div>
    </div>
  );
}

function SalidaItem({ salida, onResuelta }: { salida: SalidaCajaDTO; onResuelta: () => void }) {
  const [autorizando, setAutorizando] = useState(false);
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [procesando, setProcesando] = useState(false);

  async function autorizar() {
    if (!clave) { setError("Ingresá tu contraseña de admin"); return; }
    setProcesando(true); setError("");
    try { await autorizarSalida(salida.id, "autorizar", clave); onResuelta(); }
    catch (e) { setError((e as Error).message); setProcesando(false); }
  }
  async function rechazar() {
    setProcesando(true);
    try { await autorizarSalida(salida.id, "rechazar"); onResuelta(); }
    catch (e) { setError((e as Error).message); setProcesando(false); }
  }

  return (
    <div className="descuadre-item" style={{ borderColor: "#c0d8f0" }}>
      <div className="descuadre-info">
        {salida.monto < 0
          ? <span className="pill green">Ingreso</span>
          : <span className="pill" style={{ background: "#e6f0fa", color: "#022E45" }}>Depósito</span>
        }
        <b>{"L " + Math.abs(salida.monto).toLocaleString("es-HN", { minimumFractionDigits: 2 })}</b>
        <span className="muted small">· {salida.concepto.replace("[INGRESO] ", "")} · {salida.solicitado_por}</span>
      </div>
      {!autorizando ? (
        <div className="descuadre-acciones">
          <button className="mini btn-reactivar" onClick={() => setAutorizando(true)}>Autorizar</button>
          <button className="mini btn-baja" onClick={rechazar} disabled={procesando}>Rechazar</button>
        </div>
      ) : (
        <div className="descuadre-confirmar">
          <input type="password" placeholder="Tu contraseña de admin" value={clave}
            onChange={e => setClave(e.target.value)} onKeyDown={e => e.key === "Enter" && autorizar()} />
          <button className="mini btn-reactivar" onClick={autorizar} disabled={procesando}>Confirmar</button>
          <button className="mini" onClick={() => { setAutorizando(false); setClave(""); setError(""); }}>Cancelar</button>
        </div>
      )}
      {error && <div className="error" style={{ marginTop: 6 }}>{error}</div>}
    </div>
  );
}
