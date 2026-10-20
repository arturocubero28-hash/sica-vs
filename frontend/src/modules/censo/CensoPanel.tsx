import { useState, useEffect, Fragment } from "react";
import {
  listarCenso, crearCasaCenso, agregarPersonaCenso, convertirCasaCenso,
  darAccesoPersona, subirFotoResidente, urlFotoResidente, listarTarifas,
  listarUnidades,
  type Cuenta, type ResidenteDTO, type Tarifa, type ResumenPadron, type Unidad,
} from "../../api/client";
import {
  UserPlus, Camera, ArrowUpRight, ChevronDown, ChevronRight, Home, Building2,
} from "lucide-react";

/**
 * Panel del Padrón (Censo) — Día 69.
 *
 * El patronato no puede obligar a nadie a enrolarse ni a pagar la cuota.
 * Pero si las casas que no participan quedan fuera del sistema, sus
 * accesos se registran como aperturas manuales anónimas y se pierde la
 * trazabilidad justo donde más falta hace.
 *
 * Acá se cargan esas casas: existen para que el guardia identifique a su
 * gente, pero NO generan cuotas, NO entran en mora y NO reciben avisos de
 * cobro. Cuando una familia decide sumarse, se convierte la casa y las
 * cuotas arrancan desde ese mes — nunca hacia atrás.
 */

function MsgBanner({ msg, onClose }: { msg: { tipo: "ok" | "err"; texto: string } | null; onClose?: () => void }) {
  if (!msg) return null;
  return (
    <div className={`msg-banner msg-banner-${msg.tipo}`} role="alert">
      <span>{msg.tipo === "err" ? "⚠ " : "✓ "}{msg.texto}</span>
      {onClose && <button className="msg-banner-close" onClick={onClose}>✕</button>}
    </div>
  );
}

export function CensoPanel() {
  const [casas, setCasas] = useState<Cuenta[]>([]);
  const [resumen, setResumen] = useState<ResumenPadron | null>(null);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);

  const [modalCasa, setModalCasa] = useState(false);
  const [modalPersona, setModalPersona] = useState<Cuenta | null>(null);
  const [modalConvertir, setModalConvertir] = useState<Cuenta | null>(null);
  const [modalAcceso, setModalAcceso] = useState<{ casa: Cuenta; persona: ResidenteDTO } | null>(null);

  function recargar() {
    setCargando(true);
    listarCenso()
      .then(r => { setCasas(r.casas); setResumen(r.resumen ?? null); })
      .catch(e => setMsg({ tipo: "err", texto: (e as Error).message }))
      .finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  const q = busqueda.trim().toLowerCase();
  const filtradas = casas.filter(c => {
    if (!q) return true;
    const gente = (c.residentes || []).map(r => r.nombre).join(" ");
    return `${c.nombre_completo || c.identificador || ""} ${c.apartamento || ""} ${gente}`.toLowerCase().includes(q);
  });

  // Día 70 — un edificio del padrón tiene la MISMA forma que en el alta
  // normal, porque convertirlo es un cambio de modo y no una migración:
  //   - dueño que solo administra -> cuenta contenedora ("edificio_contenedor"),
  //     que nunca paga cuota;
  //   - dueño que vive ahí        -> su apartamento es la administración
  //     ("edificio_admin"), y no hay contenedora;
  //   - inquilinos                -> apartamentos ("apartamento").
  // Se agrupan bajo una cabecera por edificio, con la administración
  // primero, igual que en "Casas y residentes".
  const esDeEdificio = (c: Cuenta) => c.tipo_cuenta === "edificio_contenedor"
    || c.tipo_cuenta === "edificio_admin" || c.tipo_cuenta === "apartamento";
  const sueltas = filtradas.filter(c => !esDeEdificio(c));
  const porEdificio = new Map<string, Cuenta[]>();
  for (const c of filtradas) {
    if (!esDeEdificio(c)) continue;
    const clave = c.identificador || "—";
    porEdificio.set(clave, [...(porEdificio.get(clave) || []), c]);
  }
  const orden = (c: Cuenta) =>
    c.tipo_cuenta === "edificio_contenedor" ? 0 : c.tipo_cuenta === "edificio_admin" ? 1 : 2;
  for (const lista of porEdificio.values()) {
    lista.sort((a, b) => orden(a) - orden(b)
      || (a.apartamento || "").localeCompare(b.apartamento || "", "es", { numeric: true }));
  }
  /** Quién es el dueño y si vive ahí, para la cabecera del edificio. */
  function dueno(lista: Cuenta[]): string {
    const cont = lista.find(c => c.tipo_cuenta === "edificio_contenedor");
    if (cont?.titular) return `Dueño: ${cont.titular.nombre} · solo administra`;
    const adm = lista.find(c => c.tipo_cuenta === "edificio_admin");
    if (adm?.titular) return `Dueño: ${adm.titular.nombre} · vive en el apto ${adm.apartamento}`;
    return "Sin dueño registrado";
  }

  const totalPersonas = casas.reduce((n, c) => n + (c.residentes?.length || 0), 0);

  return (
    <div className="censo-panel">
      <div className="lista-head">
        <h2>Padrón de la residencial</h2>
        <button className="btn-accion" onClick={() => setModalCasa(true)}>+ Agregar al padrón</button>
      </div>

      <p className="muted small" style={{ marginTop: -4, marginBottom: 12, maxWidth: 680 }}>
        Estas casas están registradas solo para dejar constancia de quién entra y sale.
        No se les genera cuota, no entran en mora y no reciben avisos de cobro.
        Cuando una familia decida sumarse, convertila y las cuotas empiezan desde ese mes.
      </p>

      {msg && (
        <div style={{ position: "sticky", top: 8, zIndex: 20, marginBottom: 12 }}>
          <MsgBanner msg={msg} onClose={() => setMsg(null)} />
        </div>
      )}

      {/* Métrica de adopción. Es el número que el patronato pide en cada
          reunión, y conviene que sea visible acá y no en un reporte aparte:
          "cuánta gente está dentro del sistema" y "cuánta además paga" son
          dos cosas distintas, y la primera ya tiene valor sin la segunda —
          una casa del censo tiene sus accesos registrados igual. */}
      {resumen && resumen.total > 0 && (
        <div className="metric-grid small" style={{ marginBottom: 14 }}>
          <div className="mini-metric">
            <div className="mini-valor">{resumen.total}</div>
            <div className="mini-label">Casas en el sistema</div>
          </div>
          <div className="mini-metric">
            <div className="mini-valor">{resumen.completas}</div>
            <div className="mini-label">Participan con cuota ({resumen.pct_completas}%)</div>
          </div>
          <div className="mini-metric">
            <div className="mini-valor">{resumen.censo}</div>
            <div className="mini-label">Solo padrón</div>
          </div>
          <div className="mini-metric">
            <div className="mini-valor">{resumen.convertidas}</div>
            <div className="mini-label">Se sumaron desde el padrón</div>
          </div>
        </div>
      )}

      <div className="lista-card">
        <div className="casas-filtros">
          <input className="casas-buscar" placeholder="Buscar por casa o por nombre…"
            value={busqueda} onChange={e => setBusqueda(e.target.value)} />
        </div>
        <div className="casas-contador muted small">
          {filtradas.length} de {casas.length} casas · {totalPersonas} persona(s) en el padrón
        </div>

        {cargando ? <p className="muted">Cargando…</p> : filtradas.length === 0 ? (
          <div className="cuota-vacia">
            <Home size={28} className="cuota-vacia-icon" />
            <p className="muted">
              {casas.length === 0
                ? "Todavía no hay casas en el padrón. Agregá la primera para empezar a registrar accesos de las familias que no usan el sistema."
                : "Ninguna casa coincide con la búsqueda."}
            </p>
          </div>
        ) : (
          <div className="scroll-x">
            <table className="data tabla-casas">
              <thead>
                <tr><th>Casa</th><th>Personas</th><th>Titular</th><th></th></tr>
              </thead>
              <tbody>
                {/* Primero las casas sueltas; después cada edificio con su
                    administración y sus apartamentos colgando. */}
                {[
                  ...sueltas.map(c => ({ casa: c, sangria: false })),
                  ...[...porEdificio.entries()].flatMap(([nombre, lista]) => [
                    { encabezado: nombre,
                      aptos: lista.filter(c => c.tipo_cuenta !== "edificio_contenedor").length,
                      dueno: dueno(lista) },
                    ...lista.map(c => ({ casa: c, sangria: true })),
                  ]),
                ].map((fila, i) => {
                  // Cabecera de edificio: no es una familia, es el edificio.
                  if ("encabezado" in fila) {
                    return (
                      <tr key={`ed-${fila.encabezado}-${i}`} className="censo-fila-edificio">
                        <td colSpan={4}>
                          <div className="casa-cell">
                            <Building2 size={15} />
                            <div className="casa-cell-txt">
                              <span className="casa-id">{fila.encabezado}</span>
                              <span className="casa-titular">
                                Edificio · {fila.dueno} · {fila.aptos === 0
                                  ? "sin apartamentos en el padrón"
                                  : `${fila.aptos} apartamento${fila.aptos === 1 ? "" : "s"}`}
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  }
                  const casa = fila.casa;
                  const sangria = fila.sangria;
                  const esContenedora = casa.tipo_cuenta === "edificio_contenedor";
                  const expandida = abierta === casa.id;
                  const gente = casa.residentes || [];
                  return (
                    <Fragment key={casa.id}>
                      <tr className={sangria ? "censo-fila-apto" : undefined}>
                        <td>
                          <div className="casa-cell">
                            <button className="icono-accion"
                              onClick={() => setAbierta(expandida ? null : casa.id)}
                              title={expandida ? "Ocultar personas" : "Ver personas"}>
                              {expandida ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <div className="casa-cell-txt">
                              <span className="casa-id">
                                {esContenedora
                                  ? "Administración del edificio"
                                  : casa.tipo_cuenta === "edificio_admin"
                                    ? `Apto ${casa.apartamento} · vive el dueño`
                                    : casa.tipo_cuenta === "apartamento"
                                      ? `Apto ${casa.apartamento}`
                                      : (casa.nombre_completo || casa.identificador || "—")}
                              </span>
                              {/* Se dice cuántas personas hay y que se toca
                                  para verlas. La fila se expandía con un
                                  chevron sin explicación, así que las fotos
                                  y los miembros quedaban escondidos ahí. */}
                              <span className="casa-titular">
                                Solo padrón · {gente.length === 0
                                  ? "sin personas"
                                  : `tocá para ver ${gente.length === 1
                                      ? "la persona y su foto"
                                      : `las ${gente.length} personas y sus fotos`}`}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td><span className="pill">{gente.length}</span></td>
                        <td className="small">{casa.titular?.nombre || "—"}</td>
                        <td>
                          {/* Botones CON TEXTO a propósito. Antes eran dos
                              íconos pelados, uno al lado del otro, que solo
                              se distinguían pasando el mouse por encima --
                              en la práctica, invisibles: nadie encontraba
                              dónde agregar a los familiares. */}
                          <div className="casa-acciones">
                            {/* La administración de un edificio cuyo dueño
                                no vive ahí no tiene familia que agregar: es
                                solo el dueño, igual que en el alta normal. */}
                            {!esContenedora && (
                              <button className="btn-tabla btn-tabla-neutro"
                                title="Agregar un familiar o miembro"
                                onClick={() => setModalPersona(casa)}>
                                <UserPlus size={14} /> Agregar persona
                              </button>
                            )}
                            <button className="btn-tabla btn-tabla-ok"
                              title={esContenedora
                                ? "El dueño se suma al sistema; no paga cuota"
                                : "Esta familia decidió sumarse al sistema y pagar cuota"}
                              onClick={() => setModalConvertir(casa)}>
                              <ArrowUpRight size={14} /> Sumar al sistema
                            </button>
                          </div>
                        </td>
                      </tr>
                      {expandida && (
                        <tr>
                          <td colSpan={4} style={{ background: "var(--fondo-suave, #f8f9fa)" }}>
                            <FilaPersonas
                              casa={casa}
                              onMsg={setMsg}
                              onCambio={recargar}
                              onDarAcceso={p => setModalAcceso({ casa, persona: p })}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalCasa && (
        <ModalCasaCenso
          onCerrar={() => setModalCasa(false)}
          onListo={(nombre) => {
            setModalCasa(false); recargar();
            setMsg({ tipo: "ok", texto: `${nombre} quedó registrada en el padrón.` });
          }}
          onError={t => setMsg({ tipo: "err", texto: t })}
        />
      )}

      {modalPersona && (
        <ModalPersonaCenso
          casa={modalPersona}
          onCerrar={() => setModalPersona(null)}
          onListo={(nombre) => {
            setModalPersona(null); recargar();
            setMsg({ tipo: "ok", texto: `${nombre} se agregó al padrón.` });
          }}
          onError={t => setMsg({ tipo: "err", texto: t })}
        />
      )}

      {modalConvertir && (
        <ModalConvertir
          casa={modalConvertir}
          onCerrar={() => setModalConvertir(null)}
          onListo={(nota) => {
            setModalConvertir(null); recargar();
            setMsg({ tipo: "ok", texto: nota });
          }}
          onError={t => setMsg({ tipo: "err", texto: t })}
        />
      )}

      {modalAcceso && (
        <ModalDarAcceso
          persona={modalAcceso.persona}
          onCerrar={() => setModalAcceso(null)}
          onListo={(texto) => {
            setModalAcceso(null); recargar();
            setMsg({ tipo: "ok", texto });
          }}
          onError={t => setMsg({ tipo: "err", texto: t })}
        />
      )}
    </div>
  );
}

// ─── Lista de personas de una casa, con su foto ──────────────────────────
function FilaPersonas({ casa, onMsg, onCambio, onDarAcceso }: {
  casa: Cuenta;
  onMsg: (m: { tipo: "ok" | "err"; texto: string }) => void;
  onCambio: () => void;
  onDarAcceso: (p: ResidenteDTO) => void;
}) {
  const [subiendo, setSubiendo] = useState<string | null>(null);
  const gente = casa.residentes || [];

  async function subirFoto(persona: ResidenteDTO, archivo: File) {
    setSubiendo(persona.id);
    try {
      await subirFotoResidente(casa.id, persona.id, archivo);
      onCambio();
      onMsg({ tipo: "ok", texto: `Foto de ${persona.nombre} actualizada.` });
    } catch (e) {
      onMsg({ tipo: "err", texto: (e as Error).message });
    } finally {
      setSubiendo(null);
    }
  }

  if (gente.length === 0) return <p className="muted small">Esta casa no tiene personas registradas.</p>;

  return (
    <div className="censo-personas">
      {gente.map(p => (
        <div key={p.id} className="censo-persona">
          {/* La foto la captura administración. El residente la verá en su
              perfil pero no puede cambiarla: es la que el guardia usa para
              verificar identidad en el portón. */}
          <div className="censo-foto">
            {p.foto_url
              ? <img src={urlFotoResidente(p.foto_url)} alt={p.nombre} className="preview-img" />
              : <span className="casa-icono">{(p.nombre_solo || p.nombre || "?").charAt(0).toUpperCase()}</span>}
          </div>

          <div className="casa-cell-txt" style={{ flex: 1 }}>
            <span className="casa-id">
              {p.nombre}
              {p.rol_cuenta === "titular" && <span className="pill" style={{ marginLeft: 8 }}>Titular</span>}
            </span>
            <span className="casa-titular small muted">
              {p.dni ? `Identidad ${p.dni}` : "Sin identidad registrada"}
              {p.telefono ? ` · ${p.telefono}` : ""}
            </span>
          </div>

          <div className="casa-acciones">
            <label className="icono-accion" title={p.foto_url ? "Reemplazar la foto" : "Tomar o subir la foto"}
              style={{ cursor: subiendo === p.id ? "wait" : "pointer" }}>
              <Camera size={16} />
              <input type="file" accept="image/*" capture="environment" style={{ display: "none" }}
                disabled={subiendo === p.id}
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) subirFoto(p, f);
                  e.target.value = "";
                }} />
            </label>

            {p.es_censo && (
              <button className="icono-accion" title="Darle acceso a la app"
                onClick={() => onDarAcceso(p)}>
                <ArrowUpRight size={16} />
              </button>
            )}
            {!p.es_censo && <span className="pill green">Con acceso</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Modal: alta de casa en el padrón ────────────────────────────────────
function ModalCasaCenso({ onCerrar, onListo, onError }: {
  onCerrar: () => void; onListo: (nombre: string) => void; onError: (t: string) => void;
}) {
  // Día 70 — mismas tres formas que el alta normal. Un edificio se registra
  // PRIMERO, con su dueño, y después sus apartamentos: si el padrón armara
  // los edificios de otra manera, al convertirlos a cuenta completa
  // aterrizarían en "Casas y residentes" con una forma que el resto del
  // sistema no sabe mostrar.
  const [tipo, setTipo] = useState<"casa" | "edificio" | "apartamento">("casa");
  const [identificador, setIdentificador] = useState("");
  const [maxAptos, setMaxAptos] = useState("");
  const [duenoVive, setDuenoVive] = useState<boolean | null>(null);
  const [edificioId, setEdificioId] = useState("");
  const [apartamento, setApartamento] = useState("");
  const [edificios, setEdificios] = useState<Unidad[]>([]);
  const [nombre, setNombre] = useState("");
  const [apellido, setApellido] = useState("");
  const [dni, setDni] = useState("");
  const [telefono, setTelefono] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    listarUnidades()
      .then(us => setEdificios(us.filter(u => u.tipo === "edificio")))
      .catch(() => { /* sin lista, el formulario de apartamento lo avisa */ });
  }, []);

  async function guardar() {
    if (!nombre.trim()) { onError("Indicá el nombre del titular"); return; }
    if (tipo === "casa" && !identificador.trim()) {
      onError("Indicá el identificador de la casa"); return;
    }
    if (tipo === "edificio") {
      if (!identificador.trim()) { onError("Indicá el nombre del edificio"); return; }
      if (duenoVive === null) { onError("Indicá si el dueño vive en el edificio o solo lo administra"); return; }
      if (duenoVive && !apartamento.trim()) { onError("Indicá en qué apartamento vive el dueño"); return; }
    }
    if (tipo === "apartamento") {
      if (!edificioId) { onError("Elegí el edificio"); return; }
      if (!apartamento.trim()) { onError("Indicá el número de apartamento"); return; }
    }

    setGuardando(true);
    try {
      await crearCasaCenso({
        tipo,
        identificador: tipo === "apartamento" ? undefined : identificador.trim(),
        unidad_id: tipo === "apartamento" ? edificioId : undefined,
        apartamento: (tipo === "apartamento" || (tipo === "edificio" && duenoVive))
          ? apartamento.trim() : undefined,
        dueno_vive: tipo === "edificio" ? !!duenoVive : undefined,
        max_apartamentos: tipo === "edificio" && maxAptos ? Number(maxAptos) : undefined,
        titular: {
          nombre: nombre.trim(), apellido: apellido.trim(),
          dni: dni.trim() || undefined, telefono: telefono.trim() || undefined,
        },
      });
      const nombreEd = edificios.find(e => e.id === edificioId)?.identificador ?? "El edificio";
      onListo(tipo === "apartamento" ? `${nombreEd} · Apto ${apartamento.trim()}` : identificador.trim());
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  const etiquetaTitular = tipo === "edificio" ? "Nombre del dueño del edificio" : "Nombre del titular";

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Agregar al padrón</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <p className="muted small">
          No se pide tarifa ni día de pago: en el padrón nadie paga. Solo queda
          registrado para que sus accesos tengan nombre.
        </p>

        <div className="form-field">
          <label>¿Qué estás registrando?</label>
          <div className="tabs" style={{ marginBottom: 0 }}>
            <button type="button" className={tipo === "casa" ? "tab on" : "tab"}
              onClick={() => setTipo("casa")}>Casa</button>
            <button type="button" className={tipo === "edificio" ? "tab on" : "tab"}
              onClick={() => setTipo("edificio")}>Edificio</button>
            <button type="button" className={tipo === "apartamento" ? "tab on" : "tab"}
              onClick={() => setTipo("apartamento")}>Apartamento</button>
          </div>
        </div>

        {tipo === "casa" && (
          <div className="form-field">
            <label>Casa</label>
            <input value={identificador} onChange={e => setIdentificador(e.target.value)}
              placeholder="Casa 24" />
          </div>
        )}

        {tipo === "edificio" && (
          <>
            <p className="muted small" style={{ marginTop: 0 }}>
              Primero se registra el edificio con su dueño. Los inquilinos se
              agregan después, cada uno como "Apartamento".
            </p>
            <div className="form-field">
              <label>Nombre del edificio</label>
              <input value={identificador} onChange={e => setIdentificador(e.target.value)}
                placeholder="Edificio Las Palmas" />
            </div>
            <div className="form-field">
              <label>Cantidad de apartamentos (opcional)</label>
              <input type="number" min={1} value={maxAptos}
                onChange={e => setMaxAptos(e.target.value)} placeholder="12" />
            </div>
            <div className="form-field">
              {/* La misma pregunta que el alta normal. Define la forma del
                  edificio: si el dueño solo administra, su cuenta nunca
                  paga cuota; si vive ahí, paga como su apartamento. */}
              <label>¿El dueño vive en el edificio?</label>
              <div className="tabs" style={{ marginBottom: 0 }}>
                <button type="button" className={duenoVive === false ? "tab on" : "tab"}
                  onClick={() => setDuenoVive(false)}>No, solo lo administra</button>
                <button type="button" className={duenoVive === true ? "tab on" : "tab"}
                  onClick={() => setDuenoVive(true)}>Sí, vive en un apartamento</button>
              </div>
              {duenoVive === false && (
                <p className="muted small" style={{ marginTop: 6 }}>
                  Cuando se sume al sistema no se le va a generar cuota.
                </p>
              )}
            </div>
            {duenoVive === true && (
              <div className="form-field">
                <label>Apartamento donde vive el dueño</label>
                <input value={apartamento} onChange={e => setApartamento(e.target.value)}
                  placeholder="1A" />
              </div>
            )}
          </>
        )}

        {tipo === "apartamento" && (
          edificios.length === 0 ? (
            <p className="muted small">
              Todavía no hay edificios registrados. Registrá primero el edificio
              con su dueño (opción "Edificio") y después sus apartamentos.
            </p>
          ) : (
            <>
              <div className="form-field">
                <label>Edificio</label>
                <select value={edificioId} onChange={e => setEdificioId(e.target.value)}>
                  <option value="">— Elegí el edificio —</option>
                  {edificios.map(ed => (
                    <option key={ed.id} value={ed.id}>{ed.identificador}</option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label>Apartamento</label>
                <input value={apartamento} onChange={e => setApartamento(e.target.value)}
                  placeholder="2B" />
              </div>
            </>
          )
        )}

        {!(tipo === "apartamento" && edificios.length === 0) && (
          <>
            <div className="form-field">
              <label>{etiquetaTitular}</label>
              <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Juan" />
            </div>
            <div className="form-field">
              <label>Apellido</label>
              <input value={apellido} onChange={e => setApellido(e.target.value)} placeholder="Pérez" />
            </div>
            <div className="form-field">
              {/* Muy recomendada: es con lo que el guardia compara cuando la
                  persona llega sin código a pedir que le abran. */}
              <label>Identidad (la usa el guardia para verificar en el portón)</label>
              <input value={dni} onChange={e => setDni(e.target.value)} placeholder="0000-0000-00000" />
            </div>
            <div className="form-field">
              <label>Teléfono (opcional)</label>
              <input value={telefono} onChange={e => setTelefono(e.target.value)} placeholder="9999-9999" />
            </div>
            <button onClick={guardar} disabled={guardando}>
              {guardando ? "Guardando…" : "Agregar al padrón"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Modal: agregar persona a una casa del padrón ────────────────────────
function ModalPersonaCenso({ casa, onCerrar, onListo, onError }: {
  casa: Cuenta; onCerrar: () => void; onListo: (n: string) => void; onError: (t: string) => void;
}) {
  const [nombre, setNombre] = useState("");
  const [apellido, setApellido] = useState("");
  const [dni, setDni] = useState("");
  const [relacion, setRelacion] = useState("familiar");
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    if (!nombre.trim()) { onError("El nombre es obligatorio"); return; }
    setGuardando(true);
    try {
      await agregarPersonaCenso(casa.id, {
        nombre: nombre.trim(), apellido: apellido.trim(),
        dni: dni.trim() || undefined, relacion,
      });
      onListo(`${nombre.trim()} ${apellido.trim()}`.trim());
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Agregar persona a {casa.nombre_completo || casa.identificador}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <div className="form-field">
          <label>Nombre</label>
          <input value={nombre} onChange={e => setNombre(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Apellido</label>
          <input value={apellido} onChange={e => setApellido(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Identidad (opcional)</label>
          <input value={dni} onChange={e => setDni(e.target.value)} placeholder="0000-0000-00000" />
        </div>
        <div className="form-field">
          <label>Relación</label>
          <select value={relacion} onChange={e => setRelacion(e.target.value)}>
            <option value="familiar">Familiar</option>
            <option value="hijo">Hijo / hija</option>
            <option value="conyuge">Cónyuge</option>
            <option value="inquilino">Inquilino</option>
            <option value="otro">Otro</option>
          </select>
        </div>
        <button onClick={guardar} disabled={guardando}>
          {guardando ? "Guardando…" : "Agregar"}
        </button>
      </div>
    </div>
  );
}

// ─── Modal: convertir la casa a participación completa ───────────────────
function ModalConvertir({ casa, onCerrar, onListo, onError }: {
  casa: Cuenta; onCerrar: () => void; onListo: (nota: string) => void; onError: (t: string) => void;
}) {
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [tarifaId, setTarifaId] = useState<number | "">("");
  const [diaPago, setDiaPago] = useState(1);
  const [guardando, setGuardando] = useState(false);
  // Día 70 — la administración de un edificio cuyo dueño no vive ahí no
  // paga cuota nunca (igual que en el alta normal): no se le pide tarifa.
  const esContenedora = casa.tipo_cuenta === "edificio_contenedor";
  const titulo = esContenedora
    ? `${casa.identificador} · administración`
    : (casa.nombre_completo || casa.identificador);

  useEffect(() => {
    if (!esContenedora) listarTarifas().then(setTarifas).catch(() => setTarifas([]));
  }, [esContenedora]);

  async function convertir() {
    setGuardando(true);
    try {
      const r = await convertirCasaCenso(casa.id, esContenedora ? {} : {
        tarifa_id: tarifaId === "" ? undefined : Number(tarifaId),
        dia_pago: diaPago,
      });
      onListo(`${titulo} ya participa del sistema. ${r.nota}`);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{titulo} se suma al sistema</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        {esContenedora ? (
          <div className="ok-box">
            El dueño solo administra el edificio, así que <strong>no se le genera
            cuota</strong>. Las cuotas las pagan los apartamentos.
          </div>
        ) : (
        <>
        <div className="ok-box">
          Las cuotas empiezan a generarse <strong>desde el mes en curso</strong>.
          No se le cobran los meses en que estuvo solo en el padrón.
        </div>
        <div className="form-field">
          <label>Tarifa</label>
          <select value={tarifaId} onChange={e => setTarifaId(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Elegí una tarifa…</option>
            {tarifas.map(t => (
              <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label>Día de pago</label>
          <input type="number" min={1} max={30} value={diaPago}
            onChange={e => setDiaPago(Number(e.target.value))} />
        </div>
        </>
        )}
        <p className="muted small">
          Después de convertirla, dale acceso a la app a cada persona que lo necesite
          desde la lista de la casa.
        </p>
        <button onClick={convertir} disabled={guardando}>
          {guardando ? "Convirtiendo…" : "Sumar al sistema"}
        </button>
      </div>
    </div>
  );
}

// ─── Modal: dar acceso a la app a una persona del padrón ─────────────────
function ModalDarAcceso({ persona, onCerrar, onListo, onError }: {
  persona: ResidenteDTO; onCerrar: () => void; onListo: (t: string) => void; onError: (t: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function dar() {
    if (!email.trim()) { onError("El correo es obligatorio"); return; }
    setGuardando(true);
    try {
      await darAccesoPersona(persona.id, email.trim());
      onListo(`${persona.nombre} ya puede usar la app. Se le envió el enlace para que defina su contraseña.`);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Dar acceso a {persona.nombre}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <p className="muted small">
          Se le crea el acceso sobre su misma ficha, así que conserva todo su
          historial de entradas y salidas. Va a recibir un correo para definir
          su contraseña.
        </p>
        <div className="form-field">
          <label>Correo</label>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            placeholder="persona@correo.com" />
        </div>
        <button onClick={dar} disabled={guardando}>
          {guardando ? "Creando acceso…" : "Dar acceso a la app"}
        </button>
      </div>
    </div>
  );
}
