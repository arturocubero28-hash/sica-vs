import { useEffect, useState } from "react";
import { Check, X, AlertTriangle, Handshake, Ban, Landmark, ShieldCheck, RefreshCw } from "lucide-react";
import {
  cancelarArreglo, cambiarPropositoArreglo, type ArregloDTO, type PropositoArreglo,
} from "../../api/client";
import { Aviso } from "../unidades/SalidaSistema";

/* Día 75 — detalle de un arreglo, en el mismo lenguaje que el asistente
   de creación y que «Salida del sistema». La cancelación se explica adentro
   del mismo modal, en vez de abrir un segundo modal encima. */

const L = (n: number) =>
  `L ${n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fecha = (iso: string) =>
  new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString("es-HN", { day: "numeric", month: "short", year: "numeric" });

const ESTADO: Record<ArregloDTO["estado"], { texto: string; clase: string }> = {
  activo: { texto: "Activo", clase: "green" },
  completado: { texto: "Completado", clase: "" },
  incumplido: { texto: "Incumplido", clase: "red" },
  cancelado: { texto: "Cancelado", clase: "amber" },
};
const PROPOSITO: Record<PropositoArreglo, string> = {
  ponerse_al_dia: "Ponerse al día y seguir pagando",
  volver_al_padron: "Saldar la deuda y volver al padrón",
};

export function DetalleArreglo({ arreglo, onCerrar, onCambio }: {
  arreglo: ArregloDTO; onCerrar: () => void; onCambio: (a: ArregloDTO) => void;
}) {
  const [vista, setVista] = useState<"detalle" | "cancelar">("detalle");
  const [motivo, setMotivo] = useState("");
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !trabajando) onCerrar(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [trabajando, onCerrar]);

  const activo = arreglo.estado === "activo";
  const abonos = arreglo.abonos || [];
  const proximo = abonos.find(a => a.estado !== "pagado");
  const pagados = abonos.filter(a => a.estado === "pagado").length;
  const vencidos = abonos.filter(a => a.estado === "vencido").length;

  async function cambiarProposito() {
    const nuevo: PropositoArreglo = arreglo.proposito === "volver_al_padron" ? "ponerse_al_dia" : "volver_al_padron";
    setTrabajando(true); setError("");
    try { onCambio(await cambiarPropositoArreglo(arreglo.id, nuevo)); }
    catch (e) { setError((e as Error).message); }
    finally { setTrabajando(false); }
  }

  async function cancelar() {
    if (!motivo.trim()) { setError("Escribí el motivo de la cancelación."); return; }
    setTrabajando(true); setError("");
    try { onCambio(await cancelarArreglo(arreglo.id, motivo.trim())); setVista("detalle"); }
    catch (e) { setError((e as Error).message); }
    finally { setTrabajando(false); }
  }

  return (
    <div className="modal sal-fondo" onClick={() => !trabajando && onCerrar()}>
      <div className="sal-modal" role="dialog" aria-modal="true" aria-labelledby="arr-det-titulo"
        onClick={e => e.stopPropagation()}>
        <header className="sal-cabeza">
          <div>
            <h2 id="arr-det-titulo">Arreglo de pago · {arreglo.unidad}</h2>
            <p>Titular: {arreglo.titular} · <span className={`pill ${ESTADO[arreglo.estado].clase}`}>{ESTADO[arreglo.estado].texto}</span></p>
          </div>
          <button className="sal-cerrar" onClick={onCerrar} disabled={trabajando} aria-label="Cerrar"><X size={18} /></button>
        </header>

        <div className="sal-cuerpo" key={vista}>
          {vista === "detalle" && (
            <>
              {/* Lo más importante, en grande */}
              {activo && arreglo.atrasado ? (
                <Aviso tono="bloqueo" icono={<AlertTriangle size={24} />} titulo="Tiene abonos atrasados" monto={arreglo.saldo_pendiente}>
                  <p>{vencidos === 1 ? "1 abono vencido" : `${vencidos} abonos vencidos`}. Si se atrasa más de {arreglo.dias_gracia} días,
                    el arreglo queda incumplido.</p>
                </Aviso>
              ) : activo ? (
                <Aviso tono="info" icono={<Handshake size={24} />} titulo="Falta pagar" monto={arreglo.saldo_pendiente}>
                  {proximo && <p>Próximo abono: <b>{L(proximo.monto)}</b> el <b>{fecha(proximo.fecha_pactada)}</b>.</p>}
                </Aviso>
              ) : arreglo.estado === "completado" ? (
                <Aviso tono="ok" icono={<Check size={24} />} titulo="Arreglo pagado completo" monto={arreglo.total_abonado} />
              ) : arreglo.estado === "incumplido" ? (
                <Aviso tono="bloqueo" icono={<Ban size={24} />} titulo="Arreglo incumplido" monto={arreglo.saldo_pendiente}>
                  <p>{arreglo.motivo_cierre}. Las cuotas volvieron a quedar pendientes
                    {arreglo.proposito === "volver_al_padron" ? " a nombre del titular (si la casa está en el padrón, no se le bloquea el portón)." : " y la casa se bloqueó."}
                    {" "}Lo abonado ({L(arreglo.total_abonado)}) quedó acreditado.</p>
                </Aviso>
              ) : (
                <Aviso tono="cobrar" icono={<Ban size={24} />} titulo="Arreglo cancelado">
                  <p>{arreglo.motivo_cierre || "Se canceló."} Lo abonado ({L(arreglo.total_abonado)}) quedó acreditado.</p>
                </Aviso>
              )}

              {/* Los abonos como línea de tiempo */}
              <section>
                <h3 className="arr-sub">Abonos · {pagados} de {abonos.length} pagados</h3>
                <ol className="sal-lista arr-linea">
                  {abonos.map(ab => {
                    const clase = ab.estado === "pagado" ? "hecho" : ab.estado === "vencido" ? "vencido"
                      : activo && ab.id === proximo?.id ? "actual" : "";
                    return (
                      <li key={ab.id} className={clase}>
                        <span className="sal-lista-marca">
                          {ab.estado === "pagado" ? <Check size={14} strokeWidth={3} /> : ab.estado === "vencido" ? "!" : ab.numero}
                        </span>
                        <div className="arr-linea-fila">
                          <span>
                            <b>{L(ab.monto)}</b>
                            <small>{ab.estado === "pagado" && ab.pagado_en ? `Pagado el ${fecha(ab.pagado_en)}`
                              : ab.estado === "vencido" ? `Venció el ${fecha(ab.fecha_pactada)}`
                              : `Vence el ${fecha(ab.fecha_pactada)}`}</small>
                          </span>
                          <span className={`pill ${ab.estado === "pagado" ? "green" : ab.estado === "vencido" ? "red" : "amber"}`}>
                            {ab.estado === "pagado" ? "Pagado" : ab.estado === "vencido" ? "Vencido" : "Pendiente"}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ol>
                {activo && (
                  <p className="arr-nota"><Landmark size={15} /><span>Los abonos se cobran en <b>Caja</b>, o el residente sube su comprobante desde la app.</span></p>
                )}
              </section>

              {/* Los números y el historial */}
              <dl className="arr-cuentas arr-cuentas--detalle">
                <div><dt>Para qué se firmó</dt><dd>{PROPOSITO[arreglo.proposito] || "—"}</dd></div>
                {arreglo.meses_incluidos && arreglo.meses_incluidos.length > 0 && (
                  <div><dt>Cuotas incluidas</dt><dd>{arreglo.meses_incluidos.map(m => m.mes_label).join(", ")}</dd></div>
                )}
                {arreglo.descuento_monto > 0 && <>
                  <div><dt>Deuda de las cuotas</dt><dd>{L(arreglo.deuda_original)}</dd></div>
                  <div className="desc"><dt>Descuento ({arreglo.descuento_pct} %)</dt><dd>− {L(arreglo.descuento_monto)}</dd></div>
                </>}
                <div><dt>Deuda del arreglo</dt><dd>{L(arreglo.deuda_total)}</dd></div>
                <div><dt>Abonado</dt><dd>{L(arreglo.total_abonado)}</dd></div>
                <div className="total"><dt>Falta</dt><dd>{L(arreglo.saldo_pendiente)}</dd></div>
              </dl>
              {arreglo.descuento_autorizado_por && (
                <p className="arr-nota"><ShieldCheck size={15} /><span>Descuento autorizado por <b>{arreglo.descuento_autorizado_por}</b>
                  {arreglo.descuento_autorizado_en && ` el ${new Date(arreglo.descuento_autorizado_en).toLocaleString("es-HN")}`}.</span></p>
              )}
              {arreglo.nota && <p className="arr-nota arr-nota--texto">{arreglo.nota}</p>}
            </>
          )}

          {vista === "cancelar" && (
            <>
              <Aviso tono="bloqueo" icono={<AlertTriangle size={24} />} titulo="¿Cancelar este arreglo?">
                <p>Las cuotas que tenía vuelven a quedar pendientes. Si alguna ya venció, la casa se bloquea
                  de nuevo. Lo ya abonado ({L(arreglo.total_abonado)}) queda acreditado.</p>
                <p>Si la familia solo cambió de idea sobre para qué lo firmó, no hace falta cancelar:
                  se puede <b>cambiar el propósito</b>.</p>
              </Aviso>
              <label className="sal-campo">
                <span>Motivo de la cancelación (queda en el historial)</span>
                <textarea value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} autoFocus
                  placeholder="Acordado con el titular: cambia a otro plan" />
              </label>
            </>
          )}

          {error && <div className="sal-error" role="alert"><AlertTriangle size={16} /> {error}</div>}
        </div>

        {activo && (
          <footer className="sal-pie">
            {vista === "detalle" ? (
              <>
                <button className="sal-btn sal-btn--fantasma arr-btn-cancelar" disabled={trabajando}
                  onClick={() => { setMotivo(""); setError(""); setVista("cancelar"); }}>
                  <Ban size={16} /> Cancelar arreglo
                </button>
                <button className="sal-btn sal-btn--secundario" onClick={cambiarProposito} disabled={trabajando}>
                  <RefreshCw size={16} className={trabajando ? "sal-gira" : ""} />
                  {arreglo.proposito === "volver_al_padron" ? "Cambiar a: ponerse al día" : "Cambiar a: volver al padrón"}
                </button>
              </>
            ) : (
              <>
                <button className="sal-btn sal-btn--fantasma" onClick={() => { setError(""); setVista("detalle"); }} disabled={trabajando}>
                  Volver
                </button>
                <button className="sal-btn sal-btn--peligro" onClick={cancelar} disabled={trabajando}>
                  {trabajando ? "Cancelando…" : "Sí, cancelar el arreglo"}
                </button>
              </>
            )}
          </footer>
        )}
      </div>
    </div>
  );
}
