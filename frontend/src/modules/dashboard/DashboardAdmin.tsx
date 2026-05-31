import { useState, useEffect } from "react";
import {
  dashboardMetricas, dashboardVisitas,
  type MetricasDTO, type VisitaTablaDTO,
} from "../../api/client";

export function DashboardAdmin() {
  const [m, setM] = useState<MetricasDTO | null>(null);
  const [visitas, setVisitas] = useState<VisitaTablaDTO[]>([]);

  useEffect(() => {
    dashboardMetricas().then(setM).catch(() => {});
    dashboardVisitas().then(setVisitas).catch(() => {});
  }, []);

  const tipos: Record<string, string> = {
    unica: "Visita unica", recurrente: "Recurrente", repartidor: "Repartidor",
  };
  const estadoColor: Record<string, string> = {
    activa: "green", usada: "amber", expirada: "", revocada: "red",
  };
  const estadoLabel: Record<string, string> = {
    activa: "Activa", usada: "Ingreso", expirada: "Expirada", revocada: "Revocada",
  };

  return (
    <div className="dash">
      <div className="dash-head">
        <h2>Centro de Monitoreo</h2>
        <span className="muted">Villas del Sol · datos en vivo</span>
      </div>

      {/* Tarjetas de metricas */}
      <div className="metric-grid">
        <MetricCard label="QR generados hoy" valor={m?.qr_generados_hoy} icon="QR" color="azul" />
        <MetricCard label="Visitantes activos" valor={m?.visitantes_activos} icon="●" color="verde" />
        <MetricCard label="QR utilizados" valor={m?.qr_utilizados} icon="✓" color="naranja" />
        <MetricCard label="QR expirados" valor={m?.qr_expirados} icon="!" color="gris" />
      </div>

      {/* Segunda fila de metricas */}
      <div className="metric-grid small">
        <MiniMetric label="Casas / Edificios" valor={m?.total_unidades} />
        <MiniMetric label="Cuentas" valor={m?.total_cuentas} />
        <MiniMetric label="Residentes" valor={m?.total_residentes} />
        <MiniMetric label="Accesos hoy" valor={m?.accesos_hoy} />
        <MiniMetric label="Bloqueadas (mora)" valor={m?.cuentas_bloqueadas} alerta={!!m?.cuentas_bloqueadas} />
      </div>

      {/* Tabla de visitas */}
      <div className="dash-card">
        <h3>Visitas y QR recientes</h3>
        {visitas.length === 0 ? (
          <p className="muted">No hay visitas registradas todavia.</p>
        ) : (
          <table className="data">
            <thead>
              <tr><th>Residente</th><th>Unidad</th><th>Visitante</th><th>Tipo</th><th>Vigencia</th><th>Estado</th></tr>
            </thead>
            <tbody>
              {visitas.map(v => (
                <tr key={v.id}>
                  <td>{v.residente}</td>
                  <td>{v.unidad}</td>
                  <td>{v.visitante}</td>
                  <td>{tipos[v.tipo] || v.tipo}</td>
                  <td className="small">{v.vigencia}</td>
                  <td><span className={`pill ${estadoColor[v.estado] || ""}`}>{estadoLabel[v.estado] || v.estado}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, valor, icon, color }:
  { label: string; valor?: number; icon: string; color: string }) {
  return (
    <div className={`metric-card ${color}`}>
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className="metric-icon">{icon}</span>
      </div>
      <div className="metric-valor">{valor ?? "—"}</div>
    </div>
  );
}

function MiniMetric({ label, valor, alerta }:
  { label: string; valor?: number; alerta?: boolean }) {
  return (
    <div className={`mini-metric ${alerta ? "alerta" : ""}`}>
      <div className="mini-valor">{valor ?? "—"}</div>
      <div className="mini-label">{label}</div>
    </div>
  );
}
