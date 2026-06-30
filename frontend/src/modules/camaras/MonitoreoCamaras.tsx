import { useState, useEffect } from "react";
import {
  listarCamaras, crearCamara, editarCamara, eliminarCamara, probarCamara,
  urlStreamCamara, type CamaraDTO,
} from "../../api/client";
import { AlertTriangle, Settings, Video } from "lucide-react";

const LAYOUTS = [
  { n: 1, label: "1", cols: 1 },
  { n: 2, label: "2", cols: 2 },
  { n: 4, label: "4", cols: 2 },
  { n: 6, label: "6", cols: 3 },
  { n: 9, label: "9", cols: 3 },
  { n: 12, label: "12", cols: 4 },
];

export function MonitoreoCamaras() {
  const [camaras, setCamaras] = useState<CamaraDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [layout, setLayout] = useState(4);
  const [config, setConfig] = useState(false);
  const [maximizada, setMaximizada] = useState<CamaraDTO | null>(null);
  // Asignación de cámaras a celdas: índice de celda -> id de cámara
  const [asignacion, setAsignacion] = useState<(string | null)[]>([]);
  const [arrastrando, setArrastrando] = useState<string | null>(null);

  function recargar() {
    listarCamaras().then(setCamaras).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  // Inicializar/ajustar la asignación cuando cambia el layout o las cámaras
  useEffect(() => {
    setAsignacion(prev => {
      const nueva = Array.from({ length: layout }, (_, i) => prev[i] ?? null);
      // Autocompletar celdas vacías con cámaras activas no asignadas
      const activas = camaras.filter(c => c.activa).map(c => c.id);
      const yaAsignadas = new Set(nueva.filter(Boolean) as string[]);
      const disponibles = activas.filter(id => !yaAsignadas.has(id));
      let d = 0;
      for (let i = 0; i < nueva.length; i++) {
        if (!nueva[i] && d < disponibles.length) nueva[i] = disponibles[d++];
      }
      return nueva;
    });
  }, [layout, camaras]);

  if (config) {
    return <ConfigCamaras camaras={camaras} onVolver={() => { setConfig(false); recargar(); }} />;
  }

  const cols = LAYOUTS.find(l => l.n === layout)?.cols || 2;
  const activas = camaras.filter(c => c.activa);
  const camById = (id: string | null) => activas.find(c => c.id === id) || null;

  function soltarEnCelda(celdaIdx: number) {
    if (!arrastrando) return;
    setAsignacion(prev => {
      const nueva = [...prev];
      // Si la cámara ya estaba en otra celda, la quitamos de ahí (swap)
      const idxPrevio = nueva.indexOf(arrastrando);
      if (idxPrevio !== -1) nueva[idxPrevio] = nueva[celdaIdx];
      nueva[celdaIdx] = arrastrando;
      return nueva;
    });
    setArrastrando(null);
  }

  function quitarDeCelda(celdaIdx: number) {
    setAsignacion(prev => { const n = [...prev]; n[celdaIdx] = null; return n; });
  }

  return (
    <div className="monitoreo-vms">
      <div className="vms-header">
        <div>
          <h2 className="dash-titulo">Centro de Monitoreo</h2>
          <span className="muted">{activas.length} cámara{activas.length !== 1 ? "s" : ""} en línea</span>
        </div>
        <div className="vms-header-acciones">
          <div className="layout-selector">
            {LAYOUTS.map(l => (
              <button key={l.n} className={`layout-btn ${layout === l.n ? "on" : ""}`}
                onClick={() => setLayout(l.n)} title={`${l.n} cámaras`}>
                <LayoutIcon n={l.n} />
              </button>
            ))}
          </div>
          <button className="vms-config-btn" onClick={() => setConfig(true)}><Settings size={16} /> Configurar</button>
        </div>
      </div>

      <div className="vms-body">
        {/* Lista lateral de cámaras */}
        <aside className="vms-sidebar">
          <div className="vms-sidebar-title">Cámaras</div>
          {cargando ? (
            <p className="muted small" style={{ padding: 12 }}>Cargando…</p>
          ) : activas.length === 0 ? (
            <div className="vms-sidebar-vacio">
              <span>Sin cámaras</span>
              <button className="vms-config-btn" onClick={() => setConfig(true)}>Agregar</button>
            </div>
          ) : (
            <div className="vms-cam-list">
              {activas.map(cam => {
                const enUso = asignacion.includes(cam.id);
                return (
                  <div key={cam.id}
                    className={`vms-cam-item ${enUso ? "en-uso" : ""} ${arrastrando === cam.id ? "drag" : ""}`}
                    draggable
                    onDragStart={() => setArrastrando(cam.id)}
                    onDragEnd={() => setArrastrando(null)}
                    title="Arrastrá a una celda de la grilla">
                    <span className="vms-cam-thumb"><Video size={16} /></span>
                    <div className="vms-cam-meta">
                      <span className="vms-cam-nombre">{cam.nombre}</span>
                      <span className="vms-cam-ip">{cam.ip}</span>
                    </div>
                    <span className="vms-cam-dot" />
                  </div>
                );
              })}
            </div>
          )}
          <div className="vms-sidebar-hint">Arrastrá una cámara a la grilla →</div>
        </aside>

        {/* Grilla de celdas */}
        <div className="vms-grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {asignacion.map((camId, idx) => {
            const cam = camById(camId);
            return (
              <div key={idx}
                className={`vms-celda ${arrastrando ? "soltable" : ""} ${cam ? "ocupada" : "vacia"}`}
                onDragOver={(e) => { if (arrastrando) e.preventDefault(); }}
                onDrop={() => soltarEnCelda(idx)}>
                {cam ? (
                  <CamaraTile camara={cam} onMaximizar={() => setMaximizada(cam)}
                    onQuitar={() => quitarDeCelda(idx)} />
                ) : (
                  <div className="vms-celda-vacia">
                    <span className="vms-celda-num">{idx + 1}</span>
                    <span className="muted small">Arrastrá una cámara aquí</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {maximizada && (
        <div className="camara-fullscreen" onDoubleClick={() => setMaximizada(null)}>
          <div className="camara-fs-header">
            <span className="camara-nombre">{maximizada.nombre}</span>
            <button className="ghost mini" onClick={() => setMaximizada(null)}>✕ Cerrar</button>
          </div>
          <div className="camara-fs-video">
            <img src={urlStreamCamara(maximizada.id)} alt={maximizada.nombre} />
          </div>
          <span className="camara-fs-hint">Doble clic para volver a la grilla</span>
        </div>
      )}
    </div>
  );
}

// Iconos de layout (mini-grillas)
function LayoutIcon({ n }: { n: number }) {
  const cols = LAYOUTS.find(l => l.n === n)?.cols || 2;
  const rows = Math.ceil(n / cols);
  return (
    <span className="layout-icon" style={{
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      gridTemplateRows: `repeat(${rows}, 1fr)`,
    }}>
      {Array.from({ length: n }).map((_, i) => <i key={i} />)}
    </span>
  );
}

function CamaraTile({ camara, onMaximizar, onQuitar }: {
  camara: CamaraDTO; onMaximizar: () => void; onQuitar?: () => void;
}) {
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  return (
    <div className="camara-tile" onDoubleClick={onMaximizar} title="Doble clic para maximizar">
      <div className="camara-tile-header">
        <span className="camara-nombre">{camara.nombre}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`camara-dot ${error ? "off" : "on"}`} />
          {onQuitar && (
            <button className="vms-quitar" onClick={(e) => { e.stopPropagation(); onQuitar(); }}
              title="Quitar de la grilla">✕</button>
          )}
        </div>
      </div>
      <div className="camara-video">
        {error ? (
          <div className="camara-sin-senal">
            <span className="sin-senal-icon"><AlertTriangle size={16} /></span>
            <span>Sin señal</span>
            <span className="muted small">{camara.ip}</span>
          </div>
        ) : (
          <>
            {cargando && <div className="camara-loading">Conectando…</div>}
            <img
              src={urlStreamCamara(camara.id)}
              alt={camara.nombre}
              onLoad={() => setCargando(false)}
              onError={() => { setError(true); setCargando(false); }}
            />
          </>
        )}
      </div>
    </div>
  );
}

function ConfigCamaras({ camaras, onVolver }: { camaras: CamaraDTO[]; onVolver: () => void }) {
  const [lista, setLista] = useState<CamaraDTO[]>(camaras);
  const [editando, setEditando] = useState<CamaraDTO | null>(null);
  const [nueva, setNueva] = useState(false);

  function recargar() {
    listarCamaras().then(setLista).catch(() => {});
  }
  useEffect(() => { recargar(); }, []);

  async function borrar(cam: CamaraDTO) {
    if (!confirm(`¿Eliminar la cámara "${cam.nombre}"?`)) return;
    await eliminarCamara(cam.id);
    recargar();
  }

  return (
    <div className="monitoreo">
      <div className="dash-head with-back">
        <button className="ghost mini" onClick={onVolver}>← Volver al monitoreo</button>
        <h2>Configuración de cámaras</h2>
        <button className="cuota-btn-pagar" style={{ maxWidth: 160 }} onClick={() => setNueva(true)}>
          + Agregar cámara
        </button>
      </div>

      {lista.length === 0 ? (
        <p className="muted">No hay cámaras. Agregá la primera con el botón de arriba.</p>
      ) : (
        <div className="config-list">
          {lista.map(cam => (
            <div key={cam.id} className="config-cam">
              <div className="config-cam-info">
                <div className="config-cam-nombre">
                  {cam.nombre}
                  {!cam.activa && <span className="pill" style={{ marginLeft: 8 }}>Inactiva</span>}
                </div>
                <div className="muted small">
                  {cam.usuario ? `${cam.usuario}@` : ""}{cam.ip}:{cam.puerto_rtsp}{cam.ruta_stream}
                </div>
              </div>
              <div className="config-cam-acciones">
                <BotonProbar uuid={cam.id} />
                <button className="ghost mini" onClick={() => setEditando(cam)}>Editar</button>
                <button className="ghost mini" style={{ color: "#c81e1e" }} onClick={() => borrar(cam)}>Eliminar</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(nueva || editando) && (
        <FormCamara
          camara={editando}
          onCerrar={() => { setNueva(false); setEditando(null); }}
          onGuardada={() => { setNueva(false); setEditando(null); recargar(); }}
        />
      )}
    </div>
  );
}

function BotonProbar({ uuid }: { uuid: string }) {
  const [estado, setEstado] = useState<"idle" | "probando" | "ok" | "fail">("idle");
  async function probar() {
    setEstado("probando");
    try {
      const r = await probarCamara(uuid);
      setEstado(r.online ? "ok" : "fail");
    } catch {
      setEstado("fail");
    }
    setTimeout(() => setEstado("idle"), 4000);
  }
  const txt = { idle: "Probar", probando: "Probando…", ok: "✓ En línea", fail: "✕ Sin señal" }[estado];
  return (
    <button className={`ghost mini ${estado === "ok" ? "ok-btn" : estado === "fail" ? "fail-btn" : ""}`}
      onClick={probar} disabled={estado === "probando"}>
      {txt}
    </button>
  );
}

function FormCamara({ camara, onCerrar, onGuardada }: {
  camara: CamaraDTO | null; onCerrar: () => void; onGuardada: () => void;
}) {
  const [nombre, setNombre] = useState(camara?.nombre || "");
  const [ip, setIp] = useState(camara?.ip || "");
  const [puertoRtsp, setPuertoRtsp] = useState(String(camara?.puerto_rtsp || 554));
  const [usuario, setUsuario] = useState(camara?.usuario || "");
  const [password, setPassword] = useState("");
  const [ruta, setRuta] = useState(camara?.ruta_stream || "/Streaming/Channels/101");
  const [activa, setActiva] = useState(camara?.activa ?? true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  async function guardar() {
    if (!nombre.trim() || !ip.trim()) { setError("Nombre e IP son obligatorios"); return; }
    setError(""); setGuardando(true);
    const body: any = {
      nombre, ip, puerto_rtsp: parseInt(puertoRtsp) || 554,
      usuario, ruta_stream: ruta, activa,
    };
    if (password) body.password = password;
    try {
      if (camara) await editarCamara(camara.id, body);
      else await crearCamara(body);
      onGuardada();
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
          <h3>{camara ? "Editar cámara" : "Nueva cámara"}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        <div className="form-pago">
          <div className="form-field">
            <label>Nombre</label>
            <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej. Entrada Principal" />
          </div>
          <div className="form-field">
            <label>Dirección IP</label>
            <input value={ip} onChange={e => setIp(e.target.value)} placeholder="192.168.1.50" />
          </div>
          <div className="form-field">
            <label>Puerto RTSP</label>
            <input value={puertoRtsp} onChange={e => setPuertoRtsp(e.target.value)} placeholder="554" />
          </div>
          <div className="form-field">
            <label>Usuario ONVIF</label>
            <input value={usuario} onChange={e => setUsuario(e.target.value)} placeholder="admin" />
          </div>
          <div className="form-field">
            <label>Contraseña {camara && <span className="muted small">(dejá vacío para no cambiar)</span>}</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <div className="form-field">
            <label>Ruta del stream RTSP</label>
            <input value={ruta} onChange={e => setRuta(e.target.value)} placeholder="/Streaming/Channels/101" />
            <span className="muted small">
              Hikvision: /Streaming/Channels/101 · Dahua: /cam/realmonitor?channel=1&amp;subtype=0
            </span>
          </div>
          <label className="check-row">
            <input type="checkbox" checked={activa} onChange={e => setActiva(e.target.checked)} />
            Cámara activa
          </label>

          {error && <div className="error">{error}</div>}

          <button className="cuota-btn-pagar full" onClick={guardar} disabled={guardando}>
            {guardando ? "Guardando…" : camara ? "Guardar cambios" : "Agregar cámara"}
          </button>
        </div>
      </div>
    </div>
  );
}
