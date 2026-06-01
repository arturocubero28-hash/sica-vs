import { useState, useEffect } from "react";
import {
  login, getMe, logout, getToken, setToken,
  activarCuenta, solicitarRecuperacion, restablecerPassword,
  type Usuario, type Rol,
} from "./api/client";
import { UnidadesPanel } from "./modules/unidades/UnidadesPanel";
import { ResidentePortal } from "./modules/residente/ResidentePortal";
import { GuardiaPanel } from "./modules/guardia/GuardiaPanel";
import { DashboardAdmin } from "./modules/dashboard/DashboardAdmin";
import { PagosAdmin } from "./modules/dashboard/PagosAdmin";

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

// ─── Vista admin con pestañas ────────────────────────────────
function AdminView({ seccion }: { seccion: string }) {
  if (seccion === "casas") return <UnidadesPanel embedded />;
  if (seccion === "pagos") return <PagosAdmin />;
  return <DashboardAdmin />;
}

// ─── Dashboard con sidebar moderno ───────────────────────────
type NavItem = { id: string; label: string; icon: string };

function navParaRol(rol: Rol): NavItem[] {
  if (rol === "admin" || rol === "super_admin") {
    return [
      { id: "dashboard", label: "Monitoreo", icon: "📊" },
      { id: "casas", label: "Casas y residentes", icon: "🏘️" },
      { id: "pagos", label: "Revisión de pagos", icon: "💳" },
    ];
  }
  if (rol === "residente") {
    return [
      { id: "qr", label: "Generar QR", icon: "🎫" },
      { id: "historial", label: "Mis visitas", icon: "📋" },
      { id: "cuotas", label: "Mis cuotas", icon: "💳" },
      { id: "cuenta", label: "Mi cuenta", icon: "👤" },
    ];
  }
  return [{ id: "guardia", label: "Caseta", icon: "🛡️" }];
}

function Dashboard({ usuario, onLogout }: { usuario: Usuario; onLogout: () => void }) {
  const nav = navParaRol(usuario.rol);
  const [seccion, setSeccion] = useState(nav[0].id);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const esAdmin = usuario.rol === "admin" || usuario.rol === "super_admin";
  const esResidente = usuario.rol === "residente";

  const iniciales = `${usuario.nombre?.[0] || ""}${usuario.apellido?.[0] || ""}`.toUpperCase();
  const rolLabel: Record<string, string> = {
    admin: "Administrador", super_admin: "Super Admin",
    guardia: "Guardia", residente: "Residente",
  };

  return (
    <div className="shell">
      {/* Sidebar */}
      <aside className={`sidebar ${menuAbierto ? "abierto" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-logo">VS</div>
          <div className="brand-text">
            <b>SICA-VS</b>
            <span>Villas del Sol</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {nav.map(item => (
            <button
              key={item.id}
              className={`nav-item ${seccion === item.id ? "on" : ""}`}
              onClick={() => { setSeccion(item.id); setMenuAbierto(false); }}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="user-chip">
            <div className="user-avatar">{iniciales}</div>
            <div className="user-info">
              <b>{usuario.nombre} {usuario.apellido}</b>
              <span>{rolLabel[usuario.rol] || usuario.rol}</span>
            </div>
          </div>
          <button className="ghost mini logout-btn" onClick={onLogout}>Cerrar sesión</button>
        </div>
      </aside>

      {/* Overlay para cerrar menú en móvil */}
      {menuAbierto && <div className="sidebar-overlay" onClick={() => setMenuAbierto(false)} />}

      {/* Área principal */}
      <div className="main-area">
        <header className="topbar">
          <button className="hamburger" onClick={() => setMenuAbierto(true)} aria-label="Menú">☰</button>
          <b className="topbar-title">{nav.find(n => n.id === seccion)?.label}</b>
          <div className="user-avatar small">{iniciales}</div>
        </header>

        <main className="content">
          {esAdmin && <AdminView seccion={seccion} />}
          {usuario.rol === "guardia" && <GuardiaPanel />}
          {esResidente && <ResidentePortal seccion={seccion} />}
        </main>
      </div>

      {/* Barra de navegación inferior (solo móvil) */}
      <nav className="bottom-nav">
        {nav.map(item => (
          <button
            key={item.id}
            className={`bottom-item ${seccion === item.id ? "on" : ""}`}
            onClick={() => setSeccion(item.id)}
          >
            <span className="bottom-icon">{item.icon}</span>
            <span className="bottom-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
