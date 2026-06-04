import { useState, useEffect, useCallback } from "react";
import { devMetricas, devLogs, type DevMetricasDTO } from "../../api/client";

export function PanelDesarrollador() {
  const [m, setM] = useState<DevMetricasDTO | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [cargando, setCargando] = useState(true);
  const [tab, setTab] = useState<"salud" | "logs">("salud");
  // Filtros de logs
  const [email, setEmail] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [soloErrores, setSoloErrores] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPags, setTotalPags] = useState(1);
  const [totalLogs, setTotalLogs] = useState(0);
  const [cargandoLogs, setCargandoLogs] = useState(false);

  const cargarMetricas = useCallback(() => {
    devMetricas().then(setM).catch(() => {}).finally(() => setCargando(false));
  }, []);

  const cargarLogs = useCallback(() => {
    setCargandoLogs(true);
    devLogs({ email, endpoint, errores: soloErrores ? "1" : "", pagina })
      .then((r: any) => {
        setLogs(r.logs || []);
        setTotalPags(r.total_paginas || 1);
        setTotalLogs(r.total || 0);
      }).catch(() => {}).finally(() => setCargandoLogs(false));
  }, [email, endpoint, soloErrores, pagina]);

  useEffect(() => {
    cargarMetricas();
    const id = setInterval(cargarMetricas, 15000);
    return () => clearInterval(id);
  }, [cargarMetricas]);

  useEffect(() => {
    if (tab === "logs") cargarLogs();
  }, [tab, cargarLogs]);

  function Barra({ pct, color }: { pct: number; color: string }) {
    const c = pct > 85 ? "#e53e3e" : pct > 65 ? "#F48723" : color;
    return (
      <div style={{ background: "#1a3347", borderRadius: 6, height: 10, overflow: "hidden", margin: "6px 0" }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", background: c, borderRadius: 6, transition: "width .4s" }} />
      </div>
    );
  }

  return (
    <div className="dev-panel">
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Panel del desarrollador</h2>
          <span className="muted">Salud del sistema y auditoría forense</span>
        </div>
        {m && (
          <div className={`dev-estado ${m.db_conectada && m.redis?.conectado ? "ok" : "fail"}`}>
            <span className="dev-estado-dot" />
            {m.estado_general === "operativo" ? "Sistema operativo" : "Sistema degradado"}
          </div>
        )}
      </div>

      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "salud" ? "on" : ""}`} onClick={() => setTab("salud")}>🖥️ Salud del sistema</button>
        <button className={`hist-tab ${tab === "logs" ? "on" : ""}`} onClick={() => setTab("logs")}>🔍 Logs de auditoría</button>
      </div>

      {tab === "salud" && (
        cargando ? <p className="muted">Cargando métricas…</p> :
        !m ? <p className="muted">No se pudieron cargar las métricas.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Tarjetas de servicios */}
            <div className="dev-grid">
              <div className="dev-card">
                <span className="dev-card-label">Base de datos</span>
                <span className={`dev-card-valor ${m.db_conectada ? "verde" : "rojo"}`}>
                  {m.db_conectada ? "Conectada" : "Error"}
                </span>
                {m.db_latencia_ms != null && <span className="muted small">{m.db_latencia_ms} ms latencia</span>}
                {m.db_error && <span className="dev-error-msg">{m.db_error}</span>}
              </div>
              <div className="dev-card">
                <span className="dev-card-label">Redis (caché / cola)</span>
                <span className={`dev-card-valor ${m.redis?.conectado ? "verde" : "rojo"}`}>
                  {m.redis?.conectado ? "Conectado" : "Error"}
                </span>
                {m.redis?.error && <span className="dev-error-msg">{m.redis.error}</span>}
              </div>
              <div className="dev-card">
                <span className="dev-card-label">CPU</span>
                <span className="dev-card-valor" style={{ color: (m.sistema?.cpu_porcentaje || 0) > 85 ? "#e53e3e" : "#2ecc71" }}>
                  {m.sistema?.cpu_porcentaje ?? "—"}%
                </span>
              </div>
              <div className="dev-card">
                <span className="dev-card-label">Errores 500 recientes</span>
                <span className={`dev-card-valor ${(m.errores_recientes?.length || 0) > 0 ? "rojo" : "verde"}`}>
                  {m.errores_recientes?.length ?? 0}
                </span>
              </div>
            </div>

            {/* Disco y RAM */}
            {m.sistema?.disco && (
              <div className="dash-card">
                <h3>Recursos del servidor</h3>
                <div className="dev-recurso">
                  <div className="dev-recurso-header">
                    <span>Disco</span>
                    <span className="muted small">{m.sistema.disco.usado_gb} GB usados de {m.sistema.disco.total_gb} GB ({m.sistema.disco.porcentaje}%)</span>
                  </div>
                  <Barra pct={m.sistema.disco.porcentaje} color="#2ecc71" />
                  <span className="muted small">Libre: {m.sistema.disco.libre_gb} GB</span>
                </div>
                <div className="dev-recurso" style={{ marginTop: 14 }}>
                  <div className="dev-recurso-header">
                    <span>RAM</span>
                    <span className="muted small">{m.sistema.ram.usado_gb} GB usados de {m.sistema.ram.total_gb} GB ({m.sistema.ram.porcentaje}%)</span>
                  </div>
                  <Barra pct={m.sistema.ram.porcentaje} color="#3498db" />
                  <span className="muted small">Disponible: {m.sistema.ram.libre_gb} GB</span>
                </div>
              </div>
            )}

            {/* Errores recientes */}
            {m.errores_recientes && m.errores_recientes.length > 0 && (
              <div className="dash-card" style={{ borderLeft: "3px solid #e53e3e" }}>
                <h3 style={{ color: "#e53e3e" }}>Errores 500 recientes</h3>
                <div className="dev-logs">
                  {m.errores_recientes.map((e: any, i: number) => (
                    <div key={i} className="dev-log-item">
                      <span className="dev-log-tag" style={{ background: "#fdecec", color: "#c81e1e" }}>{e.status_code}</span>
                      <span className="dev-log-desc">{e.metodo} {e.endpoint}</span>
                      <span className="muted small">{e.email} · {e.ip}</span>
                      <span className="dev-log-time muted small">{e.created_at ? new Date(e.created_at).toLocaleString("es-HN") : "—"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="muted small" style={{ textAlign: "center" }}>
              Auto-actualización cada 15s · {m.timestamp ? new Date(m.timestamp).toLocaleTimeString("es-HN") : ""}
            </p>
          </div>
        )
      )}

      {tab === "logs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Filtros */}
          <div className="historial-filtros">
            <div className="filtro-campo flex1">
              <label>Usuario (correo)</label>
              <input placeholder="Filtrar por email…" value={email} onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === "Enter" && cargarLogs()} />
            </div>
            <div className="filtro-campo flex1">
              <label>Endpoint</label>
              <input placeholder="/api/v1/auth/login…" value={endpoint} onChange={e => setEndpoint(e.target.value)}
                onKeyDown={e => e.key === "Enter" && cargarLogs()} />
            </div>
            <div className="filtro-campo" style={{ justifyContent: "flex-end", paddingTop: 20 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={soloErrores} onChange={e => setSoloErrores(e.target.checked)} />
                Solo errores (4xx/5xx)
              </label>
            </div>
            <div className="filtro-botones">
              <button className="cuota-btn-pagar" style={{ maxWidth: 110 }} onClick={() => { setPagina(1); cargarLogs(); }}>Filtrar</button>
              <button className="ghost mini" onClick={() => { setEmail(""); setEndpoint(""); setSoloErrores(false); setPagina(1); setTimeout(cargarLogs, 0); }}>Limpiar</button>
            </div>
          </div>

          {cargandoLogs ? <p className="muted">Cargando logs…</p> : logs.length === 0 ? (
            <div className="cuota-vacia"><div className="cuota-vacia-icon">🔍</div><p>Sin logs que coincidan.</p></div>
          ) : (
            <>
              <div className="dash-card" style={{ padding: 0 }}>
                <div className="scroll-x">
                  <table className="data">
                    <thead>
                      <tr><th>Fecha / Hora</th><th>Usuario</th><th>Rol</th><th>Método</th><th>Endpoint</th><th>Status</th><th>IP</th></tr>
                    </thead>
                    <tbody>
                      {logs.map((l: any, i: number) => (
                        <tr key={i} className={l.status_code >= 500 ? "fila-error" : l.status_code >= 400 ? "fila-warn" : ""}>
                          <td className="small">{l.created_at ? new Date(l.created_at).toLocaleString("es-HN") : "—"}</td>
                          <td className="small">{l.email}</td>
                          <td><span className="pill">{l.rol}</span></td>
                          <td><span className="dev-method">{l.metodo}</span></td>
                          <td className="small" style={{ fontFamily: "monospace", fontSize: 11 }}>{l.endpoint}</td>
                          <td><span className={`pill ${l.status_code < 300 ? "green" : l.status_code < 500 ? "" : "red"}`}>{l.status_code}</span></td>
                          <td className="small">{l.ip}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="paginacion">
                <button className="ghost mini" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>← Anterior</button>
                <span className="muted small">Página {pagina} de {totalPags} · {totalLogs} entradas</span>
                <button className="ghost mini" disabled={pagina >= totalPags} onClick={() => setPagina(p => p + 1)}>Siguiente →</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
