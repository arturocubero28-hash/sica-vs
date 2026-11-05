import { useEffect, useRef, useState } from "react";
import { consultarVerificacion, verificarCorreo } from "../api/client";

/**
 * Día 73 — confirmar la dirección de correo ANTES de crear nada.
 *
 * LA REGLA: si el correo no llega, no se crea nada. Ni la casa, ni la
 * cuota, ni el acceso. Solo cuando Resend confirma la entrega se ejecuta
 * la creación. Mientras no hay confirmación, no se crea nada y la
 * pantalla se queda en el error hasta que se corrija la dirección.
 *
 * UN SOLO CORREO: el que se manda para confirmar la dirección ES el de
 * activación, con el enlace para la contraseña. El enlace lleva el correo
 * adentro y la cuenta se busca recién cuando la persona hace clic, así
 * que puede salir antes de que la cuenta exista. Si rebota, no le llega a
 * nadie y la cuenta nunca se crea.
 *
 * El orden:
 *   1. Se pide la verificación: el servidor manda el correo de activación.
 *   2. Se espera el aviso del webhook de Resend.
 *   3a. Entregado -> se ejecuta onConfirmado(id), que crea todo de una vez.
 *   3b. Rebotó, o 60 s sin confirmación -> no se creó nada. Pantalla de
 *       error hasta corregir la dirección.
 *
 * El backend es quien hace cumplir la regla (ver api/verificacion_correo.py):
 * esta pantalla es la forma cómoda de cumplirla, no la única barrera. Y
 * el backend es idempotente: si el pedido de crear llega dos veces con la
 * misma verificación, devuelve lo creado en vez de duplicarlo.
 */
type Fase =
  | "confirmando"   // pidiendo la verificación y esperando el aviso
  | "creando"       // llegó: guardando todo
  | "listo"         // creado
  | "no_llego"      // rebotó, o no se pudo confirmar: nada creado
  | "ocupado"       // el correo ya es de otra persona: nada creado
  | "error";        // falló el envío o la creación

type Props = {
  email: string;
  /** Nombre de la persona, para el mensaje final. */
  nombre?: string;
  /** Lo que se crea SOLO si el correo llegó. Recibe el id de la verificación. */
  onConfirmado: (verificacionId: string) => Promise<void>;
  /** Volver al formulario a corregir el correo. */
  onCorregir: () => void;
  /** Cerrar y seguir, una vez creado. */
  onListo: () => void;
  textoListo?: string;
  /** Qué se creó, para el mensaje final. Ej: "La casa 60 ya participa del sistema." */
  textoCreado?: string;
};

const CADA_MS = 2500;
const INTENTOS = 24;          // 60 segundos

export function ConfirmacionEnvio({
  email, nombre, onConfirmado, onCorregir, onListo, textoListo, textoCreado,
}: Props) {
  const [fase, setFase] = useState<Fase>("confirmando");
  const [detalle, setDetalle] = useState("");
  const [porTiempo, setPorTiempo] = useState(false);   // no_llego por falta de respuesta
  const [verifId, setVerifId] = useState<string | null>(null);
  const [ronda, setRonda] = useState(0);
  const vivo = useRef(true);
  // Cada una de estas cosas corre UNA sola vez aunque React vuelva a
  // ejecutar el efecto (en desarrollo lo hace a propósito): pedir dos
  // verificaciones le mandaría dos correos a la persona, y crear dos veces
  // la misma casa sería justo lo que se está evitando.
  const pedida = useRef(false);
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

  // 1. Pedir la verificación: manda el correo de activación.
  useEffect(() => {
    vivo.current = true;
    if (pedida.current) return () => { vivo.current = false; };
    pedida.current = true;
    (async () => {
      try {
        const v = await verificarCorreo(email, nombre);
        if (!vivo.current) return;
        setVerifId(v.id);
        if (v.estado === "entregado") { await crear(v.id); return; }
        if (v.estado === "rebotado" || v.estado === "queja") {
          setDetalle(v.detalle || "");
          setPorTiempo(false);
          setFase("no_llego");
          return;
        }
        if (v.estado === "error") {
          setDetalle(v.detalle || "No se pudo enviar el correo.");
          setFase("error");
        }
        // enviando / enviado / demorado: el efecto de abajo espera el aviso.
      } catch (e) {
        if (!vivo.current) return;
        const msg = (e as Error).message || "";
        // El backend dice de quién es el correo ("ya está registrado para…").
        if (/ya está registrado/i.test(msg)) { setDetalle(msg); setFase("ocupado"); return; }
        setDetalle(msg);
        setFase("error");
      }
    })();
    return () => { vivo.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. Esperar el aviso del webhook.
  useEffect(() => {
    if (fase !== "confirmando" || !verifId) return;
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
            setDetalle(v.detalle || "");
            setPorTiempo(false);
            setFase("no_llego");
            return;
          }
        } catch {
          // Un tropiezo de red no decide nada: se sigue intentando.
        }
      }
      if (!cancelado && vivo.current) { setPorTiempo(true); setFase("no_llego"); }
    })();
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fase, verifId, ronda]);

  const quien = nombre?.trim() ? nombre.trim().split(" ")[0] : "la persona";

  // ── Esperando ──────────────────────────────────────────────────────────
  if (fase === "confirmando" || fase === "creando") {
    return (
      <div className="confirmacion" role="status" aria-live="polite">
        <div className="confirmacion-sobre">
          <svg viewBox="0 0 48 36" width="48" height="36" aria-hidden="true">
            <rect x="1" y="1" width="46" height="34" rx="4" className="confirmacion-sobre-cuerpo" />
            <path d="M1 5 L24 21 L47 5" className="confirmacion-sobre-solapa" />
          </svg>
        </div>
        <h4>{fase === "creando" ? "Correo confirmado. Terminando el registro…"
                                : "Confirmando la dirección de correo…"}</h4>
        <p className="muted small">
          {fase === "creando"
            ? <>El servidor de <b>{email}</b> recibió el correo. Guardando todo.</>
            : <>Le enviamos a <b>{email}</b> el correo con el enlace para crear su
               contraseña. Hasta que el servidor de correo confirme que lo recibió,
               no se crea nada.</>}
        </p>
        <div className="confirmacion-barra"><span /></div>
      </div>
    );
  }

  // ── Llegó y se creó ────────────────────────────────────────────────────
  if (fase === "listo") {
    return (
      <div className="confirmacion confirmacion--ok" role="status" aria-live="polite">
        <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-check" aria-hidden="true">
          <circle cx="26" cy="26" r="24" className="confirmacion-check-aro" />
          <path d="M15 27 l8 8 l15 -16" className="confirmacion-check-tilde" />
        </svg>
        <h4>Correo enviado</h4>
        {textoCreado && <p className="muted small" style={{ marginBottom: 4 }}>{textoCreado}</p>}
        <div className="confirmacion-indicaciones">
          <b>Decile a {quien}:</b>
          <ol>
            <li>Que busque en <b>{email}</b> un correo de la residencial con el
              asunto <i>«Activá tu cuenta»</i>. Si no está en la bandeja de entrada,
              que revise <b>spam</b> o <b>promociones</b>.</li>
            <li>Que toque <b>«Confirmar mi cuenta»</b> y cree su contraseña.</li>
            <li>El enlace vale <b>48 horas</b>. Si se le vence, se le manda otro
              desde la ficha de la casa con «Regenerar enlace».</li>
          </ol>
        </div>
        <button onClick={onListo}>{textoListo || "Terminar"}</button>
      </div>
    );
  }

  // ── El correo ya es de otra persona ────────────────────────────────────
  if (fase === "ocupado") {
    return (
      <div className="confirmacion confirmacion--error" role="alert">
        <IconoAviso />
        <h4>Ese correo ya está en uso</h4>
        <p className="muted small">
          {detalle} <b>No se creó nada.</b> Pedile a la persona otra dirección.
        </p>
        <button onClick={onCorregir}>Poner otro correo</button>
      </div>
    );
  }

  // ── No llegó, o no se pudo confirmar ───────────────────────────────────
  if (fase === "no_llego") {
    const motivo = detalle ? ` (${detalle.replace(/[.\s]+$/, "")})` : "";
    return (
      <div className="confirmacion confirmacion--error" role="alert">
        <IconoAviso />
        <h4>No se pudo confirmar el correo</h4>
        <p className="muted small">
          {porTiempo
            ? <>El servidor de <b>{email}</b> no confirmó que recibió el mensaje.</>
            : <><b>{email}</b> no existe o rechazó el mensaje{motivo}.</>}
          {" "}<b>No se creó nada.</b> Revisá la dirección con la persona y poné un
          correo válido: lo más común es una letra de más o un dominio mal escrito
          (<i>gmial.com</i>, <i>hotmial.com</i>).
        </p>
        <div className="row-btns">
          <button onClick={onCorregir}>Corregir el correo</button>
          {/* Solo cuando fue por tiempo: hay servidores lentos, y esperar un
              poco más no manda otro correo ni crea nada. Si rebotó, esperar
              no cambia nada. */}
          {porTiempo && (
            <button className="ghost" onClick={() => { setFase("confirmando"); setRonda(r => r + 1); }}>
              Esperar un poco más
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Error del envío o de la creación ───────────────────────────────────
  return (
    <div className="confirmacion confirmacion--error" role="alert">
      <IconoAviso />
      <h4>No se pudo terminar</h4>
      <p className="muted small">
        {detalle}{" "}
        {/* Si falló la creación (hay verificación), no se puede afirmar que
            no se guardó nada: la red pudo cortarse justo después de que el
            servidor guardó. Lo que sí se puede afirmar es que reintentar no
            duplica. Si falló antes, en el envío, ahí no se creó nada. */}
        {verifId
          ? <>Reintentá: si algo llegó a guardarse, <b>no se duplica</b>.</>
          : <b>No se creó nada.</b>}
      </p>
      <div className="row-btns">
        {/* Reintentar es seguro: el servidor no duplica si el primer intento
            sí llegó a guardar. */}
        {verifId && <button onClick={() => verifId && crear(verifId)}>Reintentar</button>}
        <button className="ghost" onClick={onCorregir}>Volver al formulario</button>
      </div>
    </div>
  );
}

function IconoAviso() {
  return (
    <svg viewBox="0 0 52 52" width="56" height="56" className="confirmacion-aviso" aria-hidden="true">
      <circle cx="26" cy="26" r="24" className="confirmacion-aviso-aro" />
      <path d="M26 14 v16" className="confirmacion-aviso-linea" />
      <circle cx="26" cy="37" r="2.4" className="confirmacion-aviso-punto" />
    </svg>
  );
}
