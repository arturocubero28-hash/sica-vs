/**
 * Día 47 — colores personalizables por residencial.
 *
 * Aplica el color primario/secundario del admin como variables CSS en
 * tiempo real, sobre las variables que ya unificamos en la Parte 1
 * (--marca-azul/--marca-naranja, de las que --azul/--azul2 heredan). Al
 * cambiar el valor de una variable CSS en :root, TODO lo que la usa en
 * toda la app se actualiza solo — no hace falta recorrer componentes.
 */

const patronHex = /^#[0-9A-Fa-f]{6}$/;

// El valor de fábrica exacto que la app ya usaba para el "tono claro" del
// azul (degradados, hover) — ver backend/app/models/residencial.py
// DEFAULT_COLOR_PRIMARIO. No es una fórmula matemática limpia (fue elegido
// a mano por diseño), así que para el caso SIN personalizar se usa este
// valor exacto en vez de derivarlo — garantiza cero diferencia visual para
// una residencial que nunca toca sus colores.
const AZUL_PRIMARIO_DE_FABRICA = "#022E45";
const AZUL_CLARO_DE_FABRICA = "#044a6e";

/**
 * Aplica los colores de la residencial como variables CSS en el elemento
 * raíz. Se llama una sola vez, apenas se resuelve la sesión (ver App.tsx),
 * no en cada componente — un cambio en :root alcanza a toda la app.
 *
 * Validación defensiva: aunque el backend ya valida el formato al guardar
 * (ver PUT /unidades/mi-residencial), estos valores terminan inyectados
 * directo en CSS del lado del cliente — nunca hay que confiar solo en que
 * el servidor validó bien; si algo no tiene forma de hex de 6 dígitos, se
 * ignora en silencio y la app se queda con el color de fábrica en vez de
 * arriesgar un estilo roto o un intento de inyección.
 */
export function aplicarColoresResidencial(colorPrimario?: string, colorSecundario?: string) {
  const raiz = document.documentElement.style;

  if (colorPrimario && patronHex.test(colorPrimario)) {
    raiz.setProperty("--marca-azul", colorPrimario);
    raiz.setProperty("--azul", colorPrimario);
    // El tono "claro" (--marca-azul-2 / --azul2, usado en degradados y
    // :hover) se deriva aclarando el primario — salvo que sea EXACTAMENTE
    // el color de fábrica, en cuyo caso se usa el valor de fábrica real
    // (no una aproximación matemática), para cero diferencia visual en el
    // caso sin personalizar.
    const claro = colorPrimario.toUpperCase() === AZUL_PRIMARIO_DE_FABRICA.toUpperCase()
      ? AZUL_CLARO_DE_FABRICA
      : aclarar(colorPrimario, 0.35);
    raiz.setProperty("--marca-azul-2", claro);
    raiz.setProperty("--azul2", claro);
  }

  if (colorSecundario && patronHex.test(colorSecundario)) {
    raiz.setProperty("--marca-naranja", colorSecundario);
  }
}

/** Aclara un color hex hacia blanco un porcentaje (0 a 1), para el tono de
 * hover/degradado cuando no hay un valor de fábrica exacto que usar. */
function aclarar(hex: string, cantidad: number): string {
  const num = parseInt(hex.slice(1), 16);
  const canal = (corrimiento: number) => {
    const c = (num >> corrimiento) & 0xff;
    return Math.round(c + (255 - c) * cantidad);
  };
  return `#${[canal(16), canal(8), canal(0)].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Día 57 — restablece los colores de fábrica, quitando las variables CSS
 * personalizadas que aplicarColoresResidencial haya inyectado en :root.
 *
 * Se llama al CERRAR SESIÓN. El problema que resuelve: aplicarColoresResidencial
 * setea las variables inline en document.documentElement.style; si no se
 * limpian, quedan pegadas y las pantallas de landing/login heredan los
 * colores de la residencial de la sesión anterior.
 *
 * Se usa removeProperty (no setProperty con valores de fábrica): al quitar
 * la variable inline, el CSS "cae" al valor de fábrica ya definido en el
 * stylesheet base (:root en index.css, --marca-azul: #022E45, etc.). Así se
 * vuelve exactamente al estado inicial sin hardcodear los valores acá.
 */
export function restablecerColoresFabrica() {
  const raiz = document.documentElement.style;
  for (const prop of ["--marca-azul", "--marca-azul-2", "--marca-naranja", "--azul", "--azul2"]) {
    raiz.removeProperty(prop);
  }
}
