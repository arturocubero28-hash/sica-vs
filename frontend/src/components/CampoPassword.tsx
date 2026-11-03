import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/**
 * Día 72 — campo de contraseña con el ojito para comprobar lo escrito.
 *
 * La web no tenía forma de ver lo que se estaba escribiendo: en el login,
 * al definir la contraseña de primer uso y al cambiarla. Eso obliga a
 * escribir a ciegas una clave que además exige mayúscula y signo, y en el
 * teléfono es donde más se equivoca la gente.
 *
 * El botón queda fuera del orden del tabulador (tabIndex -1) a propósito:
 * quien llena el formulario con el teclado pasa del campo al siguiente sin
 * tropezarse con el ojo.
 */
type Props = {
  value: string;
  onChange: (valor: string) => void;
  placeholder?: string;
  /** Qué hacer al presionar Enter (normalmente enviar el formulario). */
  onEnter?: () => void;
  autoFocus?: boolean;
  /** Ayuda al administrador de contraseñas del navegador. */
  autoComplete?: string;
};

export function CampoPassword({
  value, onChange, placeholder, onEnter, autoFocus, autoComplete,
}: Props) {
  const [ver, setVer] = useState(false);
  const etiqueta = ver ? "Ocultar contraseña" : "Mostrar contraseña";

  return (
    <div className="campo-password">
      <input
        type={ver ? "text" : "password"}
        placeholder={placeholder}
        value={value}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" && onEnter) onEnter(); }}
      />
      <button
        type="button"
        className="campo-password-ojo"
        onClick={() => setVer(v => !v)}
        aria-label={etiqueta}
        title={etiqueta}
        tabIndex={-1}
      >
        {ver ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  );
}
