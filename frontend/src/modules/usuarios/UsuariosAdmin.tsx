import { useState, useEffect, useRef } from "react";
import {
  listarUsuarios, crearCajero, crearGuardia,
  resetPasswordUsuario, editarUsuario,
  type UsuarioAdminDTO,
} from "../../api/client";
import { fechaRelativa } from "../../utils/formato";

const ROL_LABEL: Record<string, string> = {
  super_admin: "Super Admin", admin: "Administrador",
  guardia: "Guardia", residente: "Residente", cajero: "Cajero", desarrollador: "Desarrollador",
};

// Componente de mensaje de error/éxito uniforme para todo el sistema
function MsgBanner({ msg, onClose }: { msg: { tipo: "ok" | "err"; texto: string } | null; onClose?: () => void }) {
  if (!msg) return null;
  return (
    <div className={`msg-banner msg-banner-${msg.tipo}`} role="alert">
      <span>{msg.tipo === "err" ? "⚠ " : "✓ "}{msg.texto}</span>
      {onClose && <button className="msg-banner-close" onClick={onClose}>✕</button>}
    </div>
  );
}

export function UsuariosAdmin() {
  const [usuarios, setUsuarios] = useState<UsuarioAdminDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [filtroRol, setFiltroRol] = useState("");
  const [creando, setCreando] = useState<"cajero" | "guardia" | null>(null);
  const [credencial, setCredencial] = useState<{ email: string; pass: string; nombre: string } | null>(null);
  const [procesando, setProcesando] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);

  function recargar() {
    setCargando(true);
    listarUsuarios().then(setUsuarios).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  async function reset(u: UsuarioAdminDTO) {
    if (!confirm(`¿Resetear la contraseña de ${u.nombre} ${u.apellido}?\nSe generará una nueva contraseña genérica que deberá cambiar en su próximo ingreso.`)) return;
    setProcesando(u.id);
    try {
      const r = await resetPasswordUsuario(u.id);
      setCredencial({ email: u.email, pass: r.password_generica, nombre: `${u.nombre} ${u.apellido}` });
      recargar();
    } catch (e) {
      setMsg({ tipo: "err", texto: (e as Error).message });
    } finally {
      setProcesando(null);
    }
  }

  async function toggle(u: UsuarioAdminDTO) {
    setProcesando(u.id);
    try {
      await editarUsuario(u.id, { activo: !u.activo });
      recargar();
      setMsg({ tipo: "ok", texto: `${u.nombre} ${u.apellido} ${!u.activo ? "activado" : "desactivado"} correctamente.` });
    } catch (e) {
      setMsg({ tipo: "err", texto: (e as Error).message });
    } finally {
      setProcesando(null);
    }
  }

  const q = busqueda.trim().toLowerCase();
  const filtrados = usuarios.filter(u => {
    if (filtroRol && u.rol !== filtroRol) return false;
    if (q) {
      const blob = `${u.nombre} ${u.apellido} ${u.email}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="usuarios-admin">
      <div className="lista-head">
        <h2>Usuarios registrados</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-accion" onClick={() => setCreando("guardia")}>+ Crear guardia</button>
          <button className="btn-accion" onClick={() => setCreando("cajero")}>+ Crear cajero</button>
        </div>
      </div>

      {/* Mensaje global sticky */}
      {msg && (
        <div style={{ position: "sticky", top: 8, zIndex: 20, marginBottom: 12 }}>
          <MsgBanner msg={msg} onClose={() => setMsg(null)} />
        </div>
      )}

      <div className="lista-card">
        <div className="casas-filtros">
          <input className="casas-buscar" placeholder="Buscar por nombre o correo…"
            value={busqueda} onChange={e => setBusqueda(e.target.value)} />
          <select className="periodo-select" value={filtroRol} onChange={e => setFiltroRol(e.target.value)}>
            <option value="">Todos los roles</option>
            <option value="admin">Administradores</option>
            <option value="cajero">Cajeros</option>
            <option value="guardia">Guardias</option>
            <option value="residente">Residentes</option>
          </select>
        </div>
        <div className="casas-contador muted small">{filtrados.length} de {usuarios.length} usuarios</div>

        {cargando ? <p className="muted">Cargando…</p> : (
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr>
                  <th>Nombre</th><th>Correo</th><th>Rol</th>
                  <th>Último acceso</th><th>Estado</th><th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map(u => (
                  <tr key={u.id} className={!u.activo ? "fila-baja" : ""}>
                    <td>
                      {u.nombre} {u.apellido}
                      {u.debe_cambiar_password && (
                        <span className="badge-pendiente" title="Debe cambiar su contraseña">🔑</span>
                      )}
                    </td>
                    <td className="small">{u.email}</td>
                    <td><span className="pill">{ROL_LABEL[u.rol] || u.rol}</span></td>
                    <td className="small muted">{u.ultimo_acceso ? fechaRelativa(u.ultimo_acceso) : "Nunca"}</td>
                    <td>
                      {u.activo
                        ? <span className="pill green">Activo</span>
                        : <span className="pill">Inactivo</span>}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button className="btn-tabla btn-tabla-neutro"
                          disabled={procesando === u.id}
                          onClick={() => reset(u)}
                          title="Generar nueva contraseña genérica">
                          🔑 Reset clave
                        </button>
                        <button
                          className={`btn-tabla ${u.activo ? "btn-tabla-baja" : "btn-tabla-ok"}`}
                          disabled={procesando === u.id}
                          onClick={() => toggle(u)}>
                          {procesando === u.id ? "…" : u.activo ? "Desactivar" : "Activar"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {creando && (
        <FormUsuario tipo={creando}
          onCerrar={() => setCreando(null)}
          onCreado={(cred) => { setCreando(null); setCredencial(cred); recargar(); }} />
      )}

      {/* Modal de credenciales */}
      {credencial && (
        <div className="modal" onClick={() => setCredencial(null)}>
          <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-head">
              <h3>Credenciales generadas</h3>
              <button className="ghost mini" onClick={() => setCredencial(null)}>✕</button>
            </div>
            <p className="muted" style={{ marginBottom: 16 }}>
              Entregá estas credenciales a <b>{credencial.nombre}</b>. Deberá cambiar la contraseña en su primer ingreso.
            </p>
            <div className="credencial-box">
              <div style={{ marginBottom: 10 }}>
                <div className="muted small" style={{ marginBottom: 3 }}>Usuario (correo)</div>
                <b>{credencial.email}</b>
              </div>
              <div>
                <div className="muted small" style={{ marginBottom: 3 }}>Contraseña genérica</div>
                <b className="cred-pass">{credencial.pass}</b>
              </div>
            </div>
            <button className="btn-accion full" style={{ marginTop: 16 }} onClick={() => setCredencial(null)}>
              Entendido
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Formulario de nuevo usuario (guardia / cajero) ────────────────────────────
function FormUsuario({ tipo, onCerrar, onCreado }: {
  tipo: "cajero" | "guardia";
  onCerrar: () => void;
  onCreado: (cred: { email: string; pass: string; nombre: string }) => void;
}) {
  const [nombre, setNombre]   = useState("");
  const [apellido, setApellido] = useState("");
  const [email, setEmail]     = useState("");
  const [telefono, setTelefono] = useState("");
  const [errors, setErrors]   = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);

  function validar(): boolean {
    const e: Record<string, string> = {};
    if (!nombre.trim())   e.nombre   = "El nombre es obligatorio.";
    if (!apellido.trim()) e.apellido  = "El apellido es obligatorio.";
    if (!email.trim())    e.email     = "El correo electrónico es obligatorio.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
                          e.email     = "El correo no tiene un formato válido (ej. juan@villasdelsol.hn).";
    if (telefono.trim() && !/^[\d\s\-+()]{7,15}$/.test(telefono.trim()))
                          e.telefono  = "El teléfono no parece válido.";
    setErrors(e);
    if (Object.keys(e).length > 0) {
      setTimeout(() => errorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      return false;
    }
    return true;
  }

  async function crear() {
    if (!validar()) return;
    setGuardando(true);
    try {
      const fn = tipo === "cajero" ? crearCajero : crearGuardia;
      const u = await fn({ nombre: nombre.trim(), apellido: apellido.trim(), email: email.trim() });
      onCreado({ email: u.email, pass: u.password_generica || "", nombre: `${u.nombre} ${u.apellido}` });
    } catch (e) {
      setErrors({ _general: (e as Error).message });
      setTimeout(() => errorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } finally {
      setGuardando(false);
    }
  }

  const titulo = tipo === "cajero" ? "Nuevo cajero" : "Nuevo guardia";
  const ph = tipo === "cajero" ? "cajero@villasdelsol.hn" : "guardia@villasdelsol.hn";

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="modal-head">
          <h3>{titulo}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        {/* Zona de errores — siempre arriba, visible */}
        <div ref={errorRef}>
          {errors._general && (
            <div className="msg-banner msg-banner-err" style={{ marginBottom: 12 }}>
              ⚠ {errors._general}
            </div>
          )}
        </div>

        <div className="form-pago">
          <CampoFormulario label="Nombre *" error={errors.nombre}>
            <input value={nombre} onChange={e => { setNombre(e.target.value); setErrors(p => ({...p, nombre: ""})); }}
              placeholder="Ej. María" className={errors.nombre ? "input-error" : ""} />
          </CampoFormulario>
          <CampoFormulario label="Apellido *" error={errors.apellido}>
            <input value={apellido} onChange={e => { setApellido(e.target.value); setErrors(p => ({...p, apellido: ""})); }}
              placeholder="Ej. López" className={errors.apellido ? "input-error" : ""} />
          </CampoFormulario>
          <CampoFormulario label="Correo electrónico * (será su usuario de acceso)" error={errors.email}>
            <input type="email" value={email} onChange={e => { setEmail(e.target.value); setErrors(p => ({...p, email: ""})); }}
              placeholder={ph} className={errors.email ? "input-error" : ""} />
          </CampoFormulario>
          <CampoFormulario label="Teléfono" error={errors.telefono}>
            <input value={telefono} onChange={e => { setTelefono(e.target.value); setErrors(p => ({...p, telefono: ""})); }}
              placeholder="Ej. 9999-0000" className={errors.telefono ? "input-error" : ""} />
          </CampoFormulario>

          <p className="muted small" style={{ marginTop: 4 }}>
            * Campos obligatorios. Se creará con contraseña genérica que deberá cambiar en su primer ingreso.
          </p>

          <button className="btn-accion full" onClick={crear} disabled={guardando} style={{ marginTop: 12 }}>
            {guardando ? "Creando…" : `Crear ${tipo}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// Componente reutilizable para campo con label y error inline
function CampoFormulario({ label, error, children }: {
  label: string; error?: string; children: React.ReactNode;
}) {
  return (
    <div className="form-field">
      <label>{label}</label>
      {children}
      {error && <span className="campo-error">{error}</span>}
    </div>
  );
}
