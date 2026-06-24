import { useState, useEffect, useCallback } from "react";
import { devMetricas, devLogs, devMetricasCodigo, devSeguridad, devAccesosFisicos, devConfigurarAcceso, devCrearAcceso, devHistorialCount, devEliminarAcceso, type DevMetricasDTO, type MetricasCodigoDTO, type SeguridadDTO, type AccesoFisicoDTO } from "../../api/client";

export function PanelDesarrollador() {
  const [m, setM] = useState<DevMetricasDTO | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [cargando, setCargando] = useState(true);
  const [tab, setTab] = useState<"salud" | "logs" | "codigo" | "seguridad" | "trancas">("salud");
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
        <button className={`hist-tab ${tab === "salud" ? "on" : ""}`} onClick={() => setTab("salud")}>🖥️ Salud del sistema</button>
        <button className={`hist-tab ${tab === "logs" ? "on" : ""}`} onClick={() => setTab("logs")}>🔍 Logs de auditoría</button>
        <button className={`hist-tab ${tab === "codigo" ? "on" : ""}`} onClick={() => setTab("codigo")}>📊 Métricas de código</button>
        <button className={`hist-tab ${tab === "seguridad" ? "on" : ""}`} onClick={() => setTab("seguridad")}>🛡️ Seguridad</button>
        <button className={`hist-tab ${tab === "trancas" ? "on" : ""}`} onClick={() => setTab("trancas")}>🚧 Trancas</button>
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
                <p className="muted small">⚠️ {m.sistema.error}</p>
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
            <div className="cuota-vacia"><div className="cuota-vacia-icon">🔍</div><p>Sin logs que coincidan.</p></div>
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
          <span style={{ fontSize: 28 }}>🛡️</span>
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
          <div className="metric-top"><span className="metric-label">Logins fallidos (24h)</span><span className="metric-icon">⚠</span></div>
          <div className="metric-valor" style={{ fontSize: 24 }}>{s.login_fallidos_24h}</div>
          <span className="muted small">{s.login_fallidos_7d} en 7 días</span>
        </div>
        <div className="metric-card naranja">
          <div className="metric-top"><span className="metric-label">Bloqueos por saturación (24h)</span><span className="metric-icon">🚦</span></div>
          <div className="metric-valor" style={{ fontSize: 24 }}>{s.bloqueos_saturacion_24h}</div>
          <span className="muted small">{s.bloqueos_saturacion_7d} en 7 días</span>
        </div>
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Accesos no autorizados (24h)</span><span className="metric-icon">🔒</span></div>
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
          <h3 style={{ color: "#c81e1e" }}>⚠ Intentos contra cuentas privilegiadas</h3>
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
          <p className="muted">No hay logins fallidos registrados. 👍</p>
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
  const [edits, setEdits] = useState<Record<number, { nombre: string; tipo: string; relay_pin: string; pulso_ms: string }>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ id: number; texto: string; ok: boolean } | null>(null);
  // Alta
  const [mostrarAlta, setMostrarAlta] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState("vehicular");
  const [creando, setCreando] = useState(false);
  const [msgAlta, setMsgAlta] = useState("");
  // Baja
  const [borrar, setBorrar] = useState<{ acceso: AccesoFisicoDTO; eventos: number } | null>(null);
  const [borrando, setBorrando] = useState(false);

  const cargar = useCallback(() => {
    setCargando(true);
    devAccesosFisicos()
      .then((data) => {
        setAccesos(data);
        const e: Record<number, { nombre: string; tipo: string; relay_pin: string; pulso_ms: string }> = {};
        data.forEach((a) => { e[a.id] = { nombre: a.nombre, tipo: a.tipo, relay_pin: a.relay_pin == null ? "" : String(a.relay_pin), pulso_ms: String(a.pulso_ms) }; });
        setEdits(e);
      })
      .catch(() => setAccesos([]))
      .finally(() => setCargando(false));
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  function setCampo(id: number, campo: "nombre" | "tipo" | "relay_pin" | "pulso_ms", valor: string) {
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
      await devCrearAcceso({ nombre, tipo: nuevoTipo });
      setNuevoNombre(""); setNuevoTipo("vehicular"); setMostrarAlta(false);
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

  return (
    <div className="dev-trancas">
      <div className="dev-trancas-aviso">
        <strong>⚠️ Configuración sensible.</strong> Estos valores controlan el hardware físico de las trancas.
        El <code>pin GPIO</code> es el pin de la Raspberry Pi que acciona el relay, y el <code>pulso</code> es
        cuántos milisegundos se mantiene el contacto seco. Un valor incorrecto puede impedir que una tranca abra.
      </div>

      <div className="dev-trancas-barra">
        <span className="dev-trancas-total">{accesos?.length || 0} acceso(s) registrado(s)</span>
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
        <div className="dev-trancas-grid">
          {accesos.map((a) => {
            const ed = edits[a.id] || { nombre: "", tipo: "vehicular", relay_pin: "", pulso_ms: "" };
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
                  <button className="dev-tranca-del" onClick={() => pedirBorrar(a)} title="Eliminar acceso">🗑</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {borrar && (
        <div className="dev-modal-overlay" onClick={() => !borrando && setBorrar(null)}>
          <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Eliminar acceso</h3>
            <p>¿Seguro que querés eliminar <strong>{borrar.acceso.nombre}</strong>?</p>
            {borrar.eventos > 0 && (
              <div className="dev-tranca-msg err" style={{ marginBottom: 14 }}>
                ⚠️ Este acceso tiene <strong>{borrar.eventos}</strong> registro(s) en el historial de entradas/salidas.
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
