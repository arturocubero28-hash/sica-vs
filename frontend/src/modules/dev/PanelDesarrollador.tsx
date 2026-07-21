import { useState, useEffect, useCallback } from "react";
import { devMetricas, devLogs, devMetricasCodigo, devSeguridad, devAccesosFisicos, devConfigurarAcceso, devCrearAcceso, devHistorialCount, devEliminarAcceso, devDispositivos, devCrearDispositivo, devActualizarDispositivo, devRegenerarToken, devEliminarDispositivo, devResidenciales, devUsuariosDeResidencial, urlLogoResidencial, type DevMetricasDTO, type MetricasCodigoDTO, type SeguridadDTO, type AccesoFisicoDTO, type DispositivoDTO, type ResidencialDTO, type UsuarioResidencialDTO } from "../../api/client";
import { AlertTriangle, BarChart3, Building2, Construction, Key, Lock, Monitor, Router, Search, Shield, ThumbsUp, TrafficCone, Trash2 } from "lucide-react";

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
        <button className={`hist-tab ${tab === "pis" ? "on" : ""}`} onClick={() => setTab("pis")}><Router size={16} /> Raspberry Pi</button>
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
            <div className="cuota-vacia"><div className="cuota-vacia-icon"><Search size={16} /></div><p>Sin logs que coincidan.</p></div>
          ) : (
            <>
              <div className="dash-card" style={{ padding: 0 }}>
                <div className="scroll-x">
                  <table className="data">
                    <thead>
                      <tr><th>Fecha / Hora</th><th>Usuario</th><th>Acción</th><th>Status</th><th>IP</th></tr>
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


function ConfigTrancas() {
  const [accesos, setAccesos] = useState<AccesoFisicoDTO[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [edits, setEdits] = useState<Record<number, { nombre: string; tipo: string; relay_pin: string; pulso_ms: string; punto_acceso: string; direccion: string }>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ id: number; texto: string; ok: boolean } | null>(null);
  // Alta
  const [mostrarAlta, setMostrarAlta] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState("vehicular");
  const [nuevoPunto, setNuevoPunto] = useState("");
  const [creando, setCreando] = useState(false);
  const [msgAlta, setMsgAlta] = useState("");
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
        const e: Record<number, { nombre: string; tipo: string; relay_pin: string; pulso_ms: string; punto_acceso: string; direccion: string }> = {};
        data.forEach((a) => { e[a.id] = { nombre: a.nombre, tipo: a.tipo, relay_pin: a.relay_pin == null ? "" : String(a.relay_pin), pulso_ms: String(a.pulso_ms), punto_acceso: a.punto_acceso || "", direccion: a.direccion || "entrada" }; });
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

  function setCampo(id: number, campo: "nombre" | "tipo" | "relay_pin" | "pulso_ms" | "punto_acceso" | "direccion", valor: string) {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }));
  }

  async function guardar(a: AccesoFisicoDTO) {
    const ed = edits[a.id];
    const nombre = ed.nombre.trim();
    const pin = ed.relay_pin.trim();
    const pulso = parseInt(ed.pulso_ms, 10);
    if (!nombre) { setMsg({ id: a.id, texto: "El nombre no puede estar vacío", ok: false }); return; }
    if (pin !== "") {
      const p = parseInt(pin, 10);
      if (isNaN(p) || p < 0 || p > 40) { setMsg({ id: a.id, texto: "El pin debe ser un número entre 0 y 40", ok: false }); return; }
    }
    if (isNaN(pulso) || pulso < 100 || pulso > 5000) { setMsg({ id: a.id, texto: "El pulso debe estar entre 100 y 5000 ms", ok: false }); return; }
    setGuardando(a.id);
    setMsg(null);
    try {
      const actualizado = await devConfigurarAcceso(a.id, {
        nombre, tipo: ed.tipo,
        punto_acceso: ed.punto_acceso.trim(), direccion: ed.direccion,
        relay_pin: pin === "" ? null : parseInt(pin, 10),
        pulso_ms: pulso,
      });
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

  async function crear() {
    const nombre = nuevoNombre.trim();
    if (!nombre) { setMsgAlta("El nombre es obligatorio"); return; }
    setCreando(true);
    setMsgAlta("");
    try {
      await devCrearAcceso({ nombre, tipo: nuevoTipo, punto_acceso: nuevoPunto.trim() });
      setNuevoNombre(""); setNuevoTipo("vehicular"); setNuevoPunto(""); setMostrarAlta(false);
      cargar();
    } catch (err: any) {
      setMsgAlta(err?.message || "No se pudo crear");
    } finally {
      setCreando(false);
    }
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
        El <code>pin GPIO</code> es el pin de la Raspberry Pi que acciona el relay, y el <code>pulso</code> es
        cuántos milisegundos se mantiene el contacto seco. Un valor incorrecto puede impedir que una tranca abra.
      </div>

      <div className="dev-trancas-barra" style={{ flexWrap: "wrap", gap: 10 }}>
        <span className="dev-trancas-total">{lista.length} acceso(s) registrado(s)</span>
        {residenciales.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: filtroResidencial ? "#eef4ff" : "var(--fondo)",
            border: `1px solid ${filtroResidencial ? "#a9c4f5" : "var(--borde)"}`,
            borderRadius: 8, padding: "6px 10px",
          }}>
            <Building2 size={15} color={filtroResidencial ? "#2c5cc5" : "#8a94a3"} />
            <span className="small" style={{ fontWeight: 600, color: filtroResidencial ? "#2c5cc5" : "#5a6472", whiteSpace: "nowrap" }}>
              Filtrar por residencial:
            </span>
            <select value={filtroResidencial} onChange={(e) => setFiltroResidencial(e.target.value)}
              className="dev-tranca-tipo-sel" style={{ maxWidth: 220, border: "none", background: "transparent" }}>
              <option value="">Todas</option>
              {residenciales.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </select>
            {filtroResidencial && (
              <button className="ghost mini" onClick={() => setFiltroResidencial("")} title="Quitar filtro">✕</button>
            )}
          </div>
        )}
        <button className="dev-tranca-add" onClick={() => { setMostrarAlta((v) => !v); setMsgAlta(""); }}>
          {mostrarAlta ? "Cancelar" : "+ Agregar acceso"}
        </button>
      </div>

      {mostrarAlta && (
        <div className="dev-tranca-alta">
          <div className="dev-tranca-alta-campos">
            <label>
              <span>Nombre</span>
              <input type="text" placeholder="Ej: Entrada Principal Vehicular" maxLength={80}
                value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)} />
            </label>
            <label>
              <span>Tipo</span>
              <select value={nuevoTipo} onChange={(e) => setNuevoTipo(e.target.value)}>
                <option value="vehicular">Vehicular</option>
                <option value="peatonal">Peatonal</option>
              </select>
            </label>
            <label>
              <span>Punto de acceso</span>
              <input type="text" placeholder="Ej: Acceso Principal" maxLength={80} list="puntos-existentes"
                value={nuevoPunto} onChange={(e) => setNuevoPunto(e.target.value)} />
              <datalist id="puntos-existentes">
                {puntos.filter(Boolean).map((p) => <option key={p} value={p as string} />)}
              </datalist>
            </label>
            <button className="dev-tranca-btn" style={{ maxWidth: 140 }} disabled={creando} onClick={crear}>
              {creando ? "Creando…" : "Crear acceso"}
            </button>
          </div>
          {msgAlta && <div className="dev-tranca-msg err" style={{ marginTop: 10 }}>{msgAlta}</div>}
        </div>
      )}

      {(!accesos || accesos.length === 0) ? (
        <p className="muted" style={{ padding: 20 }}>No hay accesos físicos. Agregá el primero con el botón de arriba.</p>
      ) : (
        grupos.map((g) => (
          <div key={g.punto || "sin-punto"} className="dev-punto-grupo">
            <div className="dev-punto-titulo">
              <span className="dev-punto-ic"><Router size={16} /></span>
              <span>{g.punto || "Sin punto asignado"}</span>
              <span className="dev-punto-sub">{g.punto ? `Raspberry Pi · ${g.items.length} dispositivo(s)` : `${g.items.length} acceso(s) sin asignar a una Pi`}</span>
            </div>
            <div className="dev-trancas-grid">
              {g.items.map((a) => {
                const ed = edits[a.id] || { nombre: "", tipo: "vehicular", relay_pin: "", pulso_ms: "", punto_acceso: "" };
                const sinConfig = a.relay_pin == null;
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
                    <div className="dev-tranca-campos">
                      <label>
                        <span>Pin GPIO</span>
                        <input type="number" min={0} max={40} placeholder="—"
                          value={ed.relay_pin} onChange={(e) => setCampo(a.id, "relay_pin", e.target.value)} />
                      </label>
                      <label>
                        <span>Pulso (ms)</span>
                        <input type="number" min={100} max={5000} step={50}
                          value={ed.pulso_ms} onChange={(e) => setCampo(a.id, "pulso_ms", e.target.value)} />
                      </label>
                    </div>
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
        ))
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
  const [nuevoPunto, setNuevoPunto] = useState("");
  const [nuevaResidencial, setNuevaResidencial] = useState("");
  const [errorAlta, setErrorAlta] = useState("");
  const [creando, setCreando] = useState(false);
  // token recién generado para mostrar una vez
  const [tokenNuevo, setTokenNuevo] = useState<{ nombre: string; token: string } | null>(null);
  // puntos de acceso existentes (sacados de las trancas) para el desplegable
  const [puntos, setPuntos] = useState<string[]>([]);
  // Bases multi-residencial (Día 37): a qué cliente asignar cada Pi
  const [residenciales, setResidenciales] = useState<ResidencialDTO[]>([]);

  const cargar = useCallback(() => {
    setCargando(true);
    // Cargar dispositivos y puntos por separado: si una falla, la otra igual
    // funciona (ej. si la tabla de dispositivos aún no existe, los puntos se
    // cargan igual desde los accesos).
    devDispositivos().then(setPis).catch(() => setPis([])).finally(() => setCargando(false));
    devAccesosFisicos()
      .then((accesos) => {
        const ps = Array.from(new Set(accesos.map((a) => a.punto_acceso).filter(Boolean))) as string[];
        setPuntos(ps);
      })
      .catch(() => setPuntos([]));
    devResidenciales().then(setResidenciales).catch(() => setResidenciales([]));
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

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
    if (!nuevaResidencial) { setErrorAlta("Elegí a qué residencial pertenece esta Pi — así queda atada desde el momento en que se crea."); return; }
    setErrorAlta("");
    setCreando(true);
    try {
      const d = await devCrearDispositivo({ nombre: nuevoNombre.trim(), punto_acceso: nuevoPunto.trim(), residencial_id: nuevaResidencial });
      if (d.token) setTokenNuevo({ nombre: d.nombre, token: d.token });
      setNuevoNombre(""); setNuevoPunto(""); setNuevaResidencial(""); setMostrarAlta(false);
      cargar();
    } catch (err: any) {
      setErrorAlta(err?.message || "No se pudo crear la Pi");
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
        <strong><Router size={16} /> Raspberry Pi de los accesos.</strong> Cada punto de acceso tiene su propia Pi, que descarga
        su copia de residentes con permiso y valida localmente. Cada Pi se identifica con un <code>token</code> único
        y secreto. El <code>punto de acceso</code> debe coincidir con el de las trancas de ese punto.
      </div>

      <div className="dev-trancas-barra">
        <span className="dev-trancas-total">{pis?.length || 0} dispositivo(s)</span>
        <button className="dev-tranca-add" onClick={() => setMostrarAlta((v) => !v)}>
          {mostrarAlta ? "Cancelar" : "+ Agregar Raspberry Pi"}
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
              <span>Punto de acceso</span>
              <select className="dev-tranca-tipo-sel" value={nuevoPunto} onChange={(e) => setNuevoPunto(e.target.value)}>
                <option value="">— Elegí un punto —</option>
                {puntos.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label>
              <span>Residencial *</span>
              <select className="dev-tranca-tipo-sel" value={nuevaResidencial} onChange={(e) => setNuevaResidencial(e.target.value)}>
                <option value="">— Elegí una residencial —</option>
                {residenciales.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
              </select>
            </label>
            <button className="dev-tranca-btn" style={{ maxWidth: 160 }} disabled={creando} onClick={crear}>
              {creando ? "Creando…" : "Crear Pi"}
            </button>
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>
            * Obligatoria: la Pi queda atada a esa residencial desde el momento en que se crea — evita
            crear dispositivos sueltos que después haya que andar asignando.
          </p>
          {errorAlta && (
            <div className="dev-tranca-msg err" style={{ marginTop: 10 }}>{errorAlta}</div>
          )}
          {puntos.length === 0 && (
            <div className="dev-tranca-msg err" style={{ marginTop: 10 }}>
              No hay puntos de acceso todavía. Primero creá trancas con su punto en la pestaña <Construction size={16} /> Trancas.
            </div>
          )}
        </div>
      )}

      {tokenNuevo && (
        <div className="dev-modal-overlay" onClick={() => setTokenNuevo(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Token de {tokenNuevo.nombre}</h3>
            <p>Copiá este token y configuralo en la Raspberry Pi. <strong>No se vuelve a mostrar</strong> por seguridad. Si lo perdés, podés regenerarlo (y actualizarlo en la Pi).</p>
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
        <p className="muted" style={{ padding: 20 }}>No hay Raspberry Pi registradas. Agregá la primera con el botón de arriba.</p>
      ) : (
        <div className="dev-trancas-grid">
          {pis.map((d) => (
            <div key={d.id} className={`dev-tranca-card ${!d.activo ? "inactiva" : ""}`}>
              <div className="dev-tranca-head">
                <span className="dev-tranca-nombre">{d.nombre}</span>
                <span className={`dev-tranca-badge ${d.activo ? "ok" : "sin"}`}>{d.activo ? "Activa" : "Revocada"}</span>
              </div>
              <div className="dev-pi-info">
                <div><span>Punto:</span> {d.punto_acceso || <em className="muted">sin asignar</em>}</div>
                <div><span>Última sincronización:</span> {d.ultima_sync ? new Date(d.ultima_sync).toLocaleString() : "nunca"}</div>
              </div>
              <div style={{ margin: "8px 0" }}>
                <label className="muted small" style={{ display: "block", marginBottom: 4 }}>
                  Residencial <span title="Bases multi-residencial: qué cliente descarga información con esta Pi">ⓘ</span>
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

  useEffect(() => {
    devResidenciales().then(setLista).catch(() => setLista([]));
  }, []);

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
      </div>

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
