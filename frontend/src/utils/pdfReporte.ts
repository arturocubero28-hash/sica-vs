/**
 * Encabezado compartido para los PDFs generados con jsPDF en todo el
 * sistema (Día 59). Extraído del patrón que ya usaba Reportería (5 reportes
 * casi idénticos, cada uno con su propia copia del mismo bloque) para que
 * Historial pueda reutilizarlo exacto y ambas pantallas generen PDFs
 * visualmente consistentes — misma banda azul, mismo naranja de acento,
 * misma tipografía — sin duplicar el código una sexta vez.
 *
 * No se tocó Reporteria.tsx al extraer esto: sus 5 reportes siguen con su
 * implementación inline tal cual estaba (ya probada, sin motivo para
 * arriesgarla), y este helper es la referencia para todo lo nuevo.
 */
export function dibujarEncabezadoReportePDF(doc: any, titulo: string, nombreResidencial: string) {
  doc.setFillColor(2, 46, 69); // var(--marca-azul)
  doc.rect(0, 0, 210, 28, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(18);
  doc.text(titulo, 14, 13);
  doc.setFontSize(10);
  doc.setTextColor(245, 197, 24);
  doc.text(`Residencial ${nombreResidencial}`, 14, 21);
  doc.setTextColor(40, 52, 64);
}

/** Mismo naranja de acento que usan las tablas (autoTable headStyles) en
 * todos los reportes existentes — para no repetir el RGB suelto en cada
 * archivo nuevo. */
export const NARANJA_TABLA_PDF: [number, number, number] = [244, 135, 35];
