import { useEffect, useRef, useState } from "react";
import { consultarVerificacion, verificarCorreo } from "../api/client";

/**
 * Día 73 — verificar que el correo llega ANTES de crear nada.
 *
 * LA REGLA: si el correo no llega, no se crea nada. Ni la casa, ni la
 * cuota, ni el acceso. Solo cuando Resend confirma que el correo fue
 * ENTREGADO se ejecuta la creación.
 *
 * POR QUÉ CAMBIÓ: la primera versión de esta pantalla creaba la cuenta y
 * DESPUÉS esperaba la confirmación. Cuando el correo rebotaba, la cuenta
 * ya existía: al corregir la dirección y reintentar, fallaba con "esta
 * persona ya tiene acceso al sistema". Pasó en la primera prueba real.
 *
 * Ahora el orden es el único que no deja restos:
 *
 *   1. Se manda un correo corto de verificación ("estamos creando tu
 *      cuenta"). No lleva enlace: todavía no hay cuenta.
 *   2. Se espera el aviso del webhook.
 *   3a. Llegó     -> se ejecuta onConfirmado(id), que crea todo de una vez
 *                    pasando el id; el backend rechaza crear sin él.
 *   3b. Rebotó    -> no se creó nada. Se corrige y se vuelve a verificar.
 *   3c. Sin respuesta en 60 s -> tampoco se creó nada. Se puede seguir
 *                    esperando o corregir.
 *
 * El backend es quien hace cumplir la regla (ver api/verificacion_correo.py):
 * esta pantalla es la forma cómoda de cumplirla, no la única barrera.
 */
type Fase =
  | "enviando"      // pidiendo la verificación
  | "esperando"     // correo salió, esperando confirmación
  | "creando"       // confirmado: ejecutando la creación
  | "listo"         // creado
  | "rebotado"      // no llegó: nada creado
  | "sin_confirmar" // 60 s sin respuesta: nada creado
  | "error";        // falló el envío o la creación

type Props = {
  email: string;
  nombre?: string;
  /** Lo que se crea SOLO si el correo llegó. Recibe el id de la verificación. */
  onConfirmado: (verificacionId: string) => Promise<void>;
  /** Volver al formulario a corregir el correo. */
  onCorregir: () => void;
  /** Cerrar y seguir, una vez creado. */
  onListo: () => void;
  textoListo?: string;
  /** Qué se creó, para el mensaje final. Ej: "La casa ya participa del sistema." */
  textoCreado?: string;
};

const CADA_MS = 2500;
const INTENTOS = 24;          // 60 segundos

export function ConfirmacionEnvio({
  email, nombre, onConfirmado, onCorregir, onListo, textoListo, textoCreado,
}: Props) {
  const [fase, setFase] = useState<Fase>("enviando");
  const [detalle, setDetalle] = useState("");
  const [verifId, setVerifId] = useState<string | null>(null);
  const [ronda, setRonda] = useState(0);     // "seguir esperando" la reinicia
  const vivo = useRef(true);
  // La creación corre UNA sola vez aunque el efecto se reejecute: crear
  // dos veces la misma casa sería justo el tipo de resto que se evita acá.
  const creada = useRef(false);

  async function crear(id: string) {
    if (creada.current) return;
    creada.current = true;
    setFase("creando");
    try {
      await onConfirmado(id);
      if (vivo.current) setFase("listo");
    } catch (e) {
      creada.current = false;
      if (vivo.current) { setDetalle((e as Error).message); setFase("error"); }
    }
  }

  // 1. Pedir la verificación (una vez por correo).
  useEffect(() => {
    vivo.current = true;
    (async () => {
      try {
        const v = await verificarCorreo(email, nombre);
        if (!vivo.current) return;
        setVerifId(v.id);
        if (v.estado === "entregado") { await crear(v.id); return; }
        if (v.estado === "error") {
          setDetalle(v.detalle || "No se pudo enviar el correo.");
          setFase("error");
          return;
        }
        setFase("esperando");
      } catch (e) {
        if (vivo.current) { setDetalle((e as Error).message); setFase("error"); }
      }
    })();
    return () => { vivo.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email]);

  // 2. Esperar el aviso del webhook.
  useEffect(() => {
    if (fase !== "esperando" || !verifId) return;
    let cancelado = false;
    (async () => {
      for (let i = 0; i < INTENTOS; i++) {
        await new Promise(r => setTimeout(r, CADA_MS));
        if (cancelado || !vivo.current) return;
        try {
          const v = await consultarVerificacion(verifId);
          if (cancelado || !vivo.current) return;
          if (v.estado === "entregado") { await crear(v.id); return; }
          if (v.estado === "rebotado" || v.estado === "queja") {
            setDetalle(v.detalle || "El servidor del destinatario rechazó el correo.");
            setFase("rebotado");
            return;
          }
        } catch {
          // Un tropiezo de red no decide nada: se sigue intentando.
        }
      }
      if (!cancelado && vivo.current) setFase("sin_confirmar");
    })();
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fase, verifId, ronda]);

  if (fase === "enviando" || fase === "esperando" || fase === "creando") {
    return (
      <div className="confirmacion" role="status" aria-live="polite">
        <div className="confirmacion-sobre">
          <svg viewBox="0 0 48 36" width="48" height="36" aria-hidden="true">
            <rect x="1" y="1" width="46" height="34" rx="4" className="confirmacion-sobre-cuerpo" />
            <path d="M1 5 L24 21 L47 5" className="confirmacion-sobre-solapa" />
          </svg>
        </div>
        <h4>
          {fase === "creando" ? "El correo llegó. Creando la cuenta…"
            : "Verificando que el correo llega…"}
        </h4>
        <p className="muted small">
          {fase === "creando"
            ? <>Confirmado que <b>{email}</b> existe. Guardando todo.</>
            : <>Le escribimos a <b>{email}</b>. Hasta que el servidor de correo
               confirme la entrega, no se crea nada.</>}
        </p>
        <div className="confirmacion-barra"><span /></div>
      </div>
    );
  }

  if (fase === "listo") {
    return (
      <div className="confirmacion confirmacion--ok" role="status" aria-live="polite">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-check" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-check-aro" />
          <path d="M15 27 l8 8 l15 -16" className="confirmacion-check-tilde" />
        </svg>
        <h4>Listo</h4>
        <p className="muted small">
          {textoCreado ? <>{textoCreado} </> : null}
          En unos minutos le llega a <b>{email}</b> el correo con el enlace para
          crear su contraseña. Si no lo ve, que revise spam.
        </p>
        <button onClick={onListo}>{textoListo || "Terminar"}</button>
      </div>
    );
  }

  if (fase === "rebotado") {
    return (
      <div className="confirmacion confirmacion--error" role="alert">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-aviso" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
          <path d="M26 14 v16" className="confirmacion-aviso-linea" />
          <circle cx="26" cy="37" r="2.4" className="confirmacion-aviso-punto" />
        </svg>
        <h4>Ese correo no existe</h4>
        <p className="muted small">
          <b>{email}</b> rechazó el mensaje{detalle ? `: ${detalle.replace(/[.\s]+$/, "")}.` : "."} <b>No se
          creó nada.</b> Revisá la dirección con la persona: lo más común es una
          letra de más o un dominio mal escrito.
        </p>
        <button onClick={onCorregir}>Corregir el correo</button>
      </div>
    );
  }

  if (fase === "sin_confirmar") {
    return (
      <div className="confirmacion" role="status" aria-live="polite">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-reloj" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
          <path d="M26 13 v14 l9 6" className="confirmacion-reloj-agujas" />
        </svg>
        <h4>Todavía sin confirmación</h4>
        <p className="muted small">
          El correo salió hacia <b>{email}</b> pero el servidor no confirmó la
          entrega en un minuto. <b>No se creó nada.</b> Algunos servidores tardan:
          podés seguir esperando, o revisar la dirección.
        </p>
        <div className="row-btns">
          <button onClick={() => { setFase("esperando"); setRonda(r => r + 1); }}>
            Seguir esperando
          </button>
          <button className="ghost" onClick={onCorregir}>Corregir el correo</button>
        </div>
      </div>
    );
  }

  // error: falló el envío, o la creación después de confirmar
  return (
    <div className="confirmacion confirmacion--error" role="alert">
      <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-aviso" aria-hidden="true">
        <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
        <path d="M26 14 v16" className="confirmacion-aviso-linea" />
        <circle cx="26" cy="37" r="2.4" className="confirmacion-aviso-punto" />
      </svg>
      <h4>No se pudo terminar</h4>
      <p className="muted small">{detalle} <b>No se creó nada.</b></p>
      <div className="row-btns">
        {verifId && creada.current === false && fase === "error" && (
          <button onClick={() => verifId && crear(verifId)}>Reintentar</button>
        )}
        <button className="ghost" onClick={onCorregir}>Volver al formulario</button>
      </div>
    </div>
  );
}
