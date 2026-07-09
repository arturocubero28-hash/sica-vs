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
