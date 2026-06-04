import { useState, useEffect } from "react";
import {
  listarUsuarios, crearCajero, resetPasswordUsuario, editarUsuario,
  type UsuarioAdminDTO,
} from "../../api/client";

const ROL_LABEL: Record<string, string> = {
  super_admin: "Super Admin", admin: "Administrador",
  guardia: "Guardia", residente: "Residente", cajero: "Cajero",
};

export function UsuariosAdmin() {
  const [usuarios, setUsuarios] = useState<UsuarioAdminDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [filtroRol, setFiltroRol] = useState("");
  const [creandoCajero, setCreandoCajero] = useState(false);
  const [credencial, setCredencial] = useState<{ email: string; pass: string } | null>(null);

  function recargar() {
    setCargando(true);
    listarUsuarios().then(setUsuarios).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  async function reset(u: UsuarioAdminDTO) {
    if (!confirm(`¿Resetear la contraseña de ${u.nombre} ${u.apellido} a la genérica?`)) return;
    const r = await resetPasswordUsuario(u.id);
    setCredencial({ email: u.email, pass: r.password_generica });
    recargar();
  }
  async function toggle(u: UsuarioAdminDTO) {
    await editarUsuario(u.id, { activo: !u.activo });
    recargar();
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
      <div className="dash-head">
        <h2>Usuarios registrados</h2>
        <button className="cuota-btn-pagar" style={{ maxWidth: 170 }} onClick={() => setCreandoCajero(true)}>
          + Crear cajero
        </button>
      </div>

      <div className="casas-filtros">
        <input className="casas-buscar" placeholder="🔍 Buscar por nombre o correo…"
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
            <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {filtrados.map(u => (
                <tr key={u.id} className={!u.activo ? "fila-baja" : ""}>
                  <td>{u.nombre} {u.apellido}</td>
                  <td className="small">{u.email}</td>
                  <td><span className="pill">{ROL_LABEL[u.rol] || u.rol}</span></td>
                  <td>{u.activo ? <span className="pill green">Activo</span> : <span className="pill">Inactivo</span>}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button className="mini" onClick={() => reset(u)}>Reset clave</button>
                    <button className={`mini ${u.activo ? "btn-baja" : "btn-reactivar"}`} onClick={() => toggle(u)}>
                      {u.activo ? "Desactivar" : "Activar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creandoCajero && (
        <FormCajero onCerrar={() => setCreandoCajero(false)}
          onCreado={(cred) => { setCreandoCajero(false); setCredencial(cred); recargar(); }} />
      )}

      {credencial && (
        <div className="modal" onClick={() => setCredencial(null)}>
          <div className="modal-body" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Credenciales</h3>
              <button className="ghost mini" onClick={() => setCredencial(null)}>✕</button>
            </div>
            <p className="muted">Entregá estas credenciales. Deberá cambiar la contraseña en su primer ingreso.</p>
            <div className="credencial-box">
              <div><span className="muted small">Usuario (correo)</span><b>{credencial.email}</b></div>
              <div><span className="muted small">Contraseña genérica</span><b className="cred-pass">{credencial.pass}</b></div>
            </div>
            <button className="cuota-btn-pagar full" onClick={() => setCredencial(null)}>Entendido</button>
          </div>
        </div>
      )}
    </div>
  );
}

function FormCajero({ onCerrar, onCreado }: {
  onCerrar: () => void; onCreado: (cred: { email: string; pass: string }) => void;
}) {
  const [nombre, setNombre] = useState("");
  const [apellido, setApellido] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function crear() {
    if (!nombre.trim() || !apellido.trim() || !email.trim()) { setError("Todos los campos son obligatorios"); return; }
    setError(""); setGuardando(true);
    try {
      const c = await crearCajero({ nombre, apellido, email });
      onCreado({ email: c.email, pass: c.password_generica || "" });
    } catch (e) { setError((e as Error).message); }
    finally { setGuardando(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Nuevo cajero</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <div className="form-pago">
          <div className="form-field"><label>Nombre</label>
            <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej. María" /></div>
          <div className="form-field"><label>Apellido</label>
            <input value={apellido} onChange={e => setApellido(e.target.value)} placeholder="Ej. López" /></div>
          <div className="form-field"><label>Correo (será su usuario)</label>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="cajero@villasdelsol.hn" /></div>
          <p className="muted small">Se creará con contraseña genérica que deberá cambiar en su primer ingreso.</p>
          {error && <div className="error">{error}</div>}
          <button className="cuota-btn-pagar full" onClick={crear} disabled={guardando}>
            {guardando ? "Creando…" : "Crear cajero"}
          </button>
        </div>
      </div>
    </div>
  );
}
