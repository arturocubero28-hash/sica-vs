import { useState, useRef, useEffect } from "react";

/**
 * Componente que captura el UID de una tarjeta RFID desde un lector USB.
 *
 * La mayoría de lectores RFID USB funcionan como un teclado (HID): cuando se
 * acerca una tarjeta, "teclean" el UID muy rápido y terminan con Enter.
 * Este componente detecta esa entrada veloz y la captura automáticamente,
 * distinguiéndola de una persona escribiendo a mano.
 */
export function LectorTarjeta({ onLeida, valor }: {
  onLeida: (uid: string) => void;
  valor: string;
}) {
  const [escuchando, setEscuchando] = useState(false);
  const [estado, setEstado] = useState<"idle" | "esperando" | "leida">("idle");
  const bufferRef = useRef("");
  const ultimaTeclaRef = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!escuchando) return;
    inputRef.current?.focus();

    function onKeyDown(e: KeyboardEvent) {
      const ahora = Date.now();
      // Si pasa mucho tiempo entre teclas, es una persona escribiendo → reiniciar buffer
      if (ahora - ultimaTeclaRef.current > 100) {
        bufferRef.current = "";
      }
      ultimaTeclaRef.current = ahora;

      if (e.key === "Enter") {
        const uid = bufferRef.current.trim();
        bufferRef.current = "";
        if (uid.length >= 4) {
          onLeida(uid);
          setEstado("leida");
          setEscuchando(false);
        }
        e.preventDefault();
        return;
      }
      // Acumular solo caracteres alfanuméricos
      if (e.key.length === 1 && /[a-zA-Z0-9]/.test(e.key)) {
        bufferRef.current += e.key;
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [escuchando, onLeida]);

  function activarLector() {
    bufferRef.current = "";
    setEstado("esperando");
    setEscuchando(true);
  }

  return (
    <div className="lector-tarjeta">
      {estado === "idle" && !valor && (
        <button className="lector-btn" onClick={activarLector} type="button">
          📇 Leer tarjeta con el lector
        </button>
      )}

      {estado === "esperando" && (
        <div className="lector-esperando">
          <div className="lector-pulse" />
          <span>Acercá la tarjeta al lector…</span>
          <button className="ghost mini" type="button" onClick={() => { setEscuchando(false); setEstado("idle"); }}>
            Cancelar
          </button>
        </div>
      )}

      {(estado === "leida" || valor) && (
        <div className="lector-leida">
          <span className="lector-check">✓ Tarjeta detectada</span>
          <code className="lector-uid">{valor}</code>
          <button className="ghost mini" type="button" onClick={() => { onLeida(""); setEstado("idle"); }}>
            Cambiar
          </button>
        </div>
      )}

      {/* Input oculto que mantiene el foco mientras escucha */}
      <input ref={inputRef} className="lector-input-oculto" tabIndex={-1}
        aria-hidden="true" value="" onChange={() => {}} />
    </div>
  );
}
