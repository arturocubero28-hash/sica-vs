import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Día 73 — aviso en el panel cuando el worker está caído.
 *
 * El 5 de noviembre el worker quedó en un bucle de reinicios y el panel
 * seguía funcionando igual: nada en pantalla decía que no se iban a
 * generar las cuotas del mes ni salir las notificaciones. Este aviso es
 * para quien esté usando el sistema en ese momento. El correo de alerta lo
 * manda aparte el vigilante del servidor (deploy/vigilar.sh), que no
 * depende de que nadie tenga el panel abierto.
 *
 * Se consulta al abrir y cada 2 minutos. Mientras está todo bien no se
 * dibuja nada. Un tropiezo de red puntual tampoco muestra nada: solo un
 * 503, que es lo que el backend devuelve cuando sabe que el worker no late.
 */
const CADA_MS = 120_000;

export function AvisoWorker() {
  const [caido, setCaido] = useState<null | "worker" | "redis">(null);

  useEffect(() => {
    let vivo = true;
    async function mirar() {
      try {
        const r = await fetch("/api/v1/health/worker", { cache: "no-store" });
        if (!vivo) return;
        if (r.status === 503) {
          const j = await r.json().catch(() => null);
          setCaido(j?.data?.motivo === "redis_no_responde" ? "redis" : "worker");
        } else if (r.ok) {
          setCaido(null);
        }
      } catch {
        // Sin red no sabemos nada: mejor no alarmar.
      }
    }
    mirar();
    const t = setInterval(mirar, CADA_MS);
    return () => { vivo = false; clearInterval(t); };
  }, []);

  if (!caido) return null;
  return (
    <div className="aviso-worker" role="alert">
      <AlertTriangle size={18} />
      <div>
        <b>Las tareas automáticas del sistema no están funcionando.</b>
        <span>
          {caido === "redis"
            ? " El servicio interno de colas no responde. "
            : " "}
          Mientras dure, no se generan cuotas ni se revisa la mora, y no salen
          notificaciones ni correos de recuperar contraseña. El resto del panel
          funciona. Avisale al soporte técnico.
        </span>
      </div>
    </div>
  );
}
