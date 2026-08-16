/**
 * Módulo compartido para armar el encabezado de los PDFs generados con
 * jsPDF en el navegador (Reportería, Historial). Día 59.
 *
 * Origen: extraído primero (misma fecha, commit anterior) del patrón que
 * ya usaba Reportería — pero ese primer intento seguía con una banda azul
 * y un naranja FIJOS, sin logo ni datos reales de la residencial. El
 * usuario señaló, con razón, que eso repetía el mismo error que ya se
 * había cometido con el recibo de pago: todo hardcodeado a "Villas del
 * Sol", sin soporte real para más de una residencial (el sistema ya es
 * multi-residencial desde el Día 37).
 *
 * Esta versión usa la identidad REAL de la residencial —logo, nombre,
 * dirección, colores— tomada de useMiResidencial(), replicando en jsPDF
 * (client-side) el mismo espíritu visual que ya tiene el recibo de pago
 * (backend, reportlab): franja de color de marca, logo real, nombre real.
 * No es una réplica pixel a pixel (jsPDF es más limitado que reportlab
 * para clips/gradientes), pero sí la misma idea: nada queda fijo.
 */

interface DatosResidencialPDF {
  nombre: string;
  logo: string | null;       // logo_archivo — la clave, no la URL
  direccion: string | null;
  colorPrimario: string;     // hex, ej. "#022E45"
  colorSecundario: string;   // hex, ej. "#F48723"
}

function hexARgb(hex: string): [number, number, number] {
  const limpio = hex.replace("#", "");
  const num = parseInt(limpio, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

/**
 * Descarga el logo (protegido por token, igual que <img> en la app) y lo
 * convierte a un data URL en base64, que es lo único que jsPDF puede
 * incrustar con doc.addImage(). Devuelve null si no hay logo o si falla
 * la descarga — nunca debe tumbar la generación del PDF por esto (mismo
 * criterio que el try/except del logo en el recibo del backend).
 */
async function logoComoDataUrl(logo: string | null): Promise<{ datos: string; formato: string } | null> {
  if (!logo) return null;
  try {
    const { urlLogoResidencial } = await import("../api/client");
    const resp = await fetch(urlLogoResidencial(logo));
    if (!resp.ok) return null;
    const blob = await resp.blob();
    const datos = await new Promise<string>((resolve, reject) => {
      const lector = new FileReader();
      lector.onload = () => resolve(lector.result as string);
      lector.onerror = reject;
      lector.readAsDataURL(blob);
    });
    // jsPDF necesita saber el formato (JPEG/PNG/WEBP) — se deduce del
    // content-type real del archivo, no de la extensión del nombre (que
    // podría no coincidir si algún día se permite recortar/convertir).
    const tipo = blob.type || "";
    const formato = tipo.includes("png") ? "PNG" : tipo.includes("webp") ? "WEBP" : "JPEG";
    return { datos, formato };
  } catch {
    return null; // logo corrupto o inaccesible no debe tumbar el reporte
  }
}

/**
 * Arma el encabezado con la marca REAL de la residencial: franja de color
 * (color_primario), logo si tiene, nombre, y dirección debajo si existe.
 * Es async porque necesita descargar el logo antes de poder dibujarlo.
 *
 * Devuelve la posición Y donde termina el encabezado, para que quien llama
 * sepa desde dónde seguir dibujando el resto del contenido (título de
 * sección, tabla, etc.) sin pisar la franja.
 */
export async function dibujarEncabezadoConMarca(
  doc: any, titulo: string, residencial: DatosResidencialPDF
): Promise<number> {
  const [r, g, b] = hexARgb(residencial.colorPrimario);
  const ALTO = 30;
  doc.setFillColor(r, g, b);
  // Se mantiene un rectángulo recto (no roundedRect): redondear las 4
  // esquinas se descartó a propósito -- las de ARRIBA quedan pegadas al
  // borde mismo de la página (y=0), así que redondearlas dejaría una
  // muesca visible en las puntas superiores (no hay margen arriba contra
  // el que "disimular" la curva, a diferencia del recibo, que redondea
  // SOLO abajo con un path armado a mano en reportlab). jsPDF no permite
  // elegir esquinas individuales con una sola llamada simple, y sin poder
  // generar+ver el PDF en este entorno (a diferencia de los PDFs del
  // backend, donde sí se puede con pdftoppm), no vale arriesgar un path
  // bezier a ciegas que podría salir peor que el rectángulo recto actual.
  doc.rect(0, 0, 210, ALTO, "F");

  let xTexto = 14;
  const logoInfo = await logoComoDataUrl(residencial.logo);
  if (logoInfo) {
    try {
      const tam = 16;
      doc.addImage(logoInfo.datos, logoInfo.formato, 12, 7, tam, tam);
      xTexto = 12 + tam + 5;
    } catch {
      // Un logo corrupto o en un formato que jsPDF no soporta no debe
      // tumbar el reporte — sigue sin logo, igual que en el backend.
    }
  }

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(15);
  doc.text(residencial.nombre, xTexto, 13);
  doc.setFontSize(9);
  const [rs, gs, bs] = hexARgb(residencial.colorSecundario);
  doc.setTextColor(rs, gs, bs);
  doc.text(titulo, xTexto, 20);
  if (residencial.direccion) {
    doc.setTextColor(230, 230, 230);
    doc.setFontSize(8);
    doc.text(residencial.direccion, xTexto, 26);
  }

  doc.setTextColor(40, 52, 64);
  return ALTO + 8; // deja un margen debajo de la franja para lo próximo
}

/**
 * Color de acento para tablas (autoTable headStyles) que respeta el
 * secundario real de la residencial, en vez del naranja de fábrica fijo.
 */
export function colorTablaPDF(residencial: DatosResidencialPDF): [number, number, number] {
  return hexARgb(residencial.colorSecundario);
}
