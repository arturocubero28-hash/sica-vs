import { useEffect, useRef, useState } from "react";
import {
  Home, Truck, Check, AlertTriangle, Users, CreditCard, QrCode, Handshake,
  Scale, Wallet, ArrowLeft, X, Ban, CalendarDays, RefreshCw, Info,
} from "lucide-react";
import {
  volverAlPadron, simularBajaCuenta, darBajaCuenta, nivelarSaldo,
  type Cuenta, type ResultadoVolverPadron, type SimulacionBaja, type AjusteNivelacion,
  type AccesosCasa,
} from "../../api/client";

/* ═══════════════════════════════════════════════════════════════════════
   Día 75 — SALIDA DEL SISTEMA DE CUOTAS, paso a paso.

   Reemplaza al modal de una sola pantalla del Día 74. Dos caminos:

     Vuelve al padrón:  Qué pasa → Fecha → Cobro (si hace falta) → Confirmar → Listo
     Se muda:           Qué pasa → Salida → Confirmar → Listo

   La pieza central es la BARRA DEL MES: los 30 días dibujados, con los que
   se cobran pintados. Es lo que más cuesta explicar con palabras (por qué
   son L 80 y no L 560), así que se muestra.

   Todo lo que se ve antes de confirmar sale de una SIMULACIÓN del backend
   (simular: true), que calcula y deshace: lo que el admin ve es exactamente
   lo que va a pasar.
   ═══════════════════════════════════════════════════════════════════════ */

type Camino = "padron" | "mudanza";
type Paso = "camino" | "fecha" | "cobro" | "confirmar" | "listo";

const L = (n: number) =>
  `L ${n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
// Fecha LOCAL: de noche en Honduras el UTC ya es mañana, y el backend
// rechaza fechas futuras.
const hoyLocal = () => new Date().toLocaleDateString("en-CA");
const fechaCorta = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("es-HN", { day: "numeric", month: "long" });
const mesDe = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("es-HN", { month: "long" });

const PASOS: Record<Camino, { id: Paso; nombre: string }[]> = {
  padron: [
    { id: "camino", nombre: "Qué pasa" },
    { id: "fecha", nombre: "Fecha" },
    { id: "cobro", nombre: "Cobro" },
    { id: "confirmar", nombre: "Confirmar" },
  ],
  mudanza: [
    { id: "camino", nombre: "Qué pasa" },
    { id: "fecha", nombre: "Salida" },
    { id: "confirmar", nombre: "Confirmar" },
  ],
};

export function ModalDarBaja({ cuenta, onCerrar, onBajaCompletada }: {
  cuenta: Cuenta; onCerrar: () => void; onBajaCompletada: () => void;
}) {
  const nombre = cuenta.identificador || (cuenta.apartamento ? `Apto ${cuenta.apartamento}` : "la casa");
  // ResidenteDTO.nombre ya es el nombre completo (nombre + apellido).
  const titular = cuenta.titular?.nombre || "el titular";

  const [camino, setCamino] = useState<Camino | null>(null);
  const [paso, setPaso] = useState<Paso>("camino");
  const [fecha, setFecha] = useState(hoyLocal());
  const [motivo, setMotivo] = useState("");

  const [simPadron, setSimPadron] = useState<ResultadoVolverPadron | null>(null);
  const [simBaja, setSimBaja] = useState<SimulacionBaja | null>(null);
  const [bloqueo, setBloqueo] = useState<string | null>(null);   // error duro al simular
  const [calculando, setCalculando] = useState(false);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState("");

  const [seguroSeVa, setSeguroSeVa] = useState(false);
  const [aceptaDeuda, setAceptaDeuda] = useState(false);
  const [avisoPago, setAvisoPago] = useState<"" | "falta" | "ok">("");
  const ultimaSim = useRef(0);

  // ── Simulación: al entrar al paso de fecha y cada vez que cambia ──────
  async function simular(c: Camino = camino!, f: string = fecha) {
    const n = ++ultimaSim.current;
    setCalculando(true); setError(""); setBloqueo(null);
    try {
      if (c === "padron") {
        const r = await volverAlPadron(cuenta.id, { fecha: f, simular: true });
        if (n === ultimaSim.current) setSimPadron(r);
        return r;
      }
      const r = await simularBajaCuenta(cuenta.id, f);
      if (n === ultimaSim.current) setSimBaja(r);
      return r;
    } catch (e) {
      if (n === ultimaSim.current) { setBloqueo((e as Error).message); setSimPadron(null); setSimBaja(null); }
    } finally {
      if (n === ultimaSim.current) setCalculando(false);
    }
  }
  useEffect(() => {
    if (!camino || paso !== "fecha" || !fecha) return;
    const t = setTimeout(() => simular(camino, fecha), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camino, paso, fecha]);

  // Escape cierra (salvo mientras se guarda algo).
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !trabajando && paso !== "listo") onCerrar(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [trabajando, paso, onCerrar]);

  function elegir(c: Camino) {
    setCamino(c); setSimPadron(null); setSimBaja(null); setBloqueo(null);
    setSeguroSeVa(false); setAceptaDeuda(false); setAvisoPago("");
    setPaso("fecha");
  }

  // ── Acciones ──────────────────────────────────────────────────────────
  async function nivelar() {
    setTrabajando(true); setError("");
    try { await nivelarSaldo(cuenta.id, fecha); await simular("padron", fecha); }
    catch (e) { setError((e as Error).message); }
    finally { setTrabajando(false); }
  }

  async function verificarPago() {
    setTrabajando(true); setAvisoPago("");
    const r = await simular("padron", fecha) as ResultadoVolverPadron | undefined;
    setTrabajando(false);
    if (r?.puede) { setAvisoPago("ok"); setTimeout(() => setPaso("confirmar"), 900); }
    else setAvisoPago("falta");
  }

  async function confirmar() {
    setTrabajando(true); setError("");
    try {
      if (camino === "padron") await volverAlPadron(cuenta.id, { fecha });
      else await darBajaCuenta(cuenta.id, {
        fecha_salida: fecha, motivo: motivo.trim() || "Mudanza", confirmar_deuda: aceptaDeuda,
      });
      setPaso("listo");
    } catch (e) { setError((e as Error).message); }
    finally { setTrabajando(false); }
  }

  // ── Qué sigue después del paso de fecha ───────────────────────────────
  const imp = simPadron?.impedimento?.code;
  const deudaBaja = simBaja?.deuda.total ?? 0;

  function continuarDesdeFecha() {
    if (camino === "padron") setPaso(simPadron?.puede ? "confirmar" : "cobro");
    else setPaso("confirmar");
  }
  const puedeContinuarFecha = !calculando && !bloqueo && (
    camino === "mudanza" ? !!simBaja : !!simPadron && imp !== "deuda_sin_arreglo");

  const pasos = camino ? PASOS[camino] : PASOS.padron;
  const iPaso = pasos.findIndex(p => p.id === paso);

  return (
    <div className="modal sal-fondo" onClick={() => !trabajando && paso !== "listo" && onCerrar()}>
      <div className="sal-modal" role="dialog" aria-modal="true" aria-labelledby="sal-titulo"
        onClick={e => e.stopPropagation()}>

        <header className="sal-cabeza">
          <div>
            <h2 id="sal-titulo">{paso === "listo" ? nombre : `Salida del sistema · ${nombre}`}</h2>
            {paso !== "listo" && <p>Titular: {titular}</p>}
          </div>
          {paso !== "listo" && (
            <button className="sal-cerrar" onClick={onCerrar} disabled={trabajando} aria-label="Cerrar">
              <X size={18} />
            </button>
          )}
        </header>

        {paso !== "listo" && (
          <ol className="sal-pasos" aria-label="Pasos">
            {pasos.map((p, i) => (
              <li key={p.id} className={i < iPaso ? "hecho" : i === iPaso ? "actual" : ""}
                aria-current={i === iPaso ? "step" : undefined}>
                <span className="sal-pasos-num">{i < iPaso ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
                <span className="sal-pasos-nombre">{p.nombre}</span>
              </li>
            ))}
          </ol>
        )}

        <div className="sal-cuerpo" key={paso}>
          {/* ── 1. Qué pasa con la familia ─────────────────────────────── */}
          {paso === "camino" && (
            <>
              <h3 className="sal-pregunta">¿Qué pasa con esta familia?</h3>
              <div className="sal-caminos">
                <button className="sal-camino" onClick={() => elegir("padron")}>
                  <span className="sal-camino-icono"><Home size={22} /></span>
                  <b>Sigue viviendo acá, pero deja de pagar mensualidad</b>
                  <ul>
                    <li>Vuelve al padrón: el guardia la sigue identificando</li>
                    <li>Pierde la app hasta que vuelva a sumarse</li>
                    <li>Paga en caja los días que estuvo este mes</li>
                  </ul>
                </button>
                <button className="sal-camino" onClick={() => elegir("mudanza")}>
                  <span className="sal-camino-icono sal-camino-icono--mudanza"><Truck size={22} /></span>
                  <b>Se va de la residencial</b>
                  <ul>
                    <li>Baja por mudanza; queda el historial</li>
                    <li>Si debe, la deuda queda a nombre de {titular}</li>
                    <li>La casa queda libre para otra familia</li>
                  </ul>
                </button>
              </div>
            </>
          )}

          {/* ── 2. Fecha ──────────────────────────────────────────────── */}
          {paso === "fecha" && camino && (
            <>
              <div className="sal-fila-fecha">
                <label className="sal-campo">
                  <span>{camino === "padron" ? "Deja de pagar desde" : "Fecha en que se fue"}</span>
                  <div className="sal-input-icono">
                    <CalendarDays size={16} />
                    <input type="date" value={fecha} max={hoyLocal()} onChange={e => setFecha(e.target.value)} />
                  </div>
                </label>
                {camino === "mudanza" && (
                  <label className="sal-campo sal-campo--ancho">
                    <span>Motivo (queda en el historial)</span>
                    <input value={motivo} placeholder="Se mudó a San Pedro Sula"
                      onChange={e => setMotivo(e.target.value)} />
                  </label>
                )}
              </div>

              {bloqueo && <Aviso tono="bloqueo" icono={<Ban size={22} />} titulo="No se puede sacar del sistema todavía">
                <p>{bloqueo}</p>
              </Aviso>}

              {calculando && !simPadron && !simBaja && <div className="sal-cargando">Calculando…</div>}

              {!bloqueo && (camino === "padron" ? simPadron : simBaja) && (
                <div className={calculando ? "sal-recalculando" : ""}>
                  <MesesCobrados ajustes={(camino === "padron" ? simPadron!.ajustes : simBaja!.ajustes)} />

                  {camino === "padron" && simPadron && (
                    <ResumenPadron sim={simPadron} />
                  )}
                  {camino === "mudanza" && simBaja && (
                    deudaBaja > 0
                      ? <Aviso tono="cobrar" icono={<Wallet size={22} />} titulo="Se va debiendo" monto={deudaBaja}>
                          <DesgloseDeuda d={simBaja.deuda} />
                          <p>Ya está calculada con la cuota de este mes cobrada solo hasta el {fechaCorta(fecha)}.
                            Al darla de baja, queda a nombre de {titular}.</p>
                        </Aviso>
                      : <Aviso tono="ok" icono={<Check size={22} />} titulo="Se va sin deber nada" />
                  )}
                </div>
              )}
            </>
          )}

          {/* ── 3. Cobro antes de salir (solo padrón) ─────────────────── */}
          {paso === "cobro" && simPadron && (
            <>
              <Aviso tono="cobrar" icono={<Wallet size={24} />} titulo="Antes de salir, hay que cobrar"
                monto={simPadron.a_cobrar_antes_de_salir}>
                <p>{textoCobro(simPadron)}</p>
              </Aviso>

              <ol className="sal-lista">
                <li className={simPadron.ya_nivelada ? "hecho" : "actual"}>
                  <span className="sal-lista-marca">{simPadron.ya_nivelada ? <Check size={14} strokeWidth={3} /> : 1}</span>
                  <div>
                    <b>Nivelar la cuota de {mesDe(fecha)}</b>
                    {simPadron.ya_nivelada ? (
                      <p>Listo: caja va a cobrar {L(simPadron.a_cobrar_antes_de_salir)} y no la cuota completa.</p>
                    ) : (
                      <>
                        <p>Así caja cobra solo los días que estuvo, no el mes entero.</p>
                        <div className="sal-cuidado">
                          <AlertTriangle size={18} />
                          <div>
                            <b>Nivelá solo si la familia ya confirmó que deja de pagar.</b>
                            <p>Una vez nivelada, la casa tiene que pasar al padrón: si se queda en el sistema,
                              el resto de {mesDe(fecha)} le sale gratis. Si después cambia de idea, pasala igual
                              al padrón y volvé a sumarla desde <b>Padrón → Sumar al sistema</b>: ahí se le
                              cobran los días que quedan del mes.</p>
                          </div>
                        </div>
                        <label className="sal-check">
                          <input type="checkbox" checked={seguroSeVa} onChange={e => setSeguroSeVa(e.target.checked)} />
                          <span>La familia ya confirmó que deja de pagar mensualidad</span>
                        </label>
                        <button className="sal-btn sal-btn--secundario" onClick={nivelar}
                          disabled={!seguroSeVa || trabajando}>
                          <Scale size={16} /> {trabajando ? "Nivelando…" : `Nivelar al ${fechaCorta(fecha)}`}
                        </button>
                      </>
                    )}
                  </div>
                </li>
                <li className={!simPadron.ya_nivelada ? "" : "actual"}>
                  <span className="sal-lista-marca">2</span>
                  <div>
                    <b>Cobrar {L(simPadron.a_cobrar_antes_de_salir)} en Caja</b>
                    <p>El cajero busca «{nombre}» y cobra la cuota de {mesDe(fecha)}.</p>
                    {simPadron.ya_nivelada && (
                      <button className="sal-btn sal-btn--secundario" onClick={verificarPago} disabled={trabajando}>
                        <RefreshCw size={16} className={trabajando ? "sal-gira" : ""} />
                        {trabajando ? "Verificando…" : "Ya lo cobraron: verificar"}
                      </button>
                    )}
                    {avisoPago === "falta" && (
                      <p className="sal-nota-falta">Todavía no aparece el pago. Revisá que caja lo haya registrado.</p>
                    )}
                    {avisoPago === "ok" && <p className="sal-nota-ok"><Check size={14} /> Pago recibido</p>}
                  </div>
                </li>
                <li>
                  <span className="sal-lista-marca">3</span>
                  <div>
                    <b>Pasar al padrón</b>
                    <p>Con el pago registrado, se confirma en el paso siguiente.</p>
                  </div>
                </li>
              </ol>
              <p className="sal-pie-nota">Podés cerrar esta ventana mientras se cobra: al volver, lo ya hecho aparece marcado.</p>
            </>
          )}

          {/* ── 4. Confirmar ──────────────────────────────────────────── */}
          {paso === "confirmar" && camino === "padron" && simPadron && (
            <>
              <h3 className="sal-pregunta">Confirmá el paso al padrón</h3>
              <ul className="sal-efectos">
                <Efecto icono={<CalendarDays size={18} />}>
                  Deja de pagar mensualidad desde el <b>{fechaCorta(fecha)}</b>. No se generan más cuotas.
                </Efecto>
                <EfectosAccesos a={simPadron.afectados} vuelve />
                {simPadron.arreglo && (
                  <Efecto icono={<Handshake size={18} />}>
                    Su arreglo de pago sigue: faltan <b>{L(simPadron.arreglo.saldo_pendiente)}</b> en{" "}
                    {simPadron.arreglo.abonos_total - simPadron.arreglo.abonos_pagados} abonos, que se cobran en caja.
                  </Efecto>
                )}
                <Efecto icono={<Home size={18} />}>
                  Para volver a pagar mensualidad, se suma desde <b>Padrón → Sumar al sistema</b>
                  {simPadron.arreglo ? ", estando al día con el arreglo." : "."}
                </Efecto>
              </ul>
            </>
          )}
          {paso === "confirmar" && camino === "mudanza" && simBaja && (
            <>
              <h3 className="sal-pregunta">Confirmá la baja por mudanza</h3>
              {deudaBaja > 0 && (
                <Aviso tono="bloqueo" icono={<AlertTriangle size={24} />} titulo="Se va debiendo" monto={deudaBaja}>
                  <p>La deuda queda a nombre de <b>{titular}</b>, y no va a poder darse de alta en otra
                    casa de la residencial hasta pagarla.</p>
                  <label className="sal-check sal-check--fuerte">
                    <input type="checkbox" checked={aceptaDeuda} onChange={e => setAceptaDeuda(e.target.checked)} />
                    <span>Entiendo: se da de baja con la deuda pendiente</span>
                  </label>
                </Aviso>
              )}
              <ul className="sal-efectos">
                {simBaja.ajustes.some(a => a.accion === "prorrateada") && (
                  <Efecto icono={<Scale size={18} />}>
                    La cuota de {mesDe(fecha)} se cobra solo por los días hasta el <b>{fechaCorta(fecha)}</b>.
                  </Efecto>
                )}
                <EfectosAccesos a={simBaja.afectados} />
                <Efecto icono={<Info size={18} />}>
                  La casa queda libre: se puede registrar a la familia que llegue. No se borra nada del historial.
                </Efecto>
              </ul>
            </>
          )}

          {/* ── Listo ─────────────────────────────────────────────────── */}
          {paso === "listo" && (
            <div className="sal-listo">
              <span className="sal-listo-marca"><Check size={34} strokeWidth={3} /></span>
              <h3>{camino === "padron" ? `${nombre} ya está en el padrón` : `${nombre} quedó dada de baja`}</h3>
              <p>{camino === "padron"
                ? "El guardia la sigue identificando. Si la familia quiere volver a pagar mensualidad, se suma desde Padrón."
                : deudaBaja > 0
                  ? `La deuda de ${L(deudaBaja)} queda a nombre de ${titular}. La casa está libre para la próxima familia.`
                  : "La casa está libre para la próxima familia."}</p>
              <button className="sal-btn sal-btn--principal" onClick={onBajaCompletada}>Listo</button>
            </div>
          )}

          {error && <div className="sal-error" role="alert"><AlertTriangle size={16} /> {error}</div>}
        </div>

        {/* ── Pie: navegación ──────────────────────────────────────────── */}
        {paso !== "camino" && paso !== "listo" && (
          <footer className="sal-pie">
            <button className="sal-btn sal-btn--fantasma" disabled={trabajando}
              onClick={() => { setError(""); setAvisoPago("");
                setPaso(paso === "fecha" ? "camino" : paso === "cobro" ? "fecha"
                  : camino === "padron" && !simPadron?.puede ? "cobro" : "fecha"); }}>
              <ArrowLeft size={16} /> Atrás
            </button>
            {paso === "fecha" && (
              <button className="sal-btn sal-btn--principal" onClick={continuarDesdeFecha}
                disabled={!puedeContinuarFecha}>
                Continuar
              </button>
            )}
            {paso === "confirmar" && (
              <button className={`sal-btn ${camino === "mudanza" ? "sal-btn--peligro" : "sal-btn--principal"}`}
                onClick={confirmar}
                disabled={trabajando || (camino === "mudanza" && deudaBaja > 0 && !aceptaDeuda)}>
                {trabajando ? "Guardando…" : camino === "padron" ? `Pasar ${nombre} al padrón` : `Dar de baja ${nombre}`}
              </button>
            )}
          </footer>
        )}
      </div>
    </div>
  );
}

/* ── Piezas ─────────────────────────────────────────────────────────── */

function textoCobro(s: ResultadoVolverPadron) {
  const p = s.ajustes.find(a => a.accion === "prorrateada");
  const vencido = s.queda_vencido_fuera_de_arreglo;
  const partes: string[] = [];
  if (p?.dias_ocupados) partes.push(`los ${p.dias_ocupados} días que la casa estuvo este mes`);
  if (vencido > 0) partes.push(`${L(vencido)} de cuotas atrasadas que no entraron en el arreglo`);
  return partes.length
    ? `Son ${partes.join(" y ")}. Se cobra en caja y después la casa pasa al padrón sin deber nada.`
    : "Se cobra en caja y después la casa pasa al padrón sin deber nada.";
}

function ResumenPadron({ sim }: { sim: ResultadoVolverPadron }) {
  if (sim.impedimento?.code === "deuda_sin_arreglo") {
    return (
      <Aviso tono="bloqueo" icono={<Ban size={24} />} titulo="Tiene cuotas atrasadas" monto={sim.queda_vencido_fuera_de_arreglo}>
        <p>Para volver al padrón, primero tiene que hacer una de estas dos cosas:</p>
        <ul className="sal-opciones">
          <li><b>Pagarlas en caja</b>, y volver acá.</li>
          <li><b>Firmar un arreglo de pago</b> «para volver al padrón», en <b>Arreglos de pago</b>. Las cuotas del arreglo se siguen pagando en caja desde el padrón.</li>
        </ul>
      </Aviso>
    );
  }
  if (!sim.puede) {
    return (
      <Aviso tono="cobrar" icono={<Wallet size={24} />} titulo="Antes de salir, hay que cobrar" monto={sim.a_cobrar_antes_de_salir}>
        <p>{textoCobro(sim)} En el paso siguiente te guío.</p>
      </Aviso>
    );
  }
  return (
    <Aviso tono="ok" icono={<Check size={24} />} titulo="No debe nada: puede pasar al padrón">
      {sim.arreglo && <p>Su arreglo de pago sigue igual: los abonos se cobran en caja.</p>}
    </Aviso>
  );
}

function DesgloseDeuda({ d }: { d: SimulacionBaja["deuda"] }) {
  const filas: [string, number][] = [];
  if (d.fuera_de_arreglo > 0) filas.push(["Cuotas sin pagar", d.fuera_de_arreglo]);
  if (d.arreglo) filas.push([`Arreglo de pago (${d.arreglo.abonos_total - d.arreglo.abonos_pagados} abonos)`, d.arreglo.saldo_pendiente]);
  if (filas.length < 2) return null;
  return (
    <dl className="sal-desglose">
      {filas.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{L(v)}</dd></div>)}
    </dl>
  );
}

export function Aviso({ tono, icono, titulo, monto, children }: {
  tono: "cobrar" | "bloqueo" | "ok"; icono: React.ReactNode; titulo: string;
  monto?: number; children?: React.ReactNode;
}) {
  return (
    <section className={`sal-aviso sal-aviso--${tono}`} role={tono === "bloqueo" ? "alert" : undefined}>
      <div className="sal-aviso-cabeza">
        <span className="sal-aviso-icono">{icono}</span>
        <h4>{titulo}</h4>
        {monto !== undefined && <span className="sal-aviso-monto">{L(monto)}</span>}
      </div>
      {children && <div className="sal-aviso-texto">{children}</div>}
    </section>
  );
}

function Efecto({ icono, children }: { icono: React.ReactNode; children: React.ReactNode }) {
  return <li><span className="sal-efecto-icono">{icono}</span><span>{children}</span></li>;
}

function EfectosAccesos({ a, vuelve }: { a: AccesosCasa; vuelve?: boolean }) {
  return (
    <>
      <Efecto icono={<Users size={18} />}>
        {a.usuarios === 1 ? "1 persona pierde" : `${a.usuarios} personas pierden`} la app
        {vuelve ? " (la recuperan si la casa se vuelve a sumar)." : "."}
      </Efecto>
      {a.tarjetas + a.credenciales > 0 && (
        <Efecto icono={<CreditCard size={18} />}>
          Se desactivan {a.tarjetas + a.credenciales} {a.tarjetas + a.credenciales === 1 ? "tarjeta o credencial" : "tarjetas y credenciales"} de acceso.
        </Efecto>
      )}
      {a.visitas > 0 && (
        <Efecto icono={<QrCode size={18} />}>
          Se anulan {a.visitas} {a.visitas === 1 ? "QR de visita que ya habían compartido" : "QR de visita que ya habían compartido"}.
        </Efecto>
      )}
    </>
  );
}

/**
 * La barra del mes: 30 días (mes comercial). Pinta los que se cobran, deja
 * en gris claro los de antes del alta y rayados los posteriores a la salida.
 * Si no hay cuota del mes que nivelar, no dibuja nada.
 */
function MesesCobrados({ ajustes }: { ajustes: AjusteNivelacion[] }) {
  const prorr = ajustes.filter(a => a.accion === "prorrateada");
  const anuladas = ajustes.filter(a => a.accion === "anulada");
  if (!prorr.length && !anuladas.length) return null;
  return (
    <div className="sal-meses">
      {prorr.map(a => {
        const desde = a.desde_dia ?? 1, hasta = a.hasta_dia ?? 30;
        const dias = Array.from({ length: 30 }, (_, i) => i + 1);
        return (
          <figure key={a.periodo} className="sal-mes">
            <figcaption>
              <span className="sal-mes-nombre">Cuota de {mesDe(a.periodo)}</span>
              <span className="sal-mes-cuenta">
                {a.dias_ocupados} {a.dias_ocupados === 1 ? "día" : "días"}
                {a.monto_diario ? ` × ${L(a.monto_diario)}` : ""} = <b>{L(a.monto_final)}</b>
                <s>{L(a.monto_original)}</s>
              </span>
            </figcaption>
            <div className="sal-barra" role="img"
              aria-label={`Se cobran del día ${desde} al ${hasta}: ${a.dias_ocupados} días, ${L(a.monto_final)}`}>
              {dias.map(d => (
                <span key={d} className={d < desde ? "antes" : d <= hasta ? "cobra" : "libre"} />
              ))}
            </div>
            <div className="sal-barra-escala" aria-hidden="true">
              {dias.map(d => (
                <span key={d}>{d === desde ? d : d === hasta ? d : d === 1 || d === 30 ? d : ""}</span>
              ))}
            </div>
            <ul className="sal-leyenda">
              {desde > 1 && <li><i className="antes" /> Antes del alta</li>}
              <li><i className="cobra" /> Se cobra</li>
              {hasta < 30 && <li><i className="libre" /> Ya no paga</li>}
            </ul>
          </figure>
        );
      })}
      {anuladas.map(a => (
        <p key={a.periodo} className="sal-mes-anulada">
          La cuota de {mesDe(a.periodo)} ({L(a.monto_original)}) se anula: la casa ya no está ese mes.
        </p>
      ))}
    </div>
  );
}
