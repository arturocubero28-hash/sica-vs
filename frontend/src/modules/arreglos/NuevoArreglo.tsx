import { useEffect, useMemo, useState } from "react";
import {
  Home, Check, AlertTriangle, ArrowLeft, Search, Handshake, Scale, Lock,
  CalendarDays, Info, Ban, ShieldCheck, Wallet,
} from "lucide-react";
import {
  listarCuentas, cuotasPendientesCuenta, crearArreglo,
  type Cuenta, type CuotaDTO, type PropositoArreglo, type ArregloDTO,
} from "../../api/client";
import { Aviso } from "../unidades/SalidaSistema";

/* ═══════════════════════════════════════════════════════════════════════
   Día 75 — NUEVO ARREGLO DE PAGO, paso a paso.

   Mismo lenguaje visual que «Salida del sistema» (SalidaSistema.tsx):

     Casa → Para qué → Cuotas → Plan → Confirmar → Listo

   La pieza central es el CALENDARIO DE ABONOS, que se dibuja en vivo
   mientras se arma el plan: cada abono con su fecha y su monto. Se calcula
   igual que el backend (api/arreglos.py): la prima vence hoy, los abonos
   cada «intervalo» días desde hoy, el último absorbe el redondeo.
   ═══════════════════════════════════════════════════════════════════════ */

type Paso = "casa" | "para" | "cuotas" | "plan" | "confirmar" | "listo";
const PASOS: { id: Paso; nombre: string }[] = [
  { id: "casa", nombre: "Casa" },
  { id: "para", nombre: "Para qué" },
  { id: "cuotas", nombre: "Cuotas" },
  { id: "plan", nombre: "Plan" },
  { id: "confirmar", nombre: "Confirmar" },
];

const L = (n: number) =>
  `L ${n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const hoyLocal = () => new Date().toLocaleDateString("en-CA");
const fechaCorta = (d: Date) => d.toLocaleDateString("es-HN", { day: "numeric", month: "short", year: "numeric" });
const redondear = (n: number) => Math.round(n * 100) / 100;

const FRECUENCIAS = [
  { dias: 30, nombre: "Mensual" },
  { dias: 15, nombre: "Quincenal" },
  { dias: 7, nombre: "Semanal" },
];
const CANTIDADES = [2, 3, 6, 12];

export function NuevoArreglo({ onCreado, onCancelar }: {
  onCreado: (a: ArregloDTO) => void; onCancelar: () => void;
}) {
  const [paso, setPaso] = useState<Paso>("casa");
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [cuenta, setCuenta] = useState<Cuenta | null>(null);
  const [cuotas, setCuotas] = useState<CuotaDTO[] | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [proposito, setProposito] = useState<PropositoArreglo | "">("");

  const [prima, setPrima] = useState(0);
  const [numAbonos, setNumAbonos] = useState(3);
  const [intervalo, setIntervalo] = useState(30);
  const [gracia, setGracia] = useState(15);
  const [nota, setNota] = useState("");
  const [conDescuento, setConDescuento] = useState(false);
  const [pct, setPct] = useState(0);
  const [autEmail, setAutEmail] = useState("");
  const [autPass, setAutPass] = useState("");

  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [creado, setCreado] = useState<ArregloDTO | null>(null);

  useEffect(() => { listarCuentas().then(setCuentas).catch(() => setCuentas([])); }, []);

  const enPadron = !!cuenta?.es_censo;
  const nombreCasa = cuenta ? (cuenta.identificador || (cuenta.apartamento ? `Apto ${cuenta.apartamento}` : "Casa")) : "";

  // ── Casa ──────────────────────────────────────────────────────────────
  const lista = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return cuentas
      .filter(c => !q || `${c.identificador || ""} ${c.apartamento || ""} ${c.titular?.nombre || ""}`.toLowerCase().includes(q))
      .sort((a, b) => (b.cuotas_pendientes || 0) - (a.cuotas_pendientes || 0));
  }, [cuentas, busqueda]);

  function elegirCasa(c: Cuenta) {
    setCuenta(c); setCuotas(null); setSel([]); setError("");
    setProposito(c.es_censo ? "volver_al_padron" : "");
    cuotasPendientesCuenta(c.id).then(setCuotas).catch(() => setCuotas([]));
    setPaso("para");
  }

  // ── Cuotas ────────────────────────────────────────────────────────────
  // Para volver al padrón, la cuota que todavía no vence NO va en el arreglo:
  // al salir se cobra solo por los días que la casa estuvo (Día 75).
  const hoy = hoyLocal();
  const noVence = (c: CuotaDTO) => c.fecha_vencimiento >= hoy;
  const excluida = (c: CuotaDTO) => proposito === "volver_al_padron" && noVence(c);
  const elegibles = (cuotas || []).filter(c => !excluida(c));
  useEffect(() => {
    // Al entrar a cuotas: marcar las elegibles. Al cambiar el propósito, sacar las excluidas.
    if (cuotas) setSel(s => s.length ? s.filter(id => elegibles.some(c => c.id === id)) : elegibles.map(c => c.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cuotas, proposito]);

  // ── Plan (mismo cálculo que el backend) ──────────────────────────────
  const deudaOriginal = redondear((cuotas || []).filter(c => sel.includes(c.id)).reduce((t, c) => t + c.monto, 0));
  const pctValido = conDescuento ? Math.min(Math.max(pct || 0, 0), 99.99) : 0;
  const descuento = redondear(deudaOriginal * pctValido / 100);
  const deuda = redondear(deudaOriginal - descuento);
  const financiado = redondear(Math.max(0, deuda - prima));
  const calendario = useMemo(() => {
    const filas: { n: number; fecha: Date; monto: number; prima?: boolean }[] = [];
    const base = new Date(hoy + "T00:00:00");
    let n = 1;
    if (prima > 0) filas.push({ n: n++, fecha: base, monto: prima, prima: true });
    const montoBase = redondear(financiado / Math.max(numAbonos, 1));
    let acumulado = 0;
    for (let i = 1; i <= numAbonos; i++) {
      const m = i < numAbonos ? montoBase : redondear(financiado - acumulado);
      if (i < numAbonos) acumulado = redondear(acumulado + montoBase);
      const f = new Date(base); f.setDate(f.getDate() + intervalo * i);
      filas.push({ n: n++, fecha: f, monto: m });
    }
    return filas;
  }, [prima, financiado, numAbonos, intervalo, hoy]);
  const montoAbono = calendario.find(f => !f.prima)?.monto ?? 0;

  const errorPlan =
    numAbonos < 1 || numAbonos > 36 ? "El número de abonos va de 1 a 36."
    : intervalo < 1 || intervalo > 90 ? "El intervalo entre abonos va de 1 a 90 días."
    : gracia < 1 || gracia > 90 ? "Los días de gracia van de 1 a 90."
    : prima < 0 ? "La prima no puede ser negativa."
    : financiado <= 0 ? "La prima cubre toda la deuda: no hace falta un arreglo, se cobran las cuotas en caja."
    : conDescuento && !(pct > 0 && pct < 100) ? "El descuento tiene que ser mayor que 0 y menor que 100 %."
    : conDescuento && (!autEmail.trim() || !autPass) ? "Falta el correo o la contraseña del administrador que autoriza el descuento."
    : "";

  async function crear() {
    setGuardando(true); setError("");
    try {
      const a = await crearArreglo({
        cuenta_id: cuenta!.id, cuotas: sel, abono_inicial: prima, num_abonos: numAbonos,
        dias_gracia: gracia, intervalo_dias: intervalo, nota, proposito: proposito as PropositoArreglo,
        ...(conDescuento ? { descuento_pct: pct, autorizacion: { email: autEmail.trim(), password: autPass } } : {}),
      });
      setAutPass("");
      setCreado(a); setPaso("listo");
    } catch (e) {
      setError((e as Error).message);
      setAutPass("");   // nunca dejar la contraseña de otro en pantalla
    } finally { setGuardando(false); }
  }

  // ── Navegación ────────────────────────────────────────────────────────
  const orden: Paso[] = ["casa", "para", "cuotas", "plan", "confirmar"];
  const iPaso = orden.indexOf(paso);
  const puedeSeguir =
    paso === "para" ? !!proposito
    : paso === "cuotas" ? sel.length > 0
    : paso === "plan" ? !errorPlan
    : false;
  function atras() { setError(""); setPaso(orden[Math.max(0, iPaso - 1)]); }
  function seguir() { setError(""); setPaso(orden[iPaso + 1]); }

  return (
    <div className="sal-modal sal-pagina arr">
      <header className="sal-cabeza">
        <div>
          <h2>{paso === "listo" ? "Arreglo creado" : cuenta ? `Nuevo arreglo de pago · ${nombreCasa}` : "Nuevo arreglo de pago"}</h2>
          <p>{cuenta?.titular?.nombre ? `Titular: ${cuenta.titular.nombre}`
            : "Un plan para pagar en abonos las cuotas atrasadas de una casa."}</p>
        </div>
      </header>

      {paso !== "listo" && (
        <ol className="sal-pasos" aria-label="Pasos">
          {PASOS.map((p, i) => (
            <li key={p.id} className={i < iPaso ? "hecho" : i === iPaso ? "actual" : ""}
              aria-current={i === iPaso ? "step" : undefined}>
              <span className="sal-pasos-num">{i < iPaso ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
              <span className="sal-pasos-nombre">{p.nombre}</span>
            </li>
          ))}
        </ol>
      )}

      <div className="sal-cuerpo" key={paso}>
        {/* ── 1. Casa ─────────────────────────────────────────────────── */}
        {paso === "casa" && (
          <>
            <h3 className="sal-pregunta">¿Para qué casa es el arreglo?</h3>
            <div className="sal-input-icono">
              <Search size={16} />
              <input className="arr-buscar" value={busqueda} autoFocus
                placeholder="Buscar por casa o por titular" onChange={e => setBusqueda(e.target.value)} />
            </div>
            <div className="arr-casas" role="listbox" aria-label="Casas">
              {lista.length === 0 && <p className="sal-pie-nota">Ninguna casa coincide con «{busqueda}».</p>}
              {lista.slice(0, 60).map(c => {
                const n = c.cuotas_pendientes || 0;
                return (
                  <button key={c.id} role="option" aria-selected={cuenta?.id === c.id}
                    className={`arr-casa ${n === 0 ? "arr-casa--sin" : ""}`} onClick={() => elegirCasa(c)}>
                    <span className="arr-casa-icono"><Home size={18} /></span>
                    <span className="arr-casa-texto">
                      <b>{c.identificador || (c.apartamento ? `Apto ${c.apartamento}` : "Casa")}</b>
                      <span>{c.titular?.nombre || "Sin titular"}{c.es_censo ? " · En el padrón" : ""}</span>
                    </span>
                    <span className={`arr-casa-deuda ${n > 0 ? "con" : ""}`}>
                      {n === 0 ? "Sin cuotas pendientes" : n === 1 ? "1 cuota pendiente" : `${n} cuotas pendientes`}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* ── 2. Para qué ─────────────────────────────────────────────── */}
        {paso === "para" && (
          <>
            <h3 className="sal-pregunta">¿Para qué se firma?</h3>
            {enPadron ? (
              <Aviso tono="info" icono={<Info size={22} />} titulo="La casa ya está en el padrón">
                <p>No tiene mensualidad que retomar: el arreglo es para saldar lo que dejó pendiente.
                  Los abonos se pagan en caja.</p>
              </Aviso>
            ) : (
              <div className="sal-caminos">
                <button className={`sal-camino ${proposito === "ponerse_al_dia" ? "sel" : ""}`}
                  aria-pressed={proposito === "ponerse_al_dia"} onClick={() => { setProposito("ponerse_al_dia"); setPaso("cuotas"); }}>
                  <span className="sal-camino-icono"><Handshake size={22} /></span>
                  <b>Ponerse al día y seguir pagando</b>
                  <ul>
                    <li>Paga lo atrasado en abonos</li>
                    <li>Sigue con su cuota de cada mes</li>
                    <li>Se le desbloquea el acceso hoy</li>
                  </ul>
                </button>
                <button className={`sal-camino ${proposito === "volver_al_padron" ? "sel" : ""}`}
                  aria-pressed={proposito === "volver_al_padron"} onClick={() => { setProposito("volver_al_padron"); setPaso("cuotas"); }}>
                  <span className="sal-camino-icono sal-camino-icono--mudanza"><Home size={22} /></span>
                  <b>Saldar la deuda y volver al padrón</b>
                  <ul>
                    <li>Paga lo atrasado en abonos</li>
                    <li>Deja de pagar mensualidad</li>
                    <li>Ya puede pasar al padrón con deuda</li>
                  </ul>
                </button>
              </div>
            )}
          </>
        )}

        {/* ── 3. Cuotas ───────────────────────────────────────────────── */}
        {paso === "cuotas" && (
          <>
            <h3 className="sal-pregunta">¿Qué cuotas entran en el arreglo?</h3>
            {cuotas === null && <div className="sal-cargando">Cargando cuotas…</div>}
            {cuotas && cuotas.length === 0 && (
              <Aviso tono="ok" icono={<Check size={22} />} titulo="Esta casa no debe nada">
                <p>No tiene cuotas pendientes, así que no necesita un arreglo.</p>
              </Aviso>
            )}
            {cuotas && cuotas.length > 0 && elegibles.length === 0 && (
              <Aviso tono="info" icono={<Info size={22} />} titulo="No necesita un arreglo para volver al padrón">
                <p>Su única cuota todavía no vence. Al volver al padrón se cobra solo por los días que la
                  casa estuvo, y se paga en caja antes de salir. Hacelo directo desde
                  <b> Casas y residentes → Salida del sistema</b>.</p>
              </Aviso>
            )}
            {cuotas && cuotas.length > 0 && (
              <div className="arr-cuotas">
                {cuotas.map(c => {
                  const fuera = excluida(c);
                  const marcada = !fuera && sel.includes(c.id);
                  return (
                    <label key={c.id} className={`arr-cuota ${marcada ? "sel" : ""} ${fuera ? "fuera" : ""}`}>
                      <input type="checkbox" checked={marcada} disabled={fuera}
                        onChange={() => setSel(s => s.includes(c.id) ? s.filter(x => x !== c.id) : [...s, c.id])} />
                      <span className="arr-cuota-mes">{c.mes_label}</span>
                      <span className={`arr-cuota-estado ${noVence(c) ? "" : "vencida"}`}>
                        {fuera ? "Aún no vence · no va en el arreglo"
                          : noVence(c) ? `Vence el ${fechaCorta(new Date(c.fecha_vencimiento + "T00:00:00"))}`
                          : `Vencida desde el ${fechaCorta(new Date(c.fecha_vencimiento + "T00:00:00"))}`}
                      </span>
                      <span className="arr-cuota-monto">{L(c.monto)}</span>
                    </label>
                  );
                })}
              </div>
            )}
            {sel.length > 0 && (
              <div className="arr-total">
                <span>{sel.length === 1 ? "1 cuota" : `${sel.length} cuotas`} en el arreglo</span>
                <b>{L(deudaOriginal)}</b>
              </div>
            )}
          </>
        )}

        {/* ── 4. Plan ─────────────────────────────────────────────────── */}
        {paso === "plan" && (
          <>
            <div className="arr-plan">
              <div className="arr-plan-campos">
                <label className="sal-campo">
                  <span>Prima (pago inicial, vence hoy)</span>
                  <div className="arr-input-lps">
                    <i>L</i>
                    <input type="number" min={0} step="0.01" value={prima || ""} placeholder="0.00"
                      onChange={e => setPrima(Math.max(0, Number(e.target.value)))} />
                  </div>
                  <small>Dejala en 0 si no hay prima.</small>
                </label>

                <div className="sal-campo">
                  <span>Cantidad de abonos</span>
                  <div className="arr-chips">
                    {CANTIDADES.map(n => (
                      <button key={n} className={`arr-chip ${numAbonos === n ? "sel" : ""}`}
                        aria-pressed={numAbonos === n} onClick={() => setNumAbonos(n)}>{n}</button>
                    ))}
                    <input type="number" min={1} max={36} aria-label="Otra cantidad" placeholder="Otra"
                      value={CANTIDADES.includes(numAbonos) ? "" : numAbonos}
                      className={`arr-chip-input ${CANTIDADES.includes(numAbonos) ? "" : "sel"}`}
                      onChange={e => setNumAbonos(e.target.value === "" ? 3 : Number(e.target.value))} />
                  </div>
                </div>

                <div className="sal-campo">
                  <span>Cada cuánto</span>
                  <div className="arr-chips">
                    {FRECUENCIAS.map(f => (
                      <button key={f.dias} className={`arr-chip ${intervalo === f.dias ? "sel" : ""}`}
                        aria-pressed={intervalo === f.dias} onClick={() => setIntervalo(f.dias)}>{f.nombre}</button>
                    ))}
                    <span className="arr-chip-otro">
                      Cada <input type="number" min={1} max={90} aria-label="Cada cuántos días" placeholder="—"
                        value={FRECUENCIAS.some(f => f.dias === intervalo) ? "" : intervalo}
                        className={`arr-chip-input ${FRECUENCIAS.some(f => f.dias === intervalo) ? "" : "sel"}`}
                        onChange={e => setIntervalo(e.target.value === "" ? 30 : Number(e.target.value))} /> días
                    </span>
                  </div>
                </div>

                <label className="sal-campo">
                  <span>Días de gracia por abono</span>
                  <input type="number" min={1} max={90} value={gracia} onChange={e => setGracia(Number(e.target.value))}
                    className="arr-corto" />
                  <small>Si un abono se atrasa más que esto, el arreglo queda incumplido.</small>
                </label>
              </div>

              {/* El calendario, en vivo */}
              <aside className="arr-calendario" aria-live="polite">
                <div className="arr-calendario-cabeza">
                  <span>{numAbonos === 1 ? "1 abono de" : `${numAbonos} abonos de`}</span>
                  <b>{L(montoAbono)}</b>
                  {prima > 0 && <small>más una prima de {L(prima)} hoy</small>}
                </div>
                <ol className="arr-abonos">
                  {calendario.map(f => (
                    <li key={f.n} className={f.prima ? "prima" : ""}>
                      <span className="arr-abono-n">{f.n}</span>
                      <span className="arr-abono-fecha">{f.prima ? "Hoy" : fechaCorta(f.fecha)}</span>
                      <span className="arr-abono-monto">{L(f.monto)}</span>
                    </li>
                  ))}
                </ol>
                <dl className="arr-cuentas">
                  <div><dt>Deuda de las cuotas</dt><dd>{L(deudaOriginal)}</dd></div>
                  {descuento > 0 && <div className="desc"><dt>Descuento ({pctValido} %)</dt><dd>− {L(descuento)}</dd></div>}
                  {prima > 0 && <div><dt>Prima</dt><dd>− {L(prima)}</dd></div>}
                  <div className="total"><dt>En abonos</dt><dd>{L(financiado)}</dd></div>
                </dl>
                <p className="arr-sin-recargo">Sin recargo: solo se difiere la deuda.</p>
              </aside>
            </div>

            {/* Descuento: autorización de un segundo administrador */}
            <section className={`arr-descuento ${conDescuento ? "abierto" : ""}`}>
              <label className="sal-check">
                <input type="checkbox" checked={conDescuento}
                  onChange={e => { setConDescuento(e.target.checked); if (!e.target.checked) { setAutPass(""); setPct(0); } }} />
                <span><b>Aplicar un descuento sobre la deuda</b></span>
              </label>
              {conDescuento && (
                <>
                  <div className="arr-descuento-explica">
                    <ShieldCheck size={18} />
                    <p>Lo autoriza <b>otro administrador</b>, escribiendo acá su correo y su contraseña.
                      Queda registrado quién lo autorizó y cuándo.</p>
                  </div>
                  <div className="arr-descuento-campos">
                    <label className="sal-campo">
                      <span>Descuento</span>
                      <div className="arr-input-lps arr-input-lps--pct">
                        <input type="number" min={0.01} max={99.99} step="0.01" value={pct || ""}
                          onChange={e => setPct(Number(e.target.value))} />
                        <i>%</i>
                      </div>
                    </label>
                    <label className="sal-campo sal-campo--ancho">
                      <span>Correo del administrador que autoriza</span>
                      <input type="email" autoComplete="off" value={autEmail} onChange={e => setAutEmail(e.target.value)} />
                    </label>
                    <label className="sal-campo sal-campo--ancho">
                      <span>Su contraseña</span>
                      <div className="sal-input-icono">
                        <Lock size={15} />
                        <input type="password" autoComplete="new-password" value={autPass}
                          onChange={e => setAutPass(e.target.value)} />
                      </div>
                    </label>
                  </div>
                </>
              )}
            </section>

            <label className="sal-campo">
              <span>Nota (opcional)</span>
              <input value={nota} placeholder="Acordado con el titular en la oficina" onChange={e => setNota(e.target.value)} />
            </label>
            {errorPlan && <p className="arr-aviso-campo"><AlertTriangle size={15} /> {errorPlan}</p>}
          </>
        )}

        {/* ── 5. Confirmar ────────────────────────────────────────────── */}
        {paso === "confirmar" && cuenta && (
          <>
            <Aviso tono="info" icono={<Handshake size={24} />}
              titulo={numAbonos === 1 ? "1 abono de" : `${numAbonos} abonos de`} monto={montoAbono}>
              <p>{proposito === "volver_al_padron" ? "Para saldar la deuda y volver al padrón." : "Para ponerse al día y seguir pagando."}
                {" "}El primero vence el <b>{prima > 0 ? "día de hoy (la prima)" : fechaCorta(calendario[0].fecha)}</b>
                {" "}y el último el <b>{fechaCorta(calendario[calendario.length - 1].fecha)}</b>.</p>
              {descuento > 0 && <p>Con un descuento de {pctValido} % ({L(descuento)}), autorizado por {autEmail}.</p>}
            </Aviso>
            <ul className="sal-efectos">
              <li><span className="sal-efecto-icono"><CalendarDays size={18} /></span>
                <span>Entran {sel.length === 1 ? "1 cuota" : `${sel.length} cuotas`}:{" "}
                  {(cuotas || []).filter(c => sel.includes(c.id)).map(c => c.mes_label).join(", ")}.
                  Mientras el arreglo esté al día, <b>no generan mora</b>.</span></li>
              {!enPadron && (
                <li><span className="sal-efecto-icono"><ShieldCheck size={18} /></span>
                  <span>Si la casa estaba bloqueada, <b>se desbloquea hoy</b>.</span></li>
              )}
              <li><span className="sal-efecto-icono"><Wallet size={18} /></span>
                <span>Los abonos se cobran en <b>Caja</b>, o el residente sube su comprobante desde la app.</span></li>
              <li><span className="sal-efecto-icono"><Ban size={18} /></span>
                <span>Si un abono se atrasa más de <b>{gracia} días</b>, el arreglo queda incumplido y la deuda
                  vuelve a quedar pendiente{enPadron || proposito === "volver_al_padron"
                    ? ". Si la casa ya está en el padrón, no se le bloquea el portón, pero no puede volver a sumarse hasta pagar."
                    : ", y la casa se bloquea de nuevo."}</span></li>
              {proposito === "volver_al_padron" && !enPadron && (
                <li><span className="sal-efecto-icono"><Home size={18} /></span>
                  <span>Con el arreglo firmado, ya puede pasar al padrón desde <b>Casas y residentes → Salida del sistema</b>.</span></li>
              )}
              {nota && <li><span className="sal-efecto-icono"><Scale size={18} /></span><span>Nota: {nota}</span></li>}
            </ul>
          </>
        )}

        {/* ── Listo ───────────────────────────────────────────────────── */}
        {paso === "listo" && creado && (
          <div className="sal-listo">
            <span className="sal-listo-marca"><Check size={34} strokeWidth={3} /></span>
            <h3>Arreglo creado para {nombreCasa}</h3>
            <p>{creado.num_abonos === 1 ? "1 abono" : `${creado.num_abonos} abonos`} de {L(creado.monto_por_abono)}
              {creado.proximo_abono ? `. El primero vence el ${fechaCorta(new Date(creado.proximo_abono.fecha_pactada + "T00:00:00"))}.` : "."}
              {proposito === "volver_al_padron" && !enPadron ? " Ya puede pasar al padrón desde Casas y residentes." : ""}</p>
            <div className="arr-listo-botones">
              <button className="sal-btn sal-btn--fantasma" onClick={onCancelar}>Volver a la lista</button>
              <button className="sal-btn sal-btn--principal" onClick={() => onCreado(creado)}>Ver el arreglo</button>
            </div>
          </div>
        )}

        {error && <div className="sal-error" role="alert"><AlertTriangle size={16} /> {error}</div>}
      </div>

      {paso !== "listo" && (
        <footer className="sal-pie">
          {paso === "casa"
            ? <button className="sal-btn sal-btn--fantasma" onClick={onCancelar}>Cancelar</button>
            : <button className="sal-btn sal-btn--fantasma" onClick={atras} disabled={guardando}><ArrowLeft size={16} /> Atrás</button>}
          {paso !== "casa" && paso !== "confirmar" && (
            <button className="sal-btn sal-btn--principal" onClick={seguir} disabled={!puedeSeguir}>Continuar</button>
          )}
          {paso === "confirmar" && (
            <button className="sal-btn sal-btn--principal" onClick={crear} disabled={guardando}>
              {guardando ? "Creando…" : "Crear arreglo"}
            </button>
          )}
        </footer>
      )}
    </div>
  );
}
