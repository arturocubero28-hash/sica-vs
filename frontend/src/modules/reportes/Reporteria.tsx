import { useState, useEffect } from "react";
import { reporteFinanciero, type ReporteFinancieroDTO } from "../../api/client";

function L(n: number) {
  return "L " + n.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Reporteria() {
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
    <div className="reporteria">
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
    </div>
  );
}
