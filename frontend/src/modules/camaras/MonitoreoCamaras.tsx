import { useState, useEffect } from "react";
import {
  listarCamaras, crearCamara, editarCamara, eliminarCamara, probarCamara,
  urlStreamCamara, type CamaraDTO,
} from "../../api/client";

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

  function recargar() {
    listarCamaras().then(setCamaras).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  if (config) {
    return <ConfigCamaras camaras={camaras} onVolver={() => { setConfig(false); recargar(); }} />;
  }

  const cols = LAYOUTS.find(l => l.n === layout)?.cols || 2;
  const activas = camaras.filter(c => c.activa);
  const slots = activas.slice(0, layout);

  return (
    <div className="monitoreo">
      <div className="dash-head">
        <h2>Monitoreo de cámaras</h2>
        <button className="ghost mini" onClick={() => setConfig(true)}>⚙ Configurar cámaras</button>
      </div>

      <div className="layout-selector">
        <span className="muted small">Vista:</span>
        {LAYOUTS.map(l => (
          <button
            key={l.n}
            className={`layout-btn ${layout === l.n ? "on" : ""}`}
            onClick={() => setLayout(l.n)}
          >
            {l.label}
          </button>
        ))}
      </div>

      {cargando ? (
        <p className="muted">Cargando cámaras…</p>
      ) : activas.length === 0 ? (
        <div className="camaras-vacio">
          <div className="camaras-vacio-icon">📹</div>
          <p>No hay cámaras configuradas todavía.</p>
          <button className="cuota-btn-pagar" style={{ maxWidth: 280, margin: "10px auto 0" }}
            onClick={() => setConfig(true)}>
            Agregar primera cámara
          </button>
        </div>
      ) : (
        <div className="camara-grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {slots.map(cam => <CamaraTile key={cam.id} camara={cam} />)}
          {Array.from({ length: Math.max(0, layout - slots.length) }).map((_, i) => (
            <div key={`empty-${i}`} className="camara-tile vacio">
              <span className="muted small">Sin cámara</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CamaraTile({ camara }: { camara: CamaraDTO }) {
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  return (
    <div className="camara-tile">
      <div className="camara-tile-header">
        <span className="camara-nombre">{camara.nombre}</span>
        <span className={`camara-dot ${error ? "off" : "on"}`} />
      </div>
      <div className="camara-video">
        {error ? (
          <div className="camara-sin-senal">
            <span className="sin-senal-icon">⚠</span>
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
