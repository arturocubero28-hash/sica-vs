import { useEffect, useRef, useState } from "react";
import { detalleCuenta } from "../api/client";

/**
 * Día 73 — esperar la confirmación de que el correo llegó.
 *
 * EL PROBLEMA: al dar de alta, el panel decía "Cuenta creada" y cerraba.
 * Pero crear la cuenta y que la persona RECIBA el enlace para entrar son
 * dos cosas distintas, y la segunda es la que importa: una cuenta cuyo
 * correo rebotó queda pendiente para siempre. Administración se iba
 * tranquila creyendo que había terminado.
 *
 * Ahora el alta no se da por buena hasta que Resend confirma la entrega.
 *
 * UNA ACLARACIÓN QUE IMPORTA: la cuenta YA está creada cuando esta
 * pantalla aparece — el servidor la guardó al responder, y no se puede
 * "descrear" sin borrarla, que sería peor (se perdería la casa, la unidad
 * y la cuota recién generada si la persona se equivocó en una letra del
 * correo). Lo que se bloquea es el CIERRE: no se declara éxito ni se
 * libera el formulario hasta saber qué pasó, y si rebotó se ofrece
 * corregir la dirección ahí mismo.
 *
 * El estado lo escribe el webhook de Resend (ver api/webhooks.py), así
 * que esto es consultar la ficha cada pocos segundos hasta que cambie.
 *
 * Si a los 60 segundos no hay respuesta no se da por fallido: hay
 * servidores de correo que tardan. Se dice que quedó en camino y que el
 * aviso va a aparecer en la ficha. Dar un error ahí sería mentir.
 */
type Estado = "esperando" | "entregado" | "rebotado" | "sin_confirmar";

type Props = {
  cuentaId: string;
  email: string;
  /** Qué hacer cuando la persona decide corregir el correo. */
  onCorregir?: () => void;
  /** Cerrar y seguir. */
  onListo: () => void;
  /** Texto del botón final. */
  textoListo?: string;
};

const CADA_MS = 2500;
const INTENTOS = 24;          // 60 segundos

export function ConfirmacionEnvio({ cuentaId, email, onCorregir, onListo, textoListo }: Props) {
  const [estado, setEstado] = useState<Estado>("esperando");
  const [detalle, setDetalle] = useState("");
  const vivo = useRef(true);

  useEffect(() => {
    vivo.current = true;
    (async () => {
      for (let i = 0; i < INTENTOS; i++) {
        await new Promise(r => setTimeout(r, CADA_MS));
        if (!vivo.current) return;
        try {
          const c = await detalleCuenta(cuentaId);
          const t = c.titular;
          if (!vivo.current) return;
          if (t?.correo_estado === "rebotado") {
            setDetalle(t.correo_detalle || "El servidor del destinatario lo rechazó.");
            setEstado("rebotado");
            return;
          }
          if (t?.correo_estado === "entregado") { setEstado("entregado"); return; }
        } catch {
          // Sin conexión o la sesión expiró: no tiene sentido insistir, y
          // menos mostrar un error de red donde se espera uno de correo.
          if (vivo.current) setEstado("sin_confirmar");
          return;
        }
      }
      if (vivo.current) setEstado("sin_confirmar");
    })();
    return () => { vivo.current = false; };
  }, [cuentaId]);

  if (estado === "esperando") {
    return (
      <div className="confirmacion" role="status" aria-live="polite">
        <div className="confirmacion-sobre">
          <svg viewBox="0 0 48 36" width="48" height="36" aria-hidden="true">
            <rect x="1" y="1" width="46" height="34" rx="4"
              className="confirmacion-sobre-cuerpo" />
            <path d="M1 5 L24 21 L47 5" className="confirmacion-sobre-solapa" />
          </svg>
        </div>
        <h4>Confirmando que el correo llegó…</h4>
        <p className="muted small">
          Le escribimos a <b>{email}</b>. Esperamos la confirmación del
          servidor de correo antes de dar el alta por terminada.
        </p>
        <div className="confirmacion-barra"><span /></div>
      </div>
    );
  }

  if (estado === "entregado") {
    return (
      <div className="confirmacion confirmacion--ok" role="status" aria-live="polite">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-check" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-check-aro" />
          <path d="M15 27 l8 8 l15 -16" className="confirmacion-check-tilde" />
        </svg>
        <h4>El correo le llegó</h4>
        <p className="muted small">
          El servidor de <b>{email}</b> lo recibió. Ya puede definir su contraseña
          desde el enlace. Si no lo ve, que revise spam.
        </p>
        <button onClick={onListo}>{textoListo || "Listo"}</button>
      </div>
    );
  }

  if (estado === "rebotado") {
    return (
      <div className="confirmacion confirmacion--error" role="alert">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-aviso" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
          <path d="M26 14 v16" className="confirmacion-aviso-linea" />
          <circle cx="26" cy="37" r="2.4" className="confirmacion-aviso-punto" />
        </svg>
        <h4>El correo no le llegó</h4>
        <p className="muted small">
          <b>{email}</b> rechazó el mensaje. {detalle} Revisá la dirección con la
          persona: lo más común es una letra de más o un dominio mal escrito.
        </p>
        <div className="row-btns">
          {onCorregir && <button onClick={onCorregir}>Corregir el correo</button>}
          {/* Sin forma de corregir acá (el alta normal: la dirección se
              arregla desde la ficha de la casa), un botón que dijera
              "seguir sin corregir" sonaría a que se está eligiendo mal
              a propósito. Es simplemente cerrar. */}
          <button className={onCorregir ? "ghost" : ""} onClick={onListo}>
            {onCorregir ? "Seguir sin corregir" : (textoListo || "Entendido")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="confirmacion" role="status" aria-live="polite">
      <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-reloj" aria-hidden="true">
        <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
        <path d="M26 13 v14 l9 6" className="confirmacion-reloj-agujas" />
      </svg>
      <h4>Quedó en camino</h4>
      <p className="muted small">
        El correo salió hacia <b>{email}</b>, pero el servidor todavía no confirmó
        la entrega. Algunos tardan. Si al final rebota, va a aparecer el aviso
        junto a la persona en la ficha de la casa.
      </p>
      <button onClick={onListo}>{textoListo || "Entendido"}</button>
    </div>
  );
}
