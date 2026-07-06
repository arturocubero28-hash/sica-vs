import { useEffect, useState } from "react";
import {
  listarCuentas, listarUnidades, listarTarifas, crearUnidad, crearCuenta,
  detalleCuenta, agregarMiembro, asignarTarjeta, darBajaCuenta, reactivarCuenta, editarUsuario,
  crearTarifa, editarTarifa, desactivarTarifa,
  validarCodigoEnrolamiento,
  type Cuenta, type Unidad, type Tarifa, type ResidenteDTO,
} from "../../api/client";
import { LectorTarjeta } from "./LectorTarjeta";
import { Building, Car, Footprints, Home, Pencil, User, Plus, Info } from "lucide-react";

/** Formatea un DNI hondureño mientras se escribe: 0000-0000-00000 (13 dígitos).
 *  Solo acepta números y coloca los guiones automáticamente. */
function formatearDNI(valor: string): string {
  const soloNums = valor.replace(/\D/g, "").slice(0, 13);
  const p1 = soloNums.slice(0, 4);
  const p2 = soloNums.slice(4, 8);
  const p3 = soloNums.slice(8, 13);
  let out = p1;
  if (p2) out += "-" + p2;
  if (p3) out += "-" + p3;
  return out;
}
/** ¿El DNI está completo (13 dígitos)? */
function dniCompleto(valor: string): boolean {
  return valor.replace(/\D/g, "").length === 13;
}

export function UnidadesPanel({ embedded }: { embedded?: boolean } = {}) {
  const [tab, setTab] = useState<"cuentas" | "tarifas">("cuentas");
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [seleccionada, setSeleccionada] = useState<Cuenta | null>(null);
  const [modalNueva, setModalNueva] = useState(false);

  async function recargar() { setCuentas(await listarCuentas()); }
  useEffect(() => { recargar(); }, []);

  const contenido = (
    <>
      <div className="unidades-topbar">
        <div className="tabs" style={{ marginBottom: 0, borderBottom: "none" }}>
          <button className={tab === "cuentas" ? "tab on" : "tab"} onClick={() => setTab("cuentas")}>
            Lista de casas
          </button>
          <button className={tab === "tarifas" ? "tab on" : "tab"} onClick={() => setTab("tarifas")}>
            Tarifas
          </button>
        </div>
        <button className="btn-alta" onClick={() => setModalNueva(true)}>
          <Plus size={17} /> Dar de alta
        </button>
      </div>

      {tab === "cuentas" && (
        <ListaCuentas cuentas={cuentas} onRecargar={recargar} onAbrir={async (c) =>
          setSeleccionada(await detalleCuenta(c.id))} />
      )}
      {tab === "tarifas" && <GestionTarifas />}
      {modalNueva && (
        <FormNuevaCuenta
          onCerrar={() => setModalNueva(false)}
          onCreada={async () => { await recargar(); }} />
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
          placeholder="Buscar por casa, número o titular…"
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
        <div className="lista-card"><div className="scroll-x">
          <table className="data">
            <thead><tr><th>Identificador</th><th>Titular</th><th>Tarifa</th><th>Día pago</th><th>Cuotas</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {filtradas.map((c) => {
                const dadaBaja = c.activa === false;
                const pend = c.cuotas_pendientes || 0;
                return (
                  <tr key={c.id} className={dadaBaja ? "fila-baja" : ""}>
                    <td>{c.nombre_completo || c.identificador || (c.apartamento ? `Apto ${c.apartamento}` : "Casa")}</td>
                    <td>{c.titular?.nombre || <span className="muted">— sin titular —</span>}</td>
                    <td>{c.tarifa} (L {c.monto})</td>
                    <td>{c.dia_pago}</td>
                    <td>
                      {pend === 0
                        ? <span className="pill green">Al día</span>
                        : <span className="pill red">{pend} pend.</span>}
                    </td>
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
        </div></div>
      )}
    </div>
  );
}

function FormNuevaCuenta({ onCreada, onCerrar }: { onCreada: () => void; onCerrar: () => void }) {
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
  const [dni, setDni] = useState("");
  const [rtn, setRtn] = useState("");
  const [direccionExacta, setDireccionExacta] = useState("");
  const [profesion, setProfesion] = useState("");
  const [ocupacion, setOcupacion] = useState("");
  const [centroEstudios, setCentroEstudios] = useState("");
  const [lugarTrabajo, setLugarTrabajo] = useState("");
  const [emergNombre, setEmergNombre] = useState("");
  const [emergTel, setEmergTel] = useState("");
  // Enrolamiento por código (inquilino avalado por el dueño del edificio)
  const [codigoEnrol, setCodigoEnrol] = useState("");
  const [validando, setValidando] = useState(false);
  const [enrolInfo, setEnrolInfo] = useState<{ edificio_nombre: string; apartamento_sugerido?: string | null; dueno_nombre?: string | null } | null>(null);
  const [esDuenoEdificio, setEsDuenoEdificio] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);
  const [enlace, setEnlace] = useState<{ email: string; url: string } | null>(null);
  const [nuevaUnidadTipo, setNuevaUnidadTipo] = useState<"casa" | "edificio">("casa");
  const [nuevaUnidadId, setNuevaUnidadId] = useState("");
  const [maxApartamentos, setMaxApartamentos] = useState("");
  const [creandoUnidad, setCreandoUnidad] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [mostrarSug, setMostrarSug] = useState(false);
  // Modo de selección de unidad: "nueva" (crear) es lo más común al dar de alta
  const [modoUnidad, setModoUnidad] = useState<"nueva" | "existente">("nueva");

  // Para "agregar apto a edificio existente": solo edificios
  const sugerenciasEdificios = unidades.filter(u =>
    u.tipo === "edificio" &&
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
  const esEdificio = unidadSel?.tipo === "edificio" || nuevaUnidadTipo === "edificio";

  async function crearUnidadInline() {
    if (!nuevaUnidadId.trim() || creandoUnidad) return;
    setCreandoUnidad(true);
    try {
      const u = await crearUnidad({ tipo: nuevaUnidadTipo, identificador: nuevaUnidadId.trim() });
      await recargarUnidades();
      setUnidadId(u.id);
      setNuevaUnidadId("");
      setMsg({ tipo: "ok", texto: `Unidad "${u.identificador}" creada` });
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
    finally { setCreandoUnidad(false); }
  }

  async function validarCodigo() {
    if (!codigoEnrol.trim()) return;
    setValidando(true); setMsg(null);
    try {
      const info = await validarCodigoEnrolamiento(codigoEnrol.trim());
      // Buscar el edificio en la lista y precargarlo
      const ed = unidades.find(u => u.id === info.edificio_id);
      if (ed) {
        setNuevaUnidadTipo("edificio");
        setModoUnidad("existente");
        setUnidadId(ed.id);
        setBusqueda(ed.identificador);
      }
      if (info.apartamento_sugerido) setApartamento(info.apartamento_sugerido);
      setEnrolInfo({
        edificio_nombre: info.edificio_nombre,
        apartamento_sugerido: info.apartamento_sugerido,
        dueno_nombre: info.dueno_nombre,
      });
    } catch (e) {
      setEnrolInfo(null);
      setMsg({ tipo: "err", texto: (e as Error).message });
    } finally { setValidando(false); }
  }

  async function guardar() {
    setMsg(null); setEnlace(null);
    // La unidad puede estar ya seleccionada (edificio existente) o ser nueva
    // (casa/edificio que se escribe en el momento): en ese caso se envía
    // unidad_nueva y el backend la crea junto con la cuenta.
    const hayUnidad = unidadId || (modoUnidad === "nueva" && nuevaUnidadId.trim());
    if (!hayUnidad || !tarifaId || !nombre || !email) {
      setMsg({ tipo: "err", texto: "Completá la casa/edificio, la tarifa, y el nombre y correo del titular" });
      return;
    }
    if (dni && !dniCompleto(dni)) {
      setMsg({ tipo: "err", texto: "El número de identidad debe tener 13 dígitos (0000-0000-00000)" });
      return;
    }
    try {
      const res = await crearCuenta({
        unidad_id: unidadId || undefined,
        unidad_nueva: (!unidadId && nuevaUnidadId.trim())
          ? { tipo: nuevaUnidadTipo, identificador: nuevaUnidadId.trim(),
              max_apartamentos: nuevaUnidadTipo === "edificio" && maxApartamentos
                ? Number(maxApartamentos) : undefined } : undefined,
        apartamento: esEdificio ? apartamento : undefined,
        tarifa_id: tarifaId, dia_pago: diaPago,
        codigo_enrolamiento: codigoEnrol.trim() || undefined,
        es_dueno_edificio: esEdificio && esDuenoEdificio && !enrolInfo,
        titular: {
          nombre, apellido, email, telefono, relacion: "propietario",
          dni, rtn, direccion_exacta: direccionExacta, profesion,
          ocupacion: ocupacion || undefined,
          centro_estudios: ocupacion === "estudiante" ? centroEstudios : undefined,
          lugar_trabajo: ocupacion === "profesional" ? lugarTrabajo : undefined,
          contacto_emergencia_nombre: emergNombre,
          contacto_emergencia_telefono: emergTel,
        },
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
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body modal-alta" onClick={(e) => e.stopPropagation()}>
        <div className="modal-alta-head">
          <div>
            <h3>Dar de alta una casa o apartamento</h3>
            <p className="muted small" style={{ margin: 0 }}>Creá la unidad, asigná su cuota y registrá al titular de la cuenta.</p>
          </div>
          <button className="modal-x" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </div>

        <div className="modal-alta-body">

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
          {/* Código de enrolamiento */}
          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">0</span>
              <b>¿Trae código de enrolamiento?</b>
              <InfoTip texto="Si un inquilino recibió un código de 6 dígitos del dueño de su edificio, ingresalo aquí: el edificio y apartamento se seleccionan solos. Si es una casa normal o no hay código, salteá este paso." />
              <span className="muted small" style={{ marginLeft: "auto" }}>Opcional</span>
            </div>
            <div className="row">
              <input placeholder="Código de 6 dígitos (opcional)" value={codigoEnrol}
                inputMode="numeric" maxLength={6}
                onChange={e => { setCodigoEnrol(e.target.value.replace(/\D/g, "")); setEnrolInfo(null); }}
                onKeyDown={e => e.key === "Enter" && validarCodigo()} />
              <button className="mini" onClick={validarCodigo}
                disabled={validando || codigoEnrol.length < 6}>
                {validando ? "…" : "Validar"}
              </button>
            </div>
            {enrolInfo && (
              <div className="enrol-ok">
                ✓ Código válido — <b>{enrolInfo.edificio_nombre}</b>
                {enrolInfo.apartamento_sugerido ? ` · Apto ${enrolInfo.apartamento_sugerido}` : ""}
                {enrolInfo.dueno_nombre ? <span className="muted small"><br/>Avalado por: {enrolInfo.dueno_nombre}</span> : null}
              </div>
            )}
          </div>

          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">1</span>
              <b>Casa o edificio</b>
              <InfoTip texto="Elegí si es una casa independiente o un apartamento dentro de un edificio. Podés crear una unidad nueva, o si es un edificio ya registrado, sumarle un apartamento." />
            </div>

          {/* Primero: tipo de unidad */}
          <div className="seg-toggle">
            <button type="button" className={nuevaUnidadTipo === "casa" ? "on" : ""}
              onClick={() => {
                setNuevaUnidadTipo("casa"); setModoUnidad("nueva");
                setUnidadId(""); setBusqueda(""); setNuevaUnidadId("");
              }}>
              <Home size={16} /> Casa
            </button>
            <button type="button" className={nuevaUnidadTipo === "edificio" ? "on" : ""}
              onClick={() => {
                setNuevaUnidadTipo("edificio"); setModoUnidad("nueva");
                setUnidadId(""); setBusqueda(""); setNuevaUnidadId("");
              }}>
              <Building size={16} /> Edificio
            </button>
          </div>

          {/* Para EDIFICIO: elegir entre crear uno nuevo o sumar apartamento a uno existente */}
          {nuevaUnidadTipo === "edificio" && (
            <div className="seg-toggle" style={{ marginTop: 4 }}>
              <button type="button" className={modoUnidad === "nueva" ? "on" : ""}
                onClick={() => { setModoUnidad("nueva"); setUnidadId(""); setBusqueda(""); }}>
                + Edificio nuevo
              </button>
              <button type="button" className={modoUnidad === "existente" ? "on" : ""}
                onClick={() => { setModoUnidad("existente"); setNuevaUnidadId(""); }}>
                Agregar apto a uno existente
              </button>
            </div>
          )}

          {modoUnidad === "nueva" ? (
            <div className="crear-unidad-box">
              <input placeholder={nuevaUnidadTipo === "casa" ? "Identificador (ej. Casa 24)" : "Nombre del edificio (ej. Edificio B)"}
                value={nuevaUnidadId}
                onChange={(e) => setNuevaUnidadId(e.target.value)} />
              <p className="muted small" style={{ marginTop: 6 }}>
                {nuevaUnidadTipo === "casa"
                  ? "La casa se creará junto con la cuenta al dar de alta."
                  : "El edificio se creará junto con la cuenta. Indicá el apartamento abajo."}
              </p>
              {nuevaUnidadTipo === "edificio" && (
                <input type="number" min={1} max={200} placeholder="¿Cuántos apartamentos tiene el edificio?"
                  value={maxApartamentos} onChange={(e) => setMaxApartamentos(e.target.value)}
                  style={{ marginTop: 6 }} />
              )}
            </div>
          ) : (
            <div className="search-box">
              <input
                placeholder="Buscar el edificio existente…"
                value={busqueda}
                onChange={e => { setBusqueda(e.target.value); setMostrarSug(true); setUnidadId(""); }}
                onFocus={() => setMostrarSug(true)}
                onBlur={() => setTimeout(() => setMostrarSug(false), 150)}
              />
              {mostrarSug && sugerenciasEdificios.length > 0 && (
                <div className="search-dropdown">
                  {sugerenciasEdificios.map(u => (
                    <div key={u.id} className="search-option" onMouseDown={() => seleccionarUnidad(u)}>
                      <b>{u.identificador}</b> <span className="muted small">({u.tipo})</span>
                    </div>
                  ))}
                </div>
              )}
              {unidadId && <span className="pill green" style={{position:'absolute',right:10,top:10}}>✓ seleccionado</span>}
            </div>
          )}

          {esEdificio && (
            <>
              <div className="sub">Apartamento</div>
              <input placeholder="Ej. 1A, 2B" value={apartamento}
                onChange={(e) => setApartamento(e.target.value)} />
              {!enrolInfo && (
                <label className="check-dueno">
                  <input type="checkbox" checked={esDuenoEdificio}
                    onChange={e => setEsDuenoEdificio(e.target.checked)} />
                  <span>Este titular es el <b>dueño del edificio</b> (podrá generar códigos para sus inquilinos)</span>
                </label>
              )}
            </>
          )}
          </div>

          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">2</span>
              <b>Cuota mensual</b>
              <InfoTip texto="La tarifa define cuánto paga esta casa cada mes. El día de pago es la fecha límite mensual; se autollena con hoy pero podés cambiarlo (máximo 28 para evitar problemas en febrero)." />
            </div>
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
          </div>

          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">3</span>
              <b>Titular de la cuenta</b>
              <InfoTip texto="Es la persona responsable de la cuenta (quien paga). Se le creará un acceso en estado pendiente y recibirá un enlace para definir su propia contraseña. Solo el nombre, apellido y correo son obligatorios." />
            </div>
          <div className="row">
            <input placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            <input placeholder="Apellido" value={apellido} onChange={(e) => setApellido(e.target.value)} />
          </div>
          <div className="row">
            <input placeholder="Correo electrónico" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input placeholder="Teléfono (opcional)" value={telefono} onChange={(e) => setTelefono(e.target.value)} />
          </div>
          <div className="row">
            <input placeholder="Identidad (0000-0000-00000)" value={dni} inputMode="numeric"
              maxLength={15}
              onChange={(e) => setDni(formatearDNI(e.target.value))} />
            <input placeholder="RTN (opcional)" value={rtn} onChange={(e) => setRtn(e.target.value)} />
          </div>
          <div className="row">
            <input placeholder="Dirección exacta" value={direccionExacta} onChange={(e) => setDireccionExacta(e.target.value)} />
            <input placeholder="Profesión" value={profesion} onChange={(e) => setProfesion(e.target.value)} />
            <select value={ocupacion} onChange={(e) => setOcupacion(e.target.value)} style={{ marginTop: 6 }}>
              <option value="">— Ocupación —</option>
              <option value="estudiante">Estudiante</option>
              <option value="profesional">Profesional / Empleado</option>
              <option value="otro">Otro</option>
            </select>
            {ocupacion === "estudiante" && (
              <input placeholder="Centro de estudios" value={centroEstudios} onChange={(e) => setCentroEstudios(e.target.value)} style={{ marginTop: 6 }} />
            )}
            {ocupacion === "profesional" && (
              <input placeholder="Lugar de trabajo" value={lugarTrabajo} onChange={(e) => setLugarTrabajo(e.target.value)} style={{ marginTop: 6 }} />
            )}
          </div>
          <div className="row">
            <input placeholder="Contacto de emergencia (nombre)" value={emergNombre} onChange={(e) => setEmergNombre(e.target.value)} />
            <input placeholder="Contacto de emergencia (teléfono)" value={emergTel} onChange={(e) => setEmergTel(e.target.value)} />
          </div>
          </div>

          <div className="info-box">
            <Info size={15} />
            <span>Se creará el acceso del titular en estado <b>pendiente</b>. Recibirá un enlace para definir su propia contraseña — la administración nunca conoce las contraseñas.</span>
          </div>

          {msg && <div className={msg.tipo === "ok" ? "ok-box" : "error"}>{msg.texto}</div>}
        </>
      )}
        </div>

        {!enlace && (
          <div className="modal-alta-footer">
            <button className="ghost" onClick={onCerrar}>Cancelar</button>
            <button onClick={guardar}>Dar de alta cuenta y titular</button>
          </div>
        )}
      </div>
    </div>
  );
}

function DetalleCuenta({ cuenta, onCerrar, onCambio }:
  { cuenta: Cuenta; onCerrar: () => void; onCambio: () => void }) {
  const [cardUid, setCardUid] = useState("");
  const [etiqueta, setEtiqueta] = useState("");
  // Tipo de acceso de la tarjeta. Si la cuenta es un apartamento, se sugiere
  // peatonal (común en estudiantes); si es casa, vehicular.
  const [tipoAcceso, setTipoAcceso] = useState<"vehicular" | "peatonal">(
    cuenta.es_apartamento ? "peatonal" : "vehicular");
  const [portadorId, setPortadorId] = useState("");
  const [mNombre, setMNombre] = useState("");
  const [mEmail, setMEmail] = useState("");
  const [mApellido, setMApellido] = useState("");
  const [mTelefono, setMTelefono] = useState("");
  const [mDni, setMDni] = useState("");
  const [mProfesion, setMProfesion] = useState("");
  const [mEmergNombre, setMEmergNombre] = useState("");
  const [mEmergTel, setMEmergTel] = useState("");
  const [msg, setMsg] = useState("");
  const [miembroEnlace, setMiembroEnlace] = useState<{ email: string; url: string } | null>(null);
  const [mostrarAgregar, setMostrarAgregar] = useState(false);

  async function addTarjeta() {
    if (!cardUid.trim()) return;
    try {
      await asignarTarjeta(cuenta.id, {
        card_uid: cardUid.trim(),
        etiqueta,
        tipo_acceso: tipoAcceso,
        residente_id: portadorId || undefined,
      });
      setCardUid(""); setEtiqueta(""); setPortadorId("");
      setTipoAcceso(cuenta.es_apartamento ? "peatonal" : "vehicular");
      setMsg(""); onCambio();
    } catch (e) { setMsg((e as Error).message); }
  }

  async function addMiembro() {
    if (!mNombre.trim() || !mEmail.trim()) return;
    try {
      const res = await agregarMiembro(cuenta.id, {
        nombre: mNombre, apellido: mApellido, email: mEmail, telefono: mTelefono,
        relacion: "familiar", dni: mDni, profesion: mProfesion,
        contacto_emergencia_nombre: mEmergNombre, contacto_emergencia_telefono: mEmergTel,
      });
      const token = (res as any).activacion?.token_activacion;
      if (token) {
        const url = `${window.location.origin}/?activar=${token}`;
        setMiembroEnlace({ email: mEmail, url });
      }
      setMNombre(""); setMEmail(""); setMApellido(""); setMTelefono("");
      setMDni(""); setMProfesion(""); setMEmergNombre(""); setMEmergTel("");
      setMsg(""); onCambio();
    } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{cuenta.nombre_completo || (cuenta.apartamento ? `Apartamento ${cuenta.apartamento}` : "Casa")} · {cuenta.tarifa}</h3>
          <button className="ghost mini" onClick={onCerrar}>Cerrar</button>
        </div>

        <div className="sub">Residentes de la casa</div>
        <div className="residentes-lista">
          {(cuenta.residentes || []).map((r) => (
            <FilaResidente key={r.id} residente={r} onActualizado={onCambio} />
          ))}
        </div>

        {miembroEnlace && (
          <div className="activacion-box">
            <div className="activacion-titulo">Enlace de activación para miembro</div>
            <div className="activacion-url">{miembroEnlace.url}</div>
            <button className="mini" onClick={() => navigator.clipboard.writeText(miembroEnlace.url)}>
              Copiar enlace
            </button>
          </div>
        )}

        <button className="toggle-agregar-miembro" onClick={() => setMostrarAgregar(v => !v)}>
          {mostrarAgregar ? "▲ Ocultar formulario" : "＋ Agregar nuevo miembro"}
        </button>

        {mostrarAgregar && (
        <div className="agregar-miembro-card">
          <div className="agregar-miembro-head">
            <span className="agregar-miembro-icon"><User size={16} /></span>
            <div>
              <h4>Agregar nuevo miembro</h4>
              <span className="muted small">Registrá un familiar o dependiente de esta casa. Solo el nombre y el correo son obligatorios.</span>
            </div>
          </div>

          <div className="agregar-miembro-campos">
            <div className="campo-grupo">
              <label className="campo-label">Datos básicos</label>
              <div className="row">
                <input placeholder="Nombre *" value={mNombre} onChange={(e) => setMNombre(e.target.value)} />
                <input placeholder="Apellido" value={mApellido} onChange={(e) => setMApellido(e.target.value)} />
              </div>
              <div className="row">
                <input placeholder="Correo electrónico *" value={mEmail} onChange={(e) => setMEmail(e.target.value)} />
                <input placeholder="Teléfono" value={mTelefono} onChange={(e) => setMTelefono(e.target.value)} />
              </div>
            </div>

            <div className="campo-grupo">
              <label className="campo-label">Información adicional</label>
              <div className="row">
                <input placeholder="Identidad (0000-0000-00000)" value={mDni} inputMode="numeric" maxLength={15} onChange={(e) => setMDni(formatearDNI(e.target.value))} />
                <input placeholder="Profesión" value={mProfesion} onChange={(e) => setMProfesion(e.target.value)} />
              </div>
            </div>

            <div className="campo-grupo">
              <label className="campo-label">Contacto de emergencia</label>
              <div className="row">
                <input placeholder="Nombre del contacto" value={mEmergNombre} onChange={(e) => setMEmergNombre(e.target.value)} />
                <input placeholder="Teléfono del contacto" value={mEmergTel} onChange={(e) => setMEmergTel(e.target.value)} />
              </div>
            </div>
          </div>

          <button className="agregar-miembro-btn" onClick={addMiembro}>+ Agregar miembro</button>
        </div>
        )}

        <div className="sub">Tarjetas de proximidad ({(cuenta.tarjetas || []).length})</div>
        <div className="scroll-x"><table className="data">
          <thead>
            <tr><th>Código (UID)</th><th>Etiqueta</th><th>Asignada a</th><th>Acceso</th><th>Estado</th></tr>
          </thead>
          <tbody>
            {(cuenta.tarjetas || []).map((t) => (
              <tr key={t.id}>
                <td><code>{t.card_uid}</code></td>
                <td>{t.etiqueta || <span className="muted">—</span>}</td>
                <td>{t.asignada_a}</td>
                <td>
                  <span className={`pill ${t.tipo_acceso === "peatonal" ? "" : "green"}`}>
                    {t.tipo_acceso === "peatonal" ? "<Footprints size={16} /> Peatonal" : "<Car size={16} /> Vehicular"}
                  </span>
                </td>
                <td><span className="pill green">{t.estado}</span></td>
              </tr>
            ))}
            {(cuenta.tarjetas || []).length === 0 && (
              <tr><td colSpan={5} className="muted">Sin tarjetas asignadas</td></tr>
            )}
          </tbody>
        </table></div>
        <div className="tarjeta-create-box">
          <LectorTarjeta valor={cardUid} onLeida={setCardUid} />

          <div className="row" style={{ marginTop: 8 }}>
            <select value={portadorId} onChange={(e) => setPortadorId(e.target.value)}>
              <option value="">Portador (opcional)…</option>
              {(cuenta.residentes || []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nombre}{r.rol_cuenta === "titular" ? " (titular)" : ""}
                </option>
              ))}
            </select>
            <input placeholder="Etiqueta (ej. Auto 1)" value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value)} />
          </div>

          <div className="acceso-toggle">
            <span className="muted small">Tipo de acceso:</span>
            <button type="button" className={tipoAcceso === "vehicular" ? "on" : ""}
              onClick={() => setTipoAcceso("vehicular")}>
              <Car size={16} /> Vehicular
            </button>
            <button type="button" className={tipoAcceso === "peatonal" ? "on" : ""}
              onClick={() => setTipoAcceso("peatonal")}>
              <Footprints size={16} /> Peatonal
            </button>
          </div>
          <p className="muted small" style={{ margin: "4px 0 8px" }}>
            {tipoAcceso === "peatonal"
              ? "Solo abre torniquetes peatonales."
              : "Abre torniquetes y barreras vehiculares."}
          </p>

          <button className="mini" onClick={addTarjeta} disabled={!cardUid}>+ Asignar tarjeta</button>
        </div>

        {msg && <div className="error">{msg}</div>}
      </div>
    </div>
  );
}

function FilaResidente({ residente, onActualizado }: {
  residente: ResidenteDTO; onActualizado: () => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const [editando, setEditando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState("");

  // Campos editables (precargados con lo actual)
  const [f, setF] = useState({
    nombre: residente.nombre_solo || "",
    apellido: residente.apellido || "",
    telefono: residente.telefono || "",
    dni: residente.dni || "",
    rtn: residente.rtn || "",
    direccion_exacta: residente.direccion_exacta || "",
    profesion: residente.profesion || "",
    contacto_emergencia_nombre: residente.contacto_emergencia_nombre || "",
    contacto_emergencia_telefono: residente.contacto_emergencia_telefono || "",
  });

  function set(campo: string, valor: string) { setF(prev => ({ ...prev, [campo]: valor })); }

  async function guardar() {
    if (!residente.usuario_id) { setMsg("No se puede editar este residente"); return; }
    setGuardando(true); setMsg("");
    try {
      await editarUsuario(residente.usuario_id, f);
      setEditando(false);
      onActualizado();
    } catch (e) { setMsg((e as Error).message); }
    finally { setGuardando(false); }
  }

  const Dato = ({ label, valor }: { label: string; valor?: string }) => (
    <div className="dato-item">
      <span className="muted small">{label}</span>
      <span>{valor || <span className="muted">—</span>}</span>
    </div>
  );

  return (
    <div className="residente-fila">
      <div className="residente-cabecera">
        <span className="residente-nombre">{residente.nombre}</span>
        <span className="pill">{residente.rol_cuenta}</span>
        <span className="muted small">{residente.relacion}</span>
        <span className={residente.estado_acceso === "activo" ? "pill green" : "pill amber"}>
          {residente.estado_acceso}
        </span>
        <button className="mini" onClick={() => setExpandido(e => !e)}>
          {expandido ? "Ocultar" : "Ver"}
        </button>
      </div>

      {expandido && (
        <div className="residente-detalle">
          {!editando ? (
            <>
              <div className="datos-grid">
                <Dato label="Correo" valor={residente.email} />
                <Dato label="Teléfono" valor={residente.telefono} />
                <Dato label="Identidad / DNI" valor={residente.dni} />
                <Dato label="RTN" valor={residente.rtn} />
                <Dato label="Profesión" valor={residente.profesion} />
                <Dato label="Dirección exacta" valor={residente.direccion_exacta} />
                <Dato label="Contacto emergencia" valor={residente.contacto_emergencia_nombre} />
                <Dato label="Tel. emergencia" valor={residente.contacto_emergencia_telefono} />
              </div>
              <button className="mini" onClick={() => setEditando(true)}><Pencil size={16} /> Editar información</button>
            </>
          ) : (
            <div className="datos-editar">
              <div className="row">
                <input placeholder="Nombre" value={f.nombre} onChange={e => set("nombre", e.target.value)} />
                <input placeholder="Apellido" value={f.apellido} onChange={e => set("apellido", e.target.value)} />
              </div>
              <div className="row">
                <input placeholder="Teléfono" value={f.telefono} onChange={e => set("telefono", e.target.value)} />
                <input placeholder="Identidad (0000-0000-00000)" value={f.dni} inputMode="numeric" maxLength={15} onChange={e => set("dni", formatearDNI(e.target.value))} />
              </div>
              <div className="row">
                <input placeholder="RTN" value={f.rtn} onChange={e => set("rtn", e.target.value)} />
                <input placeholder="Profesión" value={f.profesion} onChange={e => set("profesion", e.target.value)} />
              </div>
              <input placeholder="Dirección exacta" value={f.direccion_exacta} onChange={e => set("direccion_exacta", e.target.value)} />
              <div className="row">
                <input placeholder="Contacto emergencia (nombre)" value={f.contacto_emergencia_nombre} onChange={e => set("contacto_emergencia_nombre", e.target.value)} />
                <input placeholder="Contacto emergencia (teléfono)" value={f.contacto_emergencia_telefono} onChange={e => set("contacto_emergencia_telefono", e.target.value)} />
              </div>
              {msg && <div className="error">{msg}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="mini ghost" onClick={() => { setEditando(false); setMsg(""); }}>Cancelar</button>
                <button className="mini" onClick={guardar} disabled={guardando}>
                  {guardando ? "Guardando…" : "Guardar cambios"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GestionTarifas() {
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [cargando, setCargando] = useState(true);
  const [nombre, setNombre] = useState("");
  const [monto, setMonto] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);
  const [editando, setEditando] = useState<number | null>(null);
  const [editMonto, setEditMonto] = useState("");
  const [creandoTarifa, setCreandoTarifa] = useState(false);

  function cargar() {
    setCargando(true);
    listarTarifas().then(setTarifas).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  async function crear() {
    if (creandoTarifa) return;
    setMsg(null);
    const m = parseFloat(monto);
    if (!nombre.trim()) { setMsg({ tipo: "err", texto: "Indicá el nombre de la tarifa" }); return; }
    if (isNaN(m) || m < 0) { setMsg({ tipo: "err", texto: "Monto inválido" }); return; }
    setCreandoTarifa(true);
    try {
      await crearTarifa({ nombre: nombre.trim(), monto: m, descripcion: descripcion.trim() || undefined });
      setNombre(""); setMonto(""); setDescripcion("");
      setMsg({ tipo: "ok", texto: "Tarifa creada" });
      cargar();
      setTimeout(() => setMsg(null), 3000);
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
    finally { setCreandoTarifa(false); }
  }

  async function guardarEdicion(id: number) {
    const m = parseFloat(editMonto);
    if (isNaN(m) || m < 0) { setMsg({ tipo: "err", texto: "Monto inválido" }); return; }
    try {
      await editarTarifa(id, { monto: m });
      setEditando(null);
      cargar();
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
  }

  async function desactivar(id: number, nombre: string) {
    if (!confirm(`¿Desactivar la tarifa "${nombre}"? Las cuentas que la usan no se ven afectadas.`)) return;
    try { await desactivarTarifa(id); cargar(); }
    catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
  }

  return (
    <div className="form">
      <h3>Tarifas de cuota</h3>
      <p className="muted small">Definí los planes de cuota que se asignan a cada casa al darla de alta.</p>

      {/* Crear nueva tarifa */}
      <div className="crear-unidad-box" style={{ marginTop: 12 }}>
        <div className="sub">Nueva tarifa</div>
        <div className="row">
          <input placeholder="Nombre (ej. Cuota estándar)" value={nombre} onChange={e => setNombre(e.target.value)} />
          <input type="number" placeholder="Monto (L)" value={monto} onChange={e => setMonto(e.target.value)} style={{ maxWidth: 140 }} />
        </div>
        <input placeholder="Descripción (opcional)" value={descripcion}
          onChange={e => setDescripcion(e.target.value)} style={{ marginTop: 8 }} />
        <button className="mini" onClick={crear} disabled={creandoTarifa} style={{ marginTop: 8 }}>{creandoTarifa ? "Creando…" : "+ Crear tarifa"}</button>
      </div>

      {msg && <div className={msg.tipo === "ok" ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg.texto}</div>}

      {/* Lista de tarifas */}
      <div className="sub" style={{ marginTop: 16 }}>Tarifas activas</div>
      {cargando ? <p className="muted">Cargando…</p>
        : tarifas.length === 0 ? <p className="muted">No hay tarifas. Creá la primera arriba.</p>
        : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Nombre</th><th>Monto</th><th>Descripción</th><th></th></tr></thead>
              <tbody>
                {tarifas.map(t => (
                  <tr key={t.id}>
                    <td><b>{t.nombre}</b></td>
                    <td>
                      {editando === t.id ? (
                        <input type="number" value={editMonto} onChange={e => setEditMonto(e.target.value)}
                          style={{ width: 90 }} autoFocus />
                      ) : `L ${t.monto.toLocaleString("es-HN", { minimumFractionDigits: 2 })}`}
                    </td>
                    <td className="small muted">{t.descripcion || "—"}</td>
                    <td style={{ display: "flex", gap: 6 }}>
                      {editando === t.id ? (
                        <>
                          <button className="mini" onClick={() => guardarEdicion(t.id)}>Guardar</button>
                          <button className="ghost mini" onClick={() => setEditando(null)}>✕</button>
                        </>
                      ) : (
                        <>
                          <button className="mini" onClick={() => { setEditando(t.id); setEditMonto(String(t.monto)); }}>Editar monto</button>
                          <button className="ghost mini" style={{ color: "#c81e1e" }} onClick={() => desactivar(t.id, t.nombre)}>Desactivar</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}

/** "i" azul de información con tooltip al pasar el mouse (o tocar en móvil). */
function InfoTip({ texto }: { texto: string }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <span className="infotip"
      onMouseEnter={() => setAbierto(true)}
      onMouseLeave={() => setAbierto(false)}
      onClick={(e) => { e.stopPropagation(); setAbierto(v => !v); }}>
      <Info size={15} />
      {abierto && <span className="infotip-bubble">{texto}</span>}
    </span>
  );
}
