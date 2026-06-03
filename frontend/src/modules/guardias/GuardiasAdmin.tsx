import { useState, useEffect } from "react";
import {
  listarGuardias, crearGuardia, editarGuardia, resetPasswordGuardia,
  type GuardiaDTO,
} from "../../api/client";

export function GuardiasAdmin() {
  const [guardias, setGuardias] = useState<GuardiaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [creando, setCreando] = useState(false);
  const [credencial, setCredencial] = useState<{ email: string; pass: string } | null>(null);

  function recargar() {
    listarGuardias().then(setGuardias).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  async function toggleActivo(g: GuardiaDTO) {
    await editarGuardia(g.id, { activo: !g.activo });
    recargar();
  }

  async function resetPass(g: GuardiaDTO) {
    if (!confirm(`¿Restablecer la contraseña de ${g.nombre} ${g.apellido} a la genérica?`)) return;
    const r = await resetPasswordGuardia(g.id);
    setCredencial({ email: g.email, pass: r.password_generica });
    recargar();
  }

  return (
    <div className="guardias-admin">
      <div className="dash-head">
        <h2>Guardias</h2>
        <button className="cuota-btn-pagar" style={{ maxWidth: 170 }} onClick={() => setCreando(true)}>
          + Crear guardia
        </button>
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : guardias.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon">🛡️</div>
          <p>No hay guardias registrados.</p>
        </div>
      ) : (
        <div className="config-list">
          {guardias.map(g => (
            <div key={g.id} className="config-cam">
              <div className="config-cam-info">
                <div className="config-cam-nombre">
                  {g.nombre} {g.apellido}
                  {!g.activo && <span className="pill" style={{ marginLeft: 8 }}>Inactivo</span>}
                  {g.debe_cambiar_password && <span className="pill amber" style={{ marginLeft: 8 }}>Debe cambiar clave</span>}
                </div>
                <div className="muted small">{g.email}</div>
              </div>
              <div className="config-cam-acciones">
                <button className="ghost mini" onClick={() => resetPass(g)}>Resetear clave</button>
                <button className="ghost mini" onClick={() => toggleActivo(g)}>
                  {g.activo ? "Desactivar" : "Activar"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {creando && (
        <FormGuardia
          onCerrar={() => setCreando(false)}
          onCreado={(cred) => { setCreando(false); setCredencial(cred); recargar(); }}
        />
      )}

      {credencial && (
        <div className="modal" onClick={() => setCredencial(null)}>
          <div className="modal-body" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Credenciales del guardia</h3>
              <button className="ghost mini" onClick={() => setCredencial(null)}>✕</button>
            </div>
            <p className="muted">Entregá estas credenciales al guardia. Deberá cambiar la contraseña en su primer ingreso.</p>
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

function FormGuardia({ onCerrar, onCreado }: {
  onCerrar: () => void; onCreado: (cred: { email: string; pass: string }) => void;
}) {
  const [nombre, setNombre] = useState("");
  const [apellido, setApellido] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function crear() {
    if (!nombre.trim() || !apellido.trim() || !email.trim()) {
      setError("Todos los campos son obligatorios"); return;
    }
    setError(""); setGuardando(true);
    try {
      const g = await crearGuardia({ nombre, apellido, email });
      onCreado({ email: g.email, pass: g.password_generica || "" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Nuevo guardia</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <div className="form-pago">
          <div className="form-field"><label>Nombre</label>
            <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej. Carlos" /></div>
          <div className="form-field"><label>Apellido</label>
            <input value={apellido} onChange={e => setApellido(e.target.value)} placeholder="Ej. Martínez" /></div>
          <div className="form-field"><label>Correo (será su usuario)</label>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="guardia@villasdelsol.hn" /></div>
          <p className="muted small">Se creará con una contraseña genérica que el guardia deberá cambiar en su primer ingreso.</p>
          {error && <div className="error">{error}</div>}
          <button className="cuota-btn-pagar full" onClick={crear} disabled={guardando}>
            {guardando ? "Creando…" : "Crear guardia"}
          </button>
        </div>
      </div>
    </div>
  );
}
