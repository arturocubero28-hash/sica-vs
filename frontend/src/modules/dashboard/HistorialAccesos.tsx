import { useState, useEffect } from "react";
import { historialAccesos, historialPagos, historialTarjetas, urlFotoGuardia, urlReciboPDF, urlComprobante, type HistorialDTO, type HistorialPagosDTO, type HistorialTarjetasDTO, type EventoHistorialDTO } from "../../api/client";
import { L } from "../../utils/formato";
import { Camera, Car, DollarSign, Footprints, IdCard, Paperclip, QrCode, Receipt, ScrollText } from "lucide-react";

export function HistorialAccesos() {
  const [tab, setTab] = useState<"accesos" | "tarjetas" | "pagos">("accesos");

  return (
    <div className="historial">
      <div className="dash-head"><h2>Historial</h2></div>

      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "accesos" ? "on" : ""}`} onClick={() => setTab("accesos")}>
          <QrCode size={16} /> Accesos de visitas
        </button>
        <button className={`hist-tab ${tab === "tarjetas" ? "on" : ""}`} onClick={() => setTab("tarjetas")}>
          <IdCard size={16} /> Accesos de residentes
        </button>
        <button className={`hist-tab ${tab === "pagos" ? "on" : ""}`} onClick={() => setTab("pagos")}>
          <DollarSign size={16} /> Pagos
        </button>
      </div>

      {tab === "accesos" && <TabAccesos />}
      {tab === "tarjetas" && <TabTarjetas />}
      {tab === "pagos" && <TabPagos />}
    </div>
  );
}

function TabAccesos() {
  const [data, setData] = useState<HistorialDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [direccion, setDireccion] = useState("");
  const [estado, setEstado] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);
  const [detalleVer, setDetalleVer] = useState<EventoHistorialDTO | null>(null);

  function cargar() {
    setCargando(true);
    historialAccesos({ desde, hasta, direccion, estado, buscar, pagina })
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, [pagina]);

  function aplicarFiltros() {
    setPagina(1);
    cargar();
  }
  function limpiar() {
    setDesde(""); setHasta(""); setDireccion(""); setEstado(""); setBuscar(""); setPagina(1);
    setTimeout(cargar, 0);
  }

  return (
    <>
      {/* Filtros */}
      <div className="historial-filtros">
        <div className="filtro-campo">
          <label>Desde</label>
          <input type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        </div>
        <div className="filtro-campo">
          <label>Hasta</label>
          <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
        </div>
        <div className="filtro-campo">
          <label>Dirección</label>
          <select value={direccion} onChange={e => setDireccion(e.target.value)}>
            <option value="">Todas</option>
            <option value="entrada">Entradas</option>
            <option value="salida">Salidas</option>
          </select>
        </div>
        <div className="filtro-campo">
          <label>Estado</label>
          <select value={estado} onChange={e => setEstado(e.target.value)}>
            <option value="">Todos</option>
            <option value="adentro">Dentro de la residencial</option>
          </select>
        </div>
        <div className="filtro-campo flex1">
          <label>Buscar</label>
          <input placeholder="Placa, visitante o unidad" value={buscar}
            onChange={e => setBuscar(e.target.value)} onKeyDown={e => e.key === "Enter" && aplicarFiltros()} />
        </div>
        <div className="filtro-botones">
          <button className="cuota-btn-pagar" style={{ maxWidth: 110 }} onClick={aplicarFiltros}>Filtrar</button>
          <button className="ghost mini" onClick={limpiar}>Limpiar</button>
        </div>
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : !data || data.eventos.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon"><ScrollText size={16} /></div>
          <p>No hay eventos que coincidan.</p>
        </div>
      ) : (
        <>
          <div className="dash-card">
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr><th>Fecha / Hora</th><th>Dirección</th><th>Visitante</th><th>Unidad</th>
                    <th>Acceso</th><th>Placa</th><th>Guardia</th><th></th></tr>
                </thead>
                <tbody>
                  {data.eventos.map(e => (
                    <tr key={e.id} className="fila-clickeable" onClick={() => setDetalleVer(e)}>
                      <td className="small">{new Date(e.ocurrido_en).toLocaleString("es-HN")}</td>
                      <td>
                        <span className={`pill ${e.direccion === "entrada" ? "green" : ""}`}>
                          {e.direccion === "entrada" ? "Entrada" : "Salida"}
                        </span>
                        {e.esta_adentro && <span className="pill green" style={{ marginLeft: 4 }}>Adentro</span>}
                      </td>
                      <td>{e.visitante}</td>
                      <td>{e.unidad}</td>
                      <td className="small">{e.punto_acceso || "—"}</td>
                      <td>
                        {e.en_vehiculo ? (e.placa || "—") : <span className="muted small">Peatonal</span>}
                        {e.placa_no_coincide && (
                          <span className="pill" style={{ background: "#fde2e2", color: "#b42318", marginLeft: 6, fontSize: 10 }}
                            title={`El guardia observó: ${e.placa_observada}`}>
                            ⚠ no coincide
                          </span>
                        )}
                      </td>
                      <td className="small">{e.guardia}</td>
                      <td>
                        <button className="mini" onClick={(ev) => { ev.stopPropagation(); setDetalleVer(e); }}>
                          Ver detalle →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Paginación */}
          <div className="paginacion">
            <button className="ghost mini" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>← Anterior</button>
            <span className="muted small">Página {data.pagina} de {data.total_paginas} · {data.total} eventos</span>
            <button className="ghost mini" disabled={pagina >= data.total_paginas} onClick={() => setPagina(p => p + 1)}>Siguiente →</button>
          </div>
        </>
      )}

      {detalleVer && (
        <ModalDetalleEvento evento={detalleVer} onCerrar={() => setDetalleVer(null)} />
      )}
    </>
  );
}

const TIPO_VISITA_LABEL: Record<string, string> = {
  unica: "Visita única", recurrente: "Visita recurrente", repartidor: "Repartidor / delivery",
};

function ModalDetalleEvento({ evento, onCerrar }: { evento: EventoHistorialDTO; onCerrar: () => void }) {
  const fotos = [
    { label: "Identidad", archivo: evento.foto_identidad },
    { label: "Placa", archivo: evento.foto_placa },
    { label: "Número asignado", archivo: evento.foto_numero_asignado },
  ].filter(f => f.archivo);

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 700 }}>
        <div className="modal-head">
          <h3>Detalle del acceso — {evento.visitante}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>

        <div className="detalle-grid" style={{ marginBottom: 16 }}>
          <Dato label="Dirección" valor={evento.direccion === "entrada" ? "Entrada" : "Salida"} />
          <Dato label="Fecha y hora" valor={new Date(evento.ocurrido_en).toLocaleString("es-HN")} />
          <Dato label="Punto de acceso" valor={evento.punto_acceso || "—"} />
          <Dato label="Tranca" valor={evento.tranca || "—"} />
          <Dato label="Registrado por (guardia)" valor={evento.guardia} />
          <Dato label="Autorizado por (residente)" valor={evento.autorizado_por || "—"} />
        </div>

        <div className="sub" style={{ marginBottom: 8 }}>Datos de la visita</div>
        <div className="detalle-grid" style={{ marginBottom: 16 }}>
          <Dato label="Nombre" valor={evento.visitante} />
          <Dato label="Unidad visitada" valor={evento.unidad} />
          <Dato label="Tipo de visita" valor={evento.tipo_visita ? (TIPO_VISITA_LABEL[evento.tipo_visita] || evento.tipo_visita) : "—"} />
          <Dato label="Documento de identidad" valor={evento.documento_id || "—"} />
          <Dato label="Teléfono" valor={evento.telefono || "—"} />
          {evento.empresa && <Dato label="Empresa" valor={evento.empresa} />}
          {evento.visita_creada_en && (
            <Dato label="Visita generada el" valor={new Date(evento.visita_creada_en).toLocaleString("es-HN")} />
          )}
        </div>

        {evento.en_vehiculo && (
          <>
            <div className="sub" style={{ marginBottom: 8 }}>Vehículo</div>
            <div className="detalle-grid" style={{ marginBottom: 16 }}>
              <Dato label="Placa declarada por el residente" valor={evento.placa || "—"} />
              <Dato label="Placa observada por el guardia" valor={evento.placa_observada || "—"} />
            </div>
            {evento.placa_no_coincide && (
              <div className="cuota-rechazo" style={{ marginBottom: 16 }}>
                <b>⚠ La placa observada no coincide con la declarada.</b>
                <span> Revisá las fotos para confirmar.</span>
              </div>
            )}
          </>
        )}

        {fotos.length > 0 && (
          <>
            <div className="sub" style={{ marginBottom: 8 }}>Fotos del ingreso</div>
            <div className="fotos-ingreso-grid">
              {fotos.map((f, i) => (
                <div key={i} className="foto-ingreso-item">
                  <span className="muted small">{f.label}</span>
                  <img src={urlFotoGuardia(f.archivo!)} alt={f.label}
                    onClick={() => window.open(urlFotoGuardia(f.archivo!), "_blank")} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const METODO_LABEL: Record<string, string> = {
  efectivo: "Efectivo", tarjeta_pos: "Tarjeta POS", transferencia: "Transferencia", linea: "En línea",
};

function TabPagos() {
  const [data, setData] = useState<HistorialPagosDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [metodo, setMetodo] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);

  function cargar() {
    setCargando(true);
    historialPagos({ desde, hasta, metodo, buscar, pagina })
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, [pagina]);

  function aplicarFiltros() { setPagina(1); cargar(); }
  function limpiar() {
    setDesde(""); setHasta(""); setMetodo(""); setBuscar(""); setPagina(1);
    setTimeout(cargar, 0);
  }


  return (
    <>
      <div className="historial-filtros">
        <div className="filtro-campo">
          <label>Desde</label>
          <input type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        </div>
        <div className="filtro-campo">
          <label>Hasta</label>
          <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
        </div>
        <div className="filtro-campo">
          <label>Método</label>
          <select value={metodo} onChange={e => setMetodo(e.target.value)}>
            <option value="">Todos</option>
            <option value="efectivo">Efectivo</option>
            <option value="tarjeta_pos">Tarjeta POS</option>
            <option value="transferencia">Transferencia</option>
            <option value="linea">En línea</option>
          </select>
        </div>
        <div className="filtro-campo flex1">
          <label>Buscar</label>
          <input placeholder="Casa o titular" value={buscar}
            onChange={e => setBuscar(e.target.value)} onKeyDown={e => e.key === "Enter" && aplicarFiltros()} />
        </div>
        <div className="filtro-botones">
          <button className="cuota-btn-pagar" style={{ maxWidth: 110 }} onClick={aplicarFiltros}>Filtrar</button>
          <button className="ghost mini" onClick={limpiar}>Limpiar</button>
        </div>
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : !data || data.pagos.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon"><DollarSign size={16} /></div>
          <p>No hay pagos que coincidan.</p>
        </div>
      ) : (
        <>
          <div className="dash-card">
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr><th>Fecha / Hora</th><th>Casa</th><th>Titular</th><th>Monto</th><th>Método</th><th>Cobrado por</th><th>Recibo</th></tr>
                </thead>
                <tbody>
                  {data.pagos.map(p => (
                    <tr key={p.id}>
                      <td className="small">{new Date(p.fecha).toLocaleString("es-HN")}</td>
                      <td>{p.identificador}</td>
                      <td>{p.titular}</td>
                      <td><b>{L(p.monto)}</b></td>
                      <td><span className="pill">{METODO_LABEL[p.metodo] || p.metodo}</span></td>
                      <td className="small">{p.cobrado_por}</td>
                      <td>
                        <a className="mini" href={urlReciboPDF(p.id)} target="_blank" rel="noreferrer"
                          style={{ textDecoration: "none" }}><Receipt size={16} /> Recibo</a>
                        {p.comprobante_archivo && (
                          <a className="mini ghost" href={urlComprobante(p.comprobante_archivo)}
                            target="_blank" rel="noreferrer"
                            style={{ textDecoration: "none", marginLeft: 6 }}><Paperclip size={16} /> Comprobante</a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="paginacion">
            <button className="ghost mini" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>← Anterior</button>
            <span className="muted small">Página {data.pagina} de {data.total_paginas} · {data.total} pagos</span>
            <button className="ghost mini" disabled={pagina >= data.total_paginas} onClick={() => setPagina(p => p + 1)}>Siguiente →</button>
          </div>
        </>
      )}
    </>
  );
}

function TabTarjetas() {
  const [data, setData] = useState<HistorialTarjetasDTO | null>(null);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [direccion, setDireccion] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    historialTarjetas({ desde, hasta, direccion, buscar, pagina })
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }, [desde, hasta, direccion, buscar, pagina]);

  return (
    <>
      <div className="hist-filtros">
        <input type="date" value={desde} onChange={e => { setDesde(e.target.value); setPagina(1); }} />
        <input type="date" value={hasta} onChange={e => { setHasta(e.target.value); setPagina(1); }} />
        <select value={direccion} onChange={e => { setDireccion(e.target.value); setPagina(1); }}>
          <option value="">Entrada y salida</option>
          <option value="entrada">Solo entradas</option>
          <option value="salida">Solo salidas</option>
        </select>
        <input placeholder="Buscar residente, casa o tarjeta…" value={buscar}
          onChange={e => { setBuscar(e.target.value); setPagina(1); }} />
      </div>

      {cargando ? <p className="muted">Cargando…</p> : !data || data.eventos.length === 0 ? (
        <div className="empty-state">
          <p className="muted">No hay accesos por tarjeta registrados todavía.</p>
          <p className="muted small">
            Acá aparecerán las entradas y salidas de residentes cuando el sistema
            de acceso por tarjeta esté en operación.
          </p>
        </div>
      ) : (
        <>
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr><th>Fecha / Hora</th><th>Residente</th><th>Casa</th><th>Tarjeta</th><th>Tipo</th><th>Acceso</th><th>Dirección</th></tr>
              </thead>
              <tbody>
                {data.eventos.map(e => (
                  <tr key={e.id}>
                    <td className="small">{new Date(e.ocurrido_en).toLocaleString("es-HN")}</td>
                    <td>{e.residente}</td>
                    <td>{e.unidad}</td>
                    <td><code>{e.tarjeta}</code></td>
                    <td>
                      <span className={`pill ${e.tipo_acceso === "peatonal" ? "" : "green"}`}>
                        {e.tipo_acceso === "peatonal" ? "<Footprints size={16} /> Peatonal" : "<Car size={16} /> Vehicular"}
                      </span>
                    </td>
                    <td className="small">{e.acceso}</td>
                    <td>
                      <span className={`pill ${e.direccion === "entrada" ? "green" : ""}`}>
                        {e.direccion === "entrada" ? "↓ Entrada" : "↑ Salida"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total_paginas > 1 && (
            <div className="paginacion">
              <button className="mini" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>← Anterior</button>
              <span className="muted small">Página {data.pagina} de {data.total_paginas}</span>
              <button className="mini" disabled={pagina >= data.total_paginas} onClick={() => setPagina(p => p + 1)}>Siguiente →</button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Dato({ label, valor }: { label: string; valor: string }) {
  return (
    <div className="dato">
      <span className="muted small">{label}</span>
      <b>{valor}</b>
    </div>
  );
}
