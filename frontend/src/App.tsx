import { useState, useEffect, useRef, type ReactNode } from "react";
import {
  LayoutDashboard, Video, Building2, Users, ScrollText, CreditCard, Receipt,
  Handshake, TrendingUp, Ticket, Megaphone, User, Settings, Monitor, Home,
  QrCode, ClipboardList, Shield, Building, Sun, Moon, Menu as MenuIcon,
  Fingerprint, ArrowRight, ArrowLeft, Check, Smartphone, Download, type LucideIcon,
} from "lucide-react";
import {
  login, getMe, logout, getToken, setToken,
  activarCuenta, solicitarRecuperacion, restablecerPassword, cambiarPassword,
  contarPagosPendientes, misEdificios, getMiResidencial,
  loginConHuella, soportaHuella, estadisticasPublicas,
  type Usuario, type Rol,
} from "./api/client";
import { aplicarColoresResidencial, restablecerColoresFabrica } from "./utils/colores";
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

  // Día 47 — colores personalizables: apenas se resuelve la sesión (login
  // fresco u ONLINE con token guardado — ambos casos terminan poniendo
  // `usuario`), se piden los colores de SU residencial y se aplican una
  // sola vez acá, arriba de todo. Un cambio en las variables CSS de :root
  // alcanza a toda la app sin tener que tocar cada componente. Silencioso
  // si falla: la app se queda con los colores de fábrica.
  useEffect(() => {
    if (!usuario) return;
    getMiResidencial()
      .then((r) => { if (r) aplicarColoresResidencial(r.color_primario, r.color_secundario); })
      .catch(() => { /* se queda con los colores de fábrica */ });
  }, [usuario]);

  function onLogin(u: Usuario) { setUsuario(u); setVista("login"); }
  function onLogout() {
    logout();
    setUsuario(null);
    setVista("landing");
    // Día 57 — limpiar los colores personalizados de la residencial al salir,
    // para que las pantallas de landing/login no hereden el color de la
    // sesión anterior (vuelven a los de fábrica).
    restablecerColoresFabrica();
  }

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
          <button className="ghost" onClick={entrarConHuella} disabled={conHuella} style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
            <Fingerprint size={18} />
            {conHuella ? "Esperando huella…" : "Ingresar con huella / Face ID"}
          </button>
        )}
        <button className="link-btn" onClick={onRecuperar}>¿Olvidaste tu contraseña?</button>
        <button className="link-btn" onClick={onVolver}>← Volver al inicio</button>
      </div>
    </div>
  );
}

// ─── Landing page pública ────────────────────────────────────
// Hook: revela elementos cuando entran en pantalla (scroll reveal)
// Hook: revela elementos al hacer scroll + estado del navbar
function useLandingFx() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { setScrolled(window.scrollY > 50); ticking = false; });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    const els = document.querySelectorAll(".lp-reveal");
    if (!("IntersectionObserver" in window)) {
      els.forEach(e => e.classList.add("visible"));
    } else {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add("visible"); obs.unobserve(e.target); } });
      }, { threshold: 0.15 });
      els.forEach(e => obs.observe(e));
      return () => { obs.disconnect(); window.removeEventListener("scroll", onScroll); };
    }
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

// Contador que sube de 0 a 'valor' cuando entra en pantalla (ease-out)
function Contador({ valor, sufijo = "" }: { valor: number; sufijo?: string }) {
  const [n, setN] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const hecho = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) { setN(valor); return; }
    hecho.current = false;  // permite re-animar si el valor llega async (ej. conteo del backend)
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting && !hecho.current) {
          hecho.current = true;
          const dur = 1800; const t0 = performance.now();
          const tick = (t: number) => {
            const p = Math.min((t - t0) / dur, 1);
            const ease = 1 - Math.pow(1 - p, 3);
            setN(Math.round(valor * ease));
            if (p < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }
      });
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [valor]);
  return <span ref={ref}>{n}{sufijo}</span>;
}

// Sección "Cómo funciona el acceso": 4 pasos que se iluminan en secuencia
function ComoFunciona() {
  const [activos, setActivos] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const pasos = [
    { ic: "\u{1F697}", t: "Llegada", d: "El visitante se presenta en la entrada" },
    { ic: "\u{1FAAA}", t: "Verificación", d: "El guardia valida la identidad" },
    { ic: "\u2705", t: "Autorización", d: "Se registra en el sistema" },
    { ic: "\u{1F3E0}", t: "Acceso", d: "La tranca se abre y queda registrado" },
  ];
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) { setActivos(pasos.length); return; }
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          pasos.forEach((_, i) => setTimeout(() => setActivos(a => Math.max(a, i + 1)), i * 350));
          obs.unobserve(e.target);
        }
      });
    }, { threshold: 0.4 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return (
    <section className="lp-pasos-sec" ref={ref}>
      <div className="lp-section-header lp-reveal">
        <span className="lp-section-tag">Cómo funciona</span>
        <h2>Acceso simple y seguro, paso a paso</h2>
      </div>
      <div className="lp-pasos">
        <div className="lp-pasos-linea"><div className="lp-pasos-linea-fill" style={{ width: `${Math.max(0, (activos - 1)) / (pasos.length - 1) * 100}%` }} /></div>
        {pasos.map((p, i) => (
          <div key={p.t} className={"lp-paso" + (i < activos ? " activo" : "")}>
            <div className="lp-paso-circle">{i < activos ? p.ic : i + 1}</div>
            <h4>{p.t}</h4>
            <p>{p.d}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Fondo del hero: foto real si existe; si no, aurora animada (CSS).
// Prioridad: /images/hero-residencial.* (foto) > aurora.
function HeroFondo() {
  const exts = ["png", "jpg", "jpeg", "jfif", "webp", "avif", "gif", "bmp"];
  const [idx, setIdx] = useState(0);
  const [hayFoto, setHayFoto] = useState(false);

  // Precarga: empieza a bajar la imagen del hero apenas carga la página,
  // con prioridad alta, en vez de esperar a renderizar el <img>.
  useEffect(() => {
    const href = `/images/hero-residencial.${exts[idx]}`;
    const link = document.createElement("link");
    link.rel = "preload";
    link.as = "image";
    link.href = href;
    (link as HTMLLinkElement & { fetchPriority?: string }).fetchPriority = "high";
    document.head.appendChild(link);
    return () => { link.remove(); };
  }, [idx]);

  return (
    <div className={"hero-fondo" + (hayFoto ? " con-foto" : "")} aria-hidden="true">
      <div className="hero-aurora">
        <span className="aurora a1" /><span className="aurora a2" /><span className="aurora a3" />
      </div>
      <img className={"hero-bg-img" + (hayFoto ? " ok" : "")}
        src={`/images/hero-residencial.${exts[idx]}`} alt=""
        // @ts-expect-error fetchpriority es válido en HTML aunque el tipo aún no lo liste
        fetchpriority="high" decoding="async"
        onLoad={() => setHayFoto(true)}
        onError={() => { if (idx < exts.length - 1) setIdx(idx + 1); }} />
      <div className="hero-fondo-velo" />
    </div>
  );
}

function Landing({ onEntrar }: { onEntrar: () => void }) {
  const scrolled = useLandingFx();
  const [tema, setTema] = useState<"oscuro" | "claro">("claro");
  // Cantidad real de familias (unidades activas) y accesos (puntos de
  // acceso/portones distintos — Día 59: antes contaba trancas individuales,
  // ver backend/app/api/publico.py).
  const [familias, setFamilias] = useState<number | null>(null);
  const [accesos, setAccesos] = useState<number | null>(null);
  useEffect(() => {
    estadisticasPublicas()
      .then((d) => { setFamilias(d.familias); setAccesos(d.accesos); })
      .catch(() => { setFamilias(null); setAccesos(null); });
  }, []);

  // Prueba varias extensiones (.jpg/.jpeg/.jfif/.png/.webp) y usa la que cargue.
  // Si ninguna existe, muestra un marcador con ícono (nunca imagen rota).
  function GaleriaImg({ base, ic }: { base: string; ic: string }) {
    const exts = ["png", "jpg", "jpeg", "jfif", "webp", "avif", "gif", "bmp"];
    const [idx, setIdx] = useState(0);
    const [falla, setFalla] = useState(false);
    if (falla) return <div className="lp-galeria-ph"><span>{ic}</span></div>;
    return (
      <img src={`/images/${base}.${exts[idx]}`} alt="" loading="lazy"
        onError={() => { if (idx < exts.length - 1) setIdx(idx + 1); else setFalla(true); }} />
    );
  }
  const pilares = [
    { ic: "\u{1F512}", t: "Acceso controlado", d: "Solo entra quien está autorizado. Cada visita se registra y queda identificada en las cuatro entradas de la residencial." },
    { ic: "\u{1F4F9}", t: "Vigilancia 24/7", d: "Cámaras de seguridad en todos los accesos, monitoreadas de forma permanente para tu tranquilidad." },
    { ic: "\u{1F333}", t: "Comunidad ordenada", d: "Reglas claras y administración cercana para mantener Villas del Sol como un lugar limpio, tranquilo y agradable." },
  ];
  const compromisos = [
    "Entradas controladas las 24 horas",
    "Visitas siempre identificadas",
    "Monitoreo de cámaras en vivo",
    "Comunicación directa con la administración",
  ];

  return (
    <div className={"lp-v2 tema-" + tema}>
      {/* Fondo con orbes animados */}
      <div className="lp-bg">
        <div className="orb orb-1" /><div className="orb orb-2" />
        <div className="orb orb-3" /><div className="orb orb-4" />
        <div className="noise" />
      </div>

      {/* Navbar flotante */}
      <nav className={"lp-nav-v2" + (scrolled ? " scrolled" : "")}>
        <div className="lp-nav-inner">
          <div className="lp-brand-v2">
            <div className="lp-brand-glow"><img src="/logo-vs.png" alt="Villas del Sol" /></div>
            <div className="lp-brand-text">
              <span className="lp-brand-name">Villas del Sol</span>
              <span className="lp-brand-sub">San Pedro Sula</span>
            </div>
          </div>
          <div className="lp-nav-acciones">
            <button className="lp-tema-btn" onClick={() => setTema(t => t === "oscuro" ? "claro" : "oscuro")}
              aria-label="Cambiar tema" title={tema === "oscuro" ? "Modo claro" : "Modo oscuro"}>
              {tema === "oscuro" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="lp-nav-btn-v2" onClick={onEntrar}>Ingresar</button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="lp-hero-v2">
        <HeroFondo />
        <div className="hero-particles" aria-hidden="true">
          {Array.from({ length: 26 }).map((_, i) => (
            <span key={i} className="particle" style={{
              left: `${(i * 3.7 + 2) % 100}%`,
              animationDelay: `${(i * 0.9) % 20}s`,
              animationDuration: `${14 + (i % 7) * 2}s`,
            }} />
          ))}
        </div>
        <div className="lp-hero-content">
          <div className="lp-hero-eyebrow-v2 lp-anim"><span className="pulse-dot" />Residencial Villas del Sol</div>
          <h1 className="lp-hero-title-v2 lp-anim" style={{ animationDelay: ".1s" }}>
            Una comunidad <span className="gradient-text">segura, ordenada y bien cuidada.</span>
          </h1>
          <p className="lp-hero-lead-v2 lp-anim" style={{ animationDelay: ".2s" }}>
            En Villas del Sol cada acceso está controlado y vigilado las 24 horas. Vivís tranquilo,
            sabiendo quién entra y quién sale, en un entorno que cuidamos entre todos.
          </p>
          <div className="lp-hero-actions-v2 lp-anim" style={{ animationDelay: ".3s" }}>
            <button className="lp-cta-v2 lp-cta-primary cta-pulse" onClick={onEntrar}>
              Ingresar al portal <span className="cta-arrow">→</span>
            </button>
          </div>
          <div className="lp-stats lp-anim" style={{ animationDelay: ".4s" }}>
            <div className="lp-stat"><span className="lp-stat-num"><Contador valor={familias ?? 0} sufijo="+" /></span><span className="lp-stat-label">Familias</span></div>
            <div className="lp-stat"><span className="lp-stat-num"><Contador valor={accesos ?? 0} /></span><span className="lp-stat-label">Accesos</span></div>
            <div className="lp-stat"><span className="lp-stat-num">24/7</span><span className="lp-stat-label">Monitoreo</span></div>
          </div>
        </div>
      </section>

      {/* Pilares */}
      <section className="lp-pilares-v2">
        <div className="lp-section-header lp-reveal">
          <span className="lp-section-tag">Por qué vivir acá</span>
          <h2>Tu tranquilidad, nuestra prioridad</h2>
          <p>Todo en Villas del Sol está pensado para que te sientas seguro en casa.</p>
        </div>
        <div className="lp-pilares-grid">
          {pilares.map((p) => (
            <div key={p.t} className="lp-pilar-v2 lp-reveal">
              <div className="lp-pilar-glow" />
              <div className="lp-pilar-content">
                <div className="lp-pilar-ic-v2">{p.ic}</div>
                <h3>{p.t}</h3>
                <p>{p.d}</p>
                <div className="lp-pilar-line" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Galería de infraestructura */}
      <section className="lp-galeria">
        <div className="lp-section-header lp-reveal">
          <span className="lp-section-tag">Infraestructura</span>
          <h2>Seguridad que se ve y se siente</h2>
        </div>
        <div className="lp-galeria-grid">
          {[
            { base: "tranca-vehicular", ic: "\u{1F6E3}\uFE0F", title: "Acceso vehicular", desc: "Barrera automática con lector de tarjeta" },
            { base: "caseta-guardia", ic: "\u{1F6E1}\uFE0F", title: "Caseta de vigilancia", desc: "Guardia permanente las 24 horas" },
            { base: "camaras-hd", ic: "\u{1F4F9}", title: "Cámaras HD", desc: "Monitoreo en tiempo real" },
            { base: "acceso-peatonal", ic: "\u{1F6B6}", title: "Acceso peatonal", desc: "Entrada controlada con tarjeta" },
          ].map((item, i) => (
            <div key={item.title} className={`lp-galeria-item lp-reveal lp-rev-d${i + 1}`}>
              <div className="lp-galeria-img-wrap">
                <GaleriaImg base={item.base} ic={item.ic} />
                <div className="lp-galeria-shine" />
              </div>
              <div className="lp-galeria-info">
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Cómo funciona el acceso */}
      <ComoFunciona />

      {/* Banda de compromiso */}
      <section className="lp-banda-v2 lp-reveal">
        <div className="lp-banda-glow" />
        <div className="lp-banda-grid">
          <div className="lp-banda-info">
            <div className="lp-banda-tag">Nuestro compromiso</div>
            <h2>Cuidamos tu hogar como si fuera el nuestro</h2>
            <p>
              La seguridad de tu familia es lo primero. Por eso Villas del Sol cuenta con control de
              acceso, vigilancia permanente y una administración que está siempre cerca para responder.
            </p>
            <div className="lp-banda-divider" />
          </div>
          <div className="lp-compromisos-grid">
            {compromisos.map((c) => (
              <div key={c} className="lp-compromiso-v2">
                <div className="lp-compromiso-ic-v2"><Check size={18} /></div>
                <div className="lp-compromiso-text">
                  <span>{c}</span>
                  <div className="lp-compromiso-bar" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Cierre */}
      <section className="lp-cierre-v2 lp-reveal">
        <div className="lp-cierre-glow" />
        <div className="lp-cierre-content">
          <h2>Bienvenido a casa.</h2>
          <p>Ingresá al portal para gestionar tus visitas y mantenerte al día con la comunidad.</p>
          <button className="lp-cta-v2 lp-cta-large" onClick={onEntrar}>Ingresar al portal</button>
        </div>
      </section>

      {/* Descarga de la app — Día 61. El botón de Android ya descarga el
          APK real (servido como archivo estático desde este mismo
          dominio, en /descargas/sicavs.apk). El de iOS queda visualmente
          presente pero deshabilitado -- iOS no permite instalar un .apk
          (ni nada por fuera de la App Store), así que hasta que la app
          esté publicada ahí, este botón no tiene a dónde llevar. Cuando
          se publique, solo hay que cambiar su href y sacarle la clase
          "lp-descarga-pendiente". */}
      <section className="lp-descarga-v2 lp-reveal">
        <div className="lp-descarga-content">
          <span className="lp-descarga-eyebrow"><Smartphone size={14} /> Aplicación móvil</span>
          <h2>Llevá SICA-VS en el bolsillo.</h2>
          <p>Generá tu código QR de visitas, recibí notificaciones y gestioná tus accesos desde tu teléfono.</p>
          <div className="lp-descarga-botones">
            <a className="lp-descarga-btn" href="/descargas/sicavs.apk" download>
              <Download size={20} />
              <span>
                <strong>Descargar para</strong>
                Android
              </span>
            </a>
            <div className="lp-descarga-btn lp-descarga-pendiente" title="Próximamente en App Store">
              <Smartphone size={20} />
              <span>
                <strong>Próximamente en</strong>
                iOS
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="lp-footer-v2">
        <div className="lp-footer-content">
          <div className="lp-footer-brand-v2">
            <img src="/logo-vs.png" alt="Villas del Sol" />
            <div>
              <span>Residencial Villas del Sol</span>
              <span>San Pedro Sula, Cortés · Honduras</span>
            </div>
          </div>
          <span className="lp-footer-year">© 2026 Villas del Sol</span>
        </div>
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
function AdminView({ seccion, usuario }: { seccion: string; usuario: Usuario }) {
  if (seccion === "casas") return <UnidadesPanel embedded />;
  if (seccion === "pagos") return <PagosAdmin />;
  if (seccion === "monitoreo") return <MonitoreoCamaras />;
  if (seccion === "comunicados") return <ComunicadosAdmin />;
  if (seccion === "reportes") return <Reporteria />;
  if (seccion === "inventario") return <InventarioTarjetas />;
  if (seccion === "arreglos") return <ArreglosPanel />;
  if (seccion === "historial") return <HistorialAccesos />;
  if (seccion === "usuarios") return <UsuariosAdmin />;
  if (seccion === "caja") return <SupervisionCaja usuario={usuario} />;
  if (seccion === "perfil") return <MiPerfil />;
  return <DashboardAdmin />;
}

// ─── Dashboard con sidebar moderno ───────────────────────────
type NavItem = { id: string; label: string; icon: LucideIcon };

function navParaRol(rol: Rol): NavItem[] {
  // Bases multi-residencial (Día 37): supervisor tiene el mismo nivel de
  // acceso que admin en toda la app — mismo criterio que ya aplica en el
  // backend (roles_required trata a supervisor como equivalente a admin).
  if (rol === "admin" || rol === "super_admin" || rol === "supervisor") {
    return [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
      { id: "monitoreo", label: "Monitoreo", icon: Video },
      { id: "casas", label: "Casas y residentes", icon: Building2 },
      { id: "usuarios", label: "Usuarios", icon: Users },
      { id: "historial", label: "Historial", icon: ScrollText },
      { id: "pagos", label: "Revisión de pagos", icon: CreditCard },
      { id: "caja", label: "Supervisión de caja", icon: Receipt },
      { id: "arreglos", label: "Arreglos de pago", icon: Handshake },
      { id: "reportes", label: "Reportería", icon: TrendingUp },
      { id: "inventario", label: "Inventario de tarjetas", icon: Ticket },
      { id: "comunicados", label: "Comunicados", icon: Megaphone },
      { id: "perfil", label: "Mi perfil", icon: User },
    ];
  }
  if (rol === "cajero") {
    return [
      { id: "caja", label: "Caja", icon: Receipt },
      { id: "arreglos", label: "Arreglos de pago", icon: Handshake },
      { id: "perfil", label: "Mi perfil", icon: Settings },
    ];
  }
  if (rol === "desarrollador") {
    return [
      { id: "dev", label: "Sistema", icon: Monitor },
      { id: "caja", label: "Supervisión de caja", icon: Receipt },
      { id: "perfil", label: "Mi perfil", icon: Settings },
    ];
  }
  if (rol === "residente") {
    return [
      { id: "home", label: "Inicio", icon: Home },
      { id: "qr", label: "Generar QR", icon: QrCode },
      { id: "historial", label: "Mis visitas", icon: ClipboardList },
      { id: "cuotas", label: "Mis cuotas", icon: CreditCard },
      { id: "cuenta", label: "Mi cuenta", icon: User },
      { id: "perfil", label: "Mi perfil", icon: Settings },
    ];
  }
  return [
    { id: "guardia", label: "Caseta", icon: Shield },
    { id: "perfil", label: "Mi perfil", icon: Settings },
  ];
}

function Dashboard({ usuario, onLogout }: { usuario: Usuario; onLogout: () => void }) {
  const navBase = navParaRol(usuario.rol);
  const [esDuenoEdif, setEsDuenoEdif] = useState(false);
  const esAdmin = usuario.rol === "admin" || usuario.rol === "super_admin" || usuario.rol === "supervisor";
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
        const item = { id: "edificio", label: "Mi edificio", icon: Building };
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
    admin: "Administrador", super_admin: "Super Admin", supervisor: "Supervisor",
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
              <span className="nav-icon"><item.icon size={18} /></span>
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
          <button className="hamburger" onClick={() => setMenuAbierto(true)} aria-label="Menú"><MenuIcon size={22} /></button>
          <b className="topbar-title">{nav.find(n => n.id === seccion)?.label}</b>
          <div className="user-avatar small">{iniciales}</div>
        </header>

        <main className="content">
          {esAdmin && <AdminView seccion={seccion} usuario={usuario} />}
          {usuario.rol === "desarrollador" && (
            seccion === "perfil" ? <div className="card wide"><MiPerfil /></div>
            : seccion === "caja" ? <SupervisionCaja usuario={usuario} />
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
              <item.icon size={20} />
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
