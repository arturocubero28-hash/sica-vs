import { useState, useEffect } from "react";
import { CalendarClock, Tag, ListChecks, CheckCircle2 } from "lucide-react";
import {
  estadoConfigCuotas, setConfigResidencial, crearTarifa, listarTarifas,
  type EstadoConfigCuotas, type Tarifa,
} from "../../api/client";

/**
 * Día 55 — Sprint 2c/2d. Wizard obligatorio de activación de cuotas.
 * Aparece cuando la residencial subió a un plan con cuotas por primera vez
 * (cuotas_config_pendiente). Pasos:
 *   1. Configurar día de pago y días de gracia (global de la residencial).
 *   2. Crear la primera tarifa (si no hay ninguna).
 *   3. Asignar tarifa a las casas (2d).
 *   4. Confirmar y generar las cuotas prorrateadas (2d).
 *
 * Este archivo (2c) deja los pasos 1-2 completamente funcionales y el
 * andamiaje visual de 3-4 listo para engancharse en el 2d.
 */

const PASOS = [
  { n: 1, label: "Cobro", icon: CalendarClock },
  { n: 2, label: "Tarifa", icon: Tag },
  { n: 3, label: "Asignar", icon: ListChecks },
  { n: 4, label: "Confirmar", icon: CheckCircle2 },
];

export function WizardActivarCuotas({ onCompletado }: { onCompletado: () => void }) {
  const [estado, setEstado] = useState<EstadoConfigCuotas | null>(null);
  const [paso, setPaso] = useState(1);

  // Paso 1 — configuración de cobro
  const [diaPago, setDiaPago] = useState(1);
  const [diasGracia, setDiasGracia] = useState(5);
  const [guardando1, setGuardando1] = useState(false);

  // Paso 2 — primera tarifa
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [nombreTarifa, setNombreTarifa] = useState("");
  const [montoTarifa, setMontoTarifa] = useState("");
  const [guardando2, setGuardando2] = useState(false);

  const [err, setErr] = useState("");

  useEffect(() => {
    estadoConfigCuotas().then(setEstado).catch(() => {});
    listarTarifas().then(setTarifas).catch(() => {});
  }, []);

  async function guardarPaso1() {
    setGuardando1(true); setErr("");
    try {
      await setConfigResidencial({ dia_pago: diaPago, dias_gracia: diasGracia });
      setPaso(2);
    } catch (e) { setErr((e as Error).message); }
    finally { setGuardando1(false); }
  }

  async function crearPrimeraTarifa() {
    setGuardando2(true); setErr("");
    try {
      const monto = parseFloat(montoTarifa);
      if (!nombreTarifa.trim() || isNaN(monto) || monto <= 0) {
        setErr("Poné un nombre y un monto válido para la tarifa.");
        setGuardando2(false); return;
      }
      await crearTarifa({ nombre: nombreTarifa.trim(), monto });
      const actualizadas = await listarTarifas();
      setTarifas(actualizadas);
      setNombreTarifa(""); setMontoTarifa("");
      setPaso(3);
    } catch (e) { setErr((e as Error).message); }
    finally { setGuardando2(false); }
  }

  function saltarSiYaHayTarifas() {
    // Si ya existe alguna tarifa, el paso 2 es opcional — se puede avanzar.
    setPaso(3);
  }

  return (
    <div className="wizard-overlay">
      <div className="wizard-card">
        <div className="wizard-head">
          <h2>Activá el cobro de cuotas</h2>
          <p className="muted">
            Tu residencial subió a un plan con cuotas. Configurá el cobro en unos pocos pasos —
            desde el día que completes esto, el sistema se encarga de generar y controlar las cuotas.
          </p>
        </div>

        {/* Indicador de pasos */}
        <div className="wizard-steps">
          {PASOS.map((p) => {
            const Icono = p.icon;
            const activo = p.n === paso;
            const hecho = p.n < paso;
            return (
              <div key={p.n} className={`wizard-step ${activo ? "activo" : ""} ${hecho ? "hecho" : ""}`}>
                <span className="wizard-step-icon"><Icono size={16} /></span>
                <span className="wizard-step-label">{p.label}</span>
              </div>
            );
          })}
        </div>

        {err && <p className="err small" style={{ margin: "0 0 12px" }}>{err}</p>}

        {/* ── PASO 1 — cobro ── */}
        {paso === 1 && (
          <div className="wizard-body">
            <h3>1 · ¿Cuándo se cobra?</h3>
            <p className="muted small">
              Estos valores aplican a todas las casas por defecto (después podés ajustarlos por casa).
            </p>
            <div className="wizard-grid">
              <label className="campo-moderno">
                <span className="campo-label">Día de pago del mes</span>
                <select value={diaPago} onChange={(e) => setDiaPago(Number(e.target.value))}>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>Día {d}</option>
                  ))}
                </select>
              </label>
              <label className="campo-moderno">
                <span className="campo-label">Días de gracia</span>
                <select value={diasGracia} onChange={(e) => setDiasGracia(Number(e.target.value))}>
                  {Array.from({ length: 16 }, (_, i) => i).map((d) => (
                    <option key={d} value={d}>{d} día{d !== 1 ? "s" : ""}</option>
                  ))}
                </select>
                <span className="campo-ayuda">Plazo extra tras el día de pago antes de bloquear por mora.</span>
              </label>
            </div>
            <div className="wizard-ejemplo">
              La cuota se genera el <b>día {diaPago}</b> y el residente tiene hasta el{" "}
              <b>día {Math.min(diaPago + diasGracia, 28)}</b> para pagar sin bloqueo.
            </div>
            <div className="wizard-acciones">
              <button onClick={guardarPaso1} disabled={guardando1}>
                {guardando1 ? "Guardando…" : "Continuar"}
              </button>
            </div>
          </div>
        )}

        {/* ── PASO 2 — primera tarifa ── */}
        {paso === 2 && (
          <div className="wizard-body">
            <h3>2 · Creá una tarifa</h3>
            <p className="muted small">
              La tarifa es el monto mensual que paga una casa. Podés crear más después; ahora
              creá al menos una para poder asignarla.
            </p>
            {tarifas.length > 0 && (
              <div className="wizard-tarifas-existentes">
                <span className="muted small">Ya tenés {tarifas.length} tarifa(s):</span>
                <ul>{tarifas.map((t) => <li key={t.id}>{t.nombre} — L {t.monto}</li>)}</ul>
              </div>
            )}
            <div className="wizard-grid">
              <label className="campo-moderno">
                <span className="campo-label">Nombre de la tarifa</span>
                <input type="text" value={nombreTarifa} placeholder="Ej. Cuota general"
                  onChange={(e) => setNombreTarifa(e.target.value)} />
              </label>
              <label className="campo-moderno">
                <span className="campo-label">Monto mensual (L)</span>
                <input type="number" min={1} step="0.01" value={montoTarifa} placeholder="Ej. 500"
                  onChange={(e) => setMontoTarifa(e.target.value)} />
              </label>
            </div>
            <div className="wizard-acciones">
              <button className="ghost" onClick={() => setPaso(1)}>Atrás</button>
              {tarifas.length > 0 && (
                <button className="ghost" onClick={saltarSiYaHayTarifas}>Usar las que tengo</button>
              )}
              <button onClick={crearPrimeraTarifa} disabled={guardando2}>
                {guardando2 ? "Creando…" : "Crear y continuar"}
              </button>
            </div>
          </div>
        )}

        {/* ── PASO 3 y 4 — andamiaje, se completa en el 2d ── */}
        {paso === 3 && (
          <div className="wizard-body">
            <h3>3 · Asigná tarifa a las casas</h3>
            <p className="muted">
              {estado ? `Tenés ${estado.casas_sin_tarifa} casa(s) sin tarifa.` : "Cargando…"}
            </p>
            <p className="muted small">(Este paso se completa en la próxima entrega.)</p>
            <div className="wizard-acciones">
              <button className="ghost" onClick={() => setPaso(2)}>Atrás</button>
              <button onClick={() => setPaso(4)}>Continuar</button>
            </div>
          </div>
        )}

        {paso === 4 && (
          <div className="wizard-body">
            <h3>4 · Confirmá y generá las cuotas</h3>
            <p className="muted small">(Este paso se completa en la próxima entrega.)</p>
            <div className="wizard-acciones">
              <button className="ghost" onClick={() => setPaso(3)}>Atrás</button>
              <button onClick={onCompletado}>Finalizar</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
