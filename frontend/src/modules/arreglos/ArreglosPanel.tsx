import { useState, useEffect } from "react";
import {
  listarArreglos, detalleArreglo, type ArregloDTO, type PropositoArreglo,
} from "../../api/client";
import { L } from "../../utils/formato";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";
// Día 75 — creación paso a paso y detalle, en el lenguaje de «Salida del sistema».
import { NuevoArreglo } from "./NuevoArreglo";
import { DetalleArreglo } from "./DetalleArregloModal";

const ESTADO_PILL: Record<string, string> = {
  activo: "green", completado: "", incumplido: "red", cancelado: "amber",
};
const ESTADO_LABEL: Record<string, string> = {
  activo: "Activo", completado: "Completado", incumplido: "Incumplido", cancelado: "Cancelado",
};
// Día 74 — para qué se firmó. Decide si la casa puede volver al padrón.
const PROPOSITO_LABEL: Record<PropositoArreglo, string> = {
  ponerse_al_dia: "Ponerse al día y seguir pagando",
  volver_al_padron: "Saldar la deuda y volver al padrón",
};

export function ArreglosPanel() {
  const [tab, setTab] = useState<"lista" | "crear">("lista");
  const [filtro, setFiltro] = useState("");
  const [arreglos, setArreglos] = useState<ArregloDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [detalle, setDetalle] = useState<ArregloDTO | null>(null);
  const [errorPlan, setErrorPlan] = useState("");

  function cargar() {
    setCargando(true);
    listarArreglos(filtro || undefined).then(setArreglos)
      .catch((e) => setErrorPlan(e?.message || "")).finally(() => setCargando(false));
  }
  useEffect(() => { cargar(); }, [filtro]);

  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;

  return (
    <div className="reporteria">
      <div className="historial-tabs" style={{ marginBottom: 14 }}>
        <button className={`htab ${tab === "lista" ? "activo" : ""}`} onClick={() => setTab("lista")}>
          Arreglos
        </button>
        <button className={`htab ${tab === "crear" ? "activo" : ""}`} onClick={() => setTab("crear")}>
          + Nuevo arreglo
        </button>
      </div>

      {tab === "crear" ? (
        <NuevoArreglo
          onCreado={(a) => { setTab("lista"); cargar(); setDetalle(a); }}
          onCancelar={() => { setTab("lista"); cargar(); }}
        />
      ) : (
        <>
          <div className="dash-header-pro">
            <div>
              <h2 className="dash-titulo">Arreglos de pago</h2>
              <span className="muted">Planes de pago para cuentas morosas</span>
            </div>
            <select className="periodo-select" value={filtro} onChange={e => setFiltro(e.target.value)}>
              <option value="">Todos</option>
              <option value="activo">Activos</option>
              <option value="completado">Completados</option>
              <option value="incumplido">Incumplidos</option>
              <option value="cancelado">Cancelados</option>
            </select>
          </div>

          {cargando ? <p className="muted">Cargando…</p>
            : arreglos.length === 0 ? (
              <div className="dash-card"><p className="muted">No hay arreglos {filtro ? `en estado "${filtro}"` : ""}.</p></div>
            ) : (
              <div className="mora-lista">
                {arreglos.map(a => (
                  <div key={a.id} className="mora-casa">
                    <div className="mora-casa-head" onClick={() => detalleArreglo(a.id).then(setDetalle)}>
                      <div className="mora-casa-info">
                        <span className="mora-unidad">{a.unidad}</span>
                        <span className="muted small">{a.titular}</span>
                        <span className="muted small">
                          {a.proposito === "volver_al_padron" ? "Para volver al padrón" : "Para ponerse al día"}
                          {a.descuento_pct > 0 && ` · ${a.descuento_pct} % de descuento`}
                        </span>
                      </div>
                      <div className="mora-casa-resumen">
                        <span className={`pill ${ESTADO_PILL[a.estado]}`}>{ESTADO_LABEL[a.estado]}</span>
                        {a.atrasado && <span className="pill red">Atrasado</span>}
                        <span className="muted small">{a.abonos_pagados}/{a.num_abonos} abonos</span>
                        <span className="mora-total">{L(a.saldo_pendiente)}</span>
                        <button className="mini">Ver →</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </>
      )}

      {detalle && (
        <DetalleArreglo
          arreglo={detalle}
          onCerrar={() => setDetalle(null)}
          onCambio={(a) => { setDetalle(a); cargar(); }}
        />
      )}
    </div>
  );
}
