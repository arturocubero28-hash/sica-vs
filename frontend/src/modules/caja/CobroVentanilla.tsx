import { useEffect, useMemo, useRef, useState } from "react";
import {
  Search, Home, Check, X, AlertTriangle, Banknote, CreditCard, Receipt, Printer, Loader2,
  ShieldCheck, ArrowLeft, FileClock, RotateCcw,
} from "lucide-react";
import {
  buscarCuentaCaja, registrarPagoCaja, cobrarAbono, urlReciboPDF,
  type CuentaCajaDTO,
} from "../../api/client";
import { useMiResidencial } from "../../hooks/useMiResidencial";

/* Día 76 — cobro en ventanilla como una transacción formal.
   Antes eran dos toques: elegir una cuota y «Confirmar pago». Ahora:
     1. Cuenta     → quién paga (con su deuda a la vista)
     2. Concepto   → qué paga (cuota o abono, con vencimiento y estado)
     3. Forma de pago → efectivo (recibido y vuelto) o POS (autorización)
   y un resumen tipo ticket que hay que confirmar explícitamente. Mientras
   el servidor registra, se muestra el proceso; al terminar, el comprobante
   con su número de recibo. */

const L = (n: number) =>
  `L ${n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fechaCorta = (iso?: string) =>
  iso ? new Date(iso.length === 10 ? iso + "T00:00:00" : iso)
    .toLocaleDateString("es-HN", { day: "numeric", month: "short", year: "numeric" }) : "—";
const hoyISO = () => new Date().toISOString().slice(0, 10);

type Metodo = "efectivo" | "tarjeta_pos";
interface Concepto {
  clave: string;
  tipo: "cuota" | "abono";
  titulo: string;           // "Cuota de Noviembre 2026" | "Abono 2 de 3 · arreglo de pago"
  detalle: string;          // "Vence el 1 dic 2026"
  monto: number;
  vencido: boolean;
  bloqueado?: string;       // por qué no se puede cobrar
  nota?: string;            // ej. "Ya pagó L 80 de L 800"
  cuotaId?: string; arregloId?: string; abonoId?: string;
}
interface Resultado { pagoId: string; recibo?: number | null; hora: Date }

function conceptosDe(c: CuentaCajaDTO): Concepto[] {
  const hoy = hoyISO();
  const out: Concepto[] = [];
  for (const q of c.cuotas_pendientes) {
    const vencido = q.estado === "vencida" || (!!q.fecha_vencimiento && q.fecha_vencimiento < hoy);
    out.push({
      clave: "c" + q.cuota_id, tipo: "cuota", cuotaId: q.cuota_id,
      titulo: `Cuota de ${q.mes_label}`,
      detalle: q.fecha_vencimiento ? `${vencido ? "Venció" : "Vence"} el ${fechaCorta(q.fecha_vencimiento)}` : "",
      monto: q.monto, vencido,
      bloqueado: q.estado === "en_revision"
        ? "El residente subió un comprobante que todavía no se revisó. Si se rechaza, se cobra acá." : undefined,
      nota: q.monto_cuota && q.monto_cuota - q.monto > 0.004
        ? `Ya pagó ${L(q.monto_cuota - q.monto)} de ${L(q.monto_cuota)}` : undefined,
    });
  }
  for (const a of c.abonos_arreglo || []) {
    const vencido = a.estado === "vencido" || a.fecha_pactada < hoy;
    out.push({
      clave: "a" + a.abono_id, tipo: "abono", arregloId: a.arreglo_id, abonoId: a.abono_id,
      titulo: a.es_prima ? "Prima del arreglo de pago" : `Abono ${a.numero} de ${a.total_abonos} · arreglo de pago`,
      detalle: `${vencido ? "Venció" : "Vence"} el ${fechaCorta(a.fecha_pactada)}`,
      monto: a.monto, vencido,
      bloqueado: a.en_revision
        ? "El residente subió un comprobante que todavía no se revisó. Si se rechaza, se cobra acá." : undefined,
    });
  }
  return out;
}

export function CobroVentanilla({ cajero, onRegistrado }: { cajero: string; onRegistrado: () => void }) {
  const { nombre: residencial } = useMiResidencial();
  const [busqueda, setBusqueda] = useState("");
  const [resultados, setResultados] = useState<CuentaCajaDTO[] | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [errorBusqueda, setErrorBusqueda] = useState("");
  const [cuenta, setCuenta] = useState<CuentaCajaDTO | null>(null);
  const [clave, setClave] = useState<string>("");
  const [metodo, setMetodo] = useState<Metodo>("efectivo");
  const [recibido, setRecibido] = useState("");
  const [referencia, setReferencia] = useState("");
  const [revisando, setRevisando] = useState(false);
  const buscarRef = useRef<HTMLInputElement>(null);

  const conceptos = useMemo(() => (cuenta ? conceptosDe(cuenta) : []), [cuenta]);
  const concepto = conceptos.find(c => c.clave === clave) || null;
  // Lo que tiene un comprobante en revisión se muestra aparte: puede que ya esté pagado.
  const totalPendiente = conceptos.filter(c => !c.bloqueado).reduce((s, c) => s + c.monto, 0);
  const totalEnRevision = conceptos.filter(c => c.bloqueado).reduce((s, c) => s + c.monto, 0);

  const montoRecibido = parseFloat(recibido.replace(",", ".")) || 0;
  const vuelto = concepto ? Math.round((montoRecibido - concepto.monto) * 100) / 100 : 0;
  const pagoValido = !!concepto && !concepto.bloqueado && (
    metodo === "efectivo" ? montoRecibido >= concepto.monto - 0.004 : referencia.trim().length >= 4);

  async function buscar() {
    if (!busqueda.trim()) return;
    setBuscando(true); setErrorBusqueda("");
    try {
      const r = await buscarCuentaCaja(busqueda.trim());
      setResultados(r);
      if (r.length === 1) elegirCuenta(r[0]);
    } catch (e) {
      setErrorBusqueda((e as Error).message);
    } finally { setBuscando(false); }
  }

  function elegirCuenta(c: CuentaCajaDTO) {
    setCuenta(c);
    const primero = conceptosDe(c).find(x => !x.bloqueado);
    setClave(primero?.clave || "");
    setRecibido(""); setReferencia("");
  }

  function reiniciar() {
    setCuenta(null); setClave(""); setResultados(null); setBusqueda("");
    setRecibido(""); setReferencia(""); setMetodo("efectivo");
    setTimeout(() => buscarRef.current?.focus(), 0);
  }

  // Sugerencias de billetes para el efectivo: exacto y los redondeos útiles.
  const sugerencias = useMemo(() => {
    if (!concepto) return [];
    const m = concepto.monto;
    const s = new Set<number>([m]);
    for (const paso of [100, 500, 1000]) s.add(Math.ceil(m / paso) * paso);
    return [...s].filter(v => v >= m).sort((a, b) => a - b).slice(0, 4);
  }, [concepto]);

  const paso = !cuenta ? 1 : !concepto ? 2 : 3;

  return (
    <section className="dash-card cv" aria-label="Nuevo cobro">
      <header className="cv-cabeza">
        <h3><Receipt size={18} /> Nuevo cobro</h3>
        <ol className="cv-pasos" aria-label="Pasos del cobro">
          {["Cuenta", "Concepto", "Forma de pago"].map((n, i) => (
            <li key={n} className={i + 1 < paso ? "hecho" : i + 1 === paso ? "actual" : ""}>
              <span className="cv-pasos-num">{i + 1 < paso ? <Check size={13} strokeWidth={3} /> : i + 1}</span>{n}
            </li>
          ))}
        </ol>
      </header>

      {/* 1 · CUENTA */}
      <div className="cv-bloque">
        <div className="cv-bloque-titulo"><span>1</span> ¿Quién paga?</div>
        {!cuenta ? (
          <>
            <div className="cv-buscar">
              <Search size={17} aria-hidden="true" />
              <input ref={buscarRef} autoFocus value={busqueda} placeholder="Número de casa o nombre del titular"
                onChange={e => setBusqueda(e.target.value)} onKeyDown={e => e.key === "Enter" && buscar()}
                aria-label="Buscar casa o titular" />
              <button onClick={buscar} disabled={buscando || !busqueda.trim()}>
                {buscando ? <Loader2 size={16} className="sal-gira" /> : "Buscar"}
              </button>
            </div>
            {errorBusqueda && <p className="cv-error"><AlertTriangle size={15} /> {errorBusqueda}</p>}
            {resultados && resultados.length === 0 && (
              <p className="cv-vacio">No hay ninguna casa con «{busqueda}». Probá con el número de casa o el apellido.</p>
            )}
            {resultados && resultados.length > 1 && (
              <ul className="cv-resultados">
                {resultados.map(c => {
                  const cs = conceptosDe(c);
                  const total = cs.reduce((s, x) => s + x.monto, 0);
                  return (
                    <li key={c.cuenta_id}>
                      <button onClick={() => elegirCuenta(c)}>
                        <span className="cv-res-casa"><Home size={16} /> {c.identificador}</span>
                        <span className="cv-res-titular">{c.titular}</span>
                        <span className="cv-res-deuda">
                          {cs.length === 0 ? <span className="pill green">Al día</span>
                            : <><b>{L(total)}</b><small>{cs.length === 1 ? "1 concepto" : `${cs.length} conceptos`}</small></>}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        ) : (
          <div className="cv-cuenta">
            <div>
              <b><Home size={16} /> {cuenta.identificador}</b>
              <span>{cuenta.titular}</span>
              <div className="cv-cuenta-pills">
                {cuenta.dada_de_baja && <span className="pill amber" title={cuenta.motivo_baja || undefined}>Dada de baja · deuda pendiente</span>}
                {cuenta.bloqueada && <span className="pill red">Acceso bloqueado por mora</span>}
              </div>
            </div>
            <div className="cv-cuenta-total">
              <small>Debe en total</small>
              <b>{L(totalPendiente)}</b>
              {totalEnRevision > 0 && <small>+ {L(totalEnRevision)} en revisión</small>}
            </div>
            <button className="cv-cambiar" onClick={reiniciar}><RotateCcw size={14} /> Cambiar</button>
          </div>
        )}
      </div>

      {/* 2 · CONCEPTO */}
      {cuenta && (
        <div className="cv-bloque">
          <div className="cv-bloque-titulo"><span>2</span> ¿Qué paga?</div>
          {conceptos.length === 0 ? (
            <p className="cv-vacio"><Check size={15} /> Esta casa no debe nada. No hay nada que cobrar.</p>
          ) : (
            <div className="cv-conceptos" role="radiogroup" aria-label="Concepto a cobrar">
              {conceptos.map(c => (
                <label key={c.clave}
                  className={`cv-concepto ${clave === c.clave ? "sel" : ""} ${c.bloqueado ? "bloq" : ""}`}>
                  <input type="radio" name="cv-concepto" checked={clave === c.clave} disabled={!!c.bloqueado}
                    onChange={() => { setClave(c.clave); setRecibido(""); }} />
                  <span className="cv-concepto-texto">
                    <b>{c.titulo}</b>
                    <small>
                      {c.detalle}
                      {c.bloqueado ? <span className="pill amber"><FileClock size={12} /> En revisión</span>
                        : c.vencido ? <span className="pill red">Vencido</span> : <span className="pill">Al día</span>}
                    </small>
                    {c.nota && <small className="cv-concepto-nota">{c.nota}</small>}
                    {c.bloqueado && <small className="cv-concepto-nota">{c.bloqueado}</small>}
                  </span>
                  <span className="cv-concepto-monto">{L(c.monto)}</span>
                </label>
              ))}
            </div>
          )}
          {conceptos.length > 1 && conceptos.some(c => c.vencido) && (
            <p className="cv-ayuda">Conviene cobrar primero lo vencido: el acceso de la casa se desbloquea cuando no le queda nada vencido.</p>
          )}
        </div>
      )}

      {/* 3 · FORMA DE PAGO */}
      {concepto && !concepto.bloqueado && (
        <div className="cv-bloque">
          <div className="cv-bloque-titulo"><span>3</span> ¿Cómo paga?</div>
          <div className="cv-metodos" role="radiogroup" aria-label="Forma de pago">
            <button role="radio" aria-checked={metodo === "efectivo"} className={metodo === "efectivo" ? "sel" : ""}
              onClick={() => setMetodo("efectivo")}><Banknote size={18} /> Efectivo</button>
            <button role="radio" aria-checked={metodo === "tarjeta_pos"} className={metodo === "tarjeta_pos" ? "sel" : ""}
              onClick={() => setMetodo("tarjeta_pos")}><CreditCard size={18} /> Tarjeta (POS)</button>
          </div>

          {metodo === "efectivo" ? (
            <div className="cv-efectivo">
              <label className="cv-campo">
                <span>Efectivo recibido</span>
                <div className="cv-input-monto">
                  <i>L</i>
                  <input type="number" inputMode="decimal" min="0" step="0.01" value={recibido}
                    onChange={e => setRecibido(e.target.value)} placeholder={concepto.monto.toFixed(2)} />
                </div>
              </label>
              <div className="cv-billetes" aria-label="Montos rápidos">
                {sugerencias.map((v, i) => (
                  <button key={v} type="button" onClick={() => setRecibido(v.toFixed(2))}
                    className={montoRecibido === v ? "sel" : ""}>
                    {i === 0 ? "Exacto" : L(v).replace(".00", "")}
                  </button>
                ))}
              </div>
              <div className={`cv-vuelto ${!recibido ? "" : vuelto < 0 ? "falta" : "ok"}`} aria-live="polite">
                {!recibido ? <span>Escribí con cuánto paga para calcular el vuelto.</span>
                  : vuelto < 0 ? <><span>Faltan</span><b>{L(-vuelto)}</b></>
                  : <><span>Vuelto a entregar</span><b>{L(vuelto)}</b></>}
              </div>
            </div>
          ) : (
            <label className="cv-campo">
              <span>N.º de autorización del voucher</span>
              <input value={referencia} onChange={e => setReferencia(e.target.value)} maxLength={40}
                placeholder="Lo imprime la terminal POS" />
              <small>Pasá la tarjeta por {L(concepto.monto)} en la terminal y copiá el número de autorización.</small>
            </label>
          )}

          <button className="cv-revisar" disabled={!pagoValido} onClick={() => setRevisando(true)}>
            Revisar cobro de {L(concepto.monto)}
          </button>
        </div>
      )}

      {revisando && cuenta && concepto && (
        <ConfirmarCobro
          residencial={residencial} cajero={cajero} cuenta={cuenta} concepto={concepto}
          metodo={metodo} recibido={montoRecibido} vuelto={vuelto} referencia={referencia.trim()}
          onVolver={() => setRevisando(false)}
          onRegistrado={onRegistrado}
          onNuevo={() => { setRevisando(false); reiniciar(); }}
          onSeguirConCasa={async () => {
            setRevisando(false);
            try {
              const r = await buscarCuentaCaja(cuenta.identificador);
              const misma = r.find(x => x.cuenta_id === cuenta.cuenta_id);
              if (misma) elegirCuenta(misma); else reiniciar();
            } catch { reiniciar(); }
          }}
        />
      )}
    </section>
  );
}

const PASOS_PROCESO = ["Registrando el pago", "Asignando número de recibo", "Actualizando la cuenta de la casa"];

function ConfirmarCobro({
  residencial, cajero, cuenta, concepto, metodo, recibido, vuelto, referencia,
  onVolver, onRegistrado, onNuevo, onSeguirConCasa,
}: {
  residencial: string; cajero: string; cuenta: CuentaCajaDTO; concepto: Concepto;
  metodo: Metodo; recibido: number; vuelto: number; referencia: string;
  onVolver: () => void; onRegistrado: () => void; onNuevo: () => void; onSeguirConCasa: () => void;
}) {
  const [confirmo, setConfirmo] = useState(false);
  const [fase, setFase] = useState<"revisar" | "procesando" | "listo" | "error">("revisar");
  const [avance, setAvance] = useState(0);       // pasos del proceso ya hechos
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [error, setError] = useState("");
  const [ahora] = useState(() => new Date());
  const efectivo = metodo === "efectivo";

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && fase === "revisar") onVolver(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [fase, onVolver]);

  async function registrar() {
    setFase("procesando"); setAvance(0); setError("");
    try {
      let pago: { id: string; numero_recibo?: number | null } | undefined;
      if (concepto.tipo === "abono" && concepto.arregloId && concepto.abonoId) {
        const r = await cobrarAbono(concepto.arregloId, concepto.abonoId, metodo, referencia || undefined);
        pago = r.pago;
      } else if (concepto.cuotaId) {
        const r = await registrarPagoCaja({ cuota_id: concepto.cuotaId, metodo, referencia: referencia || undefined });
        pago = r.pago;
      }
      // El servidor ya hizo los tres pasos en una sola operación: se marcan
      // uno tras otro para que el cajero vea qué quedó registrado.
      for (let i = 1; i <= PASOS_PROCESO.length; i++) {
        setAvance(i);
        await new Promise(r => setTimeout(r, 260));
      }
      setResultado({ pagoId: pago?.id || "", recibo: pago?.numero_recibo, hora: new Date() });
      setFase("listo");
      onRegistrado();
    } catch (e) {
      setError((e as Error).message || "No se pudo registrar el cobro.");
      setFase("error");
    }
  }

  const numRecibo = resultado?.recibo ? `REC-${String(resultado.recibo).padStart(6, "0")}` : null;
  const ocupado = fase === "procesando";

  return (
    <div className="modal sal-fondo" onClick={() => fase === "revisar" && onVolver()}>
      <div className="sal-modal cv-modal" role="dialog" aria-modal="true" aria-labelledby="cv-modal-titulo"
        onClick={e => e.stopPropagation()}>
        <header className="sal-cabeza">
          <div>
            <h2 id="cv-modal-titulo">
              {fase === "listo" ? "Cobro registrado" : fase === "procesando" ? "Registrando el cobro…"
                : fase === "error" ? "No se registró el cobro" : "Confirmá el cobro"}
            </h2>
            <p>{fase === "revisar" ? "Revisá los datos con el residente antes de registrar."
              : fase === "listo" ? "El pago quedó registrado en esta caja." : `${cuenta.identificador} · ${concepto.titulo}`}</p>
          </div>
          {fase !== "procesando" && (
            <button className="sal-cerrar" onClick={fase === "listo" ? onNuevo : onVolver} aria-label="Cerrar"><X size={18} /></button>
          )}
        </header>

        <div className="sal-cuerpo">
          {/* El ticket: lo mismo que va a decir el recibo */}
          {(fase === "revisar" || fase === "listo") && (
            <article className={`cv-ticket ${fase === "listo" ? "cv-ticket--hecho" : ""}`} aria-label="Resumen del cobro">
              <div className="cv-ticket-cabeza">
                <b>{residencial}</b>
                <span>{fase === "listo" && numRecibo ? `Recibo ${numRecibo}` : "Cobro en ventanilla"}</span>
              </div>
              <dl className="cv-ticket-datos">
                <div><dt>Fecha</dt><dd>{(resultado?.hora || ahora).toLocaleString("es-HN", { dateStyle: "medium", timeStyle: "short" })}</dd></div>
                <div><dt>Cajero</dt><dd>{cajero}</dd></div>
                <div><dt>Casa</dt><dd>{cuenta.identificador}</dd></div>
                <div><dt>Titular</dt><dd>{cuenta.titular}</dd></div>
              </dl>
              <div className="cv-ticket-linea">
                <span><b>{concepto.titulo}</b><small>{concepto.detalle}</small></span>
                <span className="cv-ticket-monto">{L(concepto.monto)}</span>
              </div>
              <div className="cv-ticket-total">
                <span>Total</span><b>{L(concepto.monto)}</b>
              </div>
              <dl className="cv-ticket-datos cv-ticket-pago">
                <div><dt>Forma de pago</dt><dd>{efectivo ? "Efectivo" : "Tarjeta (POS)"}</dd></div>
                {efectivo ? <>
                  <div><dt>Recibido</dt><dd>{L(recibido)}</dd></div>
                  <div><dt>Vuelto</dt><dd>{L(Math.max(vuelto, 0))}</dd></div>
                </> : <div><dt>Autorización</dt><dd>{referencia}</dd></div>}
              </dl>
            </article>
          )}

          {fase === "revisar" && (
            <label className="sal-check cv-confirmo">
              <input type="checkbox" checked={confirmo} onChange={e => setConfirmo(e.target.checked)} />
              <span>{efectivo
                ? <>Recibí <b>{L(recibido)}</b> en efectivo{vuelto > 0 ? <> y voy a entregar <b>{L(vuelto)}</b> de vuelto</> : null}.</>
                : <>La terminal aprobó el voucher <b>{referencia}</b> por <b>{L(concepto.monto)}</b>.</>}</span>
            </label>
          )}

          {fase === "procesando" && (
            <ol className="sal-lista cv-proceso" aria-live="polite">
              {PASOS_PROCESO.map((p, i) => (
                <li key={p} className={i < avance ? "hecho" : i === avance ? "actual" : ""}>
                  <span className="sal-lista-marca">
                    {i < avance ? <Check size={14} strokeWidth={3} /> : i === avance ? <Loader2 size={14} className="sal-gira" /> : i + 1}
                  </span>
                  <div><b>{p}</b></div>
                </li>
              ))}
            </ol>
          )}

          {fase === "listo" && efectivo && vuelto > 0 && (
            <div className="cv-entregar" role="status">
              <Banknote size={22} /><span>Entregá el vuelto</span><b>{L(vuelto)}</b>
            </div>
          )}

          {fase === "error" && (
            <div className="sal-aviso sal-aviso--bloqueo" role="alert">
              <div className="sal-aviso-cabeza">
                <span className="sal-aviso-icono"><AlertTriangle size={22} /></span>
                <h4>El cobro no se registró</h4>
              </div>
              <div className="sal-aviso-texto">
                <p>{error}</p>
                <p>No se guardó ningún pago. {efectivo ? "Devolvé el efectivo si ya lo recibiste, o" : "Si la terminal ya cobró, anulá el voucher, o"} volvé atrás para revisarlo.</p>
              </div>
            </div>
          )}
        </div>

        <footer className="sal-pie">
          {fase === "revisar" && <>
            <button className="sal-btn sal-btn--fantasma" onClick={onVolver}><ArrowLeft size={16} /> Volver</button>
            <button className="sal-btn sal-btn--principal" disabled={!confirmo} onClick={registrar}>
              <ShieldCheck size={17} /> Registrar cobro de {L(concepto.monto)}
            </button>
          </>}
          {ocupado && <p className="sal-pie-nota">No cierres esta ventana mientras se registra.</p>}
          {fase === "error" && <>
            <button className="sal-btn sal-btn--fantasma" onClick={onVolver}><ArrowLeft size={16} /> Volver</button>
          </>}
          {fase === "listo" && <>
            <button className="sal-btn sal-btn--fantasma" onClick={onSeguirConCasa}>Seguir con {cuenta.identificador}</button>
            <span className="cv-pie-derecha">
              {resultado?.pagoId && (
                <a className="sal-btn sal-btn--secundario" href={urlReciboPDF(resultado.pagoId)} target="_blank" rel="noreferrer">
                  <Printer size={16} /> Imprimir recibo
                </a>
              )}
              <button className="sal-btn sal-btn--principal" onClick={onNuevo}>Nuevo cobro</button>
            </span>
          </>}
        </footer>
      </div>
    </div>
  );
}
