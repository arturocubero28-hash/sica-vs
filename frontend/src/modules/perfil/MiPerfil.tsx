import { useState, useEffect } from "react";
import { getMe, cambiarPassword, listarSesiones, cerrarSesion, cerrarOtrasSesiones,
  registrarHuella, listarCredencialesHuella, eliminarCredencialHuella, soportaHuella,
  getConfigResidencial, setConfigResidencial,
  listarPuntosAcceso, crearPuntoAcceso, editarPuntoAcceso, historialCountPunto,
  type Usuario, type SesionDTO, type CredencialWebAuthnDTO, type ConfigResidencial,
  type PuntoAccesoDTO } from "../../api/client";
import { passwordValida, RequisitosPassword } from "../../utils/password";
import { Fingerprint } from "lucide-react";

export function MiPerfil() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [tab, setTab] = useState<"perfil" | "config" | "accesos">("perfil");
  useEffect(() => { getMe().then(setUsuario).catch(() => {}); }, []);

  if (!usuario) return <p className="muted">Cargando…</p>;

  const esAdmin = ["admin", "super_admin"].includes(usuario.rol);

  const rolLabel: Record<string, string> = {
    admin: "Administrador", super_admin: "Super Admin", guardia: "Guardia", residente: "Residente",
  };

  return (
    <div className="perfil">
      <div className="dash-head"><h2>Mi perfil</h2></div>

      {esAdmin && (
        <div className="tab-bar" style={{ display: "flex", gap: 0, marginBottom: 18 }}>
          <button className={`tab-btn ${tab === "perfil" ? "active" : ""}`}
            onClick={() => setTab("perfil")}>Mi perfil</button>
          <button className={`tab-btn ${tab === "config" ? "active" : ""}`}
            onClick={() => setTab("config")}>⚙ Configuraciones</button>
          <button className={`tab-btn ${tab === "accesos" ? "active" : ""}`}
            onClick={() => setTab("accesos")}>🚧 Puntos de acceso</button>
        </div>
      )}

      {tab === "perfil" && <>
        <div className="perfil-datos">
          <div className="perfil-avatar">
            {(usuario.nombre?.[0] || "") + (usuario.apellido?.[0] || "")}
          </div>
          <div>
            <div className="perfil-nombre">{usuario.nombre} {usuario.apellido}</div>
            <div className="muted">{usuario.email}</div>
            <span className="pill" style={{ marginTop: 6, display: "inline-block" }}>
              {rolLabel[usuario.rol] || usuario.rol}
            </span>
          </div>
        </div>
        <DatosForm usuario={usuario} />
        <PasswordForm />
        <HuellaDigital />
        <SesionesForm />
      </>}

      {tab === "config" && esAdmin && <ConfigPanel />}
      {tab === "accesos" && esAdmin && <PuntosAccesoPanel />}
    </div>
  );
}

function DatosForm({ usuario }: { usuario: Usuario }) {
  return (
    <div className="dash-card">
      <h3>Datos personales</h3>
      <div className="perfil-info-grid">
        <div className="perfil-info-item">
          <span className="muted small">Nombre</span>
          <b>{usuario.nombre} {usuario.apellido}</b>
        </div>
        <div className="perfil-info-item">
          <span className="muted small">Correo</span>
          <b>{usuario.email}</b>
        </div>
        {usuario.telefono && (
          <div className="perfil-info-item">
            <span className="muted small">Teléfono</span>
            <b>{usuario.telefono}</b>
          </div>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 10 }}>
        Para cambiar estos datos, contactá a la administración.
      </p>
    </div>
  );
}

function PasswordForm() {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [nueva2, setNueva2] = useState("");
  const [msg, setMsg] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function cambiar() {
    if (!passwordValida(nueva)) { setMsg("La contraseña no cumple los requisitos mínimos"); return; }
    if (nueva !== nueva2) { setMsg("Las contraseñas no coinciden"); return; }
    setGuardando(true); setMsg("");
    try {
      await cambiarPassword(actual, nueva);
      setMsg("✓ Contraseña actualizada");
      setActual(""); setNueva(""); setNueva2("");
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setMsg((e as Error).message); }
    finally { setGuardando(false); }
  }

  return (
    <div className="dash-card">
      <h3>Cambiar contraseña</h3>
      <div className="form-pago">
        <div className="form-field"><label>Contraseña actual</label>
          <input type="password" value={actual} onChange={e => setActual(e.target.value)} /></div>
        <div className="form-field"><label>Nueva contraseña</label>
          <input type="password" value={nueva} onChange={e => setNueva(e.target.value)} /></div>
        {nueva && <RequisitosPassword password={nueva} />}
        <div className="form-field"><label>Repetir nueva contraseña</label>
          <input type="password" value={nueva2} onChange={e => setNueva2(e.target.value)} /></div>
        {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"}>{msg}</div>}
        <button className="cuota-btn-pagar full" onClick={cambiar} disabled={guardando}>
          {guardando ? "Guardando…" : "Cambiar contraseña"}
        </button>
      </div>
    </div>
  );
}

function SesionesForm() {
  const [sesiones, setSesiones] = useState<SesionDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState("");

  function cargar() {
    setCargando(true);
    listarSesiones().then(setSesiones).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  async function cerrar(id: number) {
    try { await cerrarSesion(id); cargar(); }
    catch (e) { setMsg((e as Error).message); }
  }

  async function cerrarOtras() {
    if (!confirm("¿Cerrar sesión en todos los demás dispositivos?")) return;
    try {
      const r = await cerrarOtrasSesiones();
      setMsg(`✓ ${r.message}`);
      cargar();
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setMsg((e as Error).message); }
  }

  function tiempoRelativo(iso?: string) {
    if (!iso) return "";
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "hace un momento";
    if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
    return d.toLocaleDateString("es-HN");
  }

  const hayOtras = sesiones.some(s => !s.es_actual);

  return (
    <div className="dash-card">
      <h3>Dispositivos conectados</h3>
      <p className="muted small">Estos son los dispositivos donde tu cuenta tiene sesión abierta.
        Si no reconocés alguno, cerralo.</p>

      {cargando ? <p className="muted">Cargando…</p>
        : sesiones.length === 0 ? <p className="muted">No hay sesiones activas registradas.</p>
        : (
          <div className="sesiones-lista">
            {sesiones.map(s => (
              <div key={s.id} className={`sesion-item ${s.es_actual ? "actual" : ""}`}>
                <div className="sesion-info">
                  <div className="sesion-disp">
                    {s.dispositivo}
                    {s.es_actual && <span className="pill green" style={{ marginLeft: 8 }}>Este dispositivo</span>}
                  </div>
                  <div className="muted small">
                    {s.ip || "IP desconocida"} · activo {tiempoRelativo(s.ultimo_uso)}
                  </div>
                </div>
                {!s.es_actual && (
                  <button className="mini" style={{ color: "#c81e1e" }} onClick={() => cerrar(s.id)}>
                    Cerrar
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

      {msg && <div className={msg.startsWith("✓") ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg}</div>}

      {hayOtras && (
        <button className="ghost mini" style={{ marginTop: 12, color: "#c81e1e" }} onClick={cerrarOtras}>
          Cerrar todas las otras sesiones
        </button>
      )}
    </div>
  );
}

function HuellaDigital() {
  const [creds, setCreds] = useState<CredencialWebAuthnDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [registrando, setRegistrando] = useState(false);
  const [msg, setMsg] = useState("");
  const soportado = soportaHuella();

  function recargar() {
    listarCredencialesHuella().then(setCreds).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { if (soportado) recargar(); else setCargando(false); }, []);

  async function activar() {
    setMsg(""); setRegistrando(true);
    try {
      const nombre = navigator.userAgent.includes("Mobile") ? "Mi celular" : "Este dispositivo";
      await registrarHuella(nombre);
      setMsg("✓ Huella activada en este dispositivo");
      recargar();
    } catch (e) {
      const err = (e as Error).message || "";
      if (err.includes("NotAllowed") || err.includes("cancel")) setMsg("Registro cancelado.");
      else setMsg("No se pudo activar la huella. " + err);
    } finally { setRegistrando(false); }
  }

  async function quitar(id: number) {
    try { await eliminarCredencialHuella(id); recargar(); } catch { /* noop */ }
  }

  return (
    <div className="dash-card">
      <h3><Fingerprint size={16} /> Ingreso con huella</h3>
      {!soportado ? (
        <p className="muted small">Este dispositivo o navegador no soporta ingreso con huella.</p>
      ) : (
        <>
          <p className="muted small">
            Activá el ingreso con huella o Face ID en este dispositivo para entrar más rápido,
            sin escribir tu contraseña. Tu huella nunca sale de tu teléfono.
          </p>
          {cargando ? <p className="muted">Cargando…</p> : (
            <>
              {creds.length > 0 && (
                <div className="huella-lista">
                  {creds.map(c => (
                    <div key={c.id} className="huella-item">
                      <div>
                        <b>{c.nombre_dispositivo}</b>
                        <span className="muted small">
                          {c.ultimo_uso ? ` · último uso ${new Date(c.ultimo_uso).toLocaleDateString("es-HN")}` : " · sin usar aún"}
                        </span>
                      </div>
                      <button className="ghost mini" onClick={() => quitar(c.id)}>Quitar</button>
                    </div>
                  ))}
                </div>
              )}
              <button className="cuota-btn-pagar" style={{ maxWidth: 260, marginTop: 10 }}
                onClick={activar} disabled={registrando}>
                {registrando ? "Esperando huella…" : "＋ Activar huella en este dispositivo"}
              </button>
              {msg && <p className="small" style={{ marginTop: 8,
                color: msg.startsWith("✓") ? "#1d8a4a" : "#c81e1e" }}>{msg}</p>}
            </>
          )}
        </>
      )}
    </div>
  );
}


// ── Puntos de acceso (ACCESS-04, Auditoría Día 35) ──────────────────────────
// Gestión operativa para el admin: crear puntos, nombrarlos, elegir qué
// trancas tienen, activar/desactivar. El cableado real (relay_pin, pulso_ms)
// sigue siendo exclusivo del panel de desarrollador — un admin sin
// conocimiento técnico que lo tocara por error podría dejar una tranca sin
// funcionar o dos trancas apuntando al mismo pin GPIO.

function PuntosAccesoPanel() {
  const [puntos, setPuntos] = useState<PuntoAccesoDTO[] | null>(null);
  const [error, setError] = useState("");
  const [mostrarCrear, setMostrarCrear] = useState(false);

  function cargar() {
    listarPuntosAcceso(false).then(setPuntos).catch(() => setError("No se pudieron cargar los puntos de acceso"));
  }
  useEffect(cargar, []);

  return (
    <div>
      <div className="dash-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <h3>🚧 Puntos de acceso</h3>
          <button onClick={() => setMostrarCrear(true)} style={{ padding: "8px 16px" }}>
            + Nuevo punto
          </button>
        </div>
        <p className="muted small" style={{ marginBottom: 16 }}>
          Cada punto es un lugar físico de la residencial (ej. "Portón Principal") con una o más
          trancas: peatonal, entrada vehicular, salida vehicular. Los guardias eligen en cuál
          punto están trabajando; los accesos que registren quedan atribuidos a ese punto.
        </p>

        {error && <p className="err small">{error}</p>}
        {!puntos && !error && <p className="muted">Cargando…</p>}

        {puntos && puntos.length === 0 && (
          <div className="muted small" style={{ padding: "16px 0" }}>
            Todavía no hay ningún punto de acceso creado. Creá el primero con "+ Nuevo punto".
          </div>
        )}

        {puntos && puntos.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {puntos.map((p) => (
              <PuntoAccesoFila key={p.punto_acceso} punto={p} onCambio={cargar} />
            ))}
          </div>
        )}
      </div>

      <div className="dash-card" style={{ marginTop: 16 }}>
        <h3>ℹ️ Sobre esta configuración</h3>
        <div className="muted small" style={{ lineHeight: 1.6 }}>
          <p><b>Qué podés hacer acá:</b> crear puntos de acceso, ponerles nombre, elegir qué
          trancas tienen (peatonal / entrada vehicular / salida vehicular), y activarlos o
          desactivarlos.</p>
          <p><b>Qué NO se configura acá:</b> el cableado real hacia la Raspberry Pi (número de
          pin GPIO, duración del pulso del relay). Eso lo configura quien instala el hardware
          en sitio, desde el panel técnico — evita que un cambio accidental deje una tranca sin
          funcionar.</p>
          <p><b>Desactivar en vez de borrar:</b> por seguridad, un punto nunca se elimina de
          verdad si ya tiene historial de accesos — solo se desactiva. Así el historial de
          quién entró y por dónde nunca se pierde.</p>
        </div>
      </div>

      {mostrarCrear && (
        <ModalCrearPunto onCerrar={() => setMostrarCrear(false)} onCreado={() => { setMostrarCrear(false); cargar(); }} />
      )}
    </div>
  );
}

function PuntoAccesoFila({ punto, onCambio }: { punto: PuntoAccesoDTO; onCambio: () => void }) {
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(punto.punto_acceso);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [confirmarDesactivar, setConfirmarDesactivar] = useState(false);
  const [eventosCount, setEventosCount] = useState<number | null>(null);

  const tags: string[] = [];
  if (punto.tiene_peatonal) tags.push("Peatonal");
  if (punto.tiene_vehicular_entrada) tags.push("Entrada vehicular");
  if (punto.tiene_vehicular_salida) tags.push("Salida vehicular");

  async function guardarNombre() {
    if (!nombre.trim()) { setError("El nombre no puede quedar vacío"); return; }
    setGuardando(true); setError("");
    try {
      await editarPuntoAcceso(punto.punto_acceso, { nombre: nombre.trim() });
      setEditando(false);
      onCambio();
    } catch (e: any) {
      setError(e.message || "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  async function pedirDesactivar() {
    try {
      const res = await historialCountPunto(punto.punto_acceso);
      setEventosCount(res.eventos);
    } catch {
      setEventosCount(0);
    }
    setConfirmarDesactivar(true);
  }

  async function confirmarToggle() {
    setGuardando(true); setError("");
    try {
      await editarPuntoAcceso(punto.punto_acceso, { activo: !punto.activo });
      setConfirmarDesactivar(false);
      onCambio();
    } catch (e: any) {
      setError(e.message || "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div style={{
      padding: "12px 14px", borderRadius: 10, border: "1px solid var(--borde)",
      background: punto.activo ? "var(--fondo)" : "#f7f2ea",
      opacity: punto.activo ? 1 : 0.75,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1 }}>
          {editando ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
              <input value={nombre} onChange={(e) => setNombre(e.target.value)}
                style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--borde)", fontSize: 14 }} />
              <button onClick={guardarNombre} disabled={guardando} style={{ padding: "5px 12px", fontSize: 13 }}>
                {guardando ? "…" : "Guardar"}
              </button>
              <button onClick={() => { setEditando(false); setNombre(punto.punto_acceso); }}
                className="ghost" style={{ padding: "5px 12px", fontSize: 13 }}>
                Cancelar
              </button>
            </div>
          ) : punto.sin_nombre ? (
            <div style={{ marginBottom: 6 }}>
              <span className="pill" style={{ background: "#fdf0d5", color: "#92651c", marginBottom: 4, display: "inline-block" }}>
                ⚠ Sin nombre asignado
              </span>
              <p className="muted small" style={{ margin: "4px 0" }}>
                Estas trancas se crearon antes de existir los puntos de acceso con nombre.
                Ponele un nombre para poder gestionarlas normalmente.
              </p>
              <button onClick={() => { setEditando(true); setNombre(""); }}
                style={{ fontSize: 13, padding: "5px 12px" }}>
                Ponerle nombre
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <b style={{ fontSize: 15 }}>{punto.punto_acceso}</b>
              {!punto.activo && <span className="pill" style={{ background: "#eee", color: "#888" }}>Inactivo</span>}
              <button onClick={() => setEditando(true)}
                className="btn-tabla-neutro" style={{ fontSize: 12, padding: "2px 8px" }}>
                Editar nombre
              </button>
            </div>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {tags.map((t) => (
              <span key={t} className="muted small"
                style={{ background: "#fff", border: "1px solid var(--borde)", borderRadius: 6, padding: "2px 8px" }}>
                {t}
              </span>
            ))}
          </div>
          {error && <p className="err small" style={{ marginTop: 6 }}>{error}</p>}
        </div>

        {!confirmarDesactivar ? (
          <button onClick={pedirDesactivar} disabled={guardando}
            className="ghost" style={{ fontSize: 13, padding: "6px 12px", whiteSpace: "nowrap" }}>
            {punto.activo ? "Desactivar" : "Reactivar"}
          </button>
        ) : (
          <div style={{ textAlign: "right" }}>
            <p className="small" style={{ marginBottom: 6, maxWidth: 220 }}>
              {punto.activo
                ? (eventosCount !== null && eventosCount > 0
                    ? `Este punto tiene ${eventosCount} evento(s) registrados. No se borra — solo se desactiva y deja de aparecer para los guardias.`
                    : "¿Desactivar este punto? Dejará de aparecer para los guardias.")
                : "¿Reactivar este punto de acceso?"}
            </p>
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <button onClick={confirmarToggle} disabled={guardando} style={{ fontSize: 13, padding: "5px 12px" }}>
                {guardando ? "…" : "Sí, confirmar"}
              </button>
              <button onClick={() => setConfirmarDesactivar(false)}
                className="ghost" style={{ fontSize: 13, padding: "5px 12px" }}>
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ModalCrearPunto({ onCerrar, onCreado }: { onCerrar: () => void; onCreado: () => void }) {
  const [nombre, setNombre] = useState("");
  const [peatonal, setPeatonal] = useState(true);
  const [vehEntrada, setVehEntrada] = useState(false);
  const [vehSalida, setVehSalida] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  async function crear() {
    if (!nombre.trim()) { setError("Ponele un nombre al punto de acceso"); return; }
    if (!peatonal && !vehEntrada && !vehSalida) { setError("Elegí al menos una tranca"); return; }
    setGuardando(true); setError("");
    try {
      await crearPuntoAcceso({
        nombre: nombre.trim(), peatonal, vehicular_entrada: vehEntrada, vehicular_salida: vehSalida,
      });
      onCreado();
    } catch (e: any) {
      setError(e.message || "No se pudo crear el punto de acceso");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <h3>Nuevo punto de acceso</h3>
        <p className="muted small" style={{ marginBottom: 14 }}>
          Ej: "Portón Principal", "Portón Secundario". Elegí qué trancas tiene este punto.
        </p>

        <label className="small muted" style={{ display: "block", marginBottom: 4 }}>Nombre</label>
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Portón Secundario"
          style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--borde)", marginBottom: 14 }} />

        <label className="small muted" style={{ display: "block", marginBottom: 6 }}>Trancas de este punto</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
            <input type="checkbox" checked={peatonal} onChange={(e) => setPeatonal(e.target.checked)} />
            Peatonal
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
            <input type="checkbox" checked={vehEntrada} onChange={(e) => setVehEntrada(e.target.checked)} />
            Entrada vehicular
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
            <input type="checkbox" checked={vehSalida} onChange={(e) => setVehSalida(e.target.checked)} />
            Salida vehicular
          </label>
        </div>

        {error && <p className="err small" style={{ marginBottom: 10 }}>{error}</p>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCerrar} className="ghost" disabled={guardando}>Cancelar</button>
          <button onClick={crear} disabled={guardando}>{guardando ? "Creando…" : "Crear punto"}</button>
        </div>
      </div>
    </div>
  );
}

function ConfigPanel() {
  const [cfg, setCfg] = useState<ConfigResidencial | null>(null);
  const [diaPago, setDiaPago] = useState(1);
  const [diasGracia, setDiasGracia] = useState(7);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getConfigResidencial().then((c) => {
      setCfg(c);
      setDiaPago(c.dia_pago);
      setDiasGracia(c.dias_gracia);
    }).catch(() => setError("No se pudo cargar la configuración"));
  }, []);

  async function guardar() {
    setGuardando(true);
    setMsg("");
    setError("");
    try {
      const res = await setConfigResidencial({ dia_pago: diaPago, dias_gracia: diasGracia });
      setCfg({ dia_pago: res.dia_pago, dias_gracia: res.dias_gracia, actualizado_en: res.actualizado_en ?? null });
      const n = res.cuentas_actualizadas ?? 0;
      setMsg(n > 0
        ? `✓ Configuración guardada. Se actualizaron ${n} cuenta(s).`
        : "✓ Configuración guardada.");
    } catch (e: any) {
      setError(e.message || "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  if (!cfg) return <p className="muted">Cargando configuración…</p>;

  return (
    <div>
      <div className="dash-card">
        <h3>📅 Cobro mensual</h3>
        <p className="muted small" style={{ marginBottom: 12 }}>
          Estos valores aplican a <b>todas las cuentas</b> de la residencial.
          Si cambiás el día de pago, se actualiza automáticamente en todas.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, maxWidth: 420 }}>
          <div>
            <label className="small muted" style={{ display: "block", marginBottom: 4 }}>
              Día de pago del mes
            </label>
            <select value={diaPago} onChange={(e) => setDiaPago(Number(e.target.value))}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--borde)" }}>
              {Array.from({ length: 28 }, (_, i) => i + 1).map(d => (
                <option key={d} value={d}>Día {d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="small muted" style={{ display: "block", marginBottom: 4 }}>
              Días de gracia después del vencimiento
            </label>
            <select value={diasGracia} onChange={(e) => setDiasGracia(Number(e.target.value))}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--borde)" }}>
              {Array.from({ length: 16 }, (_, i) => i).map(d => (
                <option key={d} value={d}>{d} día{d !== 1 ? "s" : ""}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="muted small" style={{ marginTop: 12, padding: "10px 14px",
          background: "var(--fondo)", borderRadius: 10, border: "1px solid var(--borde)" }}>
          <b>Ejemplo con la configuración actual:</b><br/>
          La cuota se genera el <b>día {diaPago}</b> de cada mes.
          El residente tiene hasta el <b>día {Math.min(diaPago + diasGracia, 28)}</b> para pagar.
          Si no paga, su cuenta se bloquea automáticamente por mora.
        </div>

        <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={guardar} disabled={guardando}
            style={{ padding: "10px 24px" }}>
            {guardando ? "Guardando…" : "Guardar configuración"}
          </button>
          {msg && <span className="ok" style={{ fontSize: 13 }}>{msg}</span>}
          {error && <span className="err" style={{ fontSize: 13 }}>{error}</span>}
        </div>

        {cfg.actualizado_en && (
          <p className="muted small" style={{ marginTop: 8 }}>
            Última actualización: {new Date(cfg.actualizado_en).toLocaleString("es-HN")}
          </p>
        )}
      </div>

      <div className="dash-card" style={{ marginTop: 16 }}>
        <h3>ℹ️ Sobre estas configuraciones</h3>
        <div className="muted small" style={{ lineHeight: 1.6 }}>
          <p><b>Día de pago:</b> Es el día del mes en que se genera la cuota a cada cuenta.
          Al cambiarlo, se actualiza en todas las cuentas activas de forma inmediata.</p>
          <p><b>Días de gracia:</b> Después del día de pago, el residente tiene esta cantidad
          de días adicionales para pagar sin que su cuenta se bloquee. Si al vencer los días
          de gracia no ha pagado, la cuenta se bloquea automáticamente por mora.</p>
          <p><b>Prorrateo:</b> Cuando se da de alta una cuenta nueva a mitad de mes, la primera
          cuota se calcula proporcionalmente (los días restantes del mes, usando mes comercial
          de 30 días).</p>
        </div>
      </div>
    </div>
  );
}
