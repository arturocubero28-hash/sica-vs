import { useState } from "react";
import { CapturaFoto } from "./CapturaFoto";
import { subirFotoResidente, urlFotoResidente } from "../api/client";
import type { ResidenteDTO } from "../api/client";

/**
 * Día 73 — ver y cambiar la foto de alguien ya registrado.
 *
 * Antes, tanto en Casas como en el Padrón, la foto se cambiaba con un
 * <input type="file"> escondido detrás de un ícono. Eso tiene dos
 * problemas que desde el teléfono no se notan:
 *
 *   1. En la laptop de administración —que es donde se da de alta— abre el
 *      explorador de archivos y nada más. No hay forma de TOMAR una foto
 *      nueva: solo elegir una que alguien ya sacó con otra cosa. De ahí el
 *      "no nos deja volver a tomar otra".
 *   2. No se podía ver la foto actual en grande para decidir si valía la
 *      pena cambiarla. La miniatura son 38 píxeles.
 *
 * Esta ventana resuelve las dos: muestra la foto actual grande y usa el
 * mismo componente de captura del alta (cámara del equipo o archivo). La
 * foto vieja se reemplaza solo al confirmar, así que abrir la ventana por
 * curiosidad no cambia nada.
 */
type Props = {
  residente: ResidenteDTO;
  /** Cuenta (casa/apartamento) a la que pertenece: la necesita el endpoint. */
  cuentaId: string;
  onCerrar: () => void;
  onActualizado: () => void;
};

export function ModalFotoResidente({ residente, cuentaId, onCerrar, onActualizado }: Props) {
  const [nueva, setNueva] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  const tiene = !!residente.foto_url;

  async function guardar() {
    if (!nueva) return;
    setSubiendo(true); setError("");
    try {
      await subirFotoResidente(cuentaId, residente.id, nueva);
      onActualizado();
      onCerrar();
    } catch (e) {
      // Se queda abierta con el error a la vista: cerrarla haría perder la
      // foto recién tomada y habría que volver a tomarla.
      setError((e as Error).message);
      setSubiendo(false);
    }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body modal-foto" onClick={e => e.stopPropagation()}>
        <div className="modal-alta-head">
          <div>
            <h3>Foto de {residente.nombre}</h3>
            <p className="muted small" style={{ margin: 0, textAlign: "left" }}>
              Es la que ve el guardia para verificar su identidad en el portón.
            </p>
          </div>
          <button className="modal-x" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </div>

        <div className="modal-alta-body">
          {tiene && !nueva && (
            <div className="modal-foto-actual">
              <img src={urlFotoResidente(residente.foto_url!)} alt={residente.nombre} />
            </div>
          )}

          <div className="sub" style={{ marginBottom: 8 }}>
            {tiene ? "Tomar una foto nueva" : "Tomar la foto"}
          </div>
          <CapturaFoto valor={nueva} onCambio={setNueva} />

          {error && <div className="error" style={{ marginTop: 10 }}>⚠ {error}</div>}
        </div>

        <div className="modal-alta-footer">
          <button className="ghost" onClick={onCerrar} disabled={subiendo}>Cancelar</button>
          <button onClick={guardar} disabled={!nueva || subiendo}>
            {subiendo ? "Guardando…" : tiene ? "Reemplazar foto" : "Guardar foto"}
          </button>
        </div>
      </div>
    </div>
  );
}
