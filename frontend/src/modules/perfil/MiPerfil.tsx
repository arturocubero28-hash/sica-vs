import { useState, useEffect } from "react";
import { getMe, cambiarPassword, listarSesiones, cerrarSesion, cerrarOtrasSesiones,
  type Usuario, type SesionDTO } from "../../api/client";
import { passwordValida, RequisitosPassword } from "../../utils/password";

export function MiPerfil() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  useEffect(() => { getMe().then(setUsuario).catch(() => {}); }, []);

  if (!usuario) return <p className="muted">Cargando…</p>;

  const rolLabel: Record<string, string> = {
    admin: "Administrador", super_admin: "Super Admin", guardia: "Guardia", residente: "Residente",
  };

  return (
    <div className="perfil">
      <div className="dash-head"><h2>Mi perfil</h2></div>

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
      <SesionesForm />
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
