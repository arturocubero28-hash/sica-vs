import { useState, useEffect } from "react";
import { CalendarClock, Tag, ListChecks, CheckCircle2 } from "lucide-react";
import {
  setConfigResidencial, crearTarifa, listarTarifas,
  listarCuentas, editarInfoCasa, activarCuotas,
  type Tarifa, type Cuenta,
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

  // Paso 3 — asignar tarifa a las casas sin tarifa
  const [casasSinTarifa, setCasasSinTarifa] = useState<Cuenta[]>([]);
  const [asignaciones, setAsignaciones] = useState<Record<string, number>>({});
  const [tarifaMasiva, setTarifaMasiva] = useState<number>(0);
  const [guardando3, setGuardando3] = useState(false);

  // Paso 4 — generar
  const [generando, setGenerando] = useState(false);
  const [resultado, setResultado] = useState<{ generadas: number; total: number } | null>(null);

  const [err, setErr] = useState("");

  useEffect(() => {
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
      await irAPaso3();
    } catch (e) { setErr((e as Error).message); }
    finally { setGuardando2(false); }
  }

  async function irAPaso3() {
    setErr("");
    // Cargar las casas sin tarifa de esta residencial. listar_cuentas ya
    // devuelve tarifa_id; se filtran acá las que no tienen, excluyendo el
    // contenedor de edificio (que no paga cuota).
    try {
      const todas = await listarCuentas();
      const lista = Array.isArray(todas) ? todas : (todas as { cuentas: Cuenta[] }).cuentas || [];
      const sinTarifa = lista.filter(
        (c) => !c.tarifa_id && c.tipo_cuenta !== "edificio_contenedor" && c.activa !== false);
      setCasasSinTarifa(sinTarifa);
      setPaso(3);
    } catch (e) { setErr((e as Error).message); }
  }

  function aplicarTarifaATodas() {
    if (!tarifaMasiva) return;
    const nuevo: Record<string, number> = {};
    casasSinTarifa.forEach((c) => { nuevo[c.id] = tarifaMasiva; });
    setAsignaciones(nuevo);
  }

  async function guardarAsignaciones() {
    setGuardando3(true); setErr("");
    try {
      // Asignar la tarifa elegida a cada casa (reutiliza editarInfoCasa).
      // Solo las que tienen una tarifa seleccionada.
      const pendientes = casasSinTarifa.filter((c) => asignaciones[c.id]);
      if (pendientes.length === 0) {
        setErr("Asigná una tarifa a al menos una casa (o a todas de una vez).");
        setGuardando3(false); return;
      }
      for (const c of pendientes) {
        await editarInfoCasa(c.id, { tarifa_id: asignaciones[c.id] });
      }
      setPaso(4);
    } catch (e) { setErr((e as Error).message); }
    finally { setGuardando3(false); }
  }

  async function generarCuotas() {
    setGenerando(true); setErr("");
    try {
      const r = await activarCuotas();
      setResultado({ generadas: r.cuotas_generadas, total: r.total_casas_con_tarifa });
    } catch (e) { setErr((e as Error).message); setGenerando(false); }
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
                  {Array.from({ length: 30 }, (_, i) => i + 1).map((d) => (
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
              La cuota vence el <b>día {diaPago}</b> de cada mes, y el residente tiene{" "}
              <b>{diasGracia} día{diasGracia !== 1 ? "s" : ""}</b> de gracia antes de que se bloquee por mora.
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
                <button className="ghost" onClick={irAPaso3}>Usar las que tengo</button>
              )}
              <button onClick={crearPrimeraTarifa} disabled={guardando2}>
                {guardando2 ? "Creando…" : "Crear y continuar"}
              </button>
            </div>
          </div>
        )}

        {/* ── PASO 3 — asignar tarifa a las casas ── */}
        {paso === 3 && (
          <div className="wizard-body">
            <h3>3 · Asigná tarifa a las casas</h3>
            {casasSinTarifa.length === 0 ? (
              <p className="muted">Todas tus casas ya tienen tarifa. Podés continuar.</p>
            ) : (
              <>
                <p className="muted small">
                  {casasSinTarifa.length} casa(s) sin tarifa. Asigná una a cada una, o poné la misma a todas de un tirón.
                </p>
                <div className="wizard-masiva">
                  <select value={tarifaMasiva} onChange={(e) => setTarifaMasiva(Number(e.target.value))}>
                    <option value={0}>— Elegí una tarifa —</option>
                    {tarifas.map((t) => <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>)}
                  </select>
                  <button className="ghost" onClick={aplicarTarifaATodas} disabled={!tarifaMasiva}>
                    Aplicar a todas
                  </button>
                </div>
                <div className="wizard-casas-lista">
                  {casasSinTarifa.map((c) => (
                    <div key={c.id} className="wizard-casa-row">
                      <span className="wizard-casa-nombre">
                        {c.identificador || c.nombre_completo}
                        {c.apartamento ? ` · Apto ${c.apartamento}` : ""}
                      </span>
                      <select value={asignaciones[c.id] || 0}
                        onChange={(e) => setAsignaciones({ ...asignaciones, [c.id]: Number(e.target.value) })}>
                        <option value={0}>— Sin asignar —</option>
                        {tarifas.map((t) => <option key={t.id} value={t.id}>{t.nombre} — L {t.monto}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="wizard-acciones">
              <button className="ghost" onClick={() => setPaso(2)}>Atrás</button>
              {casasSinTarifa.length === 0
                ? <button onClick={() => setPaso(4)}>Continuar</button>
                : <button onClick={guardarAsignaciones} disabled={guardando3}>
                    {guardando3 ? "Asignando…" : "Asignar y continuar"}
                  </button>}
            </div>
          </div>
        )}

        {/* ── PASO 4 — confirmar y generar ── */}
        {paso === 4 && (
          <div className="wizard-body">
            <h3>4 · Confirmá y generá las cuotas</h3>
            {resultado ? (
              <>
                <div className="wizard-exito">
                  <CheckCircle2 size={40} />
                  <b>¡Listo! Se generaron {resultado.generadas} cuota(s).</b>
                  <p className="muted small">
                    Cada casa con tarifa tiene su primera cuota prorrateada desde hoy hasta fin de ciclo.
                    De acá en adelante, el sistema genera las cuotas automáticamente cada mes.
                  </p>
                </div>
                <div className="wizard-acciones">
                  <button onClick={onCompletado}>Ir al panel</button>
                </div>
              </>
            ) : (
              <>
                <p className="muted small">
                  Se generará la <b>primera cuota prorrateada</b> (desde hoy hasta el fin del ciclo actual)
                  para cada casa que ya tiene tarifa. El próximo mes, el ciclo normal se encarga solo.
                </p>
                <div className="wizard-ejemplo">
                  Recordá: tu responsabilidad de cobro arranca hoy. Asegurate de que los residentes
                  no tengan deuda pendiente de antes de entrar al sistema.
                </div>
                <div className="wizard-acciones">
                  <button className="ghost" onClick={() => setPaso(3)} disabled={generando}>Atrás</button>
                  <button onClick={generarCuotas} disabled={generando}>
                    {generando ? "Generando…" : "Generar cuotas ahora"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
