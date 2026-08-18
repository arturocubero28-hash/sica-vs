/**
 * Comprime una imagen a formato WebP directamente en el navegador antes de
 * subirla, usando el Canvas API (nativo, sin librerías externas).
 *
 * WebP pesa 25-35% menos que JPEG con la misma calidad visual, lo que
 * ahorra ancho de banda y espacio de almacenamiento en el servidor.
 *
 * Si el archivo no es una imagen (ej. PDF de comprobante) o si el
 * navegador no soporta la conversión, devuelve el archivo original sin
 * tocar — nunca bloquea la subida por un problema de compresión.
 */
export async function comprimirImagenWebp(
  archivo: File,
  opciones: { calidad?: number; maxAncho?: number; maxAlto?: number } = {}
): Promise<File> {
  const { calidad = 0.75, maxAncho = 1600, maxAlto = 1600 } = opciones;

  // Solo comprimir imágenes rasterizadas; PDFs y otros tipos pasan intactos
  if (!archivo.type.startsWith("image/") || archivo.type === "image/svg+xml") {
    return archivo;
  }

  try {
    const bitmap = await createImageBitmap(archivo);
    let { width, height } = bitmap;

    // Redimensionar manteniendo proporción si excede el máximo
    if (width > maxAncho || height > maxAlto) {
      const ratio = Math.min(maxAncho / width, maxAlto / height);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return archivo;

    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob: Blob | null = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/webp", calidad)
    );
    if (!blob) return archivo; // navegador sin soporte de codificación WebP

    // Día 62 — BUG REAL encontrado en producción: algunos navegadores (Safari
    // entre ellos) no fallan limpiamente cuando no soportan bien codificar a
    // WebP -- en vez de devolver null (lo cual ya está cubierto arriba),
    // devuelven SILENCIOSAMENTE un blob en OTRO formato (JPEG/PNG) aunque se
    // les pidió WebP explícitamente. El código no verificaba esto: le
    // forzaba el nombre ".webp" al archivo sin importar el contenido real
    // que el navegador realmente había producido. El archivo llegaba al
    // servidor con extensión .webp pero bytes de otro formato -- el backend
    // detecta correctamente la discrepancia (validar_contenido en
    // archivos.py) y lo rechaza como "dañado/formato inválido". Por eso
    // solo funcionaba en Chrome: es el único navegador con soporte
    // confiable de codificación WebP vía canvas -- no que los demás
    // "no soporten comprimir", sino que mentían sobre qué habían producido.
    if (blob.type !== "image/webp") {
      return archivo; // el navegador no devolvió lo que pedimos -- usar original, nunca bloquear la subida
    }

    const nombreBase = archivo.name.replace(/\.[^.]+$/, "");
    return new File([blob], `${nombreBase}.webp`, {
      type: "image/webp",
      lastModified: Date.now(),
    });
  } catch {
    // Cualquier error (navegador viejo, imagen corrupta, etc.) → usar original
    return archivo;
  }
}
