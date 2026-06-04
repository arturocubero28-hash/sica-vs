import { useState, useEffect } from "react";
import { historialAccesos, historialPagos, type HistorialDTO, type HistorialPagosDTO } from "../../api/client";

export function HistorialAccesos() {
  const [tab, setTab] = useState<"accesos" | "pagos">("accesos");

  return (
    <div className="historial">
      <div className="dash-head"><h2>Historial</h2></div>

      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "accesos" ? "on" : ""}`} onClick={() => setTab("accesos")}>
          📜 Accesos
        </button>
        <button className={`hist-tab ${tab === "pagos" ? "on" : ""}`} onClick={() => setTab("pagos")}>
          💰 Pagos
        </button>
      </div>

      {tab === "accesos" ? <TabAccesos /> : <TabPagos />}
    </div>
  );
}

function TabAccesos() {
  const [data, setData] = useState<HistorialDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [direccion, setDireccion] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);

  function cargar() {
    setCargando(true);
    historialAccesos({ desde, hasta, direccion, buscar, pagina })
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, [pagina]);

  function aplicarFiltros() {
    setPagina(1);
    cargar();
  }
  function limpiar() {
    setDesde(""); setHasta(""); setDireccion(""); setBuscar(""); setPagina(1);
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
          <div className="cuota-vacia-icon">📜</div>
          <p>No hay eventos que coincidan.</p>
        </div>
      ) : (
        <>
          <div className="dash-card">
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr><th>Fecha / Hora</th><th>Dirección</th><th>Visitante</th><th>Unidad</th><th>Placa</th><th>Guardia</th></tr>
                </thead>
                <tbody>
                  {data.eventos.map(e => (
                    <tr key={e.id}>
                      <td className="small">{new Date(e.ocurrido_en).toLocaleString("es-HN")}</td>
                      <td>
                        <span className={`pill ${e.direccion === "entrada" ? "green" : ""}`}>
                          {e.direccion === "entrada" ? "Entrada" : "Salida"}
                        </span>
                      </td>
                      <td>{e.visitante}</td>
                      <td>{e.unidad}</td>
                      <td>{e.placa || "—"}</td>
                      <td className="small">{e.guardia}</td>
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
    </>
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

  function L(n: number) {
    return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
          <div className="cuota-vacia-icon">💰</div>
          <p>No hay pagos que coincidan.</p>
        </div>
      ) : (
        <>
          <div className="dash-card">
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr><th>Fecha / Hora</th><th>Casa</th><th>Titular</th><th>Monto</th><th>Método</th><th>Cobrado por</th></tr>
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
