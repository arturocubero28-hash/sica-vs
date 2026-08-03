import { useState, useEffect } from "react";
import {
  estadoCaja, abrirCaja, saldoApertura, buscarCuentaCaja, registrarPagoCaja, cerrarCaja,
  reportarDescuadre, solicitarSalida, solicitarIngreso, urlConstanciaCaja, urlReciboPDF,
  listarTiposTarjeta, venderTarjetaCaja, cobrarAbono,
  type SesionCajaDTO, type CuentaCajaDTO, type TipoTarjetaDTO,
} from "../../api/client";
import { L } from "../../utils/formato";
import { InfoTip } from "../../components/InfoTip";
import { LectorTarjeta } from "../unidades/LectorTarjeta";
import { AlertTriangle, Banknote, CreditCard, FileText, LockOpen, Receipt, Ticket } from "lucide-react";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";

export function CajaPanel() {
  const [sesion, setSesion] = useState<SesionCajaDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [cerrando, setCerrando] = useState(false);
  const [vendiendo, setVendiendo] = useState(false);
  // Día 51 — niveles de plan: sin esto, un plan sin cuotas veía la
  // pantalla de "abrir caja por primera vez" en vez de enterarse de que
  // la función ni está disponible.
  const [errorPlan, setErrorPlan] = useState("");

  function recargar() {
    estadoCaja().then(r => setSesion(r.abierta ? r.sesion! : null))
      .catch((e) => setErrorPlan(e?.message || ""))
      .finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  if (cargando) return <p className="muted">Cargando caja…</p>;
  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;
  if (!sesion) return <AbrirCaja onAbierta={recargar} />;
  if (cerrando) return <CerrarCaja sesion={sesion} onCancelar={() => setCerrando(false)} onCerrada={() => { setCerrando(false); recargar(); }} />;

  return (
    <div className="caja caja-pos">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Caja</h2>
          <span className="muted">Cajero: {sesion.cajero}</span>
        </div>
        <div className="caja-acciones">
          <button className="caja-accion-primaria" onClick={() => setVendiendo(true)}>
            <span className="caja-accion-icono"><Ticket size={16} /></span> Vender tarjeta
          </button>
          <a className="caja-accion-secundaria" href={urlConstanciaCaja(sesion.id)}
            target="_blank" rel="noreferrer">
            <span className="caja-accion-icono"><FileText size={16} /></span> Constancia
          </a>
          <button className="caja-accion-cerrar" onClick={() => setCerrando(true)}>
            Cerrar caja
          </button>
        </div>
      </div>

      {vendiendo && <ModalVenderTarjeta onCerrar={() => setVendiendo(false)}
        onVendida={() => { setVendiendo(false); recargar(); }} />}

      {/* Layout POS: cobro a la izquierda (protagonista), arqueo a la derecha */}
      <div className="pos-grid">
        <div className="pos-main">
          <RegistrarPago onRegistrado={recargar} />

          {/* Pagos de la sesión: debajo del cobro, en la columna principal */}
          <div className="dash-card pos-pagos-card">
            <h3>Pagos de esta sesión</h3>
            {!sesion.pagos || sesion.pagos.length === 0 ? (
              <p className="muted">Aún no hay pagos registrados. Los cobros aparecerán aquí.</p>
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

        <aside className="pos-side">
          <div className="pos-arqueo">
            <div className="pos-arqueo-titulo">Arqueo en vivo</div>
            <div className="pos-arqueo-row destacado">
              <span>Efectivo esperado</span><b>{L(sesion.efectivo_esperado)}</b>
            </div>
            <div className="pos-arqueo-row">
              <span>Fondo inicial</span><span>{L(sesion.monto_inicial)}</span>
            </div>
            <div className="pos-arqueo-row">
              <span>POS (tarjeta)</span><span>{L(sesion.total_pos)}</span>
            </div>
            <div className="pos-arqueo-row">
              <span>↓ Ingresos</span><span>{L((sesion as any).total_ingresos || 0)}</span>
            </div>
            <div className="pos-arqueo-row">
              <span>↑ Salidas</span><span>{L(sesion.total_salidas || 0)}</span>
            </div>
            <div className="pos-arqueo-row">
              <span>Pagos registrados</span><b>{sesion.cantidad_pagos}</b>
            </div>
          </div>

          {/* Operaciones secundarias agrupadas y comprimidas */}
          <div className="pos-ops">
            <div className="pos-ops-titulo">Movimientos de efectivo</div>
            <SolicitarSalida onRegistrada={recargar} />
            <SolicitarIngreso onRegistrado={recargar} />
            <ReportarDescuadre />
          </div>
        </aside>
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


  return (
    <div className="caja-abrir">
      <div className="dash-card" style={{ maxWidth: 460, margin: "0 auto" }}>
        <div className="caja-abrir-icon"><LockOpen size={16} /></div>
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
              <span className="muted small">Fondo de apertura <InfoTip texto="Es el efectivo con el que arranca la caja: el dinero que quedó del cierre anterior (o el saldo inicial configurado, si es la primera vez). Contá el efectivo físico y verificá que coincida antes de abrir." /></span>
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
  const [seleccion, setSeleccion] = useState<{ cuotaId?: string; arregloId?: string; abonoId?: string; label: string; monto: number } | null>(null);
  const [metodo, setMetodo] = useState("efectivo");
  const [referencia, setReferencia] = useState("");
  const [pagaCon, setPagaCon] = useState("");
  const [msg, setMsg] = useState("");
  const [ultimoRecibo, setUltimoRecibo] = useState<{ uuid: string; numero?: number | null; label: string; monto: number; vuelto: number } | null>(null);

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
      let reciboUuid = "", reciboNum: number | undefined;
      if (seleccion.abonoId && seleccion.arregloId) {
        // Cobro de un abono de arreglo de pago
        await cobrarAbono(seleccion.arregloId, seleccion.abonoId, metodo, referencia);
        // El abono no devuelve un pago con recibo directo; mostramos confirmación simple
      } else if (seleccion.cuotaId) {
        const res = await registrarPagoCaja({ cuota_id: seleccion.cuotaId, metodo, referencia });
        reciboUuid = res.pago.id; reciboNum = res.pago.numero_recibo;
      }
      const vueltoFinal = metodo === "efectivo" && montoPagaCon > 0 ? vuelto : 0;
      setUltimoRecibo({
        uuid: reciboUuid, numero: reciboNum,
        label: seleccion.label, monto: seleccion.monto, vuelto: vueltoFinal,
      });
      setMsg("");
      setSeleccion(null); setBusqueda(""); setResultados([]); setReferencia(""); setPagaCon("");
      onRegistrado();
    } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <div className="dash-card pos-cobro-card">
      <h3 className="pos-cobro-titulo"><Banknote size={16} /> Cobrar en ventanilla</h3>
      <div className="caja-buscar-row pos-buscar">
        <input placeholder="Buscar casa o titular…" value={busqueda} autoFocus
          onChange={e => setBusqueda(e.target.value)} onKeyDown={e => e.key === "Enter" && buscar()} />
        <button className="cuota-btn-pagar pos-buscar-btn" onClick={buscar} disabled={buscando}>
          {buscando ? "…" : "Buscar"}
        </button>
      </div>

      {/* Comprobante tras cobrar */}
      {ultimoRecibo && (
        <div className="recibo-cobro">
          <div className="recibo-cobro-head">
            <span className="recibo-check">✓</span>
            <div>
              <div className="recibo-cobro-titulo">Pago registrado</div>
              <div className="muted small">{ultimoRecibo.label} — {L(ultimoRecibo.monto)}
                {ultimoRecibo.numero ? ` · Recibo REC-${String(ultimoRecibo.numero).padStart(6, "0")}` : ""}</div>
            </div>
          </div>
          {ultimoRecibo.vuelto > 0 && (
            <div className="recibo-vuelto">Vuelto entregado: <b>{L(ultimoRecibo.vuelto)}</b></div>
          )}
          <div className="recibo-cobro-acciones">
            <a className="cuota-btn-pagar" href={urlReciboPDF(ultimoRecibo.uuid)} target="_blank" rel="noreferrer"
              style={{ textDecoration: "none", textAlign: "center" }}>
              <Receipt size={16} /> Imprimir recibo
            </a>
            <button className="ghost" onClick={() => setUltimoRecibo(null)}>Cobrar otro</button>
          </div>
        </div>
      )}

      {resultados.map(c => (
        <div key={c.cuenta_id} className="caja-resultado">
          <div className="caja-resultado-head">
            <b>{c.identificador}</b> · {c.titular}
          </div>
          {c.cuotas_pendientes.length === 0 && (!c.abonos_arreglo || c.abonos_arreglo.length === 0) ? (
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
              {(c.abonos_arreglo || []).map(a => (
                <button key={a.abono_id}
                  className={`caja-cuota-chip arreglo ${seleccion?.abonoId === a.abono_id ? "on" : ""}`}
                  onClick={() => setSeleccion({ arregloId: a.arreglo_id, abonoId: a.abono_id, label: `${c.identificador} · Abono ${a.numero}/${a.total_abonos}`, monto: a.monto })}>
                  Abono {a.numero}/{a.total_abonos} — {L(a.monto)}
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
            <AlertTriangle size={16} /> Tenés {sesion.salidas_pendientes} salida(s)/ingreso(s) sin autorizar. El arqueo puede no cuadrar.
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
        <h3 style={{ margin: 0 }}>↑ Sacar efectivo de la caja</h3>
        {!abierto && (
          <button className="mini" onClick={() => setAbierto(true)}>
            Registrar salida
          </button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        El dinero <b>sale</b> de la caja: depósito al banco, entrega de efectivo, etc.
        Resta del efectivo esperado. Requiere autorización del admin.
      </p>
      {abierto && (
        <div className="form-pago" style={{ marginTop: 12 }}>
          <div className="form-field">
            <label>Monto que sale (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" />
          </div>
          <div className="form-field">
            <label>Concepto</label>
            <input value={concepto} onChange={e => setConcepto(e.target.value)}
              placeholder="Ej. Depósito al banco Ficohsa, cheque #12345…" />
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
        <h3 style={{ margin: 0 }}>↓ Meter efectivo a la caja</h3>
        {!abierto && (
          <button className="mini btn-reactivar" onClick={() => setAbierto(true)}>
            Registrar ingreso
          </button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        El dinero <b>entra</b> a la caja: se trae efectivo del banco para dar cambio, refuerzo de fondo, etc.
        Suma al efectivo esperado. Requiere autorización del admin.
      </p>
      {abierto && (
        <div className="form-pago" style={{ marginTop: 12 }}>
          <div className="form-field">
            <label>Monto que entra (L)</label>
            <input type="number" value={monto} onChange={e => setMonto(e.target.value)} placeholder="0.00" />
          </div>
          <div className="form-field">
            <label>Concepto</label>
            <input value={concepto} onChange={e => setConcepto(e.target.value)}
              placeholder="Ej. Efectivo traído del banco para cambio…" />
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

// ─── Modal: vender tarjeta en caja (cobra + asigna + baja stock) ─────────────
function ModalVenderTarjeta({ onCerrar, onVendida }: {
  onCerrar: () => void; onVendida: () => void;
}) {
  const [tipos, setTipos] = useState<TipoTarjetaDTO[]>([]);
  const [tipoSel, setTipoSel] = useState<TipoTarjetaDTO | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [resultados, setResultados] = useState<CuentaCajaDTO[]>([]);
  const [casaSel, setCasaSel] = useState<CuentaCajaDTO | null>(null);
  const [cardUid, setCardUid] = useState("");
  const [etiqueta, setEtiqueta] = useState("");
  const [portadorId, setPortadorId] = useState("");
  const [metodo, setMetodo] = useState("efectivo");
  const [error, setError] = useState("");
  const [ok, setOk] = useState<{ tipo: string; stock: number } | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    listarTiposTarjeta().then(ts => setTipos(ts.filter(t => t.activo))).catch(() => {});
  }, []);

  async function buscar() {
    if (busqueda.trim().length < 2) return;
    try { setResultados(await buscarCuentaCaja(busqueda)); } catch { setResultados([]); }
  }

  async function vender() {
    if (!tipoSel) { setError("Elegí el tipo de tarjeta"); return; }
    if (!casaSel) { setError("Elegí la casa"); return; }
    if (!cardUid.trim()) { setError("Ingresá el código (UID) de la tarjeta"); return; }
    if (!portadorId) { setError("Elegí el portador a quien se asigna la tarjeta"); return; }
    setError(""); setGuardando(true);
    try {
      const r = await venderTarjetaCaja({
        tipo_tarjeta_id: tipoSel.id, cuenta_id: casaSel.cuenta_id,
        card_uid: cardUid.trim(), metodo,
        etiqueta: etiqueta.trim() || undefined,
        residente_id: portadorId || undefined,
      });
      setOk({ tipo: tipoSel.nombre, stock: r.stock_restante });
    } catch (e) { setError((e as Error).message); }
    finally { setGuardando(false); }
  }

  if (ok) {
    return (
      <div className="modal" onClick={onVendida}>
        <div className="modal-body" onClick={e => e.stopPropagation()}>
          <div className="venta-ok">
            <div className="venta-ok-icon">✓</div>
            <h3>Tarjeta vendida</h3>
            <p className="muted">{ok.tipo} · cobrada y asignada a la casa.</p>
            <p className="muted small">Stock restante de este tipo: <b>{ok.stock}</b></p>
            <button className="cuota-btn-pagar full" onClick={onVendida}>Listo</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body modal-venta" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><h3><Ticket size={16} /> Vender tarjeta</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button></div>

        {/* Paso 1: tipo de tarjeta */}
        <div className="venta-paso">
          <label className="venta-label">1. Tipo de tarjeta</label>
          {tipos.length === 0 ? (
            <p className="muted small">No hay tipos de tarjeta configurados o con stock. Pedile al admin que los configure en Inventario.</p>
          ) : (
            <div className="venta-tipos">
              {tipos.map(t => (
                <button key={t.id} type="button"
                  className={`venta-tipo-card ${tipoSel?.id === t.id ? "sel" : ""} ${t.stock <= 0 ? "agotado" : ""}`}
                  disabled={t.stock <= 0}
                  onClick={() => setTipoSel(t)}>
                  <span className="venta-tipo-nombre">{t.nombre}</span>
                  <span className="venta-tipo-precio">{L(t.precio)}</span>
                  <span className={`pill ${t.stock === 0 ? "red" : t.stock <= 5 ? "amber" : "green"}`}>
                    {t.stock > 0 ? `${t.stock} en stock` : "Sin stock"}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Paso 2: casa */}
        <div className="venta-paso">
          <label className="venta-label">2. Casa</label>
          {casaSel ? (
            <div className="venta-casa-sel">
              <span>{casaSel.identificador} · {casaSel.titular}</span>
              <button className="ghost mini" onClick={() => { setCasaSel(null); setResultados([]); }}>Cambiar</button>
            </div>
          ) : (
            <>
              <div className="caja-buscar-row">
                <input value={busqueda} onChange={e => setBusqueda(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && buscar()}
                  placeholder="Buscar por casa o titular…" />
                <button className="ghost mini" onClick={buscar}>Buscar</button>
              </div>
              {resultados.map(c => (
                <button key={c.cuenta_id} type="button" className="venta-casa-opcion"
                  onClick={() => setCasaSel(c)}>
                  {c.identificador} · {c.titular}
                </button>
              ))}
              {busqueda.trim().length >= 2 && resultados.length === 0 && (
                <div className="venta-buscar-vacio">Tocá "Buscar" para ver resultados, o no se encontró ninguna casa.</div>
              )}
            </>
          )}
        </div>

        {/* Paso 3: UID de la tarjeta (con escáner) */}
        <div className="venta-paso">
          <label className="venta-label">3. Tarjeta física</label>
          <LectorTarjeta valor={cardUid} onLeida={setCardUid} />
          <input style={{ marginTop: 8, width: "100%" }} value={cardUid}
            onChange={e => setCardUid(e.target.value)}
            placeholder="…o ingresá el UID a mano" />
          <input style={{ marginTop: 8, width: "100%" }} value={etiqueta}
            onChange={e => setEtiqueta(e.target.value)}
            placeholder="Etiqueta (ej. Auto 1, opcional)" />
          {casaSel && casaSel.residentes && casaSel.residentes.length > 0 ? (
            <select style={{ marginTop: 8, width: "100%" }} value={portadorId}
              onChange={e => setPortadorId(e.target.value)}>
              <option value="">Portador (a quién se asigna) *…</option>
              {casaSel.residentes.map(r => (
                <option key={r.id} value={r.id}>{r.nombre}</option>
              ))}
            </select>
          ) : casaSel ? (
            <div className="venta-buscar-vacio" style={{ marginTop: 8 }}>
              Esta casa no tiene residentes registrados. Agregá un residente antes de venderle una tarjeta.
            </div>
          ) : null}
        </div>

        {/* Paso 4: método de pago */}
        <div className="venta-paso">
          <label className="venta-label">4. Método de cobro</label>
          <div className="caja-cobro-metodo">
            <button type="button" className={metodo === "efectivo" ? "sel" : ""}
              onClick={() => setMetodo("efectivo")}><Banknote size={16} /> Efectivo</button>
            <button type="button" className={metodo === "tarjeta_pos" ? "sel" : ""}
              onClick={() => setMetodo("tarjeta_pos")}><CreditCard size={16} /> POS</button>
          </div>
        </div>

        {tipoSel && (
          <div className="venta-total">
            <span>Total a cobrar</span><b>{L(tipoSel.precio)}</b>
          </div>
        )}
        {error && <div className="error">{error}</div>}
        <button className="cuota-btn-pagar full" onClick={vender} disabled={guardando}>
          {guardando ? "Procesando…" : "Cobrar y asignar tarjeta"}
        </button>
      </div>
    </div>
  );
}
