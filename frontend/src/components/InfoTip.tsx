import { useState } from "react";
import { Info } from "lucide-react";

/**
 * InfoTip — ícono "i" azul que muestra una burbuja de ayuda al pasar el mouse
 * o al tocar (funciona en escritorio y en pantallas táctiles).
 *
 * UX Día 43: extraído de UnidadesPanel para poder reutilizarlo en cualquier
 * pantalla. Antes vivía dentro de ese archivo y solo se usaba en el alta.
 *
 * Uso:
 *   <InfoTip texto="Explicación breve del campo o la acción." />
 */
export function InfoTip({ texto }: { texto: string }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <span className="infotip"
      onMouseEnter={() => setAbierto(true)}
      onMouseLeave={() => setAbierto(false)}
      onClick={(e) => { e.stopPropagation(); setAbierto(v => !v); }}>
      <Info size={15} />
      {abierto && <span className="infotip-bubble">{texto}</span>}
    </span>
  );
}
