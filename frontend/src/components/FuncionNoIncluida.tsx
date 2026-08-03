import { Lock } from "lucide-react";

/**
 * FuncionNoIncluida — pantalla de "esto no está en tu plan", con estilo
 * propio en vez de texto plano.
 *
 * Día 51: antes, cuando el backend bloqueaba una función por el plan
 * (código funcion_no_incluida, ver requiere_funcion_plan en el
 * backend), las pantallas mostraban el mensaje del servidor como texto
 * suelto (<p className="muted">) — funcional, pero sin ninguna
 * intención visual. Este componente le da una tarjeta propia, con
 * ícono y jerarquía clara, reutilizable en cualquier pantalla que
 * choque con este mismo bloqueo.
 *
 * Uso:
 *   if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;
 */
export function FuncionNoIncluida({ mensaje }: { mensaje: string }) {
  return (
    <div className="funcion-no-incluida">
      <div className="funcion-no-incluida-icono"><Lock size={26} /></div>
      <h3>Esta función no está en tu plan</h3>
      <p className="muted">{mensaje}</p>
    </div>
  );
}
