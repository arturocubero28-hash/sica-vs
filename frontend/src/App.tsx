import { useState, useEffect } from "react";
import {
  login, getMe, logout, getToken, setToken,
  activarCuenta, solicitarRecuperacion, restablecerPassword,
  type Usuario,
} from "./api/client";
import { UnidadesPanel } from "./modules/unidades/UnidadesPanel";
import { ResidentePortal } from "./modules/residente/ResidentePortal";
import { GuardiaPanel } from "./modules/guardia/GuardiaPanel";

export function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);
  const [vista, setVista] = useState<"login" | "activar" | "recuperar" | "reset">("login");
  const [tokenUrl, setTokenUrl] = useState("");

  useEffect(() => {
    // Detectar tokens de activación/reset en la URL
    const params = new URLSearchParams(window.location.search);
    const act = params.get("activar");
    const rst = params.get("reset");
    if (act) { setTokenUrl(act); setVista("activar"); setCargando(false); return; }
    if (rst) { setTokenUrl(rst); setVista("reset"); setCargando(false); return; }

    if (getToken()) {
      getMe().then(setUsuario).catch(() => logout()).finally(() => setCargando(false));
    } else {
      setCargando(false);
    }
  }, []);

  function onLogin(u: Usuario) { setUsuario(u); setVista("login"); }
  function onLogout() { logout(); setUsuario(null); setVista("login"); }

  if (cargando) return <div className="center">Cargando…</div>;

  if (vista === "activar") return <ActivarCuenta token={tokenUrl} onActivado={onLogin} />;
  if (vista === "recuperar") return <RecuperarPassword onVolver={() => setVista("login")} />;
  if (vista === "reset") return <ResetPassword token={tokenUrl} onOk={() => setVista("login")} />;

  if (!usuario) return <Login onLogin={onLogin} onRecuperar={() => setVista("recuperar")} />;
  return <Dashboard usuario={usuario} onLogout={onLogout} />;
}

// ─── Login ───────────────────────────────────────────────────
function Login({ onLogin, onRecuperar }: { onLogin: (u: Usuario) => void; onRecuperar: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function entrar() {
    setError(""); setEnviando(true);
    try { onLogin(await login(email, password)); }
    catch (e) { setError((e as Error).message); }
    finally { setEnviando(false); }
  }

  return (
    <div className="center">
      <div className="card">
        <h1>SICA-VS</h1>
        <p className="muted">Residencial Villas del Sol</p>
        <input placeholder="Correo electrónico" value={email} onChange={e => setEmail(e.target.value)} />
        <input type="password" placeholder="Contraseña" value={password}
          onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} />
        {error && <div className="error">{error}</div>}
        <button onClick={entrar} disabled={enviando}>{enviando ? "Entrando…" : "Iniciar sesión"}</button>
        <button className="ghost" disabled title="Disponible más adelante">Ingresar con huella / Face ID</button>
        <button className="link-btn" onClick={onRecuperar}>¿Olvidaste tu contraseña?</button>
        <p className="muted small">Admin: admin@villasdelsol.hn / admin123</p>
      </div>
    </div>
  );
}

// ─── Activar cuenta ──────────────────────────────────────────
function ActivarCuenta({ token, onActivado }: { token: string; onActivado: (u: Usuario) => void }) {
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function activar() {
    if (password.length < 6) { setError("La contraseña debe tener al menos 6 caracteres"); return; }
    if (password !== password2) { setError("Las contraseñas no coinciden"); return; }
    setError(""); setEnviando(true);
    try {
      const data = await activarCuenta(token, password);
      setToken(data.token);
      onActivado(data.usuario);
      window.history.replaceState({}, "", "/");
    } catch (e) { setError((e as Error).message); }
    finally { setEnviando(false); }
  }

  return (
    <div className="center">
      <div className="card">
        <h1>Activar tu cuenta</h1>
        <p className="muted">Define tu contraseña para acceder al sistema</p>
        <input type="password" placeholder="Nueva contraseña" value={password} onChange={e => setPassword(e.target.value)} />
        <input type="password" placeholder="Confirmar contraseña" value={password2}
          onChange={e => setPassword2(e.target.value)} onKeyDown={e => e.key === "Enter" && activar()} />
        {error && <div className="error">{error}</div>}
        <button onClick={activar} disabled={enviando}>{enviando ? "Activando…" : "Activar cuenta"}</button>
      </div>
    </div>
  );
}

// ─── Recuperar contraseña ────────────────────────────────────
function RecuperarPassword({ onVolver }: { onVolver: () => void }) {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [devToken, setDevToken] = useState("");
  const [error, setError] = useState("");

  async function solicitar() {
    setError(""); setMsg("");
    if (!email) { setError("Ingresa tu correo"); return; }
    try {
      const data = await solicitarRecuperacion(email);
      setMsg(data.message);
      if (data.dev_token) setDevToken(data.dev_token);
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="center">
      <div className="card">
        <h2>Recuperar contraseña</h2>
        <p className="muted">Te enviaremos un enlace para restablecer tu contraseña</p>
        <input placeholder="Tu correo electrónico" value={email} onChange={e => setEmail(e.target.value)} />
        {error && <div className="error">{error}</div>}
        {msg && <div className="ok-box">{msg}</div>}
        {devToken && (
          <div className="nota">
            <b>Dev:</b> <a href={`/?reset=${devToken}`}>Click aquí para restablecer</a>
          </div>
        )}
        <button onClick={solicitar}>Enviar enlace</button>
        <button className="link-btn" onClick={onVolver}>← Volver al login</button>
      </div>
    </div>
  );
}

// ─── Reset password ──────────────────────────────────────────
function ResetPassword({ token, onOk }: { token: string; onOk: () => void }) {
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function reset() {
    if (password.length < 6) { setError("Mínimo 6 caracteres"); return; }
    if (password !== password2) { setError("Las contraseñas no coinciden"); return; }
    setError("");
    try {
      const data = await restablecerPassword(token, password);
      setMsg(data.message);
      window.history.replaceState({}, "", "/");
      setTimeout(onOk, 1500);
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="center">
      <div className="card">
        <h2>Nueva contraseña</h2>
        <input type="password" placeholder="Nueva contraseña" value={password} onChange={e => setPassword(e.target.value)} />
        <input type="password" placeholder="Confirmar" value={password2}
          onChange={e => setPassword2(e.target.value)} onKeyDown={e => e.key === "Enter" && reset()} />
        {error && <div className="error">{error}</div>}
        {msg && <div className="ok-box">{msg}</div>}
        <button onClick={reset}>Restablecer contraseña</button>
      </div>
    </div>
  );
}

// ─── Dashboard ───────────────────────────────────────────────
function Dashboard({ usuario, onLogout }: { usuario: Usuario; onLogout: () => void }) {
  return (
    <div className="app">
      <header>
        <b>SICA-VS</b>
        <span className="muted">{usuario.nombre} · {usuario.rol}</span>
        <button className="ghost mini" onClick={onLogout}>Salir</button>
      </header>
      <main>
        {(usuario.rol === "admin" || usuario.rol === "super_admin") && <UnidadesPanel />}
        {usuario.rol === "guardia" && <GuardiaPanel />}
        {usuario.rol === "residente" && <ResidentePortal />}
      </main>
    </div>
  );
}
