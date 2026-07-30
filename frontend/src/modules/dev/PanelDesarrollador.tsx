import { useState, useEffect, useCallback } from "react";
import { devMetricas, devLogs, devMetricasCodigo, devSeguridad, devAccesosFisicos, devConfigurarAcceso, devHistorialCount, devEliminarAcceso, devDispositivos, devCrearDispositivo, devActualizarDispositivo, devRegenerarToken, devEliminarDispositivo, devResidenciales, devUsuariosDeResidencial, devCrearResidencial, urlLogoResidencial, type DevMetricasDTO, type MetricasCodigoDTO, type SeguridadDTO, type AccesoFisicoDTO, type DispositivoDTO, type ResidencialDTO, type UsuarioResidencialDTO } from "../../api/client";
import { AlertTriangle, BarChart3, Building2, Construction, Cpu, Key, Lock, Monitor, Radio, Router, Search, Shield, ThumbsUp, TrafficCone, Trash2 } from "lucide-react";

export function PanelDesarrollador() {
  const [m, setM] = useState<DevMetricasDTO | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [cargando, setCargando] = useState(true);
  const [tab, setTab] = useState<"salud" | "logs" | "codigo" | "seguridad" | "trancas" | "pis" | "residenciales">("salud");
  // Filtros de logs
  const [email, setEmail] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [soloErrores, setSoloErrores] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPags, setTotalPags] = useState(1);
  const [totalLogs, setTotalLogs] = useState(0);
  const [cargandoLogs, setCargandoLogs] = useState(false);
  // Día 48, a pedido del usuario: filtro de logs por residencial.
  const [residencialLog, setResidencialLog] = useState("");
  const [residencialesLog, setResidencialesLog] = useState<ResidencialDTO[]>([]);

  const cargarMetricas = useCallback(() => {
    devMetricas().then(setM).catch(() => {}).finally(() => setCargando(false));
  }, []);

  const cargarLogs = useCallback(() => {
    setCargandoLogs(true);
    devLogs({ email, endpoint, errores: soloErrores ? "1" : "", pagina, residencialId: residencialLog || undefined })
      .then((r: any) => {
        setLogs(r.logs || []);
        setTotalPags(r.total_paginas || 1);
        setTotalLogs(r.total || 0);
      }).catch(() => {}).finally(() => setCargandoLogs(false));
  }, [email, endpoint, soloErrores, pagina, residencialLog]);

  useEffect(() => {
    cargarMetricas();
    const id = setInterval(cargarMetricas, 15000);
    return () => clearInterval(id);
  }, [cargarMetricas]);

  useEffect(() => {
    if (tab === "logs") {
      cargarLogs();
      if (residencialesLog.length === 0) {
        devResidenciales().then(setResidencialesLog).catch(() => {});
      }
    }
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
          <div className={`dev-estado ${m.db_conectada ? "ok" : "fail"}`}>
            <span className="dev-estado-dot" />
            {m.estado_general === "operativo" ? "Sistema operativo" : "Sistema degradado"}
          </div>
        )}
      </div>

      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "salud" ? "on" : ""}`} onClick={() => setTab("salud")}><Monitor size={16} /> Salud del sistema</button>
        <button className={`hist-tab ${tab === "logs" ? "on" : ""}`} onClick={() => setTab("logs")}><Search size={16} /> Logs de auditoría</button>
        <button className={`hist-tab ${tab === "codigo" ? "on" : ""}`} onClick={() => setTab("codigo")}><BarChart3 size={16} /> Métricas de código</button>
        <button className={`hist-tab ${tab === "seguridad" ? "on" : ""}`} onClick={() => setTab("seguridad")}><Shield size={16} /> Seguridad</button>
        <button className={`hist-tab ${tab === "trancas" ? "on" : ""}`} onClick={() => setTab("trancas")}><Construction size={16} /> Trancas</button>
        <button className={`hist-tab ${tab === "pis" ? "on" : ""}`} onClick={() => setTab("pis")}><Router size={16} /> Controladores de acceso</button>
        <button className={`hist-tab ${tab === "residenciales" ? "on" : ""}`} onClick={() => setTab("residenciales")}><Building2 size={16} /> Residenciales</button>
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
            {m.sistema?.error ? (
              <div className="dash-card">
                <h3>Recursos del servidor</h3>
                <p className="muted small"><AlertTriangle size={16} /> {m.sistema.error}</p>
              </div>
            ) : m.sistema?.disco && (
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
                {m.sistema.ram && (
                <div className="dev-recurso" style={{ marginTop: 14 }}>
                  <div className="dev-recurso-header">
                    <span>RAM</span>
                    <span className="muted small">{m.sistema.ram.usado_gb} GB usados de {m.sistema.ram.total_gb} GB ({m.sistema.ram.porcentaje}%)</span>
                  </div>
                  <Barra pct={m.sistema.ram.porcentaje} color="#3498db" />
                  <span className="muted small">Disponible: {m.sistema.ram.libre_gb} GB</span>
                </div>
                )}
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
            <div className="filtro-campo flex1">
              <label>Residencial</label>
              <select value={residencialLog} onChange={e => setResidencialLog(e.target.value)}>
                <option value="">Todas</option>
                {residencialesLog.map(r => <option key={r.id} value={r.id}>{r.nombre}</option>)}
              </select>
            </div>
            <div className="filtro-campo" style={{ justifyContent: "flex-end", paddingTop: 20 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={soloErrores} onChange={e => setSoloErrores(e.target.checked)} />
                Solo errores (4xx/5xx)
              </label>
            </div>
            <div className="filtro-botones">
              <button className="cuota-btn-pagar" style={{ maxWidth: 110 }} onClick={() => { setPagina(1); cargarLogs(); }}>Filtrar</button>
              <button className="ghost mini" onClick={() => { setEmail(""); setEndpoint(""); setSoloErrores(false); setResidencialLog(""); setPagina(1); setTimeout(cargarLogs, 0); }}>Limpiar</button>
            </div>
          </div>

          {cargandoLogs ? <p className="muted">Cargando logs…</p> : logs.length === 0 ? (
            <div className="cuota-vacia"><div className="cuota-vacia-icon"><Search size={16} /></div><p>Sin logs que coincidan.</p></div>
          ) : (
            <>
              <div className="dash-card" style={{ padding: 0 }}>
                <div className="scroll-x">
                  <table className="data">
                    <thead>
                      <tr><th>Fecha / Hora</th><th>Usuario</th><th>Residencial</th><th>Acción</th><th>Status</th><th>IP</th></tr>
                    </thead>
                    <tbody>
                      {logs.map((l: any, i: number) => (
                        <tr key={i} className={l.status_code >= 500 ? "fila-error" : l.status_code >= 400 ? "fila-warn" : ""}>
                          <td className="small">{l.created_at ? new Date(l.created_at).toLocaleString("es-HN") : "—"}</td>
                          <td>
                            <div style={{ lineHeight: 1.3 }}>
                              <span style={{ fontSize: 13, fontWeight: 600 }}>{l.email}</span>
                              <br/><span className="pill" style={{ fontSize: 10 }}>{l.rol}</span>
                            </div>
                          </td>
                          <td className="small muted">{l.residencial?.nombre || "—"}</td>
                          <td>
                            <div style={{ lineHeight: 1.4 }}>
                              <span style={{ fontSize: 13 }}>{l.descripcion}</span>
                              <br/><span style={{ fontFamily: "monospace", fontSize: 10, color: "#6b7280" }}>{l.metodo} {l.endpoint}</span>
                            </div>
                          </td>
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

      {tab === "codigo" && <MetricasCodigo />}
      {tab === "seguridad" && <PanelSeguridad />}
      {tab === "trancas" && <ConfigTrancas />}
      {tab === "pis" && <ConfigPis />}
      {tab === "residenciales" && <PanelResidenciales />}
    </div>
  );
}

function MetricasCodigo() {
  const [m, setM] = useState<MetricasCodigoDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    devMetricasCodigo().then(setM).catch(() => {}).finally(() => setCargando(false));
  }, []);

  if (cargando) return <p className="muted">Analizando el código…</p>;
  if (!m) return <p className="muted">No se pudieron cargar las métricas.</p>;

  const rankColor: Record<string, string> = {
    A: "#1d8a4a", B: "#5b9e3f", C: "#d89000", D: "#e06a00", E: "#d83a00", F: "#c81e1e",
  };

  return (
    <div className="dev-codigo">
      {/* Líneas de código */}
      <div className="dash-card">
        <h3>Líneas de código</h3>
        <div className="metric-grid">
          <div className="metric-card azul">
            <div className="metric-top"><span className="metric-label">Total</span></div>
            <div className="metric-valor" style={{ fontSize: 22 }}>{m.loc.total.toLocaleString()}</div>
          </div>
          <div className="metric-card verde">
            <div className="metric-top"><span className="metric-label">Backend Python</span></div>
            <div className="metric-valor" style={{ fontSize: 20 }}>{m.loc.backend_python.toLocaleString()}</div>
            <span className="muted small">{m.loc.backend_archivos} archivos</span>
          </div>
          <div className="metric-card naranja">
            <div className="metric-top"><span className="metric-label">Frontend TS/TSX</span></div>
            <div className="metric-valor" style={{ fontSize: 20 }}>{m.loc.frontend_ts.toLocaleString()}</div>
            <span className="muted small">{m.loc.frontend_archivos} archivos</span>
          </div>
          <div className="metric-card">
            <div className="metric-top"><span className="metric-label">CSS</span></div>
            <div className="metric-valor" style={{ fontSize: 20 }}>{m.loc.css.toLocaleString()}</div>
          </div>
        </div>
      </div>

      {!m.radon_disponible ? (
        <div className="dash-card"><p className="muted">El análisis de complejidad (radon) no está disponible en este entorno.</p></div>
      ) : (
        <>
          {/* Complejidad ciclomática */}
          <div className="dash-card">
            <h3>Complejidad ciclomática (McCabe)</h3>
            <p className="muted small">Mide los caminos independientes del código. Más bajo = más simple de probar y mantener.</p>
            <div className="metric-grid">
              <div className="metric-card" style={{ borderTop: `3px solid ${rankColor[m.complejidad.rank_promedio]}` }}>
                <div className="metric-top"><span className="metric-label">Promedio</span></div>
                <div className="metric-valor" style={{ color: rankColor[m.complejidad.rank_promedio] }}>
                  {m.complejidad.promedio} <span style={{ fontSize: 14 }}>({m.complejidad.rank_promedio})</span>
                </div>
              </div>
              <div className="metric-card azul">
                <div className="metric-top"><span className="metric-label">Bloques analizados</span></div>
                <div className="metric-valor" style={{ fontSize: 22 }}>{m.complejidad.total_bloques}</div>
              </div>
            </div>

            {/* Distribución por rango */}
            <div className="cc-dist">
              {["A","B","C","D","E","F"].map(r => {
                const cant = m.complejidad.distribucion[r] || 0;
                const pct = m.complejidad.total_bloques ? (cant / m.complejidad.total_bloques * 100) : 0;
                return (
                  <div key={r} className="cc-dist-row">
                    <span className="cc-rank" style={{ background: rankColor[r] }}>{r}</span>
                    <div className="cc-bar-track">
                      <div className="cc-bar-fill" style={{ width: `${pct}%`, background: rankColor[r] }} />
                    </div>
                    <span className="muted small">{cant}</span>
                  </div>
                );
              })}
            </div>
            <p className="muted small" style={{ marginTop: 8 }}>
              A (1-5): simple · B (6-10): bien · C (11-20): moderado · D+ : revisar
            </p>
          </div>

          {/* Funciones más complejas */}
          <div className="dash-card">
            <h3>Funciones más complejas</h3>
            <div className="scroll-x">
              <table className="data">
                <thead><tr><th>Función</th><th>Archivo</th><th>Complejidad</th></tr></thead>
                <tbody>
                  {m.complejidad.mas_complejos.map((f, i) => (
                    <tr key={i}>
                      <td><b>{f.nombre}</b></td>
                      <td className="small">{f.archivo}</td>
                      <td><span className="pill" style={{ background: rankColor[f.rank], color: "#fff" }}>
                        {f.complejidad} ({f.rank})</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Índice de mantenibilidad */}
          <div className="dash-card">
            <h3>Índice de mantenibilidad</h3>
            <p className="muted small">Escala 0-100 (más alto = más mantenible). Promedio del proyecto: <b>{m.resumen.mi_promedio}</b></p>
            <div className="scroll-x">
              <table className="data">
                <thead><tr><th>Archivo</th><th>Índice</th><th>Rango</th></tr></thead>
                <tbody>
                  {m.mantenibilidad.slice(0, 12).map((a, i) => (
                    <tr key={i}>
                      <td className="small">{a.archivo}</td>
                      <td>{a.mi}</td>
                      <td><span className="pill" style={{ background: rankColor[a.rank], color: "#fff" }}>{a.rank}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small" style={{ marginTop: 6 }}>Mostrando los 12 archivos con menor índice (los que más conviene vigilar).</p>
          </div>
        </>
      )}
    </div>
  );
}

function PanelSeguridad() {
  const [s, setS] = useState<SeguridadDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    devSeguridad().then(setS).catch(() => {}).finally(() => setCargando(false));
  }, []);

  if (cargando) return <p className="muted">Analizando intentos de ataque…</p>;
  if (!s) return <p className="muted">No se pudieron cargar las métricas de seguridad.</p>;

  const alerta = {
    bajo: { color: "#1d8a4a", txt: "Bajo", desc: "Sin actividad sospechosa relevante" },
    medio: { color: "#d89000", txt: "Medio", desc: "Actividad inusual detectada — vigilar" },
    alto: { color: "#c81e1e", txt: "Alto", desc: "Posible ataque en curso — revisar" },
  }[s.nivel_alerta];

  const maxTl = Math.max(...s.timeline_7d.map(t => t.fallidos), 1);

  return (
    <div className="dev-codigo">
      {/* Nivel de alerta */}
      <div className="dash-card" style={{ borderLeft: `5px solid ${alerta.color}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 28 }}><Shield size={16} /></span>
          <div>
            <div style={{ fontSize: 13, color: "#6b7280" }}>Nivel de alerta de seguridad</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: alerta.color }}>{alerta.txt}</div>
            <div className="muted small">{alerta.desc}</div>
          </div>
        </div>
      </div>

      {/* Tarjetas resumen */}
      <div className="metric-grid">
        <div className="metric-card rojo">
          <div className="metric-top"><span className="metric-label">Logins fallidos (24h)</span><span className="metric-icon"><AlertTriangle size={16} /></span></div>
          <div className="metric-valor" style={{ fontSize: 24 }}>{s.login_fallidos_24h}</div>
          <span className="muted small">{s.login_fallidos_7d} en 7 días</span>
        </div>
        <div className="metric-card naranja">
          <div className="metric-top"><span className="metric-label">Bloqueos por saturación (24h)</span><span className="metric-icon"><TrafficCone size={16} /></span></div>
          <div className="metric-valor" style={{ fontSize: 24 }}>{s.bloqueos_saturacion_24h}</div>
          <span className="muted small">{s.bloqueos_saturacion_7d} en 7 días</span>
        </div>
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Accesos no autorizados (24h)</span><span className="metric-icon"><Lock size={16} /></span></div>
          <div className="metric-valor" style={{ fontSize: 24 }}>{s.errores_autorizacion_24h}</div>
          <span className="muted small">tokens inválidos / sin permiso</span>
        </div>
      </div>

      {/* Timeline de logins fallidos */}
      <div className="dash-card">
        <h3>Logins fallidos — últimos 7 días</h3>
        <div className="seg-timeline">
          {s.timeline_7d.map((t, i) => (
            <div key={i} className="seg-tl-col">
              <div className="seg-tl-bar-track">
                <div className="seg-tl-bar" style={{
                  height: `${(t.fallidos / maxTl) * 100}%`,
                  background: t.fallidos > 15 ? "#c81e1e" : t.fallidos > 5 ? "#d89000" : "#5b9e3f",
                }} title={`${t.fallidos} intentos`} />
              </div>
              <span className="muted small">{t.dia}</span>
              <span className="seg-tl-num">{t.fallidos}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Ataques a cuentas privilegiadas */}
      {s.ataques_privilegiados.length > 0 && (
        <div className="dash-card" style={{ borderLeft: "5px solid #c81e1e" }}>
          <h3 style={{ color: "#c81e1e" }}><AlertTriangle size={16} /> Intentos contra cuentas privilegiadas</h3>
          <p className="muted small">Logins fallidos contra cuentas admin/desarrollador en los últimos 7 días. Prestar atención.</p>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Cuenta</th><th>Intentos fallidos</th></tr></thead>
              <tbody>
                {s.ataques_privilegiados.map((a, i) => (
                  <tr key={i}><td><b>{a.email}</b></td>
                    <td><span className="pill red">{a.intentos}</span></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Top IPs sospechosas */}
      <div className="dash-card">
        <h3>IPs con más logins fallidos (7 días)</h3>
        {s.top_ips.length === 0 ? (
          <p className="muted">No hay logins fallidos registrados. <ThumbsUp size={16} /></p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>IP</th><th>Intentos fallidos</th></tr></thead>
              <tbody>
                {s.top_ips.map((ip, i) => (
                  <tr key={i}>
                    <td><code>{ip.ip}</code></td>
                    <td>
                      <span className={`pill ${ip.intentos > 10 ? "red" : ip.intentos > 5 ? "amber" : ""}`}>
                        {ip.intentos}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="muted small">
        Nota: estas métricas son a nivel de la aplicación (intentos de login, saturación frenada por
        rate-limit, accesos sin permiso). Los intentos a nivel del servidor (SSH/root) se monitorean
        aparte con herramientas del sistema operativo al desplegar.
      </p>
    </div>
  );
}


// Día 49, a pedido del usuario: buscador de residencial con texto libre,
// para usarlo tanto en Trancas como en Controladores de acceso — antes
// cada pantalla tenía (o iba a necesitar) su propio <select> chico y
// escondido, doloroso de usar con muchas residenciales (imaginate con
// 50: desplazarte por una lista entera en vez de poder escribir).
// Reutilizable: recibe la lista completa y devuelve el id elegido (o ""
// para "todas").
function BuscadorResidencial({
  residenciales, valor, onChange, placeholder = "Buscar residencial…",
}: {
  residenciales: ResidencialDTO[];
  valor: string;
  onChange: (id: string) => void;
  placeholder?: string;
}) {
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState(false);
  const seleccionada = residenciales.find((r) => r.id === valor);
  // Mientras no se está escribiendo de nuevo, el input muestra el nombre
  // de la elegida (si hay una); si el usuario empieza a tipear, se ve lo
  // que escribe, no el nombre viejo.
  const textoVisible = seleccionada && !abierto ? seleccionada.nombre : texto;
  const filtradas = texto.trim()
    ? residenciales.filter((r) => r.nombre.toLowerCase().includes(texto.trim().toLowerCase()))
    : residenciales;

  return (
    <div className="dev-buscador-res">
      <Search size={16} className="dev-buscador-res-ic" />
      <input
        type="text"
        placeholder={placeholder}
        value={textoVisible}
        onChange={(e) => { setTexto(e.target.value); setAbierto(true); if (valor) onChange(""); }}
        onFocus={() => setAbierto(true)}
        onBlur={() => setTimeout(() => setAbierto(false), 150)}
      />
      {valor && (
        <button type="button" className="dev-buscador-res-clear"
          onMouseDown={(e) => { e.preventDefault(); onChange(""); setTexto(""); }} title="Quitar filtro">✕</button>
      )}
      {abierto && (
        <div className="dev-buscador-res-lista">
          <div className="dev-buscador-res-opcion todas" onMouseDown={() => { onChange(""); setTexto(""); setAbierto(false); }}>
            Todas las residenciales
          </div>
          {filtradas.length === 0 ? (
            <div className="dev-buscador-res-vacio">Sin resultados para "{texto}"</div>
          ) : (
            filtradas.map((r) => (
              <div key={r.id} className="dev-buscador-res-opcion"
                onMouseDown={() => { onChange(r.id); setTexto(""); setAbierto(false); }}>
                {r.nombre}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ConfigTrancas() {
  const [accesos, setAccesos] = useState<AccesoFisicoDTO[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [edits, setEdits] = useState<Record<number, {
    nombre: string; tipo: string; relay_pin: string; pulso_ms: string;
    punto_acceso: string; direccion: string;
    // Día 49
    modo_control: "gpio" | "modbus";
    wiegand_d0_pin: string; wiegand_d1_pin: string;
    relay_canal: string; lector_direccion_osdp: string;
  }>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ id: number; texto: string; ok: boolean } | null>(null);
  // Día 47: se quitaron los estados del formulario de alta (mostrarAlta,
  // nuevoNombre, nuevoTipo, nuevoPunto, creando, msgAlta) — el admin crea
  // las trancas desde Mi Perfil, no el panel dev.
  // Baja
  const [borrar, setBorrar] = useState<{ acceso: AccesoFisicoDTO; eventos: number } | null>(null);
  const [borrando, setBorrando] = useState(false);
  // Bases multi-residencial (Día 37): a qué cliente asignar cada tranca,
  // y filtro para ver solo las de una residencial en particular.
  const [residenciales, setResidenciales] = useState<ResidencialDTO[]>([]);
  const [filtroResidencial, setFiltroResidencial] = useState("");

  const cargar = useCallback(() => {
    setCargando(true);
    devAccesosFisicos()
      .then((data) => {
        setAccesos(data);
        const e: typeof edits = {};
        data.forEach((a) => {
          e[a.id] = {
            nombre: a.nombre, tipo: a.tipo,
            relay_pin: a.relay_pin == null ? "" : String(a.relay_pin),
            pulso_ms: String(a.pulso_ms),
            punto_acceso: a.punto_acceso || "", direccion: a.direccion || "entrada",
            modo_control: a.modo_control || "gpio",
            wiegand_d0_pin: a.wiegand_d0_pin == null ? "" : String(a.wiegand_d0_pin),
            wiegand_d1_pin: a.wiegand_d1_pin == null ? "" : String(a.wiegand_d1_pin),
            relay_canal: a.relay_canal == null ? "" : String(a.relay_canal),
            lector_direccion_osdp: a.lector_direccion_osdp == null ? "" : String(a.lector_direccion_osdp),
          };
        });
        setEdits(e);
      })
      .catch(() => setAccesos([]))
      .finally(() => setCargando(false));
    devResidenciales().then(setResidenciales).catch(() => setResidenciales([]));
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  async function asignarResidencial(a: AccesoFisicoDTO, residencialId: string) {
    // Misma lógica que las Pi: reasignar la residencial de una tranca ya
    // asignada es sensible, exige confirmación explícita.
    const nueva = residenciales.find((r) => r.id === residencialId);
    const nombreNueva = nueva ? nueva.nombre : "ninguna (sin asignar)";
    const actual = a.residencial ? a.residencial.nombre : "sin asignar";
    if (!confirm(`¿Cambiar la residencial de "${a.nombre}" de "${actual}" a "${nombreNueva}"?`)) {
      return;
    }
    try {
      const actualizado = await devConfigurarAcceso(a.id, { residencial_id: residencialId || null });
      setAccesos((prev) => prev ? prev.map((x) => x.id === a.id ? actualizado : x) : prev);
    } catch { /* noop */ }
  }

  function setCampo(id: number, campo: keyof (typeof edits)[number], valor: string) {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }));
  }

  // Día 49, corrección a pedido del usuario: la tecnología es una decisión
  // POR PUNTO, no por tranca — antes el selector estaba repetido en cada
  // tarjeta, y nada impedía dejar la tranca de entrada en un modo y la de
  // salida en otro, sin sentido físico (las tres del mismo punto comparten
  // un solo Pi y un solo hardware). Esta función actualiza el modo de
  // TODAS las trancas del grupo a la vez, en el estado local — cada una se
  // sigue guardando por separado (el canal/pin sí es distinto por tranca),
  // pero ya no se pueden desincronizar entre sí.
  function cambiarModoDelPunto(items: AccesoFisicoDTO[], nuevoModo: "gpio" | "modbus") {
    setEdits((prev) => {
      const siguiente = { ...prev };
      items.forEach((a) => {
        siguiente[a.id] = { ...siguiente[a.id], modo_control: nuevoModo };
      });
      return siguiente;
    });
  }

  async function guardar(a: AccesoFisicoDTO) {
    const ed = edits[a.id];
    const nombre = ed.nombre.trim();
    const pulso = parseInt(ed.pulso_ms, 10);
    if (!nombre) { setMsg({ id: a.id, texto: "El nombre no puede estar vacío", ok: false }); return; }
    if (isNaN(pulso) || pulso < 100 || pulso > 5000) { setMsg({ id: a.id, texto: "El pulso debe estar entre 100 y 5000 ms", ok: false }); return; }

    // Día 49: validación según el modo elegido — cada uno valida solo sus
    // propios campos, no los del otro modo (quedan como estaban, sin tocar).
    const num = (v: string) => v.trim() === "" ? null : parseInt(v, 10);
    const cuerpo: Parameters<typeof devConfigurarAcceso>[1] = {
      nombre, tipo: ed.tipo,
      punto_acceso: ed.punto_acceso.trim(), direccion: ed.direccion,
      pulso_ms: pulso, modo_control: ed.modo_control,
    };

    if (ed.modo_control === "gpio") {
      const pin = ed.relay_pin.trim();
      if (pin !== "") {
        const p = parseInt(pin, 10);
        if (isNaN(p) || p < 0 || p > 40) { setMsg({ id: a.id, texto: "El pin del relay debe ser un número entre 0 y 40", ok: false }); return; }
      }
      for (const [campo, valor] of [["Wiegand D0", ed.wiegand_d0_pin], ["Wiegand D1", ed.wiegand_d1_pin]] as const) {
        if (valor.trim() === "") continue;
        const p = parseInt(valor, 10);
        if (isNaN(p) || p < 0 || p > 40) { setMsg({ id: a.id, texto: `El pin ${campo} debe ser un número entre 0 y 40`, ok: false }); return; }
      }
      cuerpo.relay_pin = num(ed.relay_pin);
      cuerpo.wiegand_d0_pin = num(ed.wiegand_d0_pin);
      cuerpo.wiegand_d1_pin = num(ed.wiegand_d1_pin);
    } else {
      const canal = ed.relay_canal.trim();
      if (canal !== "") {
        const c = parseInt(canal, 10);
        if (isNaN(c) || c < 1 || c > 4) { setMsg({ id: a.id, texto: "El canal del relay debe ser un número entre 1 y 4", ok: false }); return; }
      }
      const dir = ed.lector_direccion_osdp.trim();
      if (dir !== "") {
        const d = parseInt(dir, 10);
        if (isNaN(d) || d < 0 || d > 126) { setMsg({ id: a.id, texto: "La dirección OSDP debe ser un número entre 0 y 126", ok: false }); return; }
      }
      cuerpo.relay_canal = num(ed.relay_canal);
      cuerpo.lector_direccion_osdp = num(ed.lector_direccion_osdp);
    }

    setGuardando(a.id);
    setMsg(null);
    try {
      const actualizado = await devConfigurarAcceso(a.id, cuerpo);
      setAccesos((prev) => prev ? prev.map((x) => x.id === a.id ? actualizado : x) : prev);
      setMsg({ id: a.id, texto: "Guardado correctamente", ok: true });
    } catch (err: any) {
      setMsg({ id: a.id, texto: err?.message || "No se pudo guardar", ok: false });
    } finally {
      setGuardando(null);
    }
  }

  async function alternarActivo(a: AccesoFisicoDTO) {
    try {
      const actualizado = await devConfigurarAcceso(a.id, { activo: !a.activo });
      setAccesos((prev) => prev ? prev.map((x) => x.id === a.id ? actualizado : x) : prev);
    } catch { /* noop */ }
  }

  async function pedirBorrar(a: AccesoFisicoDTO) {
    try {
      const { eventos } = await devHistorialCount(a.id);
      setBorrar({ acceso: a, eventos });
    } catch {
      setBorrar({ acceso: a, eventos: 0 });
    }
  }

  async function confirmarBorrar() {
    if (!borrar) return;
    setBorrando(true);
    try {
      await devEliminarAcceso(borrar.acceso.id);
      setBorrar(null);
      cargar();
    } catch { /* noop */ } finally {
      setBorrando(false);
    }
  }

  if (cargando) return <p className="muted" style={{ padding: 20 }}>Cargando trancas…</p>;

  // Lista de puntos existentes (para el autocompletado) y agrupación por punto.
  // Bases multi-residencial (Día 37): si hay un filtro activo, solo se
  // agrupan/muestran las trancas de esa residencial.
  const listaCompleta = accesos || [];
  const lista = filtroResidencial
    ? listaCompleta.filter((a) => a.residencial?.id === filtroResidencial)
    : listaCompleta;
  const puntos = Array.from(new Set(lista.map((a) => a.punto_acceso).filter(Boolean)));
  const grupos: { punto: string; items: AccesoFisicoDTO[] }[] = [];
  const sinPunto: AccesoFisicoDTO[] = [];
  lista.forEach((a) => {
    if (!a.punto_acceso) { sinPunto.push(a); return; }
    let g = grupos.find((x) => x.punto === a.punto_acceso);
    if (!g) { g = { punto: a.punto_acceso, items: [] }; grupos.push(g); }
    g.items.push(a);
  });
  if (sinPunto.length) grupos.push({ punto: "", items: sinPunto });

  return (
    <div className="dev-trancas">
      <div className="dev-trancas-aviso">
        <strong><AlertTriangle size={16} /> Configuración sensible.</strong> Estos valores controlan el hardware físico de las trancas.
        Elegí primero la <code>tecnología</code> de cada punto: en <strong>Económico</strong> el pin
        del relay y del lector Wiegand van directo a la Raspberry Pi; en <strong>Premium</strong> el
        relay y el lector viven en hardware externo, y solo hace falta indicar el canal y la dirección
        de cada uno. El <code>pulso</code> (milisegundos que se mantiene el contacto seco) aplica igual
        en los dos casos. Un valor incorrecto puede impedir que una tranca abra.
      </div>

      <div className="dev-trancas-barra" style={{ flexWrap: "wrap", gap: 10 }}>
        <span className="dev-trancas-total">{lista.length} tranca(s)/torniquete(s) registrado(s)</span>
        {residenciales.length > 0 && (
          <BuscadorResidencial residenciales={residenciales} valor={filtroResidencial} onChange={setFiltroResidencial} />
        )}
      </div>

      {/* Día 47: se quitó el botón "+ Agregar acceso" y su formulario — era
          una vía duplicada e inferior a la que ya tiene el admin en
          Mi Perfil → Puntos de acceso (esa hereda la residencial
          automáticamente; esta dejaba crear sin pedirla y asignarla
          después, por separado). El panel dev sigue siendo el lugar
          correcto para configurar relay_pin/pulso_ms de trancas YA
          creadas por el admin — eso sí es exclusivo del desarrollador. */}

      {(!accesos || accesos.length === 0) ? (
        <p className="muted" style={{ padding: 20 }}>
          No hay accesos físicos todavía. El admin de cada residencial los crea desde
          Mi Perfil → Puntos de acceso; una vez creados, aparecen acá para configurar su hardware.
        </p>
      ) : (
        grupos.map((g) => {
          // Día 49, a pedido del usuario: mostrar a qué residencial
          // pertenece cada grupo, para que sea más entendible de un
          // vistazo (sobre todo con varias residenciales mezcladas en la
          // misma pantalla). Se toma del primer ítem del grupo — todas
          // las trancas de un mismo punto deberían tener la misma
          // residencial, ya que se hereda al crearlas desde Mi Perfil.
          const residencialDelGrupo = g.items[0]?.residencial?.nombre;
          return (
          <div key={g.punto || "sin-punto"} className="dev-punto-grupo">
            <div className="dev-punto-titulo">
              <span className="dev-punto-ic"><Router size={16} /></span>
              <span>{g.punto || "Sin punto asignado"}</span>
              {residencialDelGrupo && (
                <span className="dev-punto-residencial">
                  <Building2 size={12} /> {residencialDelGrupo}
                </span>
              )}
              <span className="dev-punto-sub">{g.punto ? `Raspberry Pi · ${g.items.length} dispositivo(s)` : `${g.items.length} acceso(s) sin asignar a una Pi`}</span>
              {g.punto && (
                <div className="dev-modo-selector dev-modo-selector-punto">
                  <button type="button"
                    className={`dev-modo-btn ${(edits[g.items[0]?.id]?.modo_control || "gpio") === "gpio" ? "sel" : ""}`}
                    onClick={() => cambiarModoDelPunto(g.items, "gpio")}>
                    <Cpu size={16} />
                    <span className="dev-modo-btn-texto">
                      <strong>Económico</strong>
                      <span>Wiegand + GPIO</span>
                    </span>
                  </button>
                  <button type="button"
                    className={`dev-modo-btn ${(edits[g.items[0]?.id]?.modo_control || "gpio") === "modbus" ? "sel" : ""}`}
                    onClick={() => cambiarModoDelPunto(g.items, "modbus")}>
                    <Radio size={16} />
                    <span className="dev-modo-btn-texto">
                      <strong>Premium</strong>
                      <span>Cidron + OSDP/Modbus</span>
                    </span>
                  </button>
                </div>
              )}
            </div>
            <div className="dev-trancas-grid">
              {g.items.map((a) => {
                const ed = edits[a.id] || {
                  nombre: "", tipo: "vehicular", relay_pin: "", pulso_ms: "", punto_acceso: "", direccion: "entrada",
                  modo_control: "gpio" as const,
                  wiegand_d0_pin: "", wiegand_d1_pin: "", relay_canal: "", lector_direccion_osdp: "",
                };
                // Día 49: "sin configurar" depende del modo — en GPIO
                // alcanza con el pin del relay; en Modbus hace falta el
                // canal Y la dirección del lector (ambos, para que el
                // punto quede realmente operativo).
                const sinConfig = a.modo_control === "modbus"
                  ? (a.relay_canal == null || a.lector_direccion_osdp == null)
                  : a.relay_pin == null;
                return (
                  <div key={a.id} className={`dev-tranca-card ${!a.activo ? "inactiva" : ""}`}>
                    <div className="dev-tranca-head">
                      <input className="dev-tranca-nombre-input" value={ed.nombre} maxLength={80}
                        onChange={(e) => setCampo(a.id, "nombre", e.target.value)} />
                      <span className={`dev-tranca-badge ${sinConfig ? "sin" : "ok"}`}>
                        {sinConfig ? "Sin configurar" : "Configurada"}
                      </span>
                    </div>
                    <div className="dev-tranca-fila">
                      <select className="dev-tranca-tipo-sel" value={ed.tipo} onChange={(e) => setCampo(a.id, "tipo", e.target.value)}>
                        <option value="vehicular">Vehicular</option>
                        <option value="peatonal">Peatonal</option>
                      </select>
                      <button className={`dev-tranca-toggle ${a.activo ? "on" : "off"}`} onClick={() => alternarActivo(a)}>
                        {a.activo ? "Activa" : "Inactiva"}
                      </button>
                    </div>
                    <div className="dev-tranca-dir">
                      <button className={`dev-dir-btn ${ed.direccion === "entrada" ? "sel-ent" : ""}`}
                        onClick={() => setCampo(a.id, "direccion", "entrada")}>↓ Entrada</button>
                      <button className={`dev-dir-btn ${ed.direccion === "salida" ? "sel-sal" : ""}`}
                        onClick={() => setCampo(a.id, "direccion", "salida")}>↑ Salida</button>
                    </div>
                    <label className="dev-tranca-punto">
                      <span>Punto de acceso (Raspberry Pi)</span>
                      <input type="text" placeholder="Ej: Acceso Principal" maxLength={80} list="puntos-existentes"
                        value={ed.punto_acceso} onChange={(e) => setCampo(a.id, "punto_acceso", e.target.value)} />
                    </label>
                    <label className="dev-tranca-punto">
                      <span>Residencial</span>
                      <select value={a.residencial?.id || ""} onChange={(e) => asignarResidencial(a, e.target.value)}
                        className="dev-tranca-tipo-sel" style={{ width: "100%" }}>
                        <option value="">— Sin asignar —</option>
                        {residenciales.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                      </select>
                    </label>
                    {/* Día 49, corregido: la tecnología ya no se elige acá
                        — se eligió una sola vez arriba, en el encabezado
                        del punto (ver cambiarModoDelPunto), para que no se
                        pueda desincronizar entre las trancas de un mismo
                        punto. Esto es solo un indicador de solo lectura,
                        para confirmar cuál está activa sin poder tocarla. */}
                    <div className="dev-tranca-modo-indicador">
                      {ed.modo_control === "gpio" ? <Cpu size={13} /> : <Radio size={13} />}
                      <span>{ed.modo_control === "gpio" ? "Económico — Wiegand + GPIO" : "Premium — Cidron + OSDP/Modbus"}</span>
                    </div>

                    {ed.modo_control === "gpio" ? (
                      <div className="dev-tranca-campos">
                        <label>
                          <span>Pin GPIO (relay)</span>
                          <input type="number" min={0} max={40} placeholder="—"
                            value={ed.relay_pin} onChange={(e) => setCampo(a.id, "relay_pin", e.target.value)} />
                        </label>
                        <label>
                          <span>Wiegand D0</span>
                          <input type="number" min={0} max={40} placeholder="—"
                            value={ed.wiegand_d0_pin} onChange={(e) => setCampo(a.id, "wiegand_d0_pin", e.target.value)} />
                        </label>
                        <label>
                          <span>Wiegand D1</span>
                          <input type="number" min={0} max={40} placeholder="—"
                            value={ed.wiegand_d1_pin} onChange={(e) => setCampo(a.id, "wiegand_d1_pin", e.target.value)} />
                        </label>
                        <label>
                          <span>Pulso (ms)</span>
                          <input type="number" min={100} max={5000} step={50}
                            value={ed.pulso_ms} onChange={(e) => setCampo(a.id, "pulso_ms", e.target.value)} />
                        </label>
                      </div>
                    ) : (
                      <div className="dev-tranca-campos">
                        <label>
                          <span>Canal del relay (1-4)</span>
                          <input type="number" min={1} max={4} placeholder="—"
                            value={ed.relay_canal} onChange={(e) => setCampo(a.id, "relay_canal", e.target.value)} />
                        </label>
                        <label>
                          <span>Dirección OSDP del lector</span>
                          <input type="number" min={0} max={126} placeholder="—"
                            value={ed.lector_direccion_osdp} onChange={(e) => setCampo(a.id, "lector_direccion_osdp", e.target.value)} />
                        </label>
                        <label>
                          <span>Pulso (ms)</span>
                          <input type="number" min={100} max={5000} step={50}
                            value={ed.pulso_ms} onChange={(e) => setCampo(a.id, "pulso_ms", e.target.value)} />
                        </label>
                      </div>
                    )}
                    {msg && msg.id === a.id && (
                      <div className={`dev-tranca-msg ${msg.ok ? "ok" : "err"}`}>{msg.texto}</div>
                    )}
                    <div className="dev-tranca-acciones">
                      <button className="dev-tranca-btn" disabled={guardando === a.id} onClick={() => guardar(a)}>
                        {guardando === a.id ? "Guardando…" : "Guardar"}
                      </button>
                      <button className="dev-tranca-del" onClick={() => pedirBorrar(a)} title="Eliminar acceso"><Trash2 size={16} /></button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          );
        })
      )}

      {borrar && (
        <div className="dev-modal-overlay" onClick={() => !borrando && setBorrar(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Eliminar acceso</h3>
            <p>¿Seguro que querés eliminar <strong>{borrar.acceso.nombre}</strong>?</p>
            {borrar.eventos > 0 && (
              <div className="dev-tranca-msg err" style={{ marginBottom: 14 }}>
                <AlertTriangle size={16} /> Este acceso tiene <strong>{borrar.eventos}</strong> registro(s) en el historial de entradas/salidas.
                Si lo eliminás, esos registros también se borrarán. Si solo querés dejar de usarlo, mejor marcalo como Inactiva.
              </div>
            )}
            <div className="dev-modal-acciones">
              <button className="ghost" disabled={borrando} onClick={() => setBorrar(null)}>Cancelar</button>
              <button className="dev-tranca-del-confirm" disabled={borrando} onClick={confirmarBorrar}>
                {borrando ? "Eliminando…" : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function ConfigPis() {
  const [pis, setPis] = useState<DispositivoDTO[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [mostrarAlta, setMostrarAlta] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState<"acceso" | "lector_ct9">("acceso");
  const [nuevoPunto, setNuevoPunto] = useState("");
  const [nuevaResidencial, setNuevaResidencial] = useState("");
  const [errorAlta, setErrorAlta] = useState("");
  const [creando, setCreando] = useState(false);
  // token recién generado para mostrar una vez
  const [tokenNuevo, setTokenNuevo] = useState<{ nombre: string; token: string } | null>(null);
  // Día 47: se guarda la lista completa de accesos (con su residencial),
  // no solo los nombres de punto — así el desplegable de "Punto de acceso"
  // se puede filtrar según la residencial elegida, en vez de mezclar los
  // puntos de todas las residenciales.
  const [accesosTodos, setAccesosTodos] = useState<AccesoFisicoDTO[]>([]);
  // Bases multi-residencial (Día 37): a qué cliente asignar cada Pi
  const [residenciales, setResidenciales] = useState<ResidencialDTO[]>([]);

  const cargar = useCallback(() => {
    setCargando(true);
    // Cargar dispositivos y puntos por separado: si una falla, la otra igual
    // funciona (ej. si la tabla de dispositivos aún no existe, los puntos se
    // cargan igual desde los accesos).
    // Esta pestaña es "Controladores de acceso": solo Pi de acceso y
    // lectores CT9, NO las Pi de cámara (que tienen su propia gestión).
    devDispositivos()
      .then((todos) => setPis(todos.filter((d) => d.tipo !== "camara")))
      .catch(() => setPis([]))
      .finally(() => setCargando(false));
    devAccesosFisicos()
      .then(setAccesosTodos)
      .catch(() => setAccesosTodos([]));
    devResidenciales().then(setResidenciales).catch(() => setResidenciales([]));
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  // Puntos de acceso DE LA RESIDENCIAL elegida únicamente — antes se
  // mezclaban los de todas. Sin residencial elegida todavía, no hay nada
  // que mostrar (se fuerza a elegir residencial primero).
  const puntosFiltrados = nuevaResidencial
    ? Array.from(new Set(
        accesosTodos
          .filter((a) => a.residencial?.id === nuevaResidencial)
          .map((a) => a.punto_acceso)
          .filter(Boolean)
      )) as string[]
    : [];

  // Día 49, Etapa 3: contexto para el desarrollador — qué modo tiene
  // configurado el punto elegido, así sabe de antemano qué hardware llevar
  // a la instalación (lector Wiegand vs. Cidron + relay Modbus). Se toma
  // del primer acceso que matchee — deberían estar todos sincronizados,
  // gracias a la corrección de la Etapa 2 (el modo se elige por punto, no
  // por tranca individual).
  const modoDelPuntoElegido = nuevoPunto
    ? accesosTodos.find((a) => a.residencial?.id === nuevaResidencial && a.punto_acceso === nuevoPunto)?.modo_control
    : undefined;

  async function asignarResidencial(d: DispositivoDTO, residencialId: string) {
    // Reasignar la residencial de una Pi ya en uso es una acción sensible
    // (esa Pi deja de descargar información de su cliente anterior) —
    // exige confirmación explícita, no se aplica con solo tocar el select.
    const nueva = residenciales.find((r) => r.id === residencialId);
    const nombreNueva = nueva ? nueva.nombre : "ninguna (sin asignar)";
    const actual = d.residencial ? d.residencial.nombre : "sin asignar";
    if (!confirm(
      `¿Cambiar la residencial de "${d.nombre}" de "${actual}" a "${nombreNueva}"?\n\n` +
      `Esta Pi dejará de sincronizar información de la residencial anterior.`
    )) {
      return; // no tocar nada — el <select> se re-renderiza con el valor real desde el estado
    }
    try {
      await devActualizarDispositivo(d.id, { residencial_id: residencialId || null });
      cargar();
    } catch { /* noop */ }
  }

  async function crear() {
    if (!nuevoNombre.trim()) return;
    if (!nuevaResidencial) { setErrorAlta("Elegí a qué residencial pertenece este controlador — así queda atado desde el momento en que se crea."); return; }
    setErrorAlta("");
    setCreando(true);
    try {
      const d = await devCrearDispositivo({
        nombre: nuevoNombre.trim(), tipo: nuevoTipo,
        punto_acceso: nuevoPunto.trim(), residencial_id: nuevaResidencial,
      });
      if (d.token) setTokenNuevo({ nombre: d.nombre, token: d.token });
      setNuevoNombre(""); setNuevoTipo("acceso"); setNuevoPunto(""); setNuevaResidencial(""); setMostrarAlta(false);
      cargar();
    } catch (err: any) {
      setErrorAlta(err?.message || "No se pudo crear el controlador");
    } finally { setCreando(false); }
  }

  async function alternarActivo(d: DispositivoDTO) {
    try { await devActualizarDispositivo(d.id, { activo: !d.activo }); cargar(); } catch { /* noop */ }
  }

  async function regenerar(d: DispositivoDTO) {
    if (!confirm(`¿Regenerar el token de "${d.nombre}"? El token anterior dejará de funcionar y habrá que actualizarlo en la Pi.`)) return;
    try {
      const actualizado = await devRegenerarToken(d.id);
      if (actualizado.token) setTokenNuevo({ nombre: actualizado.nombre, token: actualizado.token });
    } catch { /* noop */ }
  }

  async function eliminar(d: DispositivoDTO) {
    if (!confirm(`¿Eliminar la Pi "${d.nombre}"? Dejará de poder sincronizar.`)) return;
    try { await devEliminarDispositivo(d.id); cargar(); } catch { /* noop */ }
  }

  function copiar(texto: string) {
    navigator.clipboard?.writeText(texto);
  }

  if (cargando) return <p className="muted" style={{ padding: 20 }}>Cargando dispositivos…</p>;

  return (
    <div className="dev-trancas">
      <div className="dev-trancas-aviso">
        <strong><Router size={16} /> Controladores de acceso.</strong> Cada punto de acceso tiene su propio
        controlador —una Raspberry Pi o un lector inteligente (CT9)— que descarga su copia de residentes
        con permiso y valida localmente. Cada uno se identifica con un <code>token</code> único y secreto.
        El <code>punto de acceso</code> debe coincidir con el de las trancas de ese punto.
      </div>

      <div className="dev-trancas-barra">
        <span className="dev-trancas-total">{pis?.length || 0} controlador(es)</span>
        <button className="dev-tranca-add" onClick={() => setMostrarAlta((v) => !v)}>
          {mostrarAlta ? "Cancelar" : "+ Agregar controlador"}
        </button>
      </div>

      {mostrarAlta && (
        <div className="dev-tranca-alta">
          <div className="dev-tranca-alta-campos">
            <label>
              <span>Nombre</span>
              <input type="text" placeholder="Ej: Pi Acceso Principal" maxLength={80}
                value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)} />
            </label>
            <label>
              <span>Tipo de controlador</span>
              <select className="dev-tranca-tipo-sel" value={nuevoTipo}
                onChange={(e) => setNuevoTipo(e.target.value as "acceso" | "lector_ct9")}>
                <option value="acceso">Raspberry Pi</option>
                <option value="lector_ct9">Lector inteligente (CT9)</option>
              </select>
            </label>
            {/* Día 47: Residencial va ANTES que Punto de acceso — el punto
                elegible depende de la residencial, no al revés. Antes se
                preguntaba el punto primero con TODOS los puntos de TODAS
                las residenciales mezclados en un mismo desplegable. */}
            <label>
              <span>Residencial *</span>
              <select className="dev-tranca-tipo-sel" value={nuevaResidencial}
                onChange={(e) => { setNuevaResidencial(e.target.value); setNuevoPunto(""); }}>
                <option value="">— Elegí una residencial —</option>
                {residenciales.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
              </select>
            </label>
            <label>
              <span>Punto de acceso</span>
              <select className="dev-tranca-tipo-sel" value={nuevoPunto} onChange={(e) => setNuevoPunto(e.target.value)}
                disabled={!nuevaResidencial}>
                <option value="">
                  {nuevaResidencial ? "— Elegí un punto —" : "Elegí primero una residencial"}
                </option>
                {puntosFiltrados.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              {nuevaResidencial && puntosFiltrados.length === 0 && (
                <span className="muted small">
                  Esta residencial todavía no tiene puntos de acceso creados (los crea su admin
                  desde Mi Perfil).
                </span>
              )}
              {modoDelPuntoElegido && (
                <div className="dev-tranca-modo-indicador" style={{ marginTop: 6, marginBottom: 0 }}>
                  {modoDelPuntoElegido === "gpio" ? <Cpu size={13} /> : <Radio size={13} />}
                  <span>
                    Este punto es {modoDelPuntoElegido === "gpio" ? "Económico" : "Premium"} —
                    llevá {modoDelPuntoElegido === "gpio" ? "el lector Wiegand" : "el Cidron y el relay Modbus"} a la instalación
                  </span>
                </div>
              )}
            </label>
            <button className="dev-tranca-btn" style={{ maxWidth: 160 }} disabled={creando} onClick={crear}>
              {creando ? "Creando…" : "Crear Pi"}
            </button>
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>
            * Obligatoria: el controlador queda atado a esa residencial desde el momento en que se crea — evita
            crear dispositivos sueltos que después haya que andar asignando.
          </p>
          {nuevoTipo === "lector_ct9" && (
            <div className="dev-tranca-msg" style={{ marginTop: 10, background: "#fef2d5", color: "#92651c" }}>
              El lector CT9 todavía no sincroniza con el servidor — falta construir el adaptador que
              traduce su protocolo (pendiente del SDK de Civintec). Podés registrarlo ya para tener su
              token y nombre listos, pero no va a validar accesos hasta que esa integración esté lista.
            </div>
          )}
          {errorAlta && (
            <div className="dev-tranca-msg err" style={{ marginTop: 10 }}>{errorAlta}</div>
          )}
        </div>
      )}

      {tokenNuevo && (
        <div className="dev-modal-overlay" onClick={() => setTokenNuevo(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Token de {tokenNuevo.nombre}</h3>
            <p>Copiá este token y configuralo en el controlador (Raspberry Pi o CT9). <strong>No se vuelve a mostrar</strong> por seguridad. Si lo perdés, podés regenerarlo (y actualizarlo en el dispositivo).</p>
            <div className="dev-token-box">
              <code>{tokenNuevo.token}</code>
              <button className="dev-tranca-btn" style={{ maxWidth: 110 }} onClick={() => copiar(tokenNuevo.token)}>Copiar</button>
            </div>
            <div className="dev-modal-acciones">
              <button className="dev-tranca-del-confirm" style={{ background: "#022E45" }} onClick={() => setTokenNuevo(null)}>Ya lo copié</button>
            </div>
          </div>
        </div>
      )}

      {(!pis || pis.length === 0) ? (
        <p className="muted" style={{ padding: 20 }}>No hay controladores registrados. Agregá el primero con el botón de arriba.</p>
      ) : (
        <div className="dev-trancas-grid">
          {pis.map((d) => (
            <div key={d.id} className={`dev-tranca-card ${!d.activo ? "inactiva" : ""}`}>
              <div className="dev-tranca-head">
                <span className="dev-tranca-nombre">{d.nombre}</span>
                <span className={`dev-tranca-badge ${d.activo ? "ok" : "sin"}`}>{d.activo ? "Activa" : "Revocada"}</span>
              </div>
              <div className="muted small" style={{ marginBottom: 6 }}>
                {d.tipo === "lector_ct9" ? "Lector inteligente (CT9)" : "Raspberry Pi"}
              </div>
              {d.tipo === "lector_ct9" && (
                <div className="dev-tranca-msg" style={{ background: "#fef2d5", color: "#92651c", marginBottom: 8 }}>
                  Integración pendiente — este CT9 aún no sincroniza (falta el adaptador del SDK).
                </div>
              )}
              <div className="dev-pi-info">
                <div><span>Punto:</span> {d.punto_acceso || <em className="muted">sin asignar</em>}</div>
                <div><span>Última sincronización:</span> {d.ultima_sync ? new Date(d.ultima_sync).toLocaleString() : "nunca"}</div>
              </div>
              <div style={{ margin: "8px 0" }}>
                <label className="muted small" style={{ display: "block", marginBottom: 4 }}>
                  Residencial <span title="Bases multi-residencial: qué cliente descarga información con este controlador">ⓘ</span>
                </label>
                <select value={d.residencial?.id || ""} onChange={(e) => asignarResidencial(d, e.target.value)}
                  className="dev-tranca-tipo-sel" style={{ width: "100%" }}>
                  <option value="">— Sin asignar —</option>
                  {residenciales.map((r) => (
                    <option key={r.id} value={r.id}>{r.nombre}</option>
                  ))}
                </select>
              </div>
              <div className="dev-pi-acciones">
                <button className="dev-tranca-toggle on" onClick={() => regenerar(d)} title="Generar un token nuevo"><Key size={16} /> Token</button>
                <button className={`dev-tranca-toggle ${d.activo ? "off" : "on"}`} onClick={() => alternarActivo(d)}>
                  {d.activo ? "Revocar" : "Reactivar"}
                </button>
                <button className="dev-tranca-del" onClick={() => eliminar(d)} title="Eliminar"><Trash2 size={16} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Residenciales: cuántos admins/clientes hay y qué usuarios tiene cada uno
// (bases multi-residencial, Día 37) ─────────────────────────────────────────
const ROL_LABEL_DEV: Record<string, string> = {
  admin: "Administrador", supervisor: "Supervisor", guardia: "Guardia", cajero: "Cajero",
};

function PanelResidenciales() {
  const [lista, setLista] = useState<ResidencialDTO[] | null>(null);
  const [seleccionada, setSeleccionada] = useState<ResidencialDTO | null>(null);
  const [detalle, setDetalle] = useState<{ staff: UsuarioResidencialDTO[]; residentes_count: number } | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  // Alta de una nueva residencial (cliente nuevo del futuro SaaS)
  const [mostrarAlta, setMostrarAlta] = useState(false);
  const [nombreRes, setNombreRes] = useState("");
  const [direccionRes, setDireccionRes] = useState("");
  const [telefonoRes, setTelefonoRes] = useState("");
  const [nombreAdmin, setNombreAdmin] = useState("");
  const [apellidoAdmin, setApellidoAdmin] = useState("");
  const [emailAdmin, setEmailAdmin] = useState("");
  const [telefonoAdmin, setTelefonoAdmin] = useState("");
  const [creando, setCreando] = useState(false);
  const [errorAlta, setErrorAlta] = useState("");
  // Credenciales del admin recién creado, para mostrar una sola vez
  const [credencialNueva, setCredencialNueva] = useState<{ email: string; nombre: string; pass: string } | null>(null);

  const cargar = () => devResidenciales().then(setLista).catch(() => setLista([]));
  useEffect(() => { cargar(); }, []);

  async function verDetalle(r: ResidencialDTO) {
    setSeleccionada(r);
    setCargandoDetalle(true);
    setDetalle(null);
    try {
      const d = await devUsuariosDeResidencial(r.id);
      setDetalle({ staff: d.staff, residentes_count: d.residentes_count });
    } catch {
      setDetalle({ staff: [], residentes_count: 0 });
    } finally {
      setCargandoDetalle(false);
    }
  }

  function limpiarForm() {
    setNombreRes(""); setDireccionRes(""); setTelefonoRes("");
    setNombreAdmin(""); setApellidoAdmin(""); setEmailAdmin(""); setTelefonoAdmin("");
  }

  async function crearResidencial() {
    const faltan: string[] = [];
    if (!nombreRes.trim()) faltan.push("nombre de la residencial");
    if (!direccionRes.trim()) faltan.push("dirección");
    if (!telefonoRes.trim()) faltan.push("teléfono de la residencial");
    if (!nombreAdmin.trim()) faltan.push("nombre del admin");
    if (!apellidoAdmin.trim()) faltan.push("apellido del admin");
    if (!emailAdmin.trim()) faltan.push("correo del admin");
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailAdmin.trim())) faltan.push("correo del admin (formato inválido)");
    if (faltan.length > 0) { setErrorAlta("Faltan: " + faltan.join(", ")); return; }

    setCreando(true); setErrorAlta("");
    try {
      const res = await devCrearResidencial({
        nombre_residencial: nombreRes.trim(), direccion: direccionRes.trim(), telefono_residencial: telefonoRes.trim(),
        nombre_admin: nombreAdmin.trim(), apellido_admin: apellidoAdmin.trim(),
        email_admin: emailAdmin.trim(), telefono_admin: telefonoAdmin.trim() || undefined,
      });
      setCredencialNueva({ email: res.admin.email, nombre: res.admin.nombre, pass: res.admin.password_generica });
      limpiarForm();
      setMostrarAlta(false);
      cargar();
    } catch (err: any) {
      setErrorAlta(err?.message || "No se pudo crear la residencial");
    } finally {
      setCreando(false);
    }
  }

  if (lista === null) return <p className="muted" style={{ padding: 20 }}>Cargando residenciales…</p>;

  return (
    <div className="dev-trancas">
      <div className="dev-trancas-aviso">
        <strong><Building2 size={16} /> Residenciales (clientes).</strong> Cada fila es un admin dueño con todo lo que
        creó bajo él — guardias, cajeros, supervisores y residentes. Hoy, en Villas del Sol, hay una sola. Esta vista
        se vuelve realmente útil cuando exista un segundo cliente del futuro SaaS.
      </div>

      <div className="dev-trancas-barra">
        <span className="dev-trancas-total">{lista.length} residencial(es)</span>
        <button className="dev-tranca-add" onClick={() => { setMostrarAlta((v) => !v); setErrorAlta(""); }}>
          {mostrarAlta ? "Cancelar" : "+ Nueva residencial"}
        </button>
      </div>

      {mostrarAlta && (
        <div className="dev-tranca-alta">
          <p className="muted small" style={{ marginBottom: 10 }}>
            Crea un cliente nuevo: un admin dueño con todo lo que él cree colgando de esta residencial.
          </p>
          <div className="sub" style={{ marginBottom: 6 }}>Datos de la residencial</div>
          <div className="dev-tranca-alta-campos">
            <label>
              <span>Nombre de la residencial</span>
              <input type="text" placeholder="Ej: Residencial Las Colinas" maxLength={160}
                value={nombreRes} onChange={(e) => setNombreRes(e.target.value)} />
            </label>
            <label>
              <span>Dirección</span>
              <input type="text" placeholder="Ej: Col. Las Colinas, Tegucigalpa" maxLength={255}
                value={direccionRes} onChange={(e) => setDireccionRes(e.target.value)} />
            </label>
            <label>
              <span>Teléfono de contacto</span>
              <input type="text" placeholder="Ej: 9999-0000" maxLength={30}
                value={telefonoRes} onChange={(e) => setTelefonoRes(e.target.value)} />
            </label>
          </div>

          <div className="sub" style={{ margin: "14px 0 6px" }}>Datos del administrador dueño (con quien inicia sesión)</div>
          <div className="dev-tranca-alta-campos">
            <label>
              <span>Nombre</span>
              <input type="text" placeholder="Ej: María" maxLength={120}
                value={nombreAdmin} onChange={(e) => setNombreAdmin(e.target.value)} />
            </label>
            <label>
              <span>Apellido</span>
              <input type="text" placeholder="Ej: López" maxLength={120}
                value={apellidoAdmin} onChange={(e) => setApellidoAdmin(e.target.value)} />
            </label>
            <label>
              <span>Correo (será su usuario)</span>
              <input type="email" placeholder="admin@lascolinas.hn" maxLength={160}
                value={emailAdmin} onChange={(e) => setEmailAdmin(e.target.value)} />
            </label>
            <label>
              <span>Teléfono (opcional)</span>
              <input type="text" placeholder="Ej: 9999-0000" maxLength={30}
                value={telefonoAdmin} onChange={(e) => setTelefonoAdmin(e.target.value)} />
            </label>
            <button className="dev-tranca-btn" style={{ maxWidth: 200 }} disabled={creando} onClick={crearResidencial}>
              {creando ? "Creando…" : "Crear residencial"}
            </button>
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>
            Se genera una contraseña aleatoria que se muestra una sola vez — anotala y entregásela al
            cliente. Deberá cambiarla en su primer ingreso. (Esto se reemplazará por un correo de
            activación más adelante.)
          </p>
          {errorAlta && <div className="dev-tranca-msg err" style={{ marginTop: 10 }}>{errorAlta}</div>}
        </div>
      )}

      {credencialNueva && (
        <div className="dev-modal-overlay" onClick={() => setCredencialNueva(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Credenciales de {credencialNueva.nombre}</h3>
            <p>Entregáselas al cliente. <strong>No se vuelven a mostrar</strong> — si las pierde, un admin
            puede restablecerlas por correo desde el login.</p>
            <div className="dev-token-box">
              <code>{credencialNueva.email} / {credencialNueva.pass}</code>
              <button className="dev-tranca-btn" style={{ maxWidth: 110 }}
                onClick={() => navigator.clipboard?.writeText(`${credencialNueva.email} / ${credencialNueva.pass}`)}>
                Copiar
              </button>
            </div>
            <div className="dev-modal-acciones">
              <button className="dev-tranca-del-confirm" style={{ background: "#022E45" }} onClick={() => setCredencialNueva(null)}>Ya las copié</button>
            </div>
          </div>
        </div>
      )}

      {lista.length === 0 ? (
        <p className="muted" style={{ padding: 20 }}>
          No hay ninguna residencial creada todavía — se crea automáticamente al correr la migración
          con el admin existente.
        </p>
      ) : (
        <div className="dev-trancas-grid">
          {lista.map((r) => (
            <div key={r.id} className={`dev-tranca-card ${!r.activa ? "inactiva" : ""}`}
              style={{ cursor: "pointer" }} onClick={() => verDetalle(r)}>
              <div className="dev-tranca-head">
                <span className="dev-tranca-nombre" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {r.logo_archivo && (
                    <img src={urlLogoResidencial(r.logo_archivo)} alt=""
                      style={{ width: 24, height: 24, borderRadius: 6, objectFit: "contain", background: "#fff" }} />
                  )}
                  {r.nombre}
                </span>
                <span className={`dev-tranca-badge ${r.activa ? "ok" : "sin"}`}>{r.activa ? "Activa" : "Inactiva"}</span>
              </div>
              <div className="dev-pi-info">
                {r.admin && <div><span>Admin:</span> {r.admin.nombre} ({r.admin.email})</div>}
                {(r.direccion || r.telefono) && (
                  <div><span>Contacto:</span> {r.direccion || "—"}{r.telefono ? ` · ${r.telefono}` : ""}</div>
                )}
                {r.stats && (
                  <>
                    <div><span>Guardias:</span> {r.stats.guardias} · <span>Cajeros:</span> {r.stats.cajeros} · <span>Supervisores:</span> {r.stats.supervisores}</div>
                    <div><span>Residentes:</span> {r.stats.residentes} · <span>Dispositivos:</span> {r.stats.dispositivos}</div>
                  </>
                )}
              </div>
              <div className="dev-pi-acciones">
                <button className="dev-tranca-toggle on" onClick={(e) => { e.stopPropagation(); verDetalle(r); }}>
                  Ver usuarios →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {seleccionada && (
        <div className="dev-modal-overlay" onClick={() => setSeleccionada(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
            <h3>Usuarios de {seleccionada.nombre}</h3>
            {cargandoDetalle ? (
              <p className="muted">Cargando…</p>
            ) : detalle ? (
              <>
                <p className="muted small" style={{ marginBottom: 10 }}>
                  {detalle.residentes_count} residente(s) — no se listan individualmente acá.
                </p>
                {detalle.staff.length === 0 ? (
                  <p className="muted">No hay guardias, cajeros ni supervisores creados todavía.</p>
                ) : (
                  <table className="data" style={{ width: "100%" }}>
                    <thead>
                      <tr><th>Nombre</th><th>Rol</th><th>Correo</th><th>Estado</th></tr>
                    </thead>
                    <tbody>
                      {detalle.staff.map((u, i) => (
                        <tr key={i}>
                          <td>{u.nombre} {u.apellido}</td>
                          <td>{ROL_LABEL_DEV[u.rol] || u.rol}</td>
                          <td className="small">{u.email}</td>
                          <td>{u.activo ? <span className="pill green">Activo</span> : <span className="pill">Inactivo</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : null}
            <div className="dev-modal-acciones">
              <button className="dev-tranca-del-confirm" style={{ background: "#022E45" }} onClick={() => setSeleccionada(null)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
