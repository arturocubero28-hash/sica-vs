import { useState, useEffect, type ReactNode } from "react";
import {
  login, getMe, logout, getToken, setToken,
  activarCuenta, solicitarRecuperacion, restablecerPassword, cambiarPassword,
  contarPagosPendientes, misEdificios,
  loginConHuella, soportaHuella,
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
  const [conHuella, setConHuella] = useState(false);

  async function entrar() {
    setError(""); setEnviando(true);
    try { onLogin(await login(email, password)); }
    catch (e) { setError((e as Error).message); }
    finally { setEnviando(false); }
  }

  async function entrarConHuella() {
    setError(""); setConHuella(true);
    try { onLogin(await loginConHuella()); }
    catch (e) {
      const err = (e as Error).message || "";
      if (err.includes("NotAllowed") || err.includes("cancel")) setError("Ingreso con huella cancelado.");
      else if (err.includes("no está registrada")) setError("Esta huella no está registrada. Entrá con contraseña y activala en tu perfil.");
      else setError(err || "No se pudo entrar con huella.");
    }
    finally { setConHuella(false); }
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
        {soportaHuella() && (
          <button className="ghost" onClick={entrarConHuella} disabled={conHuella}>
            {conHuella ? "Esperando huella…" : "🔐 Ingresar con huella / Face ID"}
          </button>
        )}
        <button className="link-btn" onClick={onRecuperar}>¿Olvidaste tu contraseña?</button>
        <button className="link-btn" onClick={onVolver}>← Volver al inicio</button>
      </div>
    </div>
  );
}

// ─── Landing page pública ────────────────────────────────────
function Landing({ onEntrar }: { onEntrar: () => void }) {
  const modulos = [
    { n: "01", titulo: "Visitas con QR", desc: "El residente genera el código desde su teléfono. El guardia lo valida en la garita en segundos, con foto y registro." },
    { n: "02", titulo: "Monitoreo en vivo", desc: "Las cámaras de los cuatro accesos en una sola pantalla, con historial de cada entrada y salida." },
    { n: "03", titulo: "Cuotas y caja", desc: "Pagos en línea, aprobación inmediata y arqueo de caja con cierre diario cuadrado al centavo." },
    { n: "04", titulo: "Control y reportes", desc: "Quién entró, quién autorizó y a qué hora. Reportes financieros y de acceso para el patronato." },
  ];
  const roles = [
    { ic: "\u{1F6E1}\uFE0F", t: "Guardia", d: "Valida visitas y tarjetas en la garita" },
    { ic: "\u{1F3E0}", t: "Residente", d: "Genera QR y paga sus cuotas en línea" },
    { ic: "\u{1F4CA}", t: "Administración", d: "Controla accesos, pagos y reportes" },
    { ic: "\u{1F4B5}", t: "Cajero", d: "Cobra en ventanilla con arqueo en vivo" },
  ];

  // Muestra una captura real si existe en /landing, o el mockup dibujado por código.
  function ShotConFallback({ src, children }: { src: string; children: ReactNode }) {
    const [falla, setFalla] = useState(false);
    if (falla) return <>{children}</>;
    return <img className="lp-shot-img" src={src} alt="" onError={() => setFalla(true)} />;
  }

  return (
    <div className="lp">
      <header className="lp-nav lp-anim lp-d1">
        <div className="lp-brand">
          <img src="/logo-vs.png" alt="Villas del Sol" />
          <div>
            <span className="lp-brand-name">SICA-VS</span>
            <span className="lp-brand-sub">Villas del Sol</span>
          </div>
        </div>
        <button className="lp-nav-btn" onClick={onEntrar}>Iniciar sesión</button>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-text">
          <div className="lp-hero-eyebrow lp-anim lp-d1">Sistema Integral de Control de Accesos</div>
          <h1 className="lp-hero-title lp-anim lp-d2">
            La seguridad de la residencial,<br /><span>en una sola plataforma.</span>
          </h1>
          <p className="lp-hero-lead lp-anim lp-d3">
            SICA-VS conecta la garita, la administración y a cada familia de Villas del Sol.
            Accesos, cámaras, cuotas y comunicación, operando juntos en tiempo real.
          </p>
          <div className="lp-hero-actions lp-anim lp-d4">
            <button className="lp-cta" onClick={onEntrar}>Acceder al sistema →</button>
            <span className="lp-hero-note">San Pedro Sula, Honduras</span>
          </div>
        </div>
        <div className="lp-hero-mock lp-anim lp-d3">
          <ShotConFallback src="/landing/dashboard.png">
            <div className="lp-mock">
              <div className="lp-mock-bar">
                <span className="lp-mock-dot" style={{ background: "#ff5f57" }} />
                <span className="lp-mock-dot" style={{ background: "#febc2e" }} />
                <span className="lp-mock-dot" style={{ background: "#28c840" }} />
              </div>
              <div className="lp-mock-body">
                <div className="lp-mock-h"><span className="lp-mock-title">Panel de control</span><span className="lp-mock-pill">EN VIVO</span></div>
                <div className="lp-mock-cards">
                  <div className="lp-mc"><div className="lp-mc-n">487</div><div className="lp-mc-l">Casas activas</div></div>
                  <div className="lp-mc"><div className="lp-mc-n">23</div><div className="lp-mc-l">Visitas hoy</div></div>
                  <div className="lp-mc"><div className="lp-mc-n">L 142K</div><div className="lp-mc-l">Recaudado</div></div>
                </div>
                <div className="lp-mock-row"><span>Casa 124 · Erica Rivera</span><span className="lp-mock-tag">Al día</span></div>
                <div className="lp-mock-row"><span>Casa 88 · Visita autorizada</span><span className="lp-mock-tag">Adentro</span></div>
                <div className="lp-mock-row"><span>Edificio 2 · Apto 3</span><span className="lp-mock-tag">Al día</span></div>
              </div>
            </div>
          </ShotConFallback>
        </div>
      </section>

      <section className="lp-stats lp-anim lp-d5">
        <div className="lp-stat"><b>500+</b><span>familias conectadas</span></div>
        <div className="lp-stat-div" />
        <div className="lp-stat"><b>4</b><span>accesos controlados</span></div>
        <div className="lp-stat-div" />
        <div className="lp-stat"><b>24/7</b><span>monitoreo activo</span></div>
      </section>

      <section className="lp-accion-sec">
        <div className="lp-section-label">El sistema en acción</div>
        <h2 className="lp-section-title">Pensado para cómo trabaja la residencial</h2>
        <div className="lp-accion-grid">
          <div className="lp-accion-card">
            <div className="lp-accion-shot lp-shot-qr">
              <ShotConFallback src="/landing/guardia.png">
                <div className="lp-qr"><div className="lp-qr-grid" /></div>
              </ShotConFallback>
            </div>
            <div className="lp-accion-text">
              <h3>El guardia valida en segundos</h3>
              <p>El residente genera el QR desde su teléfono. En la garita, el guardia lo escanea, ve la foto y registra la entrada al instante.</p>
            </div>
          </div>
          <div className="lp-accion-card">
            <div className="lp-accion-shot lp-shot-arqueo">
              <ShotConFallback src="/landing/arqueo.png">
                <div className="lp-arq">
                  <div className="lp-arq-row"><span>Efectivo esperado</span><b>L 9,350</b></div>
                  <div className="lp-arq-row"><span>Fondo inicial</span><span>L 8,600</span></div>
                  <div className="lp-arq-row"><span>Pagos registrados</span><b>3</b></div>
                </div>
              </ShotConFallback>
            </div>
            <div className="lp-accion-text">
              <h3>La caja cuadra sola</h3>
              <p>Cada cobro suma al arqueo en vivo. Al cierre del día, la caja cuadra al centavo con su reporte listo para la administración.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="lp-modulos">
        <div className="lp-section-label">Qué hace el sistema</div>
        <h2 className="lp-section-title">Todo el control, en un solo lugar</h2>
        <div className="lp-modulos-grid">
          {modulos.map((m) => (
            <div key={m.n} className="lp-modulo">
              <span className="lp-modulo-n">{m.n}</span>
              <h3>{m.titulo}</h3>
              <p>{m.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-roles-sec">
        <div className="lp-section-label">Para cada rol</div>
        <h2 className="lp-section-title">Una herramienta para cada persona</h2>
        <div className="lp-roles-grid">
          {roles.map((r) => (
            <div key={r.t} className="lp-role">
              <div className="lp-role-ic">{r.ic}</div>
              <h4>{r.t}</h4>
              <p>{r.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-cierre">
        <h2>Toda la residencial, bajo control.</h2>
        <p>Accesos, cámaras, cuotas y comunicación en una sola plataforma.</p>
        <button className="lp-cta" onClick={onEntrar}>Acceder al sistema →</button>
      </section>

      <footer className="lp-footer">
        <div className="lp-footer-brand">
          <img src="/logo-vs.png" alt="Villas del Sol" />
          <span>SICA-VS · Residencial Villas del Sol</span>
        </div>
        <span className="lp-footer-loc">San Pedro Sula, Cortés · Honduras</span>
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
