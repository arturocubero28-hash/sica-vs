import { useState, useEffect } from "react";
import { reporteFinanciero, reporteMoraPorCasa, reporteCaja, reporteAccesos, reporteInventario,
  type ReporteFinancieroDTO, type MoraPorCasaDTO, type CasaMoraDTO,
  type ReporteCajaDTO, type ReporteAccesosDTO, type ReporteInventarioDTO } from "../../api/client";
import { L } from "../../utils/formato";
import { GraficoBarras, GraficoDona, GraficoLinea, GraficoBarrasCant } from "./Graficos";

// Devuelve [primerDía, últimoDía] del mes actual en formato YYYY-MM-DD,
// para inicializar los filtros de fecha de los reportes con el mes corriente.
function rangoMesActual(): [string, string] {
  const hoy = new Date();
  const primero = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  const ultimo = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0);
  const fmt = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
  };
  return [fmt(primero), fmt(ultimo)];
}

export function Reporteria() {
  const [tab, setTab] = useState<"financiero" | "mora" | "caja" | "accesos" | "inventario">("financiero");
  return (
    <div className="reporteria">
      <div className="historial-tabs" style={{ marginBottom: 14 }}>
        <button className={`htab ${tab === "financiero" ? "activo" : ""}`} onClick={() => setTab("financiero")}>
          💰 Financiero
        </button>
        <button className={`htab ${tab === "mora" ? "activo" : ""}`} onClick={() => setTab("mora")}>
          📋 Mora y cartera
        </button>
        <button className={`htab ${tab === "caja" ? "activo" : ""}`} onClick={() => setTab("caja")}>
          🏦 Caja y arqueo
        </button>
        <button className={`htab ${tab === "accesos" ? "activo" : ""}`} onClick={() => setTab("accesos")}>
          🛡️ Accesos y seguridad
        </button>
        <button className={`htab ${tab === "inventario" ? "activo" : ""}`} onClick={() => setTab("inventario")}>
          🎟️ Inventario
        </button>
      </div>
      {tab === "financiero" && <ReporteFinancieroVista />}
      {tab === "mora" && <ReporteMoraPorCasa />}
      {tab === "caja" && <ReporteCajaVista />}
      {tab === "accesos" && <ReporteAccesosVista />}
      {tab === "inventario" && <ReporteInventarioVista />}
    </div>
  );
}

function ReporteFinancieroVista() {
  const hoy = new Date();
  const [modo, setModo] = useState<"mes" | "rango">("mes");
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [data, setData] = useState<ReporteFinancieroDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  function cargar(a = anio, m = mes) {
    setCargando(true);
    if (modo === "rango" && desde && hasta) {
      reporteFinanciero(undefined, undefined, desde, hasta)
        .then(setData).catch(() => {}).finally(() => setCargando(false));
    } else {
      reporteFinanciero(a, m).then(setData).catch(() => {}).finally(() => setCargando(false));
    }
  }

  useEffect(() => { cargar(); }, []);

  if (cargando) return <p className="muted">Cargando reporte…</p>;
  if (!data) return <p className="muted">No se pudo cargar el reporte.</p>;

  const meses = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
  ];
  const anios = Array.from({ length: 3 }, (_, i) => hoy.getFullYear() - i);

  async function exportarPDF() {
    const { jsPDF } = await import("jspdf");
    const autoTable = (await import("jspdf-autotable")).default;
    const doc = new jsPDF();

    doc.setFillColor(2, 46, 69);
    doc.rect(0, 0, 210, 28, "F");
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(18);
    doc.text("Reporte Financiero", 14, 13);
    doc.setFontSize(10);
    doc.setTextColor(245, 197, 24);
    doc.text("Residencial Villas del Sol", 14, 21);

    doc.setTextColor(40, 52, 64);
    doc.setFontSize(12);
    doc.text(`Periodo: ${data!.mes_label}`, 14, 38);
    doc.setFontSize(10);
    doc.text(`Total esperado: ${L(data!.total_esperado)}`, 14, 46);
    doc.text(`Total recaudado: ${L(data!.total_recaudado)}`, 14, 52);
    doc.text(`Total pendiente: ${L(data!.total_pendiente)}`, 14, 58);
    doc.text(`Cobranza: ${data!.pct_cobranza}%`, 14, 64);

    autoTable(doc, {
      startY: 72,
      head: [["Unidad", "Titular", "Monto", "Días atraso"]],
      body: data!.morosos.map(m => [m.unidad, m.titular, L(m.monto), String(m.dias_atraso)]),
      headStyles: { fillColor: [244, 135, 35] },
      didDrawPage: () => {
        doc.setFontSize(11);
        doc.setTextColor(200, 30, 30);
        doc.text("Cuentas en mora", 14, 70);
      },
    });

    doc.save(`reporte-financiero-${data!.mes_label.replace(/\s/g, "-")}.pdf`);
  }

  async function exportarExcel() {
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();

    const resumen = [
      ["Reporte Financiero — Villas del Sol"],
      ["Periodo", data!.mes_label],
      [],
      ["Total esperado", data!.total_esperado],
      ["Total recaudado", data!.total_recaudado],
      ["Total pendiente", data!.total_pendiente],
      ["Cobranza %", data!.pct_cobranza],
      ["Cuentas al día", data!.cuentas_al_dia],
      ["Cuentas morosas", data!.cuentas_morosas],
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumen), "Resumen");

    const morosos = [
      ["Unidad", "Titular", "Monto", "Estado", "Vencimiento", "Días atraso"],
      ...data!.morosos.map(m => [m.unidad, m.titular, m.monto, m.estado, m.vencimiento, m.dias_atraso]),
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(morosos), "Morosos");

    const alDia = [
      ["Unidad", "Titular", "Monto"],
      ...data!.al_dia.map(a => [a.unidad, a.titular, a.monto]),
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(alDia), "Al día");

    XLSX.writeFile(wb, `reporte-financiero-${data!.mes_label.replace(/\s/g, "-")}.xlsx`);
  }

  const maxTend = Math.max(...data.tendencia.map(t => t.esperado), 1);
  const esRango = data.modo === "rango";

  return (
    <>
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Reportería financiera</h2>
          <span className="muted">{data.mes_label}</span>
        </div>
        <div className="reporte-controles">
          <select className="periodo-select" value={modo}
            onChange={e => setModo(e.target.value as "mes" | "rango")}>
            <option value="mes">Por mes</option>
            <option value="rango">Por rango de fechas</option>
          </select>

          {modo === "mes" ? (
            <>
              <select className="periodo-select" value={mes} onChange={e => setMes(Number(e.target.value))}>
                {meses.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
              </select>
              <select className="periodo-select" value={anio} onChange={e => setAnio(Number(e.target.value))}>
                {anios.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </>
          ) : (
            <>
              <input className="periodo-select" type="date" value={desde}
                onChange={e => setDesde(e.target.value)} title="Desde" />
              <input className="periodo-select" type="date" value={hasta}
                onChange={e => setHasta(e.target.value)} title="Hasta" />
            </>
          )}

          <button className="ghost mini" onClick={() => cargar()}>Ver →</button>
          <div className="reporte-export">
            <button className="ghost mini" onClick={exportarPDF}>⬇ PDF</button>
            <button className="ghost mini" onClick={exportarExcel}>⬇ Excel</button>
          </div>
        </div>
      </div>


      {/* Tarjetas de resumen */}
      {esRango ? (
        <div className="metric-grid">
          <div className="metric-card verde">
            <div className="metric-top"><span className="metric-label">Recaudado en el período</span><span className="metric-icon">✓</span></div>
            <div className="metric-valor" style={{ fontSize: 22 }}>{L(data.total_recaudado)}</div>
          </div>
          <div className="metric-card azul">
            <div className="metric-top"><span className="metric-label">Cantidad de pagos</span><span className="metric-icon">#</span></div>
            <div className="metric-valor" style={{ fontSize: 22 }}>{data.total_pagos ?? 0}</div>
          </div>
        </div>
      ) : (
      <div className="metric-grid">
        <div className="metric-card azul">
          <div className="metric-top"><span className="metric-label">Esperado</span><span className="metric-icon">L</span></div>
          <div className="metric-valor" style={{ fontSize: 22 }}>{L(data.total_esperado)}</div>
        </div>
        <div className="metric-card verde">
          <div className="metric-top"><span className="metric-label">Recaudado</span><span className="metric-icon">✓</span></div>
          <div className="metric-valor" style={{ fontSize: 22 }}>{L(data.total_recaudado)}</div>
        </div>
        <div className="metric-card naranja">
          <div className="metric-top"><span className="metric-label">Pendiente</span><span className="metric-icon">!</span></div>
          <div className="metric-valor" style={{ fontSize: 22 }}>{L(data.total_pendiente)}</div>
        </div>
        <div className={`metric-card ${data.pct_cobranza >= 70 ? "verde" : "rojo"}`}>
          <div className="metric-top"><span className="metric-label">Cobranza</span><span className="metric-icon">%</span></div>
          <div className="metric-valor">{data.pct_cobranza}%</div>
        </div>
      </div>
      )}

      {/* Barra de progreso de cobranza (solo modo mes) */}
      {!esRango && (
      <div className="cobranza-bar-wrap">
        <div className="cobranza-bar-label">
          <span>{data.cuentas_al_dia} al día</span>
          <span>{data.cuentas_morosas} en mora</span>
        </div>
        <div className="cobranza-bar">
          <div className="cobranza-fill" style={{ width: `${data.pct_cobranza}%` }} />
        </div>
      </div>
      )}

      {/* Gráficos */}
      {!esRango && (
        <div className="graficos-grid">
          <GraficoBarras titulo="Esperado · Recaudado · Pendiente" datos={[
            { nombre: "Esperado", valor: data.total_esperado, color: "#044a6e" },
            { nombre: "Recaudado", valor: data.total_recaudado, color: "#1d8a4a" },
            { nombre: "Pendiente", valor: data.total_pendiente, color: "#F48723" },
          ]} />
          {data.recaudado_por_metodo && (
            <GraficoDona titulo="Recaudado por método de pago" datos={[
              { nombre: "Efectivo", valor: data.recaudado_por_metodo.efectivo },
              { nombre: "Tarjeta/POS", valor: data.recaudado_por_metodo.tarjeta_pos },
              { nombre: "Transferencia", valor: data.recaudado_por_metodo.transferencia },
              { nombre: "En línea", valor: data.recaudado_por_metodo.linea },
            ]} />
          )}
        </div>
      )}
      {!esRango && data.tendencia && data.tendencia.length > 0 && (
        <div className="graficos-grid uno">
          <GraficoLinea titulo="Recaudación últimos meses (esperado vs recaudado)"
            datos={data.tendencia.map(t => ({ nombre: t.mes_label, esperado: t.esperado, recaudado: t.recaudado }))} />
        </div>
      )}

      {/* Desglose de lo recaudado por método de pago */}
      {data.recaudado_por_metodo && (
        <div className="dash-card">
          <h3>Recaudado por método de pago</h3>
          <p className="muted small">Desglose de los {L(data.total_recaudado)} recaudados en {data.mes_label}.</p>
          <div className="metodo-grid">
            <div className="metodo-item">
              <span className="metodo-icon" style={{ background: "#e6f7ee", color: "#1d8a4a" }}>💵</span>
              <div className="metodo-info">
                <span className="muted small">Efectivo (ventanilla)</span>
                <b>{L(data.recaudado_por_metodo.efectivo)}</b>
              </div>
            </div>
            <div className="metodo-item">
              <span className="metodo-icon" style={{ background: "#fff3e6", color: "#9a6700" }}>💳</span>
              <div className="metodo-info">
                <span className="muted small">Tarjeta POS</span>
                <b>{L(data.recaudado_por_metodo.tarjeta_pos)}</b>
              </div>
            </div>
            <div className="metodo-item">
              <span className="metodo-icon" style={{ background: "#e6f0fa", color: "#044a6e" }}>🏦</span>
              <div className="metodo-info">
                <span className="muted small">Transferencia (aprobada)</span>
                <b>{L(data.recaudado_por_metodo.transferencia)}</b>
              </div>
            </div>
            <div className="metodo-item">
              <span className="metodo-icon" style={{ background: "#f3e8fc", color: "#7c3aed" }}>🌐</span>
              <div className="metodo-info">
                <span className="muted small">Pago en línea (plataforma)</span>
                <b>{L(data.recaudado_por_metodo.linea)}</b>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tendencia (solo modo mes) */}
      {!esRango && (
      <div className="dash-card">
        <h3>Recaudación últimos 6 meses</h3>
        <div className="tendencia-chart">
          {data.tendencia.map((t, i) => (
            <div key={i} className="tend-col">
              <div className="tend-bars">
                <div className="tend-bar esperado" style={{ height: `${(t.esperado / maxTend) * 100}%` }} title={`Esperado: ${L(t.esperado)}`} />
                <div className="tend-bar recaudado" style={{ height: `${(t.recaudado / maxTend) * 100}%` }} title={`Recaudado: ${L(t.recaudado)}`} />
              </div>
              <span className="tend-label">{t.mes_label}</span>
            </div>
          ))}
        </div>
        <div className="tend-leyenda">
          <span><i className="leg esperado" /> Esperado</span>
          <span><i className="leg recaudado" /> Recaudado</span>
        </div>
      </div>
      )}

      {/* Detalle de pagos (solo modo rango) */}
      {esRango && (
      <div className="dash-card">
        <h3>Detalle de pagos del período ({data.total_pagos ?? 0})</h3>
        <p className="muted small">Pagos recibidos entre las fechas seleccionadas, ordenados por fecha.</p>
        {(data.detalle_pagos?.length ?? 0) === 0 ? (
          <p className="muted">No hubo pagos en este período.</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Fecha</th><th>Unidad</th><th>Titular</th><th>Método</th><th>Monto</th></tr></thead>
              <tbody>
                {data.detalle_pagos!.map((p, i) => (
                  <tr key={i}>
                    <td className="small">{p.fecha ? new Date(p.fecha).toLocaleDateString("es-HN") : "—"}</td>
                    <td>{p.unidad}</td>
                    <td>{p.titular}</td>
                    <td><span className="pill">{p.metodo}</span></td>
                    <td>{L(p.monto)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

      {/* Morosos (solo modo mes) */}
      {!esRango && (
      <div className="dash-card">
        <h3 style={{ color: "#c81e1e" }}>Cuentas en mora ({data.morosos.length})</h3>
        {data.morosos.length === 0 ? (
          <p className="muted">Ninguna cuenta en mora este mes. 🎉</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Unidad</th><th>Titular</th><th>Monto</th><th>Días atraso</th></tr></thead>
              <tbody>
                {data.morosos.map((m, i) => (
                  <tr key={i}>
                    <td>{m.unidad}</td>
                    <td>{m.titular}</td>
                    <td>{L(m.monto)}</td>
                    <td>{m.dias_atraso > 0 ? <span className="pill red">{m.dias_atraso} días</span> : <span className="pill amber">Por vencer</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

      {/* Al día (solo modo mes) */}
      {!esRango && (
      <div className="dash-card">
        <h3 style={{ color: "#1d8a4a" }}>Cuentas al día ({data.al_dia.length})</h3>
        {data.al_dia.length === 0 ? (
          <p className="muted">Aún no hay pagos aprobados este mes.</p>
        ) : (
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Unidad</th><th>Titular</th><th>Monto</th></tr></thead>
              <tbody>
                {data.al_dia.map((a, i) => (
                  <tr key={i}><td>{a.unidad}</td><td>{a.titular}</td><td>{L(a.monto)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}
    </>
  );
}

function ReporteMoraPorCasa() {
  const [data, setData] = useState<MoraPorCasaDTO | null>(null);
  const [cargando, setCargando] = useState(true);
  const [expandida, setExpandida] = useState<string | null>(null);
  const [buscar, setBuscar] = useState("");

  useEffect(() => {
    reporteMoraPorCasa().then(setData).catch(() => {}).finally(() => setCargando(false));
  }, []);

  async function exportarPDF() {
    if (!data) return;
    const { jsPDF } = await import("jspdf");
    const autoTable = (await import("jspdf-autotable")).default;
    const doc = new jsPDF();
    doc.setFontSize(16); doc.setTextColor("#022E45");
    doc.text("Reporte de Mora por Casa", 14, 20);
    doc.setFontSize(10); doc.setTextColor("#6b7280");
    doc.text("Residencial Villas del Sol", 14, 27);
    doc.text(`Generado: ${new Date(data.generado).toLocaleDateString("es-HN")}`, 14, 33);
    doc.text(`Total adeudado: ${L(data.total_general_adeudado)}  ·  ${data.total_casas_mora} casas en mora`, 14, 39);
    let startY = 45;
    if (data.aging) {
      autoTable(doc, {
        startY: 45,
        head: [["Antigüedad de la deuda", "Monto"]],
        body: [
          ["1 – 30 días", L(data.aging.d_1_30)],
          ["31 – 60 días", L(data.aging.d_31_60)],
          ["61 – 90 días", L(data.aging.d_61_90)],
          ["90+ días (difícil cobro)", L(data.aging.d_90_mas)],
        ],
        theme: "grid", headStyles: { fillColor: [2, 46, 69] }, styles: { fontSize: 8 },
      });
      startY = (doc as any).lastAutoTable.finalY + 6;
    }
    const filas: string[][] = [];
    data.casas.forEach(c => {
      const meses = c.meses.map(m => m.mes_label).join(", ");
      filas.push([c.unidad, c.titular, c.telefono || "—", String(c.cantidad_meses), meses, L(c.total_adeudado)]);
    });
    autoTable(doc, {
      startY,
      head: [["Casa", "Titular", "Teléfono", "Meses", "Períodos que debe", "Total"]],
      body: filas,
      styles: { fontSize: 7 },
      headStyles: { fillColor: [244, 135, 35] },
      columnStyles: { 4: { cellWidth: 55 } },
    });
    doc.save(`mora-por-casa-${data.generado}.pdf`);
  }

  async function exportarExcel() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();

    // Hoja 1: resumen + antigüedad de la deuda (aging)
    const resumen: (string | number)[][] = [
      ["Reporte de Mora por Casa"],
      ["Residencial Villas del Sol"],
      ["Generado", new Date(data.generado).toLocaleDateString("es-HN")],
      [],
      ["Total adeudado", data.total_general_adeudado],
      ["Casas en mora", data.total_casas_mora],
    ];
    if (typeof data.pct_morosidad === "number") resumen.push(["% de morosidad", data.pct_morosidad]);
    if (data.aging) {
      resumen.push([], ["Antigüedad de la deuda", "Monto"]);
      resumen.push(["1 – 30 días", data.aging.d_1_30]);
      resumen.push(["31 – 60 días", data.aging.d_31_60]);
      resumen.push(["61 – 90 días", data.aging.d_61_90]);
      resumen.push(["90+ días (difícil cobro)", data.aging.d_90_mas]);
    }
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumen), "Resumen");

    // Hoja 2: detalle por casa
    const detalle: (string | number)[][] = [
      ["Casa", "Titular", "Teléfono", "Meses adeudados", "Días de atraso", "Períodos que debe", "Total adeudado"],
    ];
    data.casas.forEach(c => {
      detalle.push([
        c.unidad, c.titular, c.telefono || "—",
        c.cantidad_meses, c.max_dias_atraso,
        c.meses.map(m => m.mes_label).join(", "),
        c.total_adeudado,
      ]);
    });
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(detalle), "Detalle por casa");

    XLSX.writeFile(wb, `mora-por-casa-${data.generado}.xlsx`);
  }

  if (cargando) return <p className="muted">Cargando reporte de mora…</p>;
  if (!data) return <p className="muted">No se pudo cargar el reporte.</p>;

  const casasFiltradas = data.casas.filter((c: CasaMoraDTO) => {
    if (!buscar) return true;
    const b = buscar.toLowerCase();
    return c.unidad.toLowerCase().includes(b) || c.titular.toLowerCase().includes(b);
  });

  return (
    <>
      <div className="dash-header-pro">
        <div>
          <h2 className="dash-titulo">Mora por casa</h2>
          <span className="muted">{data.total_casas_mora} casas deben · {L(data.total_general_adeudado)} en total</span>
        </div>
        <div className="reporte-controles">
          <input className="periodo-select" placeholder="Buscar casa o titular"
            value={buscar} onChange={e => setBuscar(e.target.value)} style={{ minWidth: 160 }} />
          <button className="ghost mini" onClick={exportarPDF}>⬇ PDF</button>
          <button className="ghost mini" onClick={exportarExcel}>⬇ Excel</button>
        </div>
      </div>

      {data.aging && (
        <>
          <div className="rep-resumen-grid">
            <div className="rep-kpi"><span>Casas en mora</span><b>{data.total_casas_mora}</b></div>
            <div className="rep-kpi"><span>% morosidad</span><b>{data.pct_morosidad ?? 0}%</b></div>
            <div className="rep-kpi"><span>Cartera vencida</span><b>{L(data.total_general_adeudado)}</b></div>
          </div>
          <h3 className="rep-subtitulo">Antigüedad de la deuda (aging)</h3>
          <div className="rep-resumen-grid" style={{ marginTop: 8 }}>
            <div className="rep-kpi"><span>1 – 30 días</span><b>{L(data.aging.d_1_30)}</b></div>
            <div className="rep-kpi"><span>31 – 60 días</span><b>{L(data.aging.d_31_60)}</b></div>
            <div className="rep-kpi"><span>61 – 90 días</span><b>{L(data.aging.d_61_90)}</b></div>
            <div className="rep-kpi rep-kpi-alerta"><span>90+ días (difícil cobro)</span><b>{L(data.aging.d_90_mas)}</b></div>
          </div>
          <div className="graficos-grid uno">
            <GraficoBarras titulo="Cartera vencida por antigüedad" datos={[
              { nombre: "1–30 días", valor: data.aging.d_1_30, color: "#1d8a4a" },
              { nombre: "31–60 días", valor: data.aging.d_31_60, color: "#d89000" },
              { nombre: "61–90 días", valor: data.aging.d_61_90, color: "#F48723" },
              { nombre: "90+ días", valor: data.aging.d_90_mas, color: "#c81e1e" },
            ]} />
          </div>
        </>
      )}

      {casasFiltradas.length === 0 ? (
        <div className="dash-card">
          <p className="muted">{data.casas.length === 0
            ? "🎉 Ninguna casa tiene cuotas pendientes."
            : "No hay casas que coincidan con la búsqueda."}</p>
        </div>
      ) : (
        <div className="mora-lista">
          {casasFiltradas.map((c, i) => {
            const abierta = expandida === c.unidad + i;
            return (
              <div key={i} className="mora-casa">
                <div className="mora-casa-head" onClick={() => setExpandida(abierta ? null : c.unidad + i)}>
                  <div className="mora-casa-info">
                    <span className="mora-unidad">{c.unidad}</span>
                    <span className="muted small">{c.titular}{c.telefono ? ` · ${c.telefono}` : ""}</span>
                  </div>
                  <div className="mora-casa-resumen">
                    <span className={`pill ${c.max_dias_atraso > 60 ? "red" : "amber"}`}>
                      {c.cantidad_meses} {c.cantidad_meses === 1 ? "mes" : "meses"}
                    </span>
                    <span className="mora-total">{L(c.total_adeudado)}</span>
                    <button className="mini ghost">{abierta ? "▲" : "▼"}</button>
                  </div>
                </div>
                {abierta && (
                  <div className="mora-meses">
                    <table className="data">
                      <thead><tr><th>Mes que debe</th><th>Venció</th><th>Días atraso</th><th>Estado</th><th>Monto</th></tr></thead>
                      <tbody>
                        {c.meses.map((m, j) => (
                          <tr key={j}>
                            <td><b>{m.mes_label}</b></td>
                            <td className="small">{new Date(m.vencimiento).toLocaleDateString("es-HN")}</td>
                            <td>{m.dias_atraso > 0
                              ? <span className="pill red">{m.dias_atraso} días</span>
                              : <span className="pill amber">Por vencer</span>}</td>
                            <td><span className="pill">{m.estado}</span></td>
                            <td>{L(m.monto)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

// ════════════════════════════════════════════════════════════════
// REPORTE DE CAJA Y ARQUEO (tesorero)
// ════════════════════════════════════════════════════════════════
function ReporteCajaVista() {
  const [ini, fin] = rangoMesActual();
  const [desde, setDesde] = useState(ini);
  const [hasta, setHasta] = useState(fin);
  const [data, setData] = useState<ReporteCajaDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  function cargar() {
    setCargando(true);
    reporteCaja(desde || undefined, hasta || undefined)
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  async function exportarPDF() {
    if (!data) return;
    const { jsPDF } = await import("jspdf");
    const autoTable = (await import("jspdf-autotable")).default;
    const doc = new jsPDF();
    doc.setFillColor(2, 46, 69); doc.rect(0, 0, 210, 28, "F");
    doc.setTextColor(255); doc.setFontSize(16);
    doc.text("Reporte de Caja y Arqueo", 14, 13);
    doc.setFontSize(10);
    doc.text(`Villas del Sol · ${data.periodo_label}`, 14, 21);
    doc.setTextColor(0);

    autoTable(doc, {
      startY: 34,
      head: [["Resumen", ""]],
      body: [
        ["Sesiones cerradas", String(data.total_sesiones)],
        ["Total efectivo", L(data.total_efectivo)],
        ["Total POS", L(data.total_pos)],
        ["Total recaudado", L(data.total_recaudado)],
        ["Diferencia acumulada", L(data.total_diferencia)],
        ["Sesiones descuadradas", String(data.sesiones_descuadradas)],
      ],
      theme: "grid", headStyles: { fillColor: [244, 135, 35] },
    });

    autoTable(doc, {
      head: [["Cajero", "Sesiones", "Efectivo", "POS", "Cobros", "Diferencia"]],
      body: data.por_cajero.map(c => [
        c.cajero, String(c.sesiones), L(c.efectivo), L(c.pos),
        String(c.cobros), L(c.diferencia),
      ]),
      theme: "striped", headStyles: { fillColor: [2, 46, 69] },
    });
    doc.save(`reporte-caja-${data.periodo_label.replace(/[/\s–]/g, "-")}.pdf`);
  }

  async function exportarExcel() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();
    const resumen = [
      ["Reporte de Caja — Villas del Sol"], [data.periodo_label], [],
      ["Sesiones cerradas", data.total_sesiones],
      ["Total efectivo", data.total_efectivo],
      ["Total POS", data.total_pos],
      ["Total recaudado", data.total_recaudado],
      ["Diferencia acumulada", data.total_diferencia],
      ["Sesiones descuadradas", data.sesiones_descuadradas],
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumen), "Resumen");
    const porCajero = [["Cajero", "Sesiones", "Efectivo", "POS", "Cobros", "Diferencia"],
      ...data.por_cajero.map(c => [c.cajero, c.sesiones, c.efectivo, c.pos, c.cobros, c.diferencia])];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(porCajero), "Por cajero");
    const ses = [["Cajero", "Cerrada", "Inicial", "Efectivo", "POS", "Cobros", "Dif. efectivo", "Dif. POS", "Cuadrada"],
      ...data.sesiones.map(s => [s.cajero, s.cerrada_en?.slice(0, 16).replace("T", " "),
        s.monto_inicial, s.total_efectivo, s.total_pos, s.cantidad_pagos,
        s.diferencia_efectivo, s.diferencia_pos, s.cuadrada ? "Sí" : "No"])];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(ses), "Sesiones");
    XLSX.writeFile(wb, `reporte-caja-${data.periodo_label.replace(/[/\s–]/g, "-")}.xlsx`);
  }

  return (
    <div>
      <div className="rep-filtros">
        <label>Desde <input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
        <label>Hasta <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
        <button className="cuota-btn-pagar" style={{ maxWidth: 130 }} onClick={cargar}>Aplicar</button>
        {data && data.total_sesiones > 0 && (
          <div className="rep-export">
            <button className="ghost mini" onClick={exportarPDF}>⬇ PDF</button>
            <button className="ghost mini" onClick={exportarExcel}>⬇ Excel</button>
          </div>
        )}
      </div>

      {cargando ? <p className="muted">Cargando…</p> : !data ? <p className="muted">No se pudo cargar.</p> : (
        <>
          <div className="rep-resumen-grid">
            <div className="rep-kpi"><span>Sesiones</span><b>{data.total_sesiones}</b></div>
            <div className="rep-kpi"><span>Efectivo</span><b>{L(data.total_efectivo)}</b></div>
            <div className="rep-kpi"><span>POS</span><b>{L(data.total_pos)}</b></div>
            <div className="rep-kpi"><span>Total recaudado</span><b>{L(data.total_recaudado)}</b></div>
            <div className={`rep-kpi ${data.sesiones_descuadradas ? "rep-kpi-alerta" : ""}`}>
              <span>Descuadradas</span><b>{data.sesiones_descuadradas}</b>
            </div>
          </div>

          {data.total_sesiones === 0 ? (
            <div className="lista-card"><p className="muted">No hay sesiones de caja cerradas en este período.</p></div>
          ) : (
            <>
              <h3 className="rep-subtitulo">Por cajero</h3>
              <div className="lista-card"><div className="scroll-x">
                <table className="data">
                  <thead><tr><th>Cajero</th><th>Sesiones</th><th>Efectivo</th><th>POS</th><th>Cobros</th><th>Diferencia</th></tr></thead>
                  <tbody>
                    {data.por_cajero.map((c, i) => (
                      <tr key={i}>
                        <td>{c.cajero}</td><td>{c.sesiones}</td>
                        <td>{L(c.efectivo)}</td><td>{L(c.pos)}</td><td>{c.cobros}</td>
                        <td><span className={Math.abs(c.diferencia) < 0.01 ? "pill green" : "pill red"}>{L(c.diferencia)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div></div>

              <h3 className="rep-subtitulo">Detalle de sesiones</h3>
              <div className="lista-card"><div className="scroll-x">
                <table className="data">
                  <thead><tr><th>Cajero</th><th>Cerrada</th><th>Efectivo</th><th>POS</th><th>Cobros</th><th>Estado</th></tr></thead>
                  <tbody>
                    {data.sesiones.map(s => (
                      <tr key={s.id}>
                        <td>{s.cajero}</td>
                        <td className="small">{s.cerrada_en?.slice(0, 16).replace("T", " ")}</td>
                        <td>{L(s.total_efectivo)}</td><td>{L(s.total_pos)}</td><td>{s.cantidad_pagos}</td>
                        <td>{s.cuadrada
                          ? <span className="pill green">Cuadró</span>
                          : <span className="pill red">Descuadre</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div></div>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// REPORTE DE ACCESOS Y SEGURIDAD (administrador)
// ════════════════════════════════════════════════════════════════
function ReporteAccesosVista() {
  const [ini, fin] = rangoMesActual();
  const [desde, setDesde] = useState(ini);
  const [hasta, setHasta] = useState(fin);
  const [tipo, setTipo] = useState("");
  const [data, setData] = useState<ReporteAccesosDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  function cargar() {
    setCargando(true);
    reporteAccesos(desde || undefined, hasta || undefined, tipo || undefined)
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  const tiposLabel: Record<string, string> = {
    unica: "Visita única", recurrente: "Recurrente", repartidor: "Repartidor",
  };

  async function exportarPDF() {
    if (!data) return;
    const { jsPDF } = await import("jspdf");
    const autoTable = (await import("jspdf-autotable")).default;
    const doc = new jsPDF();
    doc.setFillColor(2, 46, 69); doc.rect(0, 0, 210, 28, "F");
    doc.setTextColor(255); doc.setFontSize(16);
    doc.text("Reporte de Accesos y Seguridad", 14, 13);
    doc.setFontSize(10);
    doc.text(`Villas del Sol · ${data.periodo_label}`, 14, 21);
    doc.setTextColor(0);
    autoTable(doc, {
      startY: 34,
      head: [["Resumen", ""]],
      body: [
        ["Total de visitas (QR)", String(data.total_visitas)],
        ["Entradas registradas", String(data.total_entradas)],
        ["Visitas únicas", String(data.por_tipo.unica)],
        ["Recurrentes", String(data.por_tipo.recurrente)],
        ["Repartidores", String(data.por_tipo.repartidor)],
      ],
      theme: "grid", headStyles: { fillColor: [244, 135, 35] },
    });
    if (data.top_casas.length) {
      autoTable(doc, {
        head: [["Casa con más visitas", "Visitas"]],
        body: data.top_casas.map(c => [c.casa, String(c.visitas)]),
        theme: "striped", headStyles: { fillColor: [2, 46, 69] },
      });
    }
    doc.save(`reporte-accesos-${data.periodo_label.replace(/[/\s–]/g, "-")}.pdf`);
  }

  async function exportarExcel() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();
    const resumen = [
      ["Reporte de Accesos — Villas del Sol"], [data.periodo_label], [],
      ["Total de visitas", data.total_visitas],
      ["Entradas registradas", data.total_entradas],
      ["Visitas únicas", data.por_tipo.unica],
      ["Recurrentes", data.por_tipo.recurrente],
      ["Repartidores", data.por_tipo.repartidor],
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumen), "Resumen");
    const casas = [["Casa", "Visitas"], ...data.top_casas.map(c => [c.casa, c.visitas])];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(casas), "Casas con más visitas");
    const horas = [["Hora", "Accesos"], ...data.horas_pico.map(h => [h.hora, h.cantidad])];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(horas), "Horas pico");
    XLSX.writeFile(wb, `reporte-accesos-${data.periodo_label.replace(/[/\s–]/g, "-")}.xlsx`);
  }

  return (
    <div>
      <div className="rep-filtros">
        <label>Desde <input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
        <label>Hasta <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
        <select value={tipo} onChange={e => setTipo(e.target.value)} className="periodo-select">
          <option value="">Todos los tipos</option>
          <option value="unica">Visita única</option>
          <option value="recurrente">Recurrente</option>
          <option value="repartidor">Repartidor</option>
        </select>
        <button className="cuota-btn-pagar" style={{ maxWidth: 130 }} onClick={cargar}>Aplicar</button>
        {data && data.total_visitas > 0 && (
          <div className="rep-export">
            <button className="ghost mini" onClick={exportarPDF}>⬇ PDF</button>
            <button className="ghost mini" onClick={exportarExcel}>⬇ Excel</button>
          </div>
        )}
      </div>

      {cargando ? <p className="muted">Cargando…</p> : !data ? <p className="muted">No se pudo cargar.</p> : (
        <>
          <div className="rep-resumen-grid">
            <div className="rep-kpi"><span>Visitas (QR)</span><b>{data.total_visitas}</b></div>
            <div className="rep-kpi"><span>Entradas</span><b>{data.total_entradas}</b></div>
            <div className="rep-kpi"><span>Únicas</span><b>{data.por_tipo.unica}</b></div>
            <div className="rep-kpi"><span>Recurrentes</span><b>{data.por_tipo.recurrente}</b></div>
            <div className="rep-kpi"><span>Repartidores</span><b>{data.por_tipo.repartidor}</b></div>
          </div>

          {data.total_visitas === 0 ? (
            <div className="lista-card"><p className="muted">No hay visitas registradas en este período.</p></div>
          ) : (
            <>
              <div className="graficos-grid">
                <GraficoBarrasCant titulo="Accesos por hora del día"
                  datos={data.horas_pico.map(h => ({ nombre: h.hora, valor: h.cantidad }))} color="#022E45" />
                <GraficoDona titulo="Visitas por tipo" money={false} datos={[
                  { nombre: "Únicas", valor: data.por_tipo.unica },
                  { nombre: "Recurrentes", valor: data.por_tipo.recurrente },
                  { nombre: "Repartidores", valor: data.por_tipo.repartidor },
                ]} />
              </div>

              <h3 className="rep-subtitulo">Horas con más accesos</h3>
              <div className="lista-card">
                {data.horas_pico.length === 0 ? <p className="muted">Sin entradas registradas.</p> : (
                  <div className="rep-horas">
                    {data.horas_pico.map((h, i) => {
                      const max = data.horas_pico[0].cantidad || 1;
                      return (
                        <div key={i} className="rep-hora-fila">
                          <span className="rep-hora-label">{h.hora}</span>
                          <div className="rep-hora-barra-cont">
                            <div className="rep-hora-barra" style={{ width: `${(h.cantidad / max) * 100}%` }} />
                          </div>
                          <span className="rep-hora-num">{h.cantidad}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <h3 className="rep-subtitulo">Casas que más visitas generan</h3>
              <div className="lista-card"><div className="scroll-x">
                <table className="data">
                  <thead><tr><th>Casa</th><th>Visitas generadas</th></tr></thead>
                  <tbody>
                    {data.top_casas.map((c, i) => (
                      <tr key={i}><td>{c.casa}</td><td><span className="pill">{c.visitas}</span></td></tr>
                    ))}
                  </tbody>
                </table>
              </div></div>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// REPORTE DE INVENTARIO DE TARJETAS (administración)
// ════════════════════════════════════════════════════════════════
function ReporteInventarioVista() {
  const [ini, fin] = rangoMesActual();
  const [desde, setDesde] = useState(ini);
  const [hasta, setHasta] = useState(fin);
  const [data, setData] = useState<ReporteInventarioDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  function cargar() {
    setCargando(true);
    reporteInventario(desde || undefined, hasta || undefined)
      .then(setData).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, []);

  async function exportarPDF() {
    if (!data) return;
    const { jsPDF } = await import("jspdf");
    const autoTable = (await import("jspdf-autotable")).default;
    const doc = new jsPDF();
    doc.setFillColor(2, 46, 69); doc.rect(0, 0, 210, 28, "F");
    doc.setTextColor(255); doc.setFontSize(16);
    doc.text("Reporte de Inventario de Tarjetas", 14, 13);
    doc.setFontSize(10);
    doc.text(`Villas del Sol · ${data.periodo_label}`, 14, 21);
    doc.setTextColor(0);
    autoTable(doc, {
      startY: 34,
      head: [["Resumen", ""]],
      body: [
        ["Tarjetas vendidas (período)", String(data.total_vendidas)],
        ["Recaudado (período)", L(data.total_recaudado)],
        ["Stock total en bodega", String(data.stock_total)],
        ["Tipos en bajo stock", String(data.tipos_bajo_stock)],
      ],
      theme: "grid", headStyles: { fillColor: [244, 135, 35] },
    });
    autoTable(doc, {
      head: [["Tipo", "Acceso", "Precio", "Stock", "Vendidas", "Recaudado"]],
      body: data.tipos.map(t => [
        t.nombre, t.tipo_acceso === "peatonal" ? "Corto alcance" : "Largo alcance",
        L(t.precio), String(t.stock), String(t.vendidas_periodo), L(t.recaudado_periodo),
      ]),
      theme: "striped", headStyles: { fillColor: [2, 46, 69] },
    });
    doc.save(`reporte-inventario-${data.periodo_label.replace(/[/\s–]/g, "-")}.pdf`);
  }

  async function exportarExcel() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();
    const resumen = [
      ["Reporte de Inventario — Villas del Sol"], [data.periodo_label], [],
      ["Tarjetas vendidas (período)", data.total_vendidas],
      ["Recaudado (período)", data.total_recaudado],
      ["Stock total en bodega", data.stock_total],
      ["Tipos en bajo stock", data.tipos_bajo_stock],
    ];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumen), "Resumen");
    const tipos = [["Tipo", "Acceso", "Precio", "Stock", "Vendidas período", "Recaudado período", "Activo"],
      ...data.tipos.map(t => [t.nombre, t.tipo_acceso, t.precio, t.stock,
        t.vendidas_periodo, t.recaudado_periodo, t.activo ? "Sí" : "No"])];
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(tipos), "Tipos de tarjeta");
    XLSX.writeFile(wb, `reporte-inventario-${data.periodo_label.replace(/[/\s–]/g, "-")}.xlsx`);
  }

  return (
    <div>
      <div className="rep-filtros">
        <label>Desde <input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
        <label>Hasta <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
        <button className="cuota-btn-pagar" style={{ maxWidth: 130 }} onClick={cargar}>Aplicar</button>
        {data && (
          <div className="rep-export">
            <button className="ghost mini" onClick={exportarPDF}>⬇ PDF</button>
            <button className="ghost mini" onClick={exportarExcel}>⬇ Excel</button>
          </div>
        )}
      </div>

      {cargando ? <p className="muted">Cargando…</p> : !data ? <p className="muted">No se pudo cargar.</p> : (
        <>
          <div className="rep-resumen-grid">
            <div className="rep-kpi"><span>Vendidas (período)</span><b>{data.total_vendidas}</b></div>
            <div className="rep-kpi"><span>Recaudado</span><b>{L(data.total_recaudado)}</b></div>
            <div className="rep-kpi"><span>Stock en bodega</span><b>{data.stock_total}</b></div>
            <div className={`rep-kpi ${data.tipos_bajo_stock ? "rep-kpi-alerta" : ""}`}>
              <span>Tipos bajo stock</span><b>{data.tipos_bajo_stock}</b>
            </div>
          </div>

          {data.tipos.length === 0 ? (
            <div className="lista-card"><p className="muted">No hay tipos de tarjeta configurados.</p></div>
          ) : (
            <div className="lista-card"><div className="scroll-x">
              <table className="data">
                <thead><tr><th>Tipo</th><th>Acceso</th><th>Precio</th><th>Stock</th><th>Vendidas</th><th>Recaudado</th></tr></thead>
                <tbody>
                  {data.tipos.map((t, i) => (
                    <tr key={i} className={!t.activo ? "fila-baja" : ""}>
                      <td>{t.nombre}</td>
                      <td>
                        <span className={`pill ${t.tipo_acceso === "peatonal" ? "" : "green"}`}>
                          {t.tipo_acceso === "peatonal" ? "🚶 Corto" : "🚗 Largo"}
                        </span>
                      </td>
                      <td>{L(t.precio)}</td>
                      <td>
                        <span className={`pill ${t.stock === 0 ? "red" : t.stock <= 5 ? "amber" : "green"}`}>
                          {t.stock} u.
                        </span>
                      </td>
                      <td>{t.vendidas_periodo}</td>
                      <td>{L(t.recaudado_periodo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div></div>
          )}
        </>
      )}
    </div>
  );
}
