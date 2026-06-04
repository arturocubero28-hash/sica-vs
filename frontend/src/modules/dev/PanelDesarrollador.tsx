import { useState, useEffect } from "react";
import { devMetricas, devLogs, type DevMetricasDTO, type DevLogDTO } from "../../api/client";

const ROL_LABEL: Record<string, string> = {
  super_admin: "Super Admin", admin: "Administrador", cajero: "Cajero",
  guardia: "Guardia", residente: "Residente", desarrollador: "Desarrollador",
};

export function PanelDesarrollador() {
  const [m, setM] = useState<DevMetricasDTO | null>(null);
  const [logs, setLogs] = useState<DevLogDTO[]>([]);
  const [cargando, setCargando] = useState(true);

  function recargar() {
    Promise.all([devMetricas(), devLogs()])
      .then(([metricas, l]) => { setM(metricas); setLogs(l); })
      .catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => {
    recargar();
    const id = setInterval(recargar, 15000);  // refresca cada 15s
    return () => clearInterval(id);
  }, []);

  if (cargando) return <p className="muted">Cargando métricas…</p>;
  if (!m) return <p className="muted">No se pudieron cargar las métricas.</p>;

  return (
    <div className="dev-panel">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Panel del desarrollador</h2>
          <span className="muted">Salud y métricas del sistema</span>
        </div>
        <div className={`dev-estado ${m.db_conectada ? "ok" : "fail"}`}>
          <span className="dev-estado-dot" />
          {m.estado_sistema === "operativo" ? "Sistema operativo" : "Sistema degradado"}
        </div>
      </div>

      {/* Salud */}
      <div className="dev-grid">
        <div className="dev-card">
          <span className="dev-card-label">Base de datos</span>
          <span className={`dev-card-valor ${m.db_conectada ? "verde" : "rojo"}`}>
            {m.db_conectada ? "Conectada" : "Error"}
          </span>
        </div>
        <div className="dev-card">
          <span className="dev-card-label">Cajas abiertas</span>
          <span className="dev-card-valor">{m.cajas_abiertas}</span>
        </div>
        <div className="dev-card">
          <span className="dev-card-label">Accesos (24h)</span>
          <span className="dev-card-valor">{m.actividad_24h.eventos_acceso}</span>
        </div>
        <div className="dev-card">
          <span className="dev-card-label">Pagos (24h)</span>
          <span className="dev-card-valor">{m.actividad_24h.pagos}</span>
        </div>
      </div>

      {/* Conteos de la BD */}
      <div className="dash-card">
        <h3>Volumen de la base de datos</h3>
        <div className="dev-conteos">
          {Object.entries(m.conteos).map(([tabla, n]) => (
            <div key={tabla} className="dev-conteo">
              <span className="dev-conteo-num">{n}</span>
              <span className="dev-conteo-tabla">{tabla.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Usuarios por rol */}
      <div className="dash-card">
        <h3>Usuarios por rol</h3>
        <div className="dev-roles">
          {Object.entries(m.usuarios_por_rol).map(([rol, n]) => (
            <div key={rol} className="dev-rol-chip">
              <b>{n}</b> {ROL_LABEL[rol] || rol}
            </div>
          ))}
        </div>
      </div>

      {/* Bitácora técnica */}
      <div className="dash-card">
        <h3>Actividad reciente del sistema</h3>
        {logs.length === 0 ? (
          <p className="muted">Sin actividad registrada.</p>
        ) : (
          <div className="dev-logs">
            {logs.map((log, i) => (
              <div key={i} className="dev-log-item">
                <span className={`dev-log-tag ${log.tipo}`}>{log.tipo}</span>
                <span className="dev-log-desc">{log.descripcion}</span>
                <span className="dev-log-time muted small">
                  {log.timestamp ? new Date(log.timestamp).toLocaleString("es-HN") : "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="muted small" style={{ textAlign: "center" }}>
        Las métricas se actualizan automáticamente cada 15 segundos · Última: {new Date(m.timestamp).toLocaleTimeString("es-HN")}
      </p>
    </div>
  );
}
