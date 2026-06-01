import { useState, useEffect } from "react";
import {
  dashboardMetricas, dashboardVisitas, dashboardVisitasActivas, urlFotoGuardia,
  type MetricasDTO, type VisitaTablaDTO, type VisitaActivaDTO,
} from "../../api/client";

function horaCorta(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-HN", {
    day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

const tiposVisita: Record<string, string> = {
  unica: "Visita única", recurrente: "Recurrente", repartidor: "Repartidor",
};

export function DashboardAdmin() {
  const [m, setM] = useState<MetricasDTO | null>(null);
  const [visitas, setVisitas] = useState<VisitaTablaDTO[]>([]);
  const [vistaActivas, setVistaActivas] = useState(false);

  useEffect(() => {
    dashboardMetricas().then(setM).catch(() => {});
    dashboardVisitas().then(setVisitas).catch(() => {});
  }, []);

  if (vistaActivas) {
    return <VisitasAdentro onVolver={() => setVistaActivas(false)} totalEsperado={m?.adentro_ahora} />;
  }

  const estadoColor: Record<string, string> = {
    activa: "green", adentro: "green", salio: "", expirada: "", revocada: "red",
  };
  const estadoLabel: Record<string, string> = {
    activa: "Activa", adentro: "Adentro 🟢", salio: "Salió ✓",
    expirada: "Expirada", revocada: "Cancelada",
  };

  return (
    <div className="dash">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Panel de control</h2>
          <span className="muted">Residencial Villas del Sol</span>
        </div>
        <div className="dash-fecha">
          <span className="dash-fecha-dia">{new Date().toLocaleDateString("es-HN", { weekday: "long" })}</span>
          <span className="dash-fecha-completa">{new Date().toLocaleDateString("es-HN", { day: "numeric", month: "long", year: "numeric" })}</span>
        </div>
      </div>

      {/* MÉTRICA PRINCIPAL — visitas adentro ahora (clicable) */}
      <button className="hero-metric" onClick={() => setVistaActivas(true)}>
        <div className="hero-left">
          <span className="hero-label">Visitas dentro de la residencial</span>
          <span className="hero-valor">{m?.adentro_ahora ?? "—"}</span>
          <span className="hero-hint">Toca para ver el detalle, fotos y filtrar por placa →</span>
        </div>
        <div className="hero-icon">🚗</div>
      </button>

      {/* Métricas secundarias relevantes */}
      <div className="metric-grid">
        <MetricCard label="QR activos ahora" valor={m?.visitantes_activos} icon="●" color="verde" />
        <MetricCard label="Accesos hoy" valor={m?.accesos_hoy} icon="✓" color="azul" />
        <MetricCard label="QR generados hoy" valor={m?.qr_generados_hoy} icon="QR" color="naranja" />
        <MetricCard label="Cuentas en mora" valor={m?.cuentas_bloqueadas} icon="!"
          color={m?.cuentas_bloqueadas ? "rojo" : "gris"} />
      </div>

      {/* Resumen del padrón */}
      <div className="padron-card">
        <div className="padron-titulo muted small">Padrón de la residencial</div>
        <div className="padron-grid">
          <div className="padron-item">
            <span className="padron-icon">🏘️</span>
            <div><b>{m?.total_unidades ?? "—"}</b><span>Casas / Edificios</span></div>
          </div>
          <div className="padron-item">
            <span className="padron-icon">📄</span>
            <div><b>{m?.total_cuentas ?? "—"}</b><span>Cuentas</span></div>
          </div>
          <div className="padron-item">
            <span className="padron-icon">👥</span>
            <div><b>{m?.total_residentes ?? "—"}</b><span>Residentes</span></div>
          </div>
        </div>
      </div>

      {/* Tabla de visitas recientes */}
      <div className="dash-card">
        <h3>Actividad reciente de QR</h3>
        {visitas.length === 0 ? (
          <p className="muted">No hay visitas registradas todavía.</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr><th>Residente</th><th>Unidad</th><th>Visitante</th><th>Tipo</th><th>Estado</th></tr>
              </thead>
              <tbody>
                {visitas.map(v => (
                  <tr key={v.id}>
                    <td>{v.residente}</td>
                    <td>{v.unidad}</td>
                    <td>{v.visitante}</td>
                    <td>{tiposVisita[v.tipo] || v.tipo}</td>
                    <td><span className={`pill ${estadoColor[v.estado] || ""}`}>{estadoLabel[v.estado] || v.estado}</span></td>
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

// ─── Vista de visitas DENTRO de la residencial ───────────────
function VisitasAdentro({ onVolver, totalEsperado }: { onVolver: () => void; totalEsperado?: number }) {
  const [lista, setLista] = useState<VisitaActivaDTO[]>([]);
  const [filtro, setFiltro] = useState("");
  const [cargando, setCargando] = useState(true);
  const [detalle, setDetalle] = useState<VisitaActivaDTO | null>(null);

  useEffect(() => {
    dashboardVisitasActivas()
      .then(setLista)
      .catch(() => {})
      .finally(() => setCargando(false));
  }, []);

  const q = filtro.trim().toLowerCase();
  const filtradas = q
    ? lista.filter(v =>
        (v.placa || "").toLowerCase().includes(q) ||
        v.visitante.toLowerCase().includes(q) ||
        v.unidad.toLowerCase().includes(q) ||
        v.residente.toLowerCase().includes(q) ||
        (v.empresa || "").toLowerCase().includes(q))
    : lista;

  return (
    <div className="dash">
      <div className="dash-head with-back">
        <button className="ghost mini" onClick={onVolver}>← Volver</button>
        <h2>Visitas dentro de la residencial</h2>
        <span className="pill green big">{lista.length} adentro</span>
      </div>

      {/* Buscador — caso del carro mal estacionado */}
      <div className="filtro-box">
        <span className="filtro-icon">🔍</span>
        <input
          placeholder="Filtrar por placa, nombre, unidad o empresa…"
          value={filtro}
          onChange={e => setFiltro(e.target.value)}
          autoFocus
        />
        {filtro && <button className="filtro-clear" onClick={() => setFiltro("")}>✕</button>}
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : filtradas.length === 0 ? (
        <p className="muted">
          {lista.length === 0
            ? "No hay visitas dentro de la residencial en este momento."
            : "Ninguna visita coincide con la búsqueda."}
        </p>
      ) : (
        <div className="activas-list">
          {filtradas.map(v => (
            <div key={v.id} className="activa-card" onClick={() => setDetalle(v)}>
              <div className="activa-top">
                <div>
                  <div className="activa-nombre">{v.visitante}</div>
                  <div className="muted small">{tiposVisita[v.tipo] || v.tipo}{v.empresa ? ` · ${v.empresa}` : ""}</div>
                </div>
                {v.placa && <span className="placa-badge">{v.placa}</span>}
              </div>
              <div className="activa-meta">
                <span><b>Unidad:</b> {v.unidad}</span>
                <span><b>Autorizó QR:</b> {v.residente}</span>
              </div>
              <div className="activa-horas">
                <span>🟢 Entró: {horaCorta(v.hora_entrada)}</span>
                <span className="muted small">Ver detalle →</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {detalle && <DetalleVisita visita={detalle} onCerrar={() => setDetalle(null)} />}
    </div>
  );
}

// ─── Modal de detalle completo de una visita ─────────────────
function DetalleVisita({ visita, onCerrar }: { visita: VisitaActivaDTO; onCerrar: () => void }) {
  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{visita.visitante}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        {visita.placa && (
          <div className="detalle-placa">
            <span className="muted small">Placa del vehículo</span>
            <span className="placa-badge grande">{visita.placa}</span>
          </div>
        )}

        <div className="detalle-grid">
          <Dato label="Tipo de visita" valor={tiposVisita[visita.tipo] || visita.tipo} />
          {visita.empresa && <Dato label="Empresa" valor={visita.empresa} />}
          {visita.documento_id && <Dato label="Documento" valor={visita.documento_id} />}
          {visita.telefono && <Dato label="Teléfono" valor={visita.telefono} />}
          <Dato label="Unidad" valor={visita.unidad} />
          <Dato label="QR generado por" valor={visita.residente} />
          {visita.guardia_autorizo && <Dato label="Guardia que autorizó" valor={visita.guardia_autorizo} />}
        </div>

        <div className="sub">Línea de tiempo</div>
        <div className="timeline">
          <div className="tl-item">
            <span className="tl-dot azul" />
            <span className="tl-label">QR creado</span>
            <span className="tl-hora">{horaCorta(visita.hora_creacion)}</span>
          </div>
          <div className="tl-item">
            <span className="tl-dot verde" />
            <span className="tl-label">Ingresó</span>
            <span className="tl-hora">{horaCorta(visita.hora_entrada)}</span>
          </div>
          <div className="tl-item">
            <span className="tl-dot gris" />
            <span className="tl-label">Salió</span>
            <span className="tl-hora">{visita.hora_salida ? horaCorta(visita.hora_salida) : "Aún adentro"}</span>
          </div>
        </div>

        {(visita.foto_identidad || visita.foto_placa) && (
          <>
            <div className="sub">Fotos del ingreso</div>
            <div className="detalle-fotos">
              {visita.foto_identidad && (
                <div className="foto-detalle">
                  <span className="muted small">Identidad</span>
                  <img src={urlFotoGuardia(visita.foto_identidad)} alt="Identidad" />
                </div>
              )}
              {visita.foto_placa && (
                <div className="foto-detalle">
                  <span className="muted small">Placa / Vehículo</span>
                  <img src={urlFotoGuardia(visita.foto_placa)} alt="Placa" />
                </div>
              )}
            </div>
          </>
        )}
      </div>
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
