import { useState, useEffect } from "react";
import {
  login, getMe, logout, getToken, setToken,
  activarCuenta, solicitarRecuperacion, restablecerPassword, cambiarPassword,
  contarPagosPendientes, misEdificios,
  type Usuario, type Rol,
} from "./api/client";
import { UnidadesPanel } from "./modules/unidades/UnidadesPanel";
import { ResidentePortal } from "./modules/residente/ResidentePortal";
import { GuardiaPanel } from "./modules/guardia/GuardiaPanel";
import { DashboardAdmin } from "./modules/dashboard/DashboardAdmin";
import { PagosAdmin } from "./modules/dashboard/PagosAdmin";
import { MonitoreoCamaras } from "./modules/camaras/MonitoreoCamaras";
import { ComunicadosAdmin } from "./modules/comunicados/ComunicadosAdmin";
import { Reporteria } from "./modules/reportes/Reporteria";
import { InventarioTarjetas } from "./modules/inventario/InventarioTarjetas";
import { HistorialAccesos } from "./modules/dashboard/HistorialAccesos";
import { MiPerfil } from "./modules/perfil/MiPerfil";
import { CajaPanel } from "./modules/caja/CajaPanel";
import { SupervisionCaja } from "./modules/caja/SupervisionCaja";
import { ArreglosPanel } from "./modules/arreglos/ArreglosPanel";
import { UsuariosAdmin } from "./modules/usuarios/UsuariosAdmin";
import { PanelDesarrollador } from "./modules/dev/PanelDesarrollador";
import { passwordValida, RequisitosPassword } from "./utils/password";

export function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);
  const [vista, setVista] = useState<"landing" | "login" | "activar" | "recuperar" | "reset">("landing");
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
  function onLogout() { logout(); setUsuario(null); setVista("landing"); }

  if (cargando) return <div className="center">Cargando…</div>;

  if (vista === "activar") return <ActivarCuenta token={tokenUrl} onActivado={onLogin} />;
  if (vista === "recuperar") return <RecuperarPassword onVolver={() => setVista("login")} />;
  if (vista === "reset") return <ResetPassword token={tokenUrl} onOk={() => setVista("login")} />;

  if (!usuario) {
    if (vista === "landing") return <Landing onEntrar={() => setVista("login")} />;
    return <Login onLogin={onLogin} onRecuperar={() => setVista("recuperar")} onVolver={() => setVista("landing")} />;
  }

  // Cambio obligatorio de contraseña en el primer login (guardias)
  if (usuario.debe_cambiar_password) {
    return <CambioObligatorio usuario={usuario} onListo={(u) => setUsuario(u)} />;
  }

  return <Dashboard usuario={usuario} onLogout={onLogout} />;
}

// ─── Login ───────────────────────────────────────────────────
function Login({ onLogin, onRecuperar, onVolver }: { onLogin: (u: Usuario) => void; onRecuperar: () => void; onVolver: () => void }) {
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
      <div className="card login-card">
        <img src="/logo-vs.png" alt="Villas del Sol" className="login-logo" />
        <h1>SICA-VS</h1>
        <p className="muted">Residencial Villas del Sol</p>
        <input placeholder="Correo electrónico" value={email} onChange={e => setEmail(e.target.value)} />
        <input type="password" placeholder="Contraseña" value={password}
          onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} />
        {error && <div className="error">{error}</div>}
        <button onClick={entrar} disabled={enviando}>{enviando ? "Entrando…" : "Iniciar sesión"}</button>
        <button className="ghost" disabled title="Disponible más adelante">Ingresar con huella / Face ID</button>
        <button className="link-btn" onClick={onRecuperar}>¿Olvidaste tu contraseña?</button>
        <button className="link-btn" onClick={onVolver}>← Volver al inicio</button>
      </div>
    </div>
  );
}

// ─── Landing page pública ────────────────────────────────────
function Landing({ onEntrar }: { onEntrar: () => void }) {
  const features = [
    { icon: "🎫", titulo: "Visitas con QR", desc: "Cada residente genera códigos QR para sus visitas. El guardia los valida en segundos." },
    { icon: "📹", titulo: "Monitoreo en vivo", desc: "Cámaras de seguridad de toda la residencial en una sola pantalla." },
    { icon: "💳", titulo: "Cuotas y pagos", desc: "Los residentes pagan en línea y la administración aprueba al instante." },
    { icon: "📊", titulo: "Control total", desc: "Sabé quién entra, quién autorizó y cuándo. Reportes para el patronato." },
  ];
  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="landing-brand">
          <img src="/logo-vs.png" alt="Villas del Sol" />
          <span>SICA-VS</span>
        </div>
        <button className="landing-login-btn" onClick={onEntrar}>Iniciar sesión</button>
      </header>

      <section className="landing-hero">
        <div className="landing-hero-text">
          <h1>Control de accesos<br /><span>inteligente y seguro</span></h1>
          <p>SICA-VS centraliza la seguridad de Residencial Villas del Sol: visitas con QR, monitoreo de cámaras, cuotas en línea y comunicación con los residentes — todo en una sola plataforma.</p>
          <button className="landing-cta" onClick={onEntrar}>Acceder al sistema →</button>
        </div>
        <div className="landing-hero-logo">
          <img src="/logo-vs.png" alt="Villas del Sol" />
        </div>
      </section>

      <section className="landing-features">
        {features.map((f, i) => (
          <div key={i} className="landing-feature">
            <div className="landing-feature-icon">{f.icon}</div>
            <h3>{f.titulo}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </section>

      <footer className="landing-footer">
        <p>Residencial Villas del Sol · San Pedro Sula, Honduras</p>
        <p className="muted small">SICA-VS — Sistema Integral de Control de Accesos</p>
      </footer>
    </div>
  );
}

// ─── Cambio obligatorio de contraseña ────────────────────────
function CambioObligatorio({ usuario, onListo }: { usuario: Usuario; onListo: (u: Usuario) => void }) {
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function guardar() {
    if (!passwordValida(pass)) { setError("La contraseña no cumple los requisitos mínimos"); return; }
    if (pass !== pass2) { setError("Las contraseñas no coinciden"); return; }
    setError(""); setEnviando(true);
    try {
      const r = await cambiarPassword("", pass);
      onListo(r.usuario);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="center">
      <div className="card login-card">
        <img src="/logo-vs.png" alt="Villas del Sol" className="login-logo" />
        <h1>Bienvenido, {usuario.nombre}</h1>
        <p className="muted">Por seguridad, definí una nueva contraseña antes de continuar.</p>
        <input type="password" placeholder="Nueva contraseña" value={pass}
          onChange={e => setPass(e.target.value)} />
        {pass && <RequisitosPassword password={pass} />}
        <input type="password" placeholder="Repetir contraseña" value={pass2}
          onChange={e => setPass2(e.target.value)} onKeyDown={e => e.key === "Enter" && guardar()} />
        {error && <div className="error">{error}</div>}
        <button onClick={guardar} disabled={enviando}>{enviando ? "Guardando…" : "Guardar y continuar"}</button>
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
    if (!passwordValida(password)) { setError("La contraseña no cumple los requisitos mínimos"); return; }
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
        {password && <RequisitosPassword password={password} />}
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
    if (!passwordValida(password)) { setError("La contraseña no cumple los requisitos mínimos"); return; }
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
        {password && <RequisitosPassword password={password} />}
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
  if (seccion === "monitoreo") return <MonitoreoCamaras />;
  if (seccion === "comunicados") return <ComunicadosAdmin />;
  if (seccion === "reportes") return <Reporteria />;
  if (seccion === "inventario") return <InventarioTarjetas />;
  if (seccion === "arreglos") return <ArreglosPanel />;
  if (seccion === "historial") return <HistorialAccesos />;
  if (seccion === "usuarios") return <UsuariosAdmin />;
  if (seccion === "caja") return <SupervisionCaja />;
  if (seccion === "perfil") return <MiPerfil />;
  return <DashboardAdmin />;
}

// ─── Dashboard con sidebar moderno ───────────────────────────
type NavItem = { id: string; label: string; icon: string };

function navParaRol(rol: Rol): NavItem[] {
  if (rol === "admin" || rol === "super_admin") {
    return [
      { id: "dashboard", label: "Dashboard", icon: "📊" },
      { id: "monitoreo", label: "Monitoreo", icon: "📹" },
      { id: "casas", label: "Casas y residentes", icon: "🏘️" },
      { id: "usuarios", label: "Usuarios", icon: "👥" },
      { id: "historial", label: "Historial", icon: "📜" },
      { id: "pagos", label: "Revisión de pagos", icon: "💳" },
      { id: "caja", label: "Supervisión de caja", icon: "🧾" },
      { id: "arreglos", label: "Arreglos de pago", icon: "🤝" },
      { id: "reportes", label: "Reportería", icon: "📈" },
      { id: "inventario", label: "Inventario de tarjetas", icon: "🎟️" },
      { id: "comunicados", label: "Comunicados", icon: "📣" },
      { id: "perfil", label: "Mi perfil", icon: "👤" },
    ];
  }
  if (rol === "cajero") {
    return [
      { id: "caja", label: "Caja", icon: "🧾" },
      { id: "arreglos", label: "Arreglos de pago", icon: "🤝" },
      { id: "perfil", label: "Mi perfil", icon: "⚙️" },
    ];
  }
  if (rol === "desarrollador") {
    return [
      { id: "dev", label: "Sistema", icon: "🖥️" },
      { id: "caja", label: "Supervisión de caja", icon: "🧾" },
      { id: "perfil", label: "Mi perfil", icon: "⚙️" },
    ];
  }
  if (rol === "residente") {
    return [
      { id: "home", label: "Inicio", icon: "🏠" },
      { id: "qr", label: "Generar QR", icon: "🎫" },
      { id: "historial", label: "Mis visitas", icon: "📋" },
      { id: "cuotas", label: "Mis cuotas", icon: "💳" },
      { id: "cuenta", label: "Mi cuenta", icon: "👤" },
      { id: "perfil", label: "Mi perfil", icon: "⚙️" },
    ];
  }
  return [
    { id: "guardia", label: "Caseta", icon: "🛡️" },
    { id: "perfil", label: "Mi perfil", icon: "⚙️" },
  ];
}

function Dashboard({ usuario, onLogout }: { usuario: Usuario; onLogout: () => void }) {
  const navBase = navParaRol(usuario.rol);
  const [esDuenoEdif, setEsDuenoEdif] = useState(false);
  const esAdmin = usuario.rol === "admin" || usuario.rol === "super_admin";
  const esResidente = usuario.rol === "residente";

  // Detectar si el residente es dueño de algún edificio (para mostrar "Mi edificio")
  useEffect(() => {
    if (!esResidente) return;
    misEdificios().then(eds => setEsDuenoEdif(eds.length > 0)).catch(() => {});
  }, [esResidente]);

  // Insertar "Mi edificio" antes de "Mi perfil" si es dueño
  const nav = esDuenoEdif
    ? (() => {
        const items = [...navBase];
        const idx = items.findIndex(i => i.id === "perfil");
        const item = { id: "edificio", label: "Mi edificio", icon: "🏢" };
        if (idx >= 0) items.splice(idx, 0, item); else items.push(item);
        return items;
      })()
    : navBase;

  const [seccion, setSeccion] = useState(navBase[0].id);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [pagosBadge, setPagosBadge] = useState(0);

  // Polling de pagos pendientes cada 30 segundos (solo admin)
  useEffect(() => {
    if (!esAdmin) return;
    let id: ReturnType<typeof setInterval>;
    function poll() {
      contarPagosPendientes()
        .then(r => setPagosBadge(r.pendientes))
        .catch(() => {
          // Si falla (token expirado), detenemos el polling
          clearInterval(id);
        });
    }
    poll();
    id = setInterval(poll, 30_000);
    return () => clearInterval(id);
  }, [esAdmin]);

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
              {item.id === "pagos" && pagosBadge > 0 && (
                <span className="nav-badge">{pagosBadge}</span>
              )}
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
          {usuario.rol === "desarrollador" && (
            seccion === "perfil" ? <div className="card wide"><MiPerfil /></div>
            : seccion === "caja" ? <SupervisionCaja />
            : <PanelDesarrollador />
          )}
          {usuario.rol === "cajero" && (
            seccion === "perfil" ? <div className="card wide"><MiPerfil /></div>
            : seccion === "arreglos" ? <ArreglosPanel />
            : <CajaPanel />
          )}
          {usuario.rol === "guardia" && (seccion === "perfil" ? <div className="card wide"><MiPerfil /></div> : <GuardiaPanel />)}
          {esResidente && (seccion === "perfil" ? <div className="card wide"><MiPerfil /></div> : <ResidentePortal seccion={seccion} />)}
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
            <span className="bottom-icon" style={{ position: "relative" }}>
              {item.icon}
              {item.id === "pagos" && pagosBadge > 0 && (
                <span className="bottom-badge">{pagosBadge}</span>
              )}
            </span>
            <span className="bottom-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
