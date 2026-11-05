import { AlertTriangle, CheckCircle, Clock, Mail, ShieldAlert } from "lucide-react";

/**
 * Día 73 — qué pasó con el último correo que le mandamos a esta persona.
 *
 * Hasta ahora esto solo se mostraba cuando el correo REBOTABA, que es
 * justo cuando ya es tarde: administración se enteraba de que algo pasó
 * únicamente en el peor caso, y en todos los demás no tenía forma de
 * saber si el correo había salido, si había llegado, o si el sistema de
 * correo estaba caído.
 *
 * Eso dejaba sin respuesta la pregunta que de verdad se hace: "le mandé
 * el enlace a esta señora hace media hora, ¿le llegó o no?". Sin este
 * dato, la respuesta era pedirle que revisara su bandeja, y si decía que
 * no, no había manera de distinguir entre "no llegó" y "no lo vio".
 *
 * Los estados vienen del webhook de Resend (ver api/webhooks.py):
 *
 *   enviado    Resend lo aceptó y lo despachó. Normal durante unos segundos.
 *   entregado  El servidor del destinatario lo recibió. Es el estado bueno.
 *   demorado   Reintentando. Suele resolverse solo; si persiste, el buzón
 *              del destinatario tiene un problema.
 *   rebotado   No llegó y no va a llegar: la dirección no existe o fue
 *              rechazada. Hay que corregirla.
 *   queja      Llegó, pero lo marcaron como spam. Importante: Resend deja
 *              de mandarle correos a esa dirección.
 *
 * Sin estado no se dibuja nada. Puede ser un residente anterior al Día 72
 * (cuando no existía esta detección) o alguien a quien nunca se le mandó
 * un correo, y en ninguno de los dos casos hay algo que informar: una
 * píldora de "sin datos" en cada fila sería ruido.
 */
type Props = {
  estado?: string | null;
  detalle?: string | null;
  /** ISO del último cambio de estado. */
  actualizado?: string | null;
  email?: string | null;
};

/** "hace 3 min", "hace 2 h", "hace 4 días". */
function haceCuanto(iso?: string | null): string {
  if (!iso) return "";
  const cuando = new Date(iso).getTime();
  if (Number.isNaN(cuando)) return "";
  const seg = Math.max(0, Math.round((Date.now() - cuando) / 1000));
  if (seg < 60) return "hace unos segundos";
  const min = Math.round(seg / 60);
  if (min < 60) return `hace ${min} min`;
  const hrs = Math.round(min / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  const dias = Math.round(hrs / 24);
  return `hace ${dias} día${dias === 1 ? "" : "s"}`;
}

const MAPA: Record<string, {
  texto: string; clase: string; icono: typeof Mail; ayuda: (e: string) => string;
}> = {
  enviado: {
    texto: "Correo enviado", clase: "pill-estado--enviado", icono: Mail,
    ayuda: e => `El correo salió hacia ${e}. En unos segundos debería confirmarse la entrega.`,
  },
  entregado: {
    texto: "Correo entregado", clase: "pill-estado--entregado", icono: CheckCircle,
    ayuda: e => `El servidor de ${e} recibió el correo. Si la persona dice que no lo ve, que revise spam.`,
  },
  demorado: {
    texto: "Entrega demorada", clase: "pill-estado--demorado", icono: Clock,
    ayuda: e => `El servidor de ${e} no lo aceptó todavía y se está reintentando. Suele resolverse solo.`,
  },
  rebotado: {
    texto: "No le llegó", clase: "pill-estado--rebotado", icono: AlertTriangle,
    ayuda: e => `El correo no le llegó a ${e}. Corregí la dirección con Editar y después tocá Regenerar enlace.`,
  },
  queja: {
    texto: "Marcado como spam", clase: "pill-estado--queja", icono: ShieldAlert,
    ayuda: e => `${e} marcó el correo como spam, así que el servicio deja de mandarle correos. Hay que contactarla por otro medio.`,
  },
};

export function EstadoCorreo({ estado, detalle, actualizado, email }: Props) {
  if (!estado) return null;
  const info = MAPA[estado];
  if (!info) return null;   // un estado nuevo de Resend que todavía no mapeamos

  const Icono = info.icono;
  const cuando = haceCuanto(actualizado);
  const ayuda = [info.ayuda(email || "esa dirección"), detalle || "", cuando ? `(${cuando})` : ""]
    .filter(Boolean).join(" ");

  return (
    <span className={`pill-estado ${info.clase}`} title={ayuda}>
      <Icono size={12} /> {info.texto}
      {cuando && <span className="pill-estado-cuando">· {cuando}</span>}
    </span>
  );
}
