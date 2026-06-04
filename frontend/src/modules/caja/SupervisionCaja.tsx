import { useState, useEffect } from "react";
import { listarSesionesCaja, detalleSesionCaja, type SesionCajaDTO } from "../../api/client";

function L(n: number) {
  return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function SupervisionCaja() {
  const [sesiones, setSesiones] = useState<SesionCajaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [detalle, setDetalle] = useState<SesionCajaDTO | null>(null);

  useEffect(() => {
    listarSesionesCaja().then(setSesiones).catch(() => {}).finally(() => setCargando(false));
  }, []);

  if (cargando) return <p className="muted">Cargando…</p>;

  const abiertas = sesiones.filter(s => s.estado === "abierta");
  const totalRecaudadoHoy = sesiones
    .filter(s => new Date(s.abierta_en).toDateString() === new Date().toDateString())
    .reduce((acc, s) => acc + s.total_efectivo + s.total_pos, 0);

  return (
    <div className="supervision">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Supervisión de caja</h2>
          <span className="muted">Sesiones de caja de los cajeros</span>
        </div>
      </div>

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
    </div>
  );
}
