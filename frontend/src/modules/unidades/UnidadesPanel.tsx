import { ModalDarBaja } from "./SalidaSistema";
import { useEffect, useState } from "react";
import {
  listarCuentas, listarUnidades, listarTarifas, crearUnidad, crearCuenta,
  detalleCuenta, agregarMiembro, quitarMiembro, regenerarEnlace,
  asignarTarjeta, reactivarCuenta, pausarAcceso, reanudarAcceso, editarUsuario,
  crearTarifa, editarTarifa, desactivarTarifa,
  validarCodigoEnrolamiento, toggleQrRecurrente, editarTipoAccesoVirtual, editarUnidad, editarInfoCasa,
  listarSolicitudesBaja, resolverSolicitudBaja, nivelarSaldo, getMiResidencial,
  subirFotoResidente, urlFotoResidente,
  type Cuenta, type Unidad, type Tarifa, type ResidenteDTO, type SolicitudBajaDTO,
} from "../../api/client";
import { LectorTarjeta } from "./LectorTarjeta";
import { InfoTip } from "../../components/InfoTip";
import { CapturaFoto } from "../../components/CapturaFoto";
import { ModalFotoResidente } from "../../components/ModalFotoResidente";
import { formatearDNI, dniCompleto } from "../../utils/dni";
import { EstadoCorreo } from "../../components/EstadoCorreo";
import { ConfirmacionEnvio } from "../../components/ConfirmacionEnvio";
import { capitalizarNombre } from "../../utils/texto";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";
import { Building, Car, DoorOpen, Footprints, Home, Pencil, User, Plus, Info, Crown, Users, RefreshCw, Trash2, Clock, CheckCircle, Eye, Play, Pause, Camera } from "lucide-react";


export function UnidadesPanel({ embedded }: { embedded?: boolean } = {}) {
  const [tab, setTab] = useState<"cuentas" | "tarifas" | "solicitudes">("cuentas");
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [seleccionada, setSeleccionada] = useState<Cuenta | null>(null);
  const [modalNueva, setModalNueva] = useState(false);
  const [numSolicitudes, setNumSolicitudes] = useState(0);
  // Día 51 — niveles de plan: si la residencial no tiene cuotas
  // incluidas, la tarifa deja de ser obligatoria para dar de alta una
  // casa (ver validación en guardar()). Default true -- sin dato
  // todavía, no se bloquea de más mientras carga.
  const [permiteCuotas, setPermiteCuotas] = useState(true);
  // Día 53 — Sprint 2: separado de permiteCuotas -- "Acceso virtual" es
  // control físico (qué trancas puede abrir la tarjeta digital), no
  // cuotas. Antes se ocultaba mirando el flag equivocado.
  const [permiteControlFisico, setPermiteControlFisico] = useState(true);

  async function recargar() { setCuentas(await listarCuentas()); }
  useEffect(() => { recargar(); }, []);
  useEffect(() => {
    getMiResidencial().then((r) => {
      setPermiteCuotas(r?.plan?.permite_cuotas ?? true);
      setPermiteControlFisico(r?.plan?.permite_control_fisico ?? true);
    }).catch(() => {});
  }, []);
  useEffect(() => {
    listarSolicitudesBaja("pendiente").then(s => setNumSolicitudes(s.length)).catch(() => {});
  }, [tab, cuentas]);

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
          <button className={tab === "solicitudes" ? "tab on" : "tab"} onClick={() => setTab("solicitudes")}>
            Solicitudes de baja
            {numSolicitudes > 0 && <span className="tab-badge">{numSolicitudes}</span>}
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
      {tab === "solicitudes" && <SolicitudesBajaPanel onCambio={recargar} />}
      {modalNueva && (
        <FormNuevaCuenta
          permiteCuotas={permiteCuotas}
          permiteControlFisico={permiteControlFisico}
          onCerrar={() => setModalNueva(false)}
          onCreada={async () => { await recargar(); }} />
      )}
      {seleccionada && (
        <DetalleCuenta cuenta={seleccionada} onCerrar={() => setSeleccionada(null)} permiteCuotas={permiteCuotas}
          permiteControlFisico={permiteControlFisico}
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
  const [cuentaBaja, setCuentaBaja] = useState<Cuenta | null>(null);

  async function reactivar(c: Cuenta) {
    setProcesando(c.id);
    try { await reactivarCuenta(c.id); onRecargar(); }
    finally { setProcesando(null); }
  }

  // Día 53 — Sprint 1: pausa liviana, distinta de dar de baja — sin saldo,
  // sin tocar tarjetas ni usuarios, reversible con un solo clic.
  async function alternarPausa(c: Cuenta) {
    setProcesando(c.id);
    try {
      if (c.acceso_pausado) await reanudarAcceso(c.id);
      else await pausarAcceso(c.id);
      onRecargar();
    } finally { setProcesando(null); }
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
    if (filtroEstado === "solo_casas" && c.tipo_cuenta !== "casa" && c.tipo_cuenta !== undefined) return false;
    if (filtroEstado === "solo_edificios" && c.tipo_cuenta !== "edificio_contenedor" && c.tipo_cuenta !== "edificio_admin") return false;
    if (filtroEstado === "solo_aptos" && c.tipo_cuenta !== "apartamento") return false;
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
          <option disabled>──────────</option>
          <option value="solo_casas">🏠 Solo casas</option>
          <option value="solo_edificios">🏢 Solo edificios</option>
          <option value="solo_aptos">🚪 Solo apartamentos</option>
        </select>
      </div>

      <div className="casas-contador muted small">
        {filtradas.length} de {cuentas.length} {cuentas.length === 1 ? "cuenta" : "cuentas"}
      </div>

      {filtradas.length === 0 ? (
        <p className="muted">No hay casas que coincidan con la búsqueda.</p>
      ) : (
        <div className="lista-card"><div className="scroll-x">
          <table className="data tabla-casas">
            <thead><tr><th>Casa / Residente</th><th>Cuota</th><th>Estado de pago</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {filtradas.map((c) => {
                const dadaBaja = c.activa === false;
                // Día 53 — Sprint 1: pausa liviana, con su propio estado visual,
                // distinto de "Baja" (dar de baja formal).
                const pausada = !dadaBaja && c.acceso_pausado === true;
                const pend = c.cuotas_pendientes || 0;
                const esContenedor = c.tipo_cuenta === "edificio_contenedor";
                const esAdminRes = c.tipo_cuenta === "edificio_admin";
                const esApto = c.tipo_cuenta === "apartamento";
                const administra = esContenedor || esAdminRes;
                return (
                  <tr key={c.id} className={dadaBaja ? "fila-baja" : pausada ? "fila-pausada" : (administra ? "fila-edificio" : (esApto ? "fila-apto" : ""))}>
                    {/* Columna principal: tipo + identificador arriba (protagonista),
                        titular debajo en gris -- agrupa la info relacionada en vez
                        de esparcirla en columnas sueltas. */}
                    <td>
                      <div className="casa-cell">
                        <span className={`casa-icono casa-icono--${administra ? "edificio" : esApto ? "apto" : "casa"}`}>
                          {administra ? <Building size={16} /> : esApto ? <DoorOpen size={16} /> : <Home size={16} />}
                        </span>
                        <div className="casa-cell-txt">
                          <span className="casa-id">
                            {esAdminRes
                              ? <>{c.identificador} · Apto {c.apartamento} <span className="badge-admin-inline"><Crown size={11} /> Admin</span></>
                              : esApto
                              ? <>{c.identificador} · Apto {c.apartamento}</>
                              : (c.nombre_completo || c.identificador || "Casa")}
                          </span>
                          <span className="casa-titular">
                            {c.titular?.nombre || <span className="muted">Sin titular asignado</span>}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td>{esContenedor
                      ? <span className="muted small">No paga cuota</span>
                      : <div className="casa-cuota"><b>L {c.monto}</b><span className="muted small">{c.tarifa} · día {c.dia_pago}</span></div>}
                    </td>
                    <td>
                      {esContenedor
                        ? <span className="muted">—</span>
                        : pend === 0
                        ? <span className="pill green">Al día</span>
                        : <span className="pill red">{pend} pendiente{pend > 1 ? "s" : ""}</span>}
                    </td>
                    <td>
                      {dadaBaja
                        ? <span className="pill" style={{ background: "#6b7280", color: "#fff" }}>Baja</span>
                        : pausada
                        ? <span className="pill" style={{ background: "#b45309", color: "#fff" }}>Pausada</span>
                        : esContenedor
                        ? <span className="pill" style={{ background: "#044a6e", color: "#fff" }}>Administración</span>
                        : <span className={c.bloqueada ? "pill red" : "pill green"}>{c.bloqueada ? "Bloqueada" : c.estado}</span>}
                    </td>
                    <td>
                      <div className="casa-acciones">
                        <button className="icono-accion icono-accion--ver" title="Ver detalle" onClick={() => onAbrir(c)}>
                          <Eye size={16} />
                        </button>
                        {dadaBaja
                          ? <button className="icono-accion icono-accion--ok" title="Reactivar" disabled={procesando === c.id} onClick={() => reactivar(c)}>
                              <RefreshCw size={16} />
                            </button>
                          : <>
                            <button className={`icono-accion ${pausada ? "icono-accion--ok" : ""}`}
                              title={pausada ? "Reanudar acceso" : "Pausar acceso"}
                              disabled={procesando === c.id} onClick={() => alternarPausa(c)}>
                              {pausada ? <Play size={16} /> : <Pause size={16} />}
                            </button>
                            <button className="icono-accion icono-accion--baja" title="Salida del sistema: se muda, o vuelve al padrón" disabled={procesando === c.id} onClick={() => setCuentaBaja(c)}>
                              <Trash2 size={16} />
                            </button>
                          </>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div></div>
      )}

      {cuentaBaja && (
        <ModalDarBaja
          cuenta={cuentaBaja}
          onCerrar={() => setCuentaBaja(null)}
          onBajaCompletada={() => { setCuentaBaja(null); onRecargar(); }}
        />
      )}
    </div>
  );
}

function FormNuevaCuenta({ onCreada, onCerrar, permiteCuotas, permiteControlFisico }:
  { onCreada: () => void; onCerrar: () => void; permiteCuotas: boolean; permiteControlFisico: boolean }) {
  const [unidades, setUnidades] = useState<Unidad[]>([]);
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [unidadId, setUnidadId] = useState("");
  const [apartamento, setApartamento] = useState("");
  const [tarifaId, setTarifaId] = useState<number>(0);
  const [diaPago, setDiaPago] = useState<number>(new Date().getDate() > 28 ? 28 : new Date().getDate());
  const [tipoAccesoVirtualAlta, setTipoAccesoVirtualAlta] = useState<"peatonal" | "vehicular">("peatonal");
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
  const [duenoVive, setDuenoVive] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);
  const [enlace, setEnlace] = useState<{ email: string; url: string | null; cuentaId: string } | null>(null);
  // Día 73 — verdadero mientras se confirma que el correo llega (y, si
  // llega, mientras se crea). El formulario se oculta pero NO se borra:
  // si rebota, se vuelve a él con todo lo cargado para corregir el correo.
  const [verificando, setVerificando] = useState(false);
  const [nuevaUnidadTipo, setNuevaUnidadTipo] = useState<"casa" | "edificio">("casa");
  const [nuevaUnidadId, setNuevaUnidadId] = useState("");
  const [maxApartamentos, setMaxApartamentos] = useState("");
  const [creandoUnidad, setCreandoUnidad] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [mostrarSug, setMostrarSug] = useState(false);
  // Modo de selección de unidad: "nueva" (crear) es lo más común al dar de alta
  const [modoUnidad, setModoUnidad] = useState<"nueva" | "existente">("nueva");
  // UX Día 43: los datos opcionales del titular (RTN, ocupación, centro de
  // estudios, lugar de trabajo) empiezan plegados para reducir el scroll del
  // formulario. El backend los trata como opcionales, así que ocultarlos no
  // afecta la creación. Se despliegan solo si el admin los necesita.
  const [mostrarDatosAdic, setMostrarDatosAdic] = useState(false);
  // Día 72 — la foto del titular ahora es obligatoria en el alta: es la
  // cara contra la que el guardia verifica a quien llega sin teléfono, y
  // si no se toma en este momento, en la práctica no se toma nunca.
  const [foto, setFoto] = useState<File | null>(null);

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
    // Día 51 — niveles de plan: en una residencial sin cuotas (Básico),
    // esta llamada devuelve 402 a propósito — se atrapa acá para que no
    // rompa el resto de la pantalla (crear casas debe seguir andando).
    try {
      setTarifas(await listarTarifas());
    } catch {
      setTarifas([]);
    }
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

  /** Devuelve si el código sirvió, para que el asistente sepa si puede avanzar. */
  async function validarCodigo(): Promise<boolean> {
    if (!codigoEnrol.trim()) return false;
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
      return true;
    } catch (e) {
      setEnrolInfo(null);
      setMsg({ tipo: "err", texto: (e as Error).message });
      return false;
    } finally { setValidando(false); }
  }

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function clearFieldError(campo: string) {
    setFieldErrors(p => { const n = {...p}; delete n[campo]; return n; });
  }

  // ─── Día 73 — el alta pasó de una pantalla con scroll a un asistente ───
  //
  // Por qué: son cuatro secciones y más de quince campos. En una sola
  // pantalla, quien da de alta no sabe cuánto le falta, los errores de
  // validación salían todos juntos al final y encima arriba (fuera de la
  // vista, de ahí el "Revisalos arriba"), y la cámara de la foto quedaba
  // al fondo del scroll.
  //
  // Los pasos se identifican por nombre y NO por número fijo, porque el de
  // la cuota desaparece cuando la cuenta es del administrador de un
  // edificio nuevo que no vive ahí. Con índices fijos ese caso dejaba un
  // paso vacío en el medio.
  type PasoId = "codigo" | "unidad" | "cuota" | "titular";

  const muestraCuota = !(esEdificio && modoUnidad === "nueva" && !duenoVive);
  const pasos: { id: PasoId; titulo: string }[] = [
    { id: "codigo", titulo: "Código" },
    { id: "unidad", titulo: esEdificio ? "Edificio" : "Casa" },
    ...(muestraCuota ? [{ id: "cuota" as PasoId, titulo: "Cuota" }] : []),
    { id: "titular", titulo: "Titular" },
  ];

  const [paso, setPaso] = useState<PasoId>("codigo");
  // Si el paso donde está deja de existir (eligió "administrador que no vive
  // aquí" justo estando en el de la cuota), cae en el último, que es el que
  // sigue. Así no lo devuelve al principio ni se queda en una pantalla que
  // ya no existe.
  const indiceCrudo = pasos.findIndex(p => p.id === paso);
  const indicePaso = indiceCrudo >= 0 ? indiceCrudo : pasos.length - 1;
  const pasoVigente = pasos[indicePaso].id;
  const esUltimoPaso = indicePaso === pasos.length - 1;

  // Qué error de validación pertenece a qué paso: sirve para no mostrarle
  // errores de campos que todavía no vio, y para llevarlo al paso correcto
  // si al final falta algo de más atrás.
  const CAMPOS_DEL_PASO: Record<PasoId, string[]> = {
    codigo: [],
    unidad: ["unidad", "apartamento"],
    cuota: ["tarifa"],
    titular: ["nombre", "apellido", "email", "telefono", "dni", "direccion",
              "profesion", "emergNombre", "emergTel", "foto"],
  };

  function irAlPaso(id: PasoId) {
    setMsg(null);
    setFieldErrors({});
    setPaso(id);
  }

  async function siguiente() {
    setMsg(null);

    // El código es opcional, pero si escribió los seis dígitos y no los
    // validó, validarlos ahora: el paso siguiente depende del edificio y
    // apartamento que el código precarga.
    if (pasoVigente === "codigo" && codigoEnrol.length === 6 && !enrolInfo) {
      const sirvio = await validarCodigo();
      if (!sirvio) return;
    }
    // Un código a medias no se puede dejar pasar: viajaría igual al backend
    // en codigo_enrolamiento y el alta fallaría recién al final, después de
    // haber llenado todo lo demás.
    if (pasoVigente === "codigo" && codigoEnrol.length > 0 && codigoEnrol.length < 6) {
      setMsg({ tipo: "err", texto: "El código tiene 6 dígitos. Completalo o borralo para saltar este paso." });
      return;
    }

    const todos = validarCampos();
    const propios: Record<string, string> = {};
    for (const campo of CAMPOS_DEL_PASO[pasoVigente]) {
      if (todos[campo]) propios[campo] = todos[campo];
    }
    if (Object.keys(propios).length > 0) {
      setFieldErrors(propios);
      setMsg({ tipo: "err", texto: "Completá lo que falta para continuar." });
      return;
    }

    setFieldErrors({});
    setPaso(pasos[Math.min(indicePaso + 1, pasos.length - 1)].id);
  }

  function atras() {
    setMsg(null);
    setFieldErrors({});
    setPaso(pasos[Math.max(indicePaso - 1, 0)].id);
  }

  // Día 72 — "Dar de alta otra cuenta" solo ocultaba el recuadro del
  // enlace (setEnlace(null)) y dejaba el formulario con TODOS los datos de
  // la cuenta recién creada: nombre, correo, identidad, dirección. Daba la
  // impresión de que la cuenta no se había guardado, y peor: tocando otra
  // vez "Dar de alta cuenta y titular" se intentaba crear a la misma
  // persona de nuevo. Ahora el formulario vuelve a su estado inicial, y de
  // paso se recargan las unidades, así el edificio que se acaba de crear
  // ya aparece en la lista para darle de alta un apartamento.
  function darDeAltaOtra() {
    setEnlace(null);
    setMsg(null);
    setFieldErrors({});
    // Unidad
    setModoUnidad("nueva");
    setUnidadId("");
    setBusqueda("");
    setMostrarSug(false);
    setNuevaUnidadTipo("casa");
    setNuevaUnidadId("");
    setMaxApartamentos("");
    setApartamento("");
    setDuenoVive(false);
    // Cuota y acceso
    setTarifaId(0);
    setDiaPago(new Date().getDate() > 28 ? 28 : new Date().getDate());
    setTipoAccesoVirtualAlta("peatonal");
    // Titular
    setNombre("");
    setApellido("");
    setEmail("");
    setTelefono("");
    setDni("");
    setRtn("");
    setDireccionExacta("");
    setProfesion("");
    setOcupacion("");
    setCentroEstudios("");
    setLugarTrabajo("");
    setEmergNombre("");
    setEmergTel("");
    setMostrarDatosAdic(false);
    // Enrolamiento por código
    setCodigoEnrol("");
    setEnrolInfo(null);
    setFoto(null);
    setPaso("codigo");   // Día 73 — la otra alta arranca desde el primer paso
    setVerificando(false);
    recargarUnidades();
  }

  /**
   * Revisa TODOS los campos y devuelve los errores encontrados.
   *
   * Día 73 — se separó de guardar() porque ahora corre en dos momentos: al
   * pasar de un paso al siguiente (donde solo se muestran los errores de
   * ese paso) y al guardar (donde se muestran todos y se salta al paso que
   * los tiene). La validación es la misma en ambos: una sola copia.
   */
  function validarCampos(): Record<string, string> {
    const hayUnidad = unidadId || (modoUnidad === "nueva" && nuevaUnidadId.trim());
    const esDuenoSinVivienda = esEdificio && modoUnidad === "nueva" && !duenoVive;
    const hayTarifa = esDuenoSinVivienda || !permiteCuotas || !!tarifaId;

    const errs: Record<string, string> = {};
    if (!hayUnidad)            errs.unidad    = "Seleccioná o ingresá la casa o edificio.";
    if (!hayTarifa)            errs.tarifa    = "Seleccioná la tarifa mensual.";
    if (!nombre.trim())        errs.nombre    = "El nombre del titular es obligatorio.";
    if (!apellido.trim())      errs.apellido  = "El apellido del titular es obligatorio.";
    if (!email.trim())         errs.email     = "El correo electrónico es obligatorio.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
                               errs.email     = "El correo no tiene un formato válido.";
    if (!telefono.trim())      errs.telefono  = "El teléfono es obligatorio.";
    if (!dni.trim())           errs.dni       = "La identidad es obligatoria.";
    else if (!dniCompleto(dni))
                               errs.dni       = "El DNI debe tener 13 dígitos (0000-0000-00000).";
    if (!direccionExacta.trim()) errs.direccion = "La dirección exacta es obligatoria.";
    if (!profesion.trim())     errs.profesion = "La profesión es obligatoria.";
    if (!emergNombre.trim())   errs.emergNombre = "El contacto de emergencia es obligatorio.";
    if (!emergTel.trim())      errs.emergTel  = "El teléfono de emergencia es obligatorio.";
    if (!foto)                 errs.foto      = "La foto del titular es obligatoria.";
    if (esEdificio && !esDuenoSinVivienda && duenoVive && !apartamento.trim())
                               errs.apartamento = "Indicá el número del apartamento que ocupa.";

    return errs;
  }

  async function guardar() {
    setMsg(null); setEnlace(null);

    const esDuenoSinVivienda = esEdificio && modoUnidad === "nueva" && !duenoVive;

    const errs = validarCampos();
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) {
      // Día 73 — con el asistente, un campo que falta puede estar en un paso
      // anterior y fuera de la pantalla. En vez de pedirle que lo busque, se
      // lo lleva al paso que lo tiene.
      const conError = pasos.find(p => CAMPOS_DEL_PASO[p.id].some(c => errs[c]));
      if (conError && conError.id !== pasoVigente) {
        setPaso(conError.id);
        setMsg({ tipo: "err", texto: `Falta algo en el paso "${conError.titulo}".` });
      } else {
        setMsg({ tipo: "err", texto: "Hay campos incompletos o con errores." });
      }
      return;
    }

    // Día 73 — NO se crea todavía. Primero se verifica que el correo llega;
    // la creación la hace crearDeVerdad(), y solo si llegó.
    setVerificando(true);
  }

  /**
   * Día 73 — crea la cuenta. Se ejecuta SOLO cuando Resend confirmó que el
   * correo llegó, y recibe el id de esa confirmación: el backend rechaza
   * crear sin él. Si algo falla acá tiene que lanzar el error, para que la
   * pantalla de verificación lo muestre y deje reintentar.
   */
  async function crearDeVerdad(verificacionId: string) {
    const esDuenoSinVivienda = esEdificio && modoUnidad === "nueva" && !duenoVive;
    {
      const res = await crearCuenta({
        verificacion_id: verificacionId,
        unidad_id: unidadId || undefined,
        unidad_nueva: (!unidadId && nuevaUnidadId.trim())
          ? { tipo: nuevaUnidadTipo, identificador: nuevaUnidadId.trim(),
              max_apartamentos: nuevaUnidadTipo === "edificio" && maxApartamentos
                ? Number(maxApartamentos) : undefined } : undefined,
        apartamento: (esEdificio && !esDuenoSinVivienda) ? apartamento : undefined,
        tarifa_id: (esDuenoSinVivienda || !permiteCuotas) ? undefined : tarifaId,
        dia_pago: (esDuenoSinVivienda || !permiteCuotas) ? 1 : diaPago,
        tipo_acceso_virtual: tipoAccesoVirtualAlta,
        codigo_enrolamiento: codigoEnrol.trim() || undefined,
        es_dueno_edificio: esEdificio && modoUnidad === "nueva" && !enrolInfo,
        es_solo_contenedor: esDuenoSinVivienda || undefined,
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
      // Día 61 — en producción el backend NO devuelve token_activacion (por
      // diseño: el token solo debe viajar por correo, nunca en la
      // respuesta de la API -- ver _bloque_activacion en cuentas.py). Antes
      // esto armaba igual un link con "?activar=undefined", confuso y roto.
      // Ahora se detecta la ausencia del token y se muestra un mensaje de
      // "se envió el correo" en vez de un link que nunca iba a funcionar.
      const token = res.activacion.token_activacion;
      const url = token ? `${window.location.origin}/?activar=${token}` : null;

      // Día 72 — la foto se sube DESPUÉS de crear la cuenta, porque el
      // endpoint necesita el id del residente, que recién existe ahora. Si
      // esta subida falla, la cuenta YA quedó creada: se avisa que falta la
      // foto y se explica dónde completarla, en vez de dar por fallida un
      // alta que sí se hizo.
      let avisoFoto = "";
      const residenteId = res.cuenta.titular?.id;
      if (foto && residenteId) {
        try {
          await subirFotoResidente(res.cuenta.id, residenteId, foto);
        } catch (e) {
          avisoFoto = ` La cuenta se creó, pero la foto no se pudo subir (${(e as Error).message}). `
            + "Agregala desde la casa, en la pestaña Miembros.";
        }
      }

      // La foto NO puede hacer fallar esto: la cuenta ya está creada, y si
      // se lanzara el error la pantalla diría "no se creó nada", que sería
      // mentira. Se avisa aparte.
      setEnlace({ email: res.activacion.usuario_email, url, cuentaId: res.cuenta.id });
      if (avisoFoto) setMsg({ tipo: "err", texto: avisoFoto });
      onCreada();
    }
  }

  function copiarEnlace() {
    if (!enlace || !enlace.url) return;
    navigator.clipboard.writeText(enlace.url);
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body modal-alta" onClick={(e) => e.stopPropagation()}>
        <div className="modal-alta-head">
          <div>
            <h3>Dar de alta una casa o apartamento</h3>
            <p className="muted small" style={{ margin: 0 }}>
              {verificando
                ? "Verificando el correo antes de crear la cuenta"
                : `Paso ${indicePaso + 1} de ${pasos.length}`}
            </p>
          </div>
          <button className="modal-x" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </div>

        {/* Día 73 — barra de pasos. Los pasos ya recorridos se pueden tocar
            para volver a ellos; los que faltan no, porque cada uno valida lo
            suyo antes de dejar avanzar. */}
        {!verificando && (
          <div className="alta-pasos" role="list">
            {pasos.map((p, i) => {
              const hecho = i < indicePaso;
              const actual = i === indicePaso;
              return (
                <button key={p.id} type="button" role="listitem"
                  className={`alta-paso ${actual ? "alta-paso--actual" : ""} ${hecho ? "alta-paso--hecho" : ""}`}
                  onClick={() => hecho && irAlPaso(p.id)}
                  disabled={!hecho}
                  aria-current={actual ? "step" : undefined}>
                  <span className="alta-paso-num">{hecho ? "✓" : i + 1}</span>
                  <span className="alta-paso-txt">{p.titulo}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="modal-alta-body">

      {/* Día 73 — verificación del correo y, solo si llega, creación.
          Si el correo no llega no se crea NADA, y "Corregir" vuelve al
          formulario con todo lo cargado: solo hay que arreglar el correo. */}
      {verificando && (
        <>
          <ConfirmacionEnvio
            email={email.trim().toLowerCase()} nombre={nombre.trim()}
            onConfirmado={crearDeVerdad}
            onCorregir={() => {
              setVerificando(false);
              setPaso("titular");
              setFieldErrors({ email: "Revisá este correo antes de seguir." });
              setMsg(null);
            }}
            textoCreado="La cuenta quedó creada."
            textoListo="Dar de alta otra cuenta"
            onListo={darDeAltaOtra} />

          {/* Fuera de producción el backend devuelve el token, y tenerlo a
              mano ahorra abrir el correo en cada prueba. En producción esto
              no aparece nunca (ver _bloque_activacion). */}
          {enlace?.url && (
            <div className="activacion-box" style={{ marginTop: 12 }}>
              <div className="activacion-titulo">Enlace de activación (solo en desarrollo)</div>
              <div className="activacion-url">{enlace.url}</div>
              <div className="row-btns" style={{ marginTop: 8 }}>
                <button className="mini" onClick={copiarEnlace}>Copiar enlace</button>
              </div>
            </div>
          )}
          {msg && msg.tipo === "err" && (
            <div className="error" style={{ marginTop: 10 }}>⚠ {msg.texto}</div>
          )}
        </>
      )}

      {!verificando && (
        <>
          {msg && (
            <div className={msg.tipo === "ok" ? "ok-box" : "error"}
              style={{ position: "sticky", top: 8, zIndex: 20, marginBottom: 14,
                       boxShadow: "0 2px 10px rgba(0,0,0,0.12)" }}>
              {msg.tipo === "err" ? "⚠ " : "✓ "}{msg.texto}
            </div>
          )}
          {/* Paso 1 — Código de enrolamiento (opcional) */}
          {pasoVigente === "codigo" && (
          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">1</span>
              <b>¿Trae código de enrolamiento?</b>
              <InfoTip texto="Si un inquilino recibió un código de 6 dígitos del dueño de su edificio, ingresalo aquí: el edificio y apartamento se seleccionan solos. Si es una casa normal o no hay código, tocá «Saltar este paso»." />
              <span className="muted small" style={{ marginLeft: "auto" }}>Opcional</span>
            </div>
            <p className="muted small" style={{ marginTop: 0, marginBottom: 10 }}>
              La mayoría de las altas son casas y no traen código: en ese caso
              tocá <b>Saltar este paso</b>.
            </p>
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
          )}

          {/* Paso 2 — Casa o edificio */}
          {pasoVigente === "unidad" && (
          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">2</span>
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
                  : "Primero se crea el edificio; luego registrás sus apartamentos uno por uno."}
              </p>

              {nuevaUnidadTipo === "edificio" && (
                <>
                  <div className="sub" style={{ marginTop: 14 }}>¿Cuántos apartamentos tiene?</div>
                  <input type="number" min={1} max={200} placeholder="Ej. 12"
                    value={maxApartamentos} onChange={(e) => setMaxApartamentos(e.target.value)} />

                  {!enrolInfo && (
                    <>
                      <div className="sub" style={{ marginTop: 14 }}>Esta cuenta que estás creando es de...</div>
                      <div className="radio-cards">
                        <label className={`radio-card ${!duenoVive ? "on" : ""}`}>
                          <input type="radio" name="dueno-vive" checked={!duenoVive}
                            onChange={() => setDuenoVive(false)} />
                          <div>
                            <b>El administrador del edificio</b>
                            <span className="muted small">No vive aquí. Solo gestiona el edificio y genera códigos para los inquilinos. No paga cuota.</span>
                          </div>
                        </label>
                        <label className={`radio-card ${duenoVive ? "on" : ""}`}>
                          <input type="radio" name="dueno-vive" checked={duenoVive}
                            onChange={() => setDuenoVive(true)} />
                          <div>
                            <b>El administrador, que también vive aquí</b>
                            <span className="muted small">Además de administrar, ocupa un apartamento y paga su cuota como los demás.</span>
                          </div>
                        </label>
                      </div>

                      {duenoVive && (
                        <>
                          <div className="sub" style={{ marginTop: 14 }}>¿Cuál apartamento ocupa?</div>
                          <input placeholder="Ej. 1A, 2B" value={apartamento}
                            onChange={(e) => setApartamento(e.target.value)} />
                        </>
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="crear-unidad-box">
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

              {/* Al agregar a un edificio existente, el apartamento siempre es necesario */}
              {(unidadId || enrolInfo) && (
                <>
                  <div className="sub" style={{ marginTop: 14 }}>Apartamento</div>
                  <input placeholder="Ej. 1A, 2B" value={apartamento}
                    className={fieldErrors.apartamento ? "input-error" : ""}
                    onChange={(e) => { setApartamento(e.target.value); clearFieldError("apartamento"); }} />
                </>
              )}
            </div>
          )}

          {/* Día 73 — estos dos errores se calculaban desde siempre pero no se
              dibujaban en ninguna parte: lo único que se veía era el mensaje
              general de "revisalos arriba", sin decir cuál faltaba. */}
          {fieldErrors.unidad && <span className="campo-error">{fieldErrors.unidad}</span>}
          {fieldErrors.apartamento && <span className="campo-error">{fieldErrors.apartamento}</span>}
          </div>
          )}

          {/* Paso 3 — Cuota mensual. El paso no existe cuando la cuenta es del
              administrador de un edificio NUEVO que no vive ahí (el edificio no
              genera cuota propia), así que acá solo se pregunta por el paso. */}
          {pasoVigente === "cuota" && (
          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">{indicePaso + 1}</span>
              <b>Cuota mensual</b>
              <InfoTip texto="La tarifa define cuánto paga esta casa cada mes. El día de pago es la fecha límite mensual; se autollena con hoy pero podés cambiarlo (máximo 28 para evitar problemas en febrero)." />
            </div>
          {!permiteCuotas ? (
            <div className="muted small" style={{
              padding: "10px 12px", background: "var(--gris-cl, #f1f3f6)",
              borderRadius: 8, marginTop: 4,
            }}>
              No aplica — tu plan actual no incluye cuotas de residentes.
            </div>
          ) : (
          <div className="row">
            <select value={tarifaId} className={fieldErrors.tarifa ? "input-error" : ""}
              onChange={(e) => { setTarifaId(Number(e.target.value)); clearFieldError("tarifa"); }}>
              <option value={0}>— Selecciona tarifa —</option>
              {tarifas.map((t) => (
                <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>
              ))}
            </select>
            <label className="diapago">
              <span className="label-con-info">
                Día de pago
                <span className="info-tip" title="El día 1 de cada mes se genera la cuota de ese mes, y el residente la paga durante el MES SIGUIENTE. Este número es el día del mes siguiente hasta el que puede pagar sin atraso. Ej: con día de pago 5, la cuota de agosto se paga hasta el 5 de septiembre. Después entra en mora (con avisos), y al vencerse los días de gracia configurados en Configuraciones, se le suspenden los accesos.">i</span>
              </span>
              {/* Día 62: max corregido de 28 a 30 -- había quedado
                  desactualizado acá cuando el Día 55 se subió el tope a 30
                  en el resto del sistema (backend y Configuraciones). */}
              <input type="number" min={1} max={30} value={diaPago}
                onChange={(e) => setDiaPago(Number(e.target.value))} />
            </label>
          </div>
          )}
          {fieldErrors.tarifa && <span className="campo-error">{fieldErrors.tarifa}</span>}
          {permiteControlFisico && (
          <div className="row" style={{ alignItems: "center", marginTop: 10 }}>
            <span className="muted small" style={{ marginRight: 10 }}>
              Acceso virtual (QR/Bluetooth) de esta cuenta:
            </span>
            <div className="segmented" role="group" aria-label="Tipo de acceso virtual">
              <button type="button"
                className={tipoAccesoVirtualAlta === "peatonal" ? "segmented-activo" : ""}
                onClick={() => setTipoAccesoVirtualAlta("peatonal")}>
                Peatonal
              </button>
              <button type="button"
                className={tipoAccesoVirtualAlta === "vehicular" ? "segmented-activo" : ""}
                onClick={() => setTipoAccesoVirtualAlta("vehicular")}>
                Vehicular
              </button>
            </div>
          </div>
          )}
          </div>
          )}

          {/* Paso final — Titular de la cuenta */}
          {pasoVigente === "titular" && (
          <div className="alta-seccion">
            <div className="alta-seccion-head">
              <span className="alta-num">{indicePaso + 1}</span>
              <b>Titular de la cuenta</b>
              <InfoTip texto="Es la persona responsable de la cuenta (quien paga). Se le creará un acceso en estado pendiente y recibirá un enlace para definir su propia contraseña. Nombre, apellido, correo y teléfono son obligatorios." />
            </div>
          <div className="campo-con-error" style={{ marginBottom: 10 }}>
            <div className="label-con-info" style={{ marginBottom: 6 }}>
              <span className="muted" style={{ fontSize: 13 }}>Foto del titular *</span>
              <InfoTip texto="Es la foto que ve el guardia para verificar la identidad de quien llega sin teléfono. Tomala con la cámara del equipo o elegí una imagen del archivo." />
            </div>
            <CapturaFoto valor={foto} error={!!fieldErrors.foto}
              onCambio={(f) => { setFoto(f); if (f) clearFieldError("foto"); }} />
            {fieldErrors.foto && <span className="campo-error">{fieldErrors.foto}</span>}
          </div>
          <div className="row">
            <div className="campo-con-error">
              <input placeholder="Nombre *" value={nombre} className={fieldErrors.nombre ? "input-error" : ""}
                onChange={(e) => { setNombre(capitalizarNombre(e.target.value)); clearFieldError("nombre"); }} />
              {fieldErrors.nombre && <span className="campo-error">{fieldErrors.nombre}</span>}
            </div>
            <div className="campo-con-error">
              <input placeholder="Apellido *" value={apellido} className={fieldErrors.apellido ? "input-error" : ""}
                onChange={(e) => { setApellido(capitalizarNombre(e.target.value)); clearFieldError("apellido"); }} />
              {fieldErrors.apellido && <span className="campo-error">{fieldErrors.apellido}</span>}
            </div>
          </div>
          <div className="row">
            <div className="campo-con-error">
              <input placeholder="Correo electrónico *" value={email} className={fieldErrors.email ? "input-error" : ""}
                onChange={(e) => { setEmail(e.target.value); clearFieldError("email"); }} />
              {fieldErrors.email && <span className="campo-error">{fieldErrors.email}</span>}
            </div>
            <div className="campo-con-error">
              <input placeholder="Teléfono *" value={telefono} className={fieldErrors.telefono ? "input-error" : ""}
                onChange={(e) => { setTelefono(e.target.value); clearFieldError("telefono"); }} />
              {fieldErrors.telefono && <span className="campo-error">{fieldErrors.telefono}</span>}
            </div>
          </div>
          <div className="row">
            <div className="campo-con-error">
              <input placeholder="Identidad (0000-0000-00000) *" value={dni} inputMode="numeric"
                maxLength={15} className={fieldErrors.dni ? "input-error" : ""}
                onChange={(e) => { setDni(formatearDNI(e.target.value)); clearFieldError("dni"); }} />
              {fieldErrors.dni && <span className="campo-error">{fieldErrors.dni}</span>}
            </div>
            <div className="campo-con-error">
              <input placeholder="Profesión *" value={profesion}
                className={fieldErrors.profesion ? "input-error" : ""}
                onChange={(e) => { setProfesion(e.target.value); clearFieldError("profesion"); }} />
              {fieldErrors.profesion && <span className="campo-error">{fieldErrors.profesion}</span>}
            </div>
          </div>
          <div className="row">
            <div className="campo-con-error">
              <input placeholder="Dirección exacta *" value={direccionExacta}
                className={fieldErrors.direccion ? "input-error" : ""}
                onChange={(e) => { setDireccionExacta(e.target.value); clearFieldError("direccion"); }} />
              {fieldErrors.direccion && <span className="campo-error">{fieldErrors.direccion}</span>}
            </div>
          </div>
          <div className="row">
            <div className="campo-con-error">
              <input placeholder="Contacto de emergencia (nombre) *" value={emergNombre}
                className={fieldErrors.emergNombre ? "input-error" : ""}
                onChange={(e) => { setEmergNombre(capitalizarNombre(e.target.value)); clearFieldError("emergNombre"); }} />
              {fieldErrors.emergNombre && <span className="campo-error">{fieldErrors.emergNombre}</span>}
            </div>
            <div className="campo-con-error">
              <input placeholder="Teléfono del contacto *" value={emergTel}
                className={fieldErrors.emergTel ? "input-error" : ""}
                onChange={(e) => { setEmergTel(e.target.value); clearFieldError("emergTel"); }} />
              {fieldErrors.emergTel && <span className="campo-error">{fieldErrors.emergTel}</span>}
            </div>
          </div>

          {/* UX Día 43: datos opcionales plegados para reducir el scroll.
              El backend los acepta como opcionales (rtn/ocupacion/centro_
              estudios/lugar_trabajo → None si vienen vacíos). */}
          {!mostrarDatosAdic ? (
            <button type="button" className="ghost mini alta-adic-toggle"
              onClick={() => setMostrarDatosAdic(true)}>
              + Agregar datos adicionales (RTN, ocupación)
            </button>
          ) : (
            <div className="alta-datos-adic">
              <div className="alta-adic-head">
                <span className="muted small">Datos adicionales (opcionales)</span>
                <button type="button" className="ghost mini"
                  onClick={() => setMostrarDatosAdic(false)}>Ocultar</button>
              </div>
              <div className="row">
                <input placeholder="RTN (opcional)" value={rtn}
                  onChange={(e) => setRtn(e.target.value)} />
                <select value={ocupacion} onChange={(e) => setOcupacion(e.target.value)}>
                  <option value="">— Ocupación (opcional) —</option>
                  <option value="estudiante">Estudiante</option>
                  <option value="profesional">Profesional / Empleado</option>
                  <option value="otro">Otro</option>
                </select>
              </div>
              {ocupacion === "estudiante" && (
                <div className="row campo-condicional">
                  <input placeholder="Centro de estudios" value={centroEstudios}
                    onChange={(e) => setCentroEstudios(e.target.value)} />
                </div>
              )}
              {ocupacion === "profesional" && (
                <div className="row campo-condicional">
                  <input placeholder="Lugar de trabajo" value={lugarTrabajo}
                    onChange={(e) => setLugarTrabajo(e.target.value)} />
                </div>
              )}
            </div>
          )}
          </div>
          )}

          {pasoVigente === "titular" && (
          <div className="info-box">
            <Info size={15} />
            <span>Se creará el acceso del titular en estado <b>pendiente</b>. Recibirá un enlace para definir su propia contraseña — la administración nunca conoce las contraseñas.</span>
          </div>
          )}
        </>
      )}
        </div>

        {!verificando && (
          <div className="modal-alta-footer">
            {/* Cancelar cierra todo; Atrás solo retrocede un paso. Nunca los
                dos juntos en el mismo lugar: en el primer paso Atrás no
                existe, y de ahí en adelante Cancelar pasa a ser la ✕ de
                arriba, para que no se confundan de un golpe. */}
            {indicePaso === 0
              ? <button className="ghost" onClick={onCerrar}>Cancelar</button>
              : <button className="ghost" onClick={atras}>← Atrás</button>}

            {esUltimoPaso ? (
              <button onClick={guardar}>Dar de alta cuenta y titular</button>
            ) : (
              <button onClick={siguiente} disabled={validando}>
                {/* El botón del primer paso dice "Saltar" mientras no haya
                    código escrito: es lo que va a hacer en la mayoría de las
                    altas, y así no tiene que adivinar que puede dejarlo vacío. */}
                {validando ? "Validando…"
                  : pasoVigente === "codigo" && !codigoEnrol.trim()
                    ? "Saltar este paso →"
                    : "Siguiente →"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DetalleCuenta({ cuenta, onCerrar, onCambio, permiteCuotas, permiteControlFisico }:
  { cuenta: Cuenta; onCerrar: () => void; onCambio: () => void; permiteCuotas: boolean; permiteControlFisico: boolean }) {
  const [cardUid, setCardUid] = useState("");
  const [etiqueta, setEtiqueta] = useState("");
  const [qrRecurrente, setQrRecurrente] = useState(cuenta.qr_recurrente_habilitado ?? false);
  const [guardandoQr, setGuardandoQr] = useState(false);
  const [tipoAccesoVirtual, setTipoAccesoVirtual] = useState<"peatonal" | "vehicular">(
    cuenta.tipo_acceso_virtual ?? "peatonal");
  const [guardandoTipoVirtual, setGuardandoTipoVirtual] = useState(false);
  const [maxAptos, setMaxAptos] = useState(cuenta.unidad?.max_apartamentos?.toString() ?? "");
  const [guardandoAptos, setGuardandoAptos] = useState(false);
  const [msgConfig, setMsgConfig] = useState("");
  // Día 55 — edición de la info de la casa (tarifa, día de pago, días de
  // gracia, identificador). Arranca cerrado; se abre con el botón "Editar".
  const [editando, setEditando] = useState(false);
  const [edTarifaId, setEdTarifaId] = useState<number>(cuenta.tarifa_id ?? 0);
  const [edDiaPago, setEdDiaPago] = useState<string>(cuenta.dia_pago?.toString() ?? "");
  const [edDiasGracia, setEdDiasGracia] = useState<string>(cuenta.dias_gracia?.toString() ?? "");
  const [edIdentificador, setEdIdentificador] = useState(cuenta.unidad?.identificador ?? cuenta.identificador ?? "");
  const [tarifasEd, setTarifasEd] = useState<Tarifa[]>([]);
  const [guardandoEd, setGuardandoEd] = useState(false);
  const [errEd, setErrEd] = useState("");

  useEffect(() => {
    if (editando && permiteCuotas && tarifasEd.length === 0) {
      listarTarifas().then(setTarifasEd).catch(() => {});
    }
  }, [editando, permiteCuotas]);
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
  // Día 73 — la foto del miembro también es obligatoria.
  //
  // En el Día 72 se hizo obligatoria la del titular, pero la de los miembros
  // quedó opcional sin razón: el guardia verifica igual a la esposa, al hijo
  // o al inquilino que llega sin teléfono, y si la foto no se toma en el
  // momento de registrarlo, en la práctica no se toma nunca.
  const [mFoto, setMFoto] = useState<File | null>(null);
  // Día 73 — mientras se verifica el correo del miembro nuevo (y, si llega,
  // mientras se crea). El formulario queda cargado por si hay que corregir.
  const [verificandoMiembro, setVerificandoMiembro] = useState(false);
  const [msg, setMsg] = useState("");
  const [miembroEnlace, setMiembroEnlace] = useState<{ email: string; url: string | null } | null>(null);
  const [mostrarAgregar, setMostrarAgregar] = useState(false);
  // UX Día 43: el detalle de cuenta se separa en pestañas (datos / miembros /
  // accesos) para eliminar el scroll largo. Antes todas las secciones se
  // apilaban verticalmente. La lógica de cada sección no cambia, solo se
  // agrupa bajo su pestaña.
  const [tabDetalle, setTabDetalle] = useState<"datos" | "miembros" | "accesos">("datos");
  const [mErrors, setMErrors] = useState<Record<string, string>>({});
  const [msgMiembro, setMsgMiembro] = useState("");
  function clearMError(k: string) { setMErrors(prev => { const c = { ...prev }; delete c[k]; return c; }); }

  async function guardarEdicion() {
    setGuardandoEd(true); setErrEd("");
    try {
      const cambios: Parameters<typeof editarInfoCasa>[1] = {};
      // Solo mandar lo que cambió, para no pisar valores sin querer.
      if (edTarifaId !== (cuenta.tarifa_id ?? 0)) cambios.tarifa_id = edTarifaId || null;
      if (edDiaPago && Number(edDiaPago) !== cuenta.dia_pago) cambios.dia_pago = Number(edDiaPago);
      const graciaActual = cuenta.dias_gracia ?? null;
      const graciaNueva = edDiasGracia === "" ? null : Number(edDiasGracia);
      if (graciaNueva !== graciaActual) cambios.dias_gracia = graciaNueva;
      const idActual = cuenta.unidad?.identificador ?? cuenta.identificador ?? "";
      if (edIdentificador.trim() && edIdentificador.trim() !== idActual) cambios.identificador = edIdentificador.trim();

      if (Object.keys(cambios).length === 0) { setEditando(false); return; }
      await editarInfoCasa(cuenta.id, cambios);
      setMsgConfig("✓ Información actualizada");
      setEditando(false);
      onCambio();
      setTimeout(() => setMsgConfig(""), 2500);
    } catch (e) { setErrEd((e as Error).message); }
    finally { setGuardandoEd(false); }
  }

  async function guardarQrRecurrente(valor: boolean) {
    setGuardandoQr(true); setMsgConfig("");
    try {
      await toggleQrRecurrente(cuenta.id, valor);
      setQrRecurrente(valor);
      setMsgConfig("✓ Guardado");
      onCambio();
      setTimeout(() => setMsgConfig(""), 2500);
    } catch (e) { setMsgConfig((e as Error).message); }
    finally { setGuardandoQr(false); }
  }

  async function guardarTipoAccesoVirtual(valor: "peatonal" | "vehicular") {
    setGuardandoTipoVirtual(true); setMsgConfig("");
    try {
      await editarTipoAccesoVirtual(cuenta.id, valor);
      setTipoAccesoVirtual(valor);
      setMsgConfig("✓ Guardado");
      onCambio();
      setTimeout(() => setMsgConfig(""), 2500);
    } catch (e) { setMsgConfig((e as Error).message); }
    finally { setGuardandoTipoVirtual(false); }
  }

  async function guardarMaxAptos() {
    if (!cuenta.unidad) return;
    setGuardandoAptos(true); setMsgConfig("");
    try {
      await editarUnidad(cuenta.unidad.id, {
        max_apartamentos: maxAptos.trim() ? Number(maxAptos) : null,
      });
      setMsgConfig("✓ Límite actualizado");
      onCambio();
      setTimeout(() => setMsgConfig(""), 2500);
    } catch (e) { setMsgConfig((e as Error).message); }
    finally { setGuardandoAptos(false); }
  }

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
    const errs: Record<string, string> = {};
    if (!mNombre.trim())    errs.nombre    = "El nombre es obligatorio.";
    if (!mApellido.trim())  errs.apellido  = "El apellido es obligatorio.";
    if (!mEmail.trim())     errs.email     = "El correo es obligatorio.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mEmail.trim()))
                            errs.email     = "El correo no tiene un formato válido.";
    if (!mTelefono.trim())  errs.telefono  = "El teléfono es obligatorio.";
    if (!mDni.trim())       errs.dni       = "La identidad es obligatoria.";
    else if (!dniCompleto(mDni))
                            errs.dni       = "El DNI debe tener 13 dígitos (0000-0000-00000).";
    if (!mProfesion.trim()) errs.profesion = "La profesión es obligatoria.";
    if (!mEmergNombre.trim()) errs.emergNombre = "El contacto de emergencia es obligatorio.";
    if (!mEmergTel.trim())    errs.emergTel    = "El teléfono de emergencia es obligatorio.";
    if (!mFoto)               errs.foto        = "La foto del miembro es obligatoria.";

    setMErrors(errs);
    if (Object.keys(errs).length > 0) {
      setMsgMiembro("Hay campos incompletos o con errores. Revisalos arriba.");
      return;
    }
    setMsgMiembro("");
    // Día 73 — no se crea todavía: primero se verifica que el correo llega.
    setVerificandoMiembro(true);
  }

  /** Se ejecuta SOLO si Resend confirmó que el correo llegó. */
  async function agregarMiembroDeVerdad(verificacionId: string) {
    {
      const res = await agregarMiembro(cuenta.id, {
        verificacion_id: verificacionId,
        nombre: mNombre, apellido: mApellido, email: mEmail, telefono: mTelefono,
        relacion: "familiar", dni: mDni, profesion: mProfesion,
        contacto_emergencia_nombre: mEmergNombre, contacto_emergencia_telefono: mEmergTel,
      });
      const token = (res as any).activacion?.token_activacion;
      // Día 61 — antes solo se guardaba el enlace si había token real (dev).
      // En producción esto dejaba silencio total: el admin no se enteraba
      // de que el correo se había enviado igual. Ahora siempre se guarda
      // el resultado, con o sin token, para poder avisar en cualquier caso.
      const url = token ? `${window.location.origin}/?activar=${token}` : null;

      // Día 73 — igual que en el alta del titular: la foto se sube DESPUÉS,
      // porque el endpoint necesita el id del residente, que recién existe
      // ahora. Si esta subida falla, el miembro YA quedó creado: se avisa
      // dónde completar la foto en vez de dar por fallido un alta que sí se
      // hizo.
      let avisoFoto = "";
      const nuevoId = res.residente?.id;
      if (mFoto && nuevoId) {
        try {
          await subirFotoResidente(cuenta.id, nuevoId, mFoto);
        } catch (e) {
          avisoFoto = `El miembro se agregó, pero la foto no se pudo subir (${(e as Error).message}). `
            + "Agregala desde la lista de miembros, tocando su foto.";
        }
      }
      if (avisoFoto) setMsgMiembro(avisoFoto);

      // El formulario se limpia recién en "Terminar" (ver terminarMiembro):
      // si se limpiara acá, la pantalla de verificación perdería el correo
      // que está mostrando.
      setMiembroEnlace({ email: mEmail, url });
      onCambio();
    }
  }

  function terminarMiembro() {
    setVerificandoMiembro(false);
    setMNombre(""); setMEmail(""); setMApellido(""); setMTelefono("");
    setMDni(""); setMProfesion(""); setMEmergNombre(""); setMEmergTel("");
    setMFoto(null);
    setMErrors({}); setMsg("");
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 className="modal-head-titulo">
            {cuenta.tipo_cuenta === "edificio_contenedor" || cuenta.tipo_cuenta === "edificio_admin"
              ? <span className="modal-tipo-icon modal-tipo-icon--edificio"><Building size={20} /></span>
              : cuenta.tipo_cuenta === "apartamento"
              ? <span className="modal-tipo-icon modal-tipo-icon--apto"><DoorOpen size={20} /></span>
              : <span className="modal-tipo-icon modal-tipo-icon--casa"><Home size={20} /></span>}
            {cuenta.nombre_completo || (cuenta.apartamento ? `Apartamento ${cuenta.apartamento}` : "Casa")}
            {cuenta.tipo_cuenta !== "edificio_contenedor" && cuenta.tarifa ? ` · ${cuenta.tarifa}` : ""}
          </h3>
          <button className="ghost mini" onClick={onCerrar}>Cerrar</button>
        </div>

        {/* UX Día 43: barra de pestañas para no apilar todo en scroll */}
        <div className="detalle-tabs">
          <button className={tabDetalle === "datos" ? "on" : ""}
            onClick={() => setTabDetalle("datos")}>Datos</button>
          <button className={tabDetalle === "miembros" ? "on" : ""}
            onClick={() => setTabDetalle("miembros")}>
            {cuenta.tipo_cuenta === "edificio_contenedor" ? "Administrador" : "Miembros"}
          </button>
          <button className={tabDetalle === "accesos" ? "on" : ""}
            onClick={() => setTabDetalle("accesos")}>Accesos</button>
        </div>

        {/* ══════ PESTAÑA: DATOS ══════ */}
        {tabDetalle === "datos" && (<>

        {/* Información general de la cuenta: estado de pago, cuota, unidad */}
        {cuenta.tipo_cuenta === "edificio_admin" && (
          <div className="banner-admin-edificio">
            <Crown size={16} style={{ flexShrink: 0 }} /> <b>Administrador del edificio</b> — Esta persona vive en el Apto {cuenta.apartamento} y
            paga su cuota como cualquier residente, pero además administra el edificio: puede generar
            códigos para inquilinos y ver todos los apartamentos.
          </div>
        )}

        <div className="detalle-info-grid">
          <div className="detalle-info-item">
            <span className="muted small">Estado de la cuenta</span>
            {cuenta.tipo_cuenta === "edificio_contenedor"
              ? <span className="pill" style={{ background: "#044a6e", color: "#fff" }}>Administración del edificio</span>
              : <span className={`pill ${cuenta.bloqueada ? "red" : "green"}`}>
                  {cuenta.bloqueada ? "Bloqueada por mora" : "Al día"}
                </span>}
          </div>
          {cuenta.tipo_cuenta !== "edificio_contenedor" && (
            <>
              <div className="detalle-info-item">
                <span className="muted small">Tarifa mensual</span>
                <b>{cuenta.tarifa ? `${cuenta.tarifa} — L ${cuenta.monto}` : "Sin tarifa"}</b>
              </div>
              <div className="detalle-info-item">
                <span className="muted small">Día de pago</span>
                <b>{cuenta.dia_pago ? `Día ${cuenta.dia_pago}` : "—"}</b>
              </div>
              <div className="detalle-info-item">
                <span className="muted small">Días de gracia</span>
                <b>{cuenta.dias_gracia != null ? `${cuenta.dias_gracia} día(s)` : "Global de la residencial"}</b>
              </div>
            </>
          )}
          <div className="detalle-info-item">
            <span className="muted small">Unidad</span>
            <b style={{ display: "flex", alignItems: "center", gap: 5 }}>
              {cuenta.unidad?.tipo === "edificio" ? <Building size={14} /> : <Home size={14} />}
              {cuenta.unidad?.identificador || cuenta.identificador} ({cuenta.unidad?.tipo === "edificio" ? "Edificio" : "Casa"})
            </b>
          </div>
          {cuenta.created_at && (
            <div className="detalle-info-item">
              <span className="muted small">Cuenta creada</span>
              <b>{new Date(cuenta.created_at).toLocaleDateString("es-HN")}</b>
            </div>
          )}
        </div>

        {/* Día 55 — editar la información de la casa. Solo para cuentas que
            pagan cuota (no el contenedor de edificio) y solo si el plan
            incluye cuotas. */}
        {cuenta.tipo_cuenta !== "edificio_contenedor" && permiteCuotas && !editando && (
          <button className="mini" style={{ marginTop: 4 }} onClick={() => {
            setEdTarifaId(cuenta.tarifa_id ?? 0);
            setEdDiaPago(cuenta.dia_pago?.toString() ?? "");
            setEdDiasGracia(cuenta.dias_gracia?.toString() ?? "");
            setEdIdentificador(cuenta.unidad?.identificador ?? cuenta.identificador ?? "");
            setErrEd(""); setEditando(true);
          }}>
            <Pencil size={13} style={{ marginRight: 5 }} /> Editar información
          </button>
        )}

        {editando && (
          <div className="editar-casa-card">
            <div className="editar-casa-head">
              <span className="editar-casa-head-icon"><Pencil size={15} /></span>
              <div>
                <b>Editar información de la casa</b>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Cambiar la tarifa afecta solo las cuotas <b>futuras</b>; las ya generadas conservan su monto.
                </p>
              </div>
            </div>
            <div className="editar-casa-grid">
              <label className="campo-moderno">
                <span className="campo-label">Tarifa mensual</span>
                <select value={edTarifaId} onChange={(e) => setEdTarifaId(Number(e.target.value))}>
                  <option value={0}>— Sin tarifa —</option>
                  {tarifasEd.map((t) => (
                    <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>
                  ))}
                </select>
              </label>
              <label className="campo-moderno">
                <span className="campo-label">Día de pago</span>
                <input type="number" min={1} max={28} value={edDiaPago}
                  onChange={(e) => setEdDiaPago(e.target.value)} />
              </label>
              <label className="campo-moderno">
                <span className="campo-label">Días de gracia</span>
                <input type="number" min={0} max={30} value={edDiasGracia}
                  placeholder="Global de la residencial"
                  onChange={(e) => setEdDiasGracia(e.target.value)} />
                <span className="campo-ayuda">Vacío = usa el valor global de la residencial.</span>
              </label>
              <label className="campo-moderno">
                <span className="campo-label">Identificador</span>
                <input type="text" value={edIdentificador}
                  onChange={(e) => setEdIdentificador(e.target.value)} />
              </label>
            </div>
            {errEd && <p className="err small" style={{ marginTop: 4 }}>{errEd}</p>}
            <div className="editar-casa-acciones">
              <button className="ghost" onClick={() => setEditando(false)} disabled={guardandoEd}>Cancelar</button>
              <button onClick={guardarEdicion} disabled={guardandoEd}>
                {guardandoEd ? "Guardando…" : "Guardar cambios"}
              </button>
            </div>
          </div>
        )}

        {/* Últimas cuotas: historial rápido (no aplica al contenedor de edificio) */}
        {cuenta.tipo_cuenta !== "edificio_contenedor" && cuenta.cuotas_recientes && cuenta.cuotas_recientes.length > 0 && (
          <>
            <div className="sub">Últimas cuotas</div>
            <div className="scroll-x"><table className="data">
              <thead><tr><th>Período</th><th>Monto</th><th>Vence</th><th>Estado</th></tr></thead>
              <tbody>
                {cuenta.cuotas_recientes.map((c, i) => (
                  <tr key={i}>
                    {/* Día 62 — bug real encontrado en producción: sin "T00:00:00",
                        new Date("2026-08-01") se interpreta como medianoche UTC.
                        Al mostrarla en hora de Honduras (UTC-6), retrocede al día
                        anterior -- y como es el 1° del mes, retrocede el MES
                        completo (agosto se mostraba como julio). Mismo patrón que
                        ya se usaba correctamente más abajo en este mismo archivo
                        (línea ~2035), pero acá faltaba. */}
                    <td>{new Date(c.periodo + "T00:00:00").toLocaleDateString("es-HN", { month: "short", year: "numeric" })}</td>
                    <td>L {c.monto.toFixed(2)}</td>
                    <td>{new Date(c.fecha_vencimiento + "T00:00:00").toLocaleDateString("es-HN")}</td>
                    <td>
                      <span className={`pill ${c.estado === "pagada" ? "green" : c.estado === "vencida" ? "red" : ""}`}>
                        {c.estado}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </>
        )}

        </>)}
        {/* ══════ FIN PESTAÑA DATOS ══════ */}

        {/* ══════ PESTAÑA: ACCESOS ══════ */}
        {tabDetalle === "accesos" && (<>

        {/* Configuraciones: cuenta activa + QR recurrente + límite de apartamentos (solo edificios) */}
        <div className="sub">Configuración</div>
        <div className="detalle-config-box">
          <div className="detalle-config-fila">
            <div>
              <b>QR recurrente</b>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                Permite a los residentes de esta cuenta generar códigos QR de visita recurrente.
              </p>
            </div>
            <label className="switch">
              <input type="checkbox" checked={qrRecurrente} disabled={guardandoQr}
                onChange={(e) => guardarQrRecurrente(e.target.checked)} />
              <span className="switch-slider" />
            </label>
          </div>

          {permiteControlFisico && (
          <div className="detalle-config-fila" style={{ marginTop: 10 }}>
            <div>
              <b>Acceso virtual (QR y Bluetooth)</b>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                Qué trancas puede abrir la tarjeta de acceso digital de los residentes
                de esta cuenta — igual criterio que las tarjetas físicas. Las cuentas
                con tarifa reducida suelen limitarse a peatonal.
              </p>
            </div>
            <div className="segmented" role="group" aria-label="Tipo de acceso virtual">
              <button
                type="button"
                className={tipoAccesoVirtual === "peatonal" ? "segmented-activo" : ""}
                disabled={guardandoTipoVirtual}
                onClick={() => guardarTipoAccesoVirtual("peatonal")}
              >
                Peatonal
              </button>
              <button
                type="button"
                className={tipoAccesoVirtual === "vehicular" ? "segmented-activo" : ""}
                disabled={guardandoTipoVirtual}
                onClick={() => guardarTipoAccesoVirtual("vehicular")}
              >
                Vehicular
              </button>
            </div>
          </div>
          )}

          {(cuenta.tipo_cuenta === "edificio_contenedor" || cuenta.tipo_cuenta === "edificio_admin") && (
            <div className="detalle-config-fila" style={{ marginTop: 10 }}>
              <div>
                <b>Límite de apartamentos</b>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Este edificio tiene {(cuenta.apartamentos?.length ?? 0) + (cuenta.tipo_cuenta === "edificio_admin" ? 1 : 0)} apartamento(s) registrado(s).
                  Cambiá el máximo si el edificio creció o se ajustó.
                </p>
              </div>
              <div className="row" style={{ maxWidth: 160 }}>
                <input type="number" min={1} max={200} placeholder="Sin límite"
                  value={maxAptos} onChange={(e) => setMaxAptos(e.target.value)} />
                <button className="btn-tabla btn-tabla-neutro" onClick={guardarMaxAptos} disabled={guardandoAptos}>
                  {guardandoAptos ? "…" : "Guardar"}
                </button>
              </div>
            </div>
          )}
          {msgConfig && <p className="muted small" style={{ marginTop: 6 }}>{msgConfig}</p>}
        </div>

        </>)}
        {/* ══════ FIN bloque Configuración de ACCESOS ══════ */}

        {/* ══════ PESTAÑA: MIEMBROS ══════ */}
        {tabDetalle === "miembros" && (<>

        {/* Lista de apartamentos bajo el edificio (contenedor o admin-residente) */}
        {(cuenta.tipo_cuenta === "edificio_contenedor" || cuenta.tipo_cuenta === "edificio_admin") && (
          <>
            <div className="sub">Apartamentos de este edificio ({cuenta.apartamentos?.length ?? 0})</div>
            {(cuenta.apartamentos?.length ?? 0) === 0 ? (
              <p className="muted small" style={{ padding: "8px 0" }}>
                Todavía no hay otros apartamentos registrados. Agregalos desde "Dar de alta" →
                seleccioná este edificio existente.
              </p>
            ) : (
              <div className="scroll-x"><table className="data">
                <thead><tr><th>Apartamento</th><th>Titular</th><th>Tarifa</th><th>Estado</th></tr></thead>
                <tbody>
                  {cuenta.apartamentos!.map((a) => (
                    <tr key={a.id}>
                      <td><b>{a.apartamento || "—"}</b></td>
                      <td>{a.titular}</td>
                      <td>{a.tarifa ? `${a.tarifa} (L ${a.monto})` : "—"}</td>
                      <td>
                        <span className={`pill ${a.bloqueada ? "red" : "green"}`}>
                          {a.bloqueada ? "Bloqueada" : a.estado}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </>
        )}

        {/* Residentes: para el contenedor solo el administrador; para casa/apto los residentes */}
        <div className="sub" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Users size={15} />
          {cuenta.tipo_cuenta === "edificio_contenedor" ? "Administrador del edificio"
            : cuenta.tipo_cuenta === "edificio_admin" ? "Residentes del apartamento del administrador"
            : "Residentes de la casa"}
        </div>
        <div className="residentes-lista">
          {(cuenta.residentes || []).map((r) => (
            <FilaResidente key={r.id} residente={r} cuentaId={cuenta.id} onActualizado={onCambio} />
          ))}
        </div>

        {miembroEnlace && (
          <div className="activacion-box">
            {miembroEnlace.url ? (
              <>
                <div className="activacion-titulo">Enlace de activación para miembro</div>
                <div className="activacion-url">{miembroEnlace.url}</div>
                <button className="mini" onClick={() => navigator.clipboard.writeText(miembroEnlace.url!)}>
                  Copiar enlace
                </button>
              </>
            ) : (
              <>
                <div className="activacion-titulo">✓ Miembro agregado exitosamente</div>
                <p>Le enviamos un correo a <b>{miembroEnlace.email}</b> con instrucciones para que defina su contraseña.</p>
              </>
            )}
          </div>
        )}

        {cuenta.tipo_cuenta !== "edificio_contenedor" && (
        <>
        <button className="toggle-agregar-miembro" onClick={() => setMostrarAgregar(v => !v)}>
          {mostrarAgregar ? "▲ Ocultar formulario" : "＋ Agregar nuevo miembro"}
        </button>

        {mostrarAgregar && (
        <div className="agregar-miembro-card">
          <div className="agregar-miembro-head">
            <span className="agregar-miembro-icon"><User size={16} /></span>
            <div>
              <h4>Agregar nuevo miembro</h4>
              <span className="muted small">Todos los campos marcados con * son obligatorios.</span>
            </div>
          </div>

          {msgMiembro && (
            <div className="msg-banner msg-banner-err" style={{ margin: "0 0 10px" }}>
              <span>⚠ {msgMiembro}</span>
              <button className="msg-banner-close" onClick={() => setMsgMiembro("")}>✕</button>
            </div>
          )}

          {/* Día 73 — verificación del correo antes de crear al miembro. */}
          {verificandoMiembro ? (
            <ConfirmacionEnvio
              email={mEmail.trim().toLowerCase()} nombre={mNombre.trim()}
              onConfirmado={agregarMiembroDeVerdad}
              onCorregir={() => {
                setVerificandoMiembro(false);
                setMErrors({ email: "Revisá este correo antes de seguir." });
              }}
              textoCreado={`${mNombre.trim()} quedó agregado a la casa.`}
              textoListo="Listo"
              onListo={terminarMiembro} />
          ) : (<>
          <div className="agregar-miembro-campos">
            {/* Día 73 — la foto va primero y no al final: es el campo que se
                olvida, y mandarla al fondo del formulario era garantizar
                que se saltara. */}
            <div className="campo-grupo">
              <label className="campo-label">Foto del miembro *</label>
              <span className="muted small" style={{ display: "block", textAlign: "left", marginBottom: 8 }}>
                Es la foto que ve el guardia para verificar a esta persona
                cuando llega sin teléfono.
              </span>
              <div className="campo-con-error">
                <CapturaFoto valor={mFoto} error={!!mErrors.foto}
                  onCambio={(f) => { setMFoto(f); if (f) clearMError("foto"); }} />
                {mErrors.foto && <span className="campo-error">{mErrors.foto}</span>}
              </div>
            </div>

            <div className="campo-grupo">
              <label className="campo-label">Datos básicos</label>
              <div className="row">
                <div className="campo-con-error">
                  <input placeholder="Nombre *" value={mNombre} className={mErrors.nombre ? "input-error" : ""}
                    onChange={(e) => { setMNombre(capitalizarNombre(e.target.value)); clearMError("nombre"); }} />
                  {mErrors.nombre && <span className="campo-error">{mErrors.nombre}</span>}
                </div>
                <div className="campo-con-error">
                  <input placeholder="Apellido *" value={mApellido} className={mErrors.apellido ? "input-error" : ""}
                    onChange={(e) => { setMApellido(capitalizarNombre(e.target.value)); clearMError("apellido"); }} />
                  {mErrors.apellido && <span className="campo-error">{mErrors.apellido}</span>}
                </div>
              </div>
              <div className="row">
                <div className="campo-con-error">
                  <input placeholder="Correo electrónico *" value={mEmail} className={mErrors.email ? "input-error" : ""}
                    onChange={(e) => { setMEmail(e.target.value); clearMError("email"); }} />
                  {mErrors.email && <span className="campo-error">{mErrors.email}</span>}
                </div>
                <div className="campo-con-error">
                  <input placeholder="Teléfono *" value={mTelefono} className={mErrors.telefono ? "input-error" : ""}
                    onChange={(e) => { setMTelefono(e.target.value); clearMError("telefono"); }} />
                  {mErrors.telefono && <span className="campo-error">{mErrors.telefono}</span>}
                </div>
              </div>
            </div>

            <div className="campo-grupo">
              <label className="campo-label">Identificación</label>
              <div className="row">
                <div className="campo-con-error">
                  <input placeholder="Identidad (0000-0000-00000) *" value={mDni} inputMode="numeric" maxLength={15}
                    className={mErrors.dni ? "input-error" : ""}
                    onChange={(e) => { setMDni(formatearDNI(e.target.value)); clearMError("dni"); }} />
                  {mErrors.dni && <span className="campo-error">{mErrors.dni}</span>}
                </div>
                <div className="campo-con-error">
                  <input placeholder="Profesión *" value={mProfesion} className={mErrors.profesion ? "input-error" : ""}
                    onChange={(e) => { setMProfesion(e.target.value); clearMError("profesion"); }} />
                  {mErrors.profesion && <span className="campo-error">{mErrors.profesion}</span>}
                </div>
              </div>
            </div>

            <div className="campo-grupo">
              <label className="campo-label">Contacto de emergencia</label>
              <div className="row">
                <div className="campo-con-error">
                  <input placeholder="Nombre del contacto *" value={mEmergNombre} className={mErrors.emergNombre ? "input-error" : ""}
                    onChange={(e) => { setMEmergNombre(capitalizarNombre(e.target.value)); clearMError("emergNombre"); }} />
                  {mErrors.emergNombre && <span className="campo-error">{mErrors.emergNombre}</span>}
                </div>
                <div className="campo-con-error">
                  <input placeholder="Teléfono del contacto *" value={mEmergTel} className={mErrors.emergTel ? "input-error" : ""}
                    onChange={(e) => { setMEmergTel(e.target.value); clearMError("emergTel"); }} />
                  {mErrors.emergTel && <span className="campo-error">{mErrors.emergTel}</span>}
                </div>
              </div>
            </div>
          </div>

          <button className="agregar-miembro-btn" onClick={addMiembro}>Verificar correo y agregar →</button>
          </>)}
        </div>
        )}
        </>
        )}

        </>)}
        {/* ══════ FIN PESTAÑA MIEMBROS ══════ */}

        {/* ══════ PESTAÑA: ACCESOS (parte 2 — tarjetas) ══════ */}
        {tabDetalle === "accesos" && permiteControlFisico && (<>

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
                    {t.tipo_acceso === "peatonal" ? "🚶 Peatonal" : "🚗 Vehicular"}
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

        </>)}
        {/* ══════ FIN PESTAÑA ACCESOS ══════ */}

        {msg && <div className="error">{msg}</div>}
      </div>
    </div>
  );
}

/**
 * Día 69 — foto del miembro, con captura y reemplazo.
 *
 * El patronato la pidió para la ficha del residente, y terminó siendo la
 * pieza del flujo del guardia: cuando alguien llega sin teléfono y da su
 * código de emergencia, esta es la cara contra la que el guardia compara
 * la identificación. Si falta, el guardia no tiene con qué verificar.
 *
 * Por eso el hueco vacío es un botón grande y visible con un "+" y no un
 * ícono discreto: que se note a quién le falta, sin tener que abrir nada.
 *
 * La captura es SOLO de administración. El residente la ve en su perfil
 * pero no la puede cambiar -- si pudiera, pondría la cara de cualquiera y
 * la verificación del guardia dejaría de servir.
 */
function FotoResidente({ residente, cuentaId, onActualizado }: {
  residente: ResidenteDTO; cuentaId: string; onActualizado: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const tiene = !!residente.foto_url;

  return (
    <>
      <button
        type="button"
        className={`foto-residente ${tiene ? "con-foto" : "sin-foto"}`}
        title={tiene ? `Ver o cambiar la foto de ${residente.nombre}`
                     : `Tomar la foto de ${residente.nombre}`}
        onClick={() => setAbierto(true)}
      >
        {tiene
          ? <img src={urlFotoResidente(residente.foto_url!)} alt={residente.nombre} />
          : <Camera size={15} />}
        {!tiene && <span className="foto-residente-mas">+</span>}
      </button>
      {abierto && (
        <ModalFotoResidente residente={residente} cuentaId={cuentaId}
          onCerrar={() => setAbierto(false)} onActualizado={onActualizado} />
      )}
    </>
  );
}

function FilaResidente({ residente, cuentaId, onActualizado }: {
  residente: ResidenteDTO; cuentaId: string; onActualizado: () => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const [editando, setEditando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState("");
  const [enlaceRegenerado, setEnlaceRegenerado] = useState<{ email: string; url?: string } | null>(null);
  const [procesando, setProcesando] = useState(false);

  // Campos editables (precargados con lo actual)
  const [f, setF] = useState({
    nombre: residente.nombre_solo || "",
    apellido: residente.apellido || "",
    // Día 72 — el correo se puede corregir. Es con el que la persona inicia
    // sesión y al que llega el enlace de activación, así que un correo mal
    // escrito en el alta dejaba la cuenta pendiente sin arreglo posible.
    email: residente.email || "",
    telefono: residente.telefono || "",
    dni: residente.dni || "",
    rtn: residente.rtn || "",
    direccion_exacta: residente.direccion_exacta || "",
    profesion: residente.profesion || "",
    contacto_emergencia_nombre: residente.contacto_emergencia_nombre || "",
    contacto_emergencia_telefono: residente.contacto_emergencia_telefono || "",
  });

  function set(campo: string, valor: string) { setF(prev => ({ ...prev, [campo]: valor })); }

  // Día 73 — al guardar un cambio de correo hay que hacer algo más, y
  // depende de si la persona ya activó su cuenta:
  //
  //   Pendiente → el enlace de activación viejo lleva el correo anterior
  //     adentro, así que al cambiarlo deja de servir solo. Si no se manda
  //     uno nuevo, esa persona queda sin forma de entrar y nadie se entera.
  //     Por eso se ofrece mandarlo en el momento, y no se da por hecho:
  //     puede ser que el admin esté corrigiendo un dato y prefiera avisarle
  //     por su cuenta.
  //
  //   Activa → no hay enlace que mandar; simplemente a partir de ahora
  //     inicia sesión con el correo nuevo. Se avisa para que el admin se lo
  //     diga, porque si no, la persona va a seguir intentando con el viejo.
  const [preguntaEnlace, setPreguntaEnlace] = useState<string | null>(null);

  async function guardar() {
    if (!residente.usuario_id) { setMsg("No se puede editar este residente"); return; }
    const correoNuevo = f.email.trim().toLowerCase();
    const cambioCorreo = correoNuevo !== (residente.email || "").toLowerCase();
    setGuardando(true); setMsg("");
    try {
      await editarUsuario(residente.usuario_id, f);
      setEditando(false);
      onActualizado();
      if (cambioCorreo) {
        if (esPendiente) {
          setPreguntaEnlace(correoNuevo);
        } else {
          setMsg(`Correo actualizado. ${residente.nombre} ahora inicia sesión `
            + `con ${correoNuevo}: avisale del cambio.`);
        }
      }
    } catch (e) { setMsg((e as Error).message); }
    finally { setGuardando(false); }
  }

  async function enviarEnlaceAlCorreoNuevo() {
    setPreguntaEnlace(null);
    await handleRegenerar();
  }

  async function handleQuitar() {
    const nombre = residente.nombre || "este miembro";
    if (!confirm(`¿Quitar a ${nombre} de esta cuenta?\n\nSe eliminará su acceso y su usuario. Esta acción no se puede deshacer.`)) return;
    setProcesando(true);
    try {
      await quitarMiembro(cuentaId, residente.id);
      onActualizado();
    } catch (e) { setMsg((e as Error).message); }
    finally { setProcesando(false); }
  }

  async function handleRegenerar() {
    setProcesando(true); setMsg(""); setEnlaceRegenerado(null);
    try {
      const res = await regenerarEnlace(cuentaId, residente.id);
      const token = res.activacion.token_activacion;
      setEnlaceRegenerado({
        email: res.activacion.usuario_email,
        url: token ? `${window.location.origin}/?activar=${token}` : undefined,
      });
    } catch (e) { setMsg((e as Error).message); }
    finally { setProcesando(false); }
  }

  const esPendiente = residente.estado_acceso === "pendiente";

  const Dato = ({ label, valor }: { label: string; valor?: string }) => (
    <div className="dato-item">
      <span className="muted small">{label}</span>
      <span>{valor || <span className="muted">—</span>}</span>
    </div>
  );

  return (
    <div className={`residente-fila ${esPendiente ? "residente-pendiente" : ""}`}>
      <div className="residente-cabecera">
        {/* Día 69 — la foto del miembro, pedido del patronato. Va en la
            CABECERA y no escondida en el detalle: es lo que el guardia ve
            en el portón para verificar identidad, así que administración
            tiene que notar de un vistazo a quién le falta. */}
        <FotoResidente residente={residente} cuentaId={cuentaId} onActualizado={onActualizado} />
        <span className="residente-nombre">{residente.nombre}</span>
        <span className="pill">{residente.rol_cuenta}</span>
        <span className="muted small">{residente.relacion}</span>
        {/* Día 72 — si Resend avisó que el correo rebotó, se muestra acá:
            es la única pista de que la cuenta no se activa porque la
            dirección está mal escrita, no porque la persona no quiera.
            Día 73 — ahora se muestran TODOS los estados, no solo el
            rebote: saber que el correo se entregó contesta la pregunta de
            "¿le llegó el enlace?" sin tener que llamar a la persona. */}
        <EstadoCorreo estado={residente.correo_estado} detalle={residente.correo_detalle}
          actualizado={residente.correo_actualizado} email={residente.email} />
        {esPendiente ? (
          <span className="pill-estado pill-estado--pendiente">
            <Clock size={12} /> Pendiente
          </span>
        ) : (
          <span className="pill-estado pill-estado--activo">
            <CheckCircle size={12} /> Activo
          </span>
        )}
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

              <div className="residente-acciones">
                <button className="mini" onClick={() => setEditando(true)}>
                  <Pencil size={14} /> Editar
                </button>

                {esPendiente && (
                  <span className="accion-con-ayuda">
                    <button className="mini btn-regenerar" onClick={handleRegenerar} disabled={procesando}>
                      <RefreshCw size={14} /> {procesando ? "Generando…" : "Regenerar enlace"}
                    </button>
                    <InfoTip texto={`${residente.nombre} todavía no activó su cuenta. Esto crea un enlace de activación nuevo y le vuelve a enviar el correo; el enlace anterior deja de servir. Útil si el correo no llegó o si ya venció (dura 48 horas).`} />
                  </span>
                )}

                {residente.rol_cuenta === "miembro" && (
                  <button className="mini btn-quitar-miembro" onClick={handleQuitar} disabled={procesando}>
                    <Trash2 size={14} /> Quitar miembro
                  </button>
                )}
              </div>

              {preguntaEnlace && (
                <div className="pregunta-enlace">
                  <div className="pregunta-enlace-texto">
                    <b>Correo actualizado.</b> El enlace de activación anterior dejó de
                    servir porque llevaba el correo viejo. ¿Le enviamos uno nuevo
                    a <b>{preguntaEnlace}</b>?
                  </div>
                  <div className="row-btns">
                    <button className="mini" onClick={enviarEnlaceAlCorreoNuevo} disabled={procesando}>
                      <RefreshCw size={14} /> {procesando ? "Enviando…" : "Enviar enlace"}
                    </button>
                    <button className="ghost mini" onClick={() => setPreguntaEnlace(null)}>
                      Ahora no
                    </button>
                  </div>
                </div>
              )}

              {enlaceRegenerado && (
                <div className="activacion-box" style={{ marginTop: 10 }}>
                  <div className="activacion-titulo">Nuevo enlace de activación (48h)</div>
                  {enlaceRegenerado.url ? (
                    <>
                      <p className="muted small">Compartí este enlace con <b>{enlaceRegenerado.email}</b>:</p>
                      <div className="activacion-url">{enlaceRegenerado.url}</div>
                      <button className="mini" onClick={() => navigator.clipboard.writeText(enlaceRegenerado.url!)}>
                        Copiar enlace
                      </button>
                    </>
                  ) : (
                    <p className="muted small">Se envió un nuevo enlace a <b>{enlaceRegenerado.email}</b> por correo.</p>
                  )}
                </div>
              )}

              {msg && <div className="error" style={{ marginTop: 8 }}>{msg}</div>}
            </>
          ) : (
            <div className="datos-editar">
              <div className="row">
                <input placeholder="Nombre" value={f.nombre} onChange={e => set("nombre", capitalizarNombre(e.target.value))} />
                <input placeholder="Apellido" value={f.apellido} onChange={e => set("apellido", capitalizarNombre(e.target.value))} />
              </div>
              <div className="campo-con-error">
                <input placeholder="Correo electrónico" type="email" value={f.email}
                  onChange={e => set("email", e.target.value)} />
                {f.email.trim().toLowerCase() !== (residente.email || "").toLowerCase() && (
                  <span className="muted small" style={{ textAlign: "left", display: "block", marginTop: 4 }}>
                    {esPendiente
                      ? "Al guardar, tocá “Regenerar enlace” para que el correo de activación salga a esta dirección nueva."
                      : "Esta persona va a iniciar sesión con el correo nuevo."}
                  </span>
                )}
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
  const [errorPlan, setErrorPlan] = useState("");

  function cargar() {
    setCargando(true);
    listarTarifas().then(setTarifas)
      .catch((e) => setErrorPlan(e?.message || "")).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;

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

/* ═══════════════════════════════════════════════════════════════════
   PESTAÑA: SOLICITUDES DE BAJA
   ═══════════════════════════════════════════════════════════════════ */
function SolicitudesBajaPanel({ onCambio }: { onCambio: () => void }) {
  const [solicitudes, setSolicitudes] = useState<SolicitudBajaDTO[]>([]);
  const [filtro, setFiltro] = useState("pendiente");
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);

  async function cargar() {
    setCargando(true);
    try { setSolicitudes(await listarSolicitudesBaja(filtro)); }
    catch { setSolicitudes([]); }
    finally { setCargando(false); }
  }
  useEffect(() => { cargar(); }, [filtro]);

  async function nivelar(s: SolicitudBajaDTO) {
    if (!confirm(
      `Nivelar saldo de Apto ${s.apartamento} (${s.edificio}) al ${new Date(s.fecha_desocupacion).toLocaleDateString("es-HN")}?\n\n` +
      `La última cuota pendiente se recalculará para cobrar solo los días ocupados hasta la fecha de desocupación.`
    )) return;
    setProcesando(s.id); setMsg(null);
    try {
      const res = await nivelarSaldo(s.cuenta_id, s.fecha_desocupacion);
      const detalle = res.ajustes.map(a =>
        a.accion === "anulada"
          ? `${a.periodo}: anulada (era L ${a.monto_original.toFixed(2)})`
          : `${a.periodo}: ${a.dias_ocupados} días → L ${a.monto_final.toFixed(2)} (era L ${a.monto_original.toFixed(2)})`
      ).join(" · ");
      setMsg({ tipo: "ok", texto: `Saldo nivelado. ${detalle}. Ahora registrá el pago en Caja si queda monto, y luego aprobá la baja.` });
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
    finally { setProcesando(null); }
  }

  async function resolver(s: SolicitudBajaDTO, accion: string) {
    let respuesta: string | undefined;
    if (accion === "rechazar") {
      respuesta = prompt("Motivo del rechazo:") || undefined;
      if (!respuesta) return;
    } else {
      if (!confirm(
        `¿Aprobar la baja de Apto ${s.apartamento} en ${s.edificio}?\n\n` +
        `Se verificará que el saldo esté en 0, se dará de baja la cuenta de ${s.titular}, ` +
        `se suspenderá su acceso a crear QR y se desactivarán sus tarjetas.`
      )) return;
    }
    setProcesando(s.id); setMsg(null);
    try {
      await resolverSolicitudBaja(s.id, accion, respuesta);
      setMsg({ tipo: "ok", texto: accion === "aprobar" ? "Baja aprobada y ejecutada." : "Solicitud rechazada." });
      cargar(); onCambio();
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
    finally { setProcesando(null); }
  }

  return (
    <div style={{ marginTop: 14 }}>
      <div className="lista-toolbar">
        <select value={filtro} onChange={e => setFiltro(e.target.value)} className="periodo-select">
          <option value="pendiente">Pendientes</option>
          <option value="aprobada">Aprobadas</option>
          <option value="rechazada">Rechazadas</option>
          <option value="todas">Todas</option>
        </select>
        <span className="muted small">{solicitudes.length} solicitud{solicitudes.length !== 1 ? "es" : ""}</span>
      </div>

      {msg && (
        <div className={`msg-banner ${msg.tipo === "ok" ? "msg-banner-ok" : "msg-banner-err"}`} style={{ margin: "10px 0" }}>
          <span>{msg.tipo === "ok" ? "✓" : "⚠"} {msg.texto}</span>
          <button className="msg-banner-close" onClick={() => setMsg(null)}>✕</button>
        </div>
      )}

      {cargando ? (
        <p className="muted" style={{ padding: 20 }}>Cargando…</p>
      ) : solicitudes.length === 0 ? (
        <p className="muted" style={{ padding: 20, textAlign: "center" }}>
          No hay solicitudes {filtro !== "todas" ? `en estado "${filtro}"` : ""}.
        </p>
      ) : (
        <div className="solicitudes-grid">
          {solicitudes.map(s => (
            <div key={s.id} className={`solicitud-card solicitud-card--${s.estado}`}>
              <div className="solicitud-card-head">
                <div>
                  <b>{s.edificio} · Apto {s.apartamento}</b>
                  <div className="muted small">Titular: {s.titular || "—"}</div>
                </div>
                <span className={`pill-estado ${
                  s.estado === "pendiente" ? "pill-estado--pendiente"
                  : s.estado === "aprobada" ? "pill-estado--activo" : "pill-estado--mora"}`}>
                  {s.estado}
                </span>
              </div>

              <div className="solicitud-card-body">
                <div className="dato-item">
                  <span className="muted small">Solicitó</span>
                  <span>{s.solicitada_por} · {new Date(s.created_at).toLocaleDateString("es-HN")}</span>
                </div>
                <div className="dato-item">
                  <span className="muted small">Motivo</span>
                  <span>{s.motivo}</span>
                </div>
                <div className="dato-item">
                  <span className="muted small">Fecha de desocupación</span>
                  <span><b>{new Date(s.fecha_desocupacion).toLocaleDateString("es-HN")}</b></span>
                </div>
                {s.respuesta_admin && (
                  <div className="dato-item">
                    <span className="muted small">Respuesta admin</span>
                    <span>{s.respuesta_admin}</span>
                  </div>
                )}
              </div>

              {s.estado === "pendiente" && (
                <div className="solicitud-card-acciones">
                  <button className="btn-tabla btn-tabla-editar" disabled={procesando === s.id}
                    onClick={() => nivelar(s)} title="Prorratear la última cuota a los días ocupados">
                    ⚖ Nivelar saldo
                  </button>
                  <button className="btn-tabla btn-tabla-ok" disabled={procesando === s.id}
                    onClick={() => resolver(s, "aprobar")}>
                    ✓ Aprobar baja
                  </button>
                  <button className="btn-tabla btn-tabla-baja" disabled={procesando === s.id}
                    onClick={() => resolver(s, "rechazar")}>
                    ✕ Rechazar
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* Día 75 — el modal de salida del sistema vive en ./SalidaSistema.tsx */
