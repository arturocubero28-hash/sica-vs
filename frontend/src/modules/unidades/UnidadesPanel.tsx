import { useEffect, useState } from "react";
import {
  listarCuentas, listarUnidades, listarTarifas, crearUnidad, crearCuenta,
  detalleCuenta, agregarMiembro, asignarTarjeta, darBajaCuenta, reactivarCuenta,
  type Cuenta, type Unidad, type Tarifa,
} from "../../api/client";
import { LectorTarjeta } from "./LectorTarjeta";

export function UnidadesPanel({ embedded }: { embedded?: boolean } = {}) {
  const [tab, setTab] = useState<"cuentas" | "nueva">("cuentas");
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [seleccionada, setSeleccionada] = useState<Cuenta | null>(null);

  async function recargar() { setCuentas(await listarCuentas()); }
  useEffect(() => { recargar(); }, []);

  const contenido = (
    <>
      <div className="tabs">
        <button className={tab === "cuentas" ? "tab on" : "tab"} onClick={() => setTab("cuentas")}>
          Lista de casas
        </button>
        <button className={tab === "nueva" ? "tab on" : "tab"} onClick={() => setTab("nueva")}>
          + Dar de alta
        </button>
      </div>

      {tab === "cuentas" && (
        <ListaCuentas cuentas={cuentas} onRecargar={recargar} onAbrir={async (c) =>
          setSeleccionada(await detalleCuenta(c.id))} />
      )}
      {tab === "nueva" && (
        <FormNuevaCuenta onCreada={async () => { await recargar(); }} />
      )}
      {seleccionada && (
        <DetalleCuenta cuenta={seleccionada} onCerrar={() => setSeleccionada(null)}
          onCambio={async () => setSeleccionada(await detalleCuenta(seleccionada.id))} />
      )}
    </>
  );

  if (embedded) return <div style={{ marginTop: 8 }}>{contenido}</div>;
  return <div className="card wide">{contenido}</div>;
}

function ListaCuentas({ cuentas, onAbrir, onRecargar }: {
  cuentas: Cuenta[]; onAbrir: (c: Cuenta) => void; onRecargar: () => void;
}) {
  const [busqueda, setBusqueda] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("todas");
  const [procesando, setProcesando] = useState<string | null>(null);

  async function baja(c: Cuenta) {
    const nombre = c.identificador || (c.apartamento ? `Apto ${c.apartamento}` : "esta casa");
    if (!confirm(`¿Dar de baja ${nombre}? Dejará de generar cuotas y sus residentes perderán acceso. Podés reactivarla luego.`)) return;
    setProcesando(c.id);
    try { await darBajaCuenta(c.id); onRecargar(); }
    finally { setProcesando(null); }
  }
  async function reactivar(c: Cuenta) {
    setProcesando(c.id);
    try { await reactivarCuenta(c.id); onRecargar(); }
    finally { setProcesando(null); }
  }

  // Filtrado en memoria
  const q = busqueda.trim().toLowerCase();
  const filtradas = cuentas.filter((c) => {
    // Filtro de texto: identificador, apartamento, nombre del titular
    if (q) {
      const blob = `${c.identificador || ""} ${c.apartamento || ""} ${c.titular?.nombre || ""}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    // Filtro de estado
    if (filtroEstado === "activas" && c.activa === false) return false;
    if (filtroEstado === "baja" && c.activa !== false) return false;
    if (filtroEstado === "bloqueadas" && !c.bloqueada) return false;
    if (filtroEstado === "al_dia" && (c.bloqueada || c.estado !== "al_dia")) return false;
    if (filtroEstado === "mora" && !c.bloqueada) return false;
    return true;
  });

  return (
    <div>
      {/* Buscador y filtros */}
      <div className="casas-filtros">
        <input
          className="casas-buscar"
          placeholder="🔍 Buscar por casa, número o titular…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <select value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)} className="periodo-select">
          <option value="todas">Todas</option>
          <option value="activas">Solo activas</option>
          <option value="baja">Dadas de baja</option>
          <option value="al_dia">Al día</option>
          <option value="mora">En mora / bloqueadas</option>
        </select>
      </div>

      <div className="casas-contador muted small">
        {filtradas.length} de {cuentas.length} {cuentas.length === 1 ? "casa" : "casas"}
      </div>

      {filtradas.length === 0 ? (
        <p className="muted">No hay casas que coincidan con la búsqueda.</p>
      ) : (
        <div className="scroll-x">
          <table className="data">
            <thead><tr><th>Identificador</th><th>Titular</th><th>Tarifa</th><th>Día pago</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {filtradas.map((c) => {
                const dadaBaja = c.activa === false;
                return (
                  <tr key={c.id} className={dadaBaja ? "fila-baja" : ""}>
                    <td>{c.identificador || (c.apartamento ? `Apto ${c.apartamento}` : "Casa")}</td>
                    <td>{c.titular?.nombre || <span className="muted">— sin titular —</span>}</td>
                    <td>{c.tarifa} (L {c.monto})</td>
                    <td>{c.dia_pago}</td>
                    <td>
                      {dadaBaja
                        ? <span className="pill" style={{ background: "#6b7280", color: "#fff" }}>Baja</span>
                        : <span className={c.bloqueada ? "pill red" : "pill green"}>{c.bloqueada ? "Bloqueada" : c.estado}</span>}
                    </td>
                    <td style={{ display: "flex", gap: 6 }}>
                      <button className="mini" onClick={() => onAbrir(c)}>Ver</button>
                      {dadaBaja
                        ? <button className="mini btn-reactivar" disabled={procesando === c.id} onClick={() => reactivar(c)}>Reactivar</button>
                        : <button className="mini btn-baja" disabled={procesando === c.id} onClick={() => baja(c)}>Dar de baja</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FormNuevaCuenta({ onCreada }: { onCreada: () => void }) {
  const [unidades, setUnidades] = useState<Unidad[]>([]);
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [unidadId, setUnidadId] = useState("");
  const [apartamento, setApartamento] = useState("");
  const [tarifaId, setTarifaId] = useState<number>(0);
  const [diaPago, setDiaPago] = useState<number>(new Date().getDate() > 28 ? 28 : new Date().getDate());
  const [nombre, setNombre] = useState("");
  const [apellido, setApellido] = useState("");
  const [email, setEmail] = useState("");
  const [telefono, setTelefono] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);
  const [enlace, setEnlace] = useState<{ email: string; url: string } | null>(null);
  const [nuevaUnidadTipo, setNuevaUnidadTipo] = useState<"casa" | "edificio">("casa");
  const [nuevaUnidadId, setNuevaUnidadId] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [mostrarSug, setMostrarSug] = useState(false);

  const sugerencias = unidades.filter(u =>
    u.identificador.toLowerCase().includes(busqueda.toLowerCase())
  ).slice(0, 8);

  function seleccionarUnidad(u: Unidad) {
    setUnidadId(u.id);
    setBusqueda(u.identificador);
    setMostrarSug(false);
  }

  async function recargarUnidades() {
    setUnidades(await listarUnidades());
    setTarifas(await listarTarifas());
  }
  useEffect(() => { recargarUnidades(); }, []);

  const unidadSel = unidades.find((u) => u.id === unidadId);
  const esEdificio = unidadSel?.tipo === "edificio";

  async function crearUnidadInline() {
    if (!nuevaUnidadId.trim()) return;
    try {
      const u = await crearUnidad({ tipo: nuevaUnidadTipo, identificador: nuevaUnidadId.trim() });
      await recargarUnidades();
      setUnidadId(u.id);
      setNuevaUnidadId("");
      setMsg({ tipo: "ok", texto: `Unidad "${u.identificador}" creada` });
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
  }

  async function guardar() {
    setMsg(null); setEnlace(null);
    if (!unidadId || !tarifaId || !nombre || !email) {
      setMsg({ tipo: "err", texto: "Completa unidad, tarifa, nombre y correo del titular" });
      return;
    }
    try {
      const res = await crearCuenta({
        unidad_id: unidadId, apartamento: esEdificio ? apartamento : undefined,
        tarifa_id: tarifaId, dia_pago: diaPago,
        titular: { nombre, apellido, email, telefono, relacion: "propietario" },
      });
      const url = `${window.location.origin}/?activar=${res.activacion.token_activacion}`;
      setEnlace({ email: res.activacion.usuario_email, url });
      setMsg({ tipo: "ok", texto: "Cuenta creada exitosamente." });
      onCreada();
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
  }

  function copiarEnlace() {
    if (!enlace) return;
    navigator.clipboard.writeText(enlace.url);
  }

  return (
    <div className="form">
      <h3>Dar de alta una casa o apartamento</h3>

      {/* Resultado: enlace de activación */}
      {enlace && (
        <div className="activacion-box">
          <div className="activacion-titulo">✓ Cuenta creada — Enlace de activación</div>
          <p>Compartí este enlace con <b>{enlace.email}</b> para que defina su contraseña:</p>
          <div className="activacion-url">{enlace.url}</div>
          <div className="row-btns" style={{ marginTop: 8 }}>
            <button className="mini" onClick={copiarEnlace}>Copiar enlace</button>
            <button className="ghost mini" onClick={() => setEnlace(null)}>Dar de alta otra cuenta</button>
          </div>
        </div>
      )}

      {!enlace && (
        <>
          <div className="sub">1. Unidad</div>
          <div className="search-box">
            <input
              placeholder="Buscar unidad (ej: Casa 24, Edificio 1...)"
              value={busqueda}
              onChange={e => { setBusqueda(e.target.value); setMostrarSug(true); setUnidadId(""); }}
              onFocus={() => setMostrarSug(true)}
              onBlur={() => setTimeout(() => setMostrarSug(false), 150)}
            />
            {mostrarSug && sugerencias.length > 0 && (
              <div className="search-dropdown">
                {sugerencias.map(u => (
                  <div key={u.id} className="search-option" onMouseDown={() => seleccionarUnidad(u)}>
                    <b>{u.identificador}</b> <span className="muted small">({u.tipo})</span>
                  </div>
                ))}
              </div>
            )}
            {unidadId && <span className="pill green" style={{position:'absolute',right:10,top:10}}>✓ seleccionada</span>}
          </div>
          <div className="inline-create">
            <span className="muted small">¿No existe? Créala:</span>
            <select value={nuevaUnidadTipo} onChange={(e) => setNuevaUnidadTipo(e.target.value as "casa" | "edificio")}>
              <option value="casa">Casa</option>
              <option value="edificio">Edificio</option>
            </select>
            <input placeholder="Ej. Casa 24" value={nuevaUnidadId}
              onChange={(e) => setNuevaUnidadId(e.target.value)} />
            <button className="mini" onClick={crearUnidadInline}>Crear unidad</button>
          </div>

          {esEdificio && (
            <>
              <div className="sub">Apartamento</div>
              <input placeholder="Ej. 1A, 2B" value={apartamento}
                onChange={(e) => setApartamento(e.target.value)} />
            </>
          )}

          <div className="sub">2. Cuota</div>
          <div className="row">
            <select value={tarifaId} onChange={(e) => setTarifaId(Number(e.target.value))}>
              <option value={0}>— Selecciona tarifa —</option>
              {tarifas.map((t) => (
                <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>
              ))}
            </select>
            <label className="diapago">Día de pago
              <input type="number" min={1} max={28} value={diaPago}
                onChange={(e) => setDiaPago(Number(e.target.value))} />
            </label>
          </div>
          <span className="muted small">El día de pago se autollenó con hoy; puedes cambiarlo.</span>

          <div className="sub">3. Titular (encargado de la cuenta)</div>
          <div className="row">
            <input placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            <input placeholder="Apellido" value={apellido} onChange={(e) => setApellido(e.target.value)} />
          </div>
          <div className="row">
            <input placeholder="Correo electrónico" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input placeholder="Teléfono (opcional)" value={telefono} onChange={(e) => setTelefono(e.target.value)} />
          </div>
          <div className="nota">
            Se creará el acceso del titular en estado <b>pendiente</b>. Recibirá un enlace
            para definir su propia contraseña (la administración nunca conoce las contraseñas).
          </div>

          {msg && <div className={msg.tipo === "ok" ? "ok-box" : "error"}>{msg.texto}</div>}
          <button onClick={guardar}>Dar de alta cuenta y titular</button>
        </>
      )}
    </div>
  );
}

function DetalleCuenta({ cuenta, onCerrar, onCambio }:
  { cuenta: Cuenta; onCerrar: () => void; onCambio: () => void }) {
  const [cardUid, setCardUid] = useState("");
  const [etiqueta, setEtiqueta] = useState("");
  const [mNombre, setMNombre] = useState("");
  const [mEmail, setMEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [miembroEnlace, setMiembroEnlace] = useState<{ email: string; url: string } | null>(null);

  async function addTarjeta() {
    if (!cardUid.trim()) return;
    try {
      await asignarTarjeta(cuenta.id, { card_uid: cardUid.trim(), etiqueta });
      setCardUid(""); setEtiqueta(""); setMsg(""); onCambio();
    } catch (e) { setMsg((e as Error).message); }
  }

  async function addMiembro() {
    if (!mNombre.trim() || !mEmail.trim()) return;
    try {
      const res = await agregarMiembro(cuenta.id, { nombre: mNombre, email: mEmail, relacion: "familiar" });
      const token = (res as any).activacion?.token_activacion;
      if (token) {
        const url = `${window.location.origin}/?activar=${token}`;
        setMiembroEnlace({ email: mEmail, url });
      }
      setMNombre(""); setMEmail(""); setMsg(""); onCambio();
    } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{cuenta.apartamento ? `Apartamento ${cuenta.apartamento}` : "Casa"} · {cuenta.tarifa}</h3>
          <button className="ghost mini" onClick={onCerrar}>Cerrar</button>
        </div>

        <div className="sub">Residentes</div>
        <div className="scroll-x"><table className="data">
          <tbody>
            {(cuenta.residentes || []).map((r) => (
              <tr key={r.id}>
                <td>{r.nombre}</td>
                <td><span className="pill">{r.rol_cuenta}</span></td>
                <td>{r.relacion}</td>
                <td><span className={r.estado_acceso === "activo" ? "pill green" : "pill amber"}>{r.estado_acceso}</span></td>
              </tr>
            ))}
          </tbody>
        </table></div>

        {miembroEnlace && (
          <div className="activacion-box">
            <div className="activacion-titulo">Enlace de activación para miembro</div>
            <div className="activacion-url">{miembroEnlace.url}</div>
            <button className="mini" onClick={() => navigator.clipboard.writeText(miembroEnlace.url)}>
              Copiar enlace
            </button>
          </div>
        )}

        <div className="inline-create">
          <input placeholder="Nombre del miembro" value={mNombre} onChange={(e) => setMNombre(e.target.value)} />
          <input placeholder="Correo" value={mEmail} onChange={(e) => setMEmail(e.target.value)} />
          <button className="mini" onClick={addMiembro}>+ Agregar miembro</button>
        </div>

        <div className="sub">Tarjetas de proximidad</div>
        <div className="scroll-x"><table className="data">
          <tbody>
            {(cuenta.tarjetas || []).map((t) => (
              <tr key={t.id}>
                <td><code>{t.card_uid}</code></td>
                <td>{t.etiqueta}</td>
                <td>{t.asignada_a}</td>
                <td><span className="pill green">{t.estado}</span></td>
              </tr>
            ))}
            {(cuenta.tarjetas || []).length === 0 && (
              <tr><td colSpan={4} className="muted">Sin tarjetas asignadas</td></tr>
            )}
          </tbody>
        </table></div>
        <div className="inline-create tarjeta-create">
          <LectorTarjeta valor={cardUid} onLeida={setCardUid} />
          <input placeholder="Etiqueta (ej. Auto 1)" value={etiqueta}
            onChange={(e) => setEtiqueta(e.target.value)} />
          <button className="mini" onClick={addTarjeta} disabled={!cardUid}>+ Asignar tarjeta</button>
        </div>

        {msg && <div className="error">{msg}</div>}
      </div>
    </div>
  );
}
