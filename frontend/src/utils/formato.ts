// Formato de moneda y fecha centralizados.
// Antes la función L() estaba duplicada en 7+ archivos. Acá vive una sola vez.

/** Formatea un número como Lempiras: 1234.5 -> "L 1,234.50" */
export function L(n: number): string {
  return "L " + n.toLocaleString("es-HN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Fecha corta en formato Honduras: "12/06/2026" */
export function fechaCorta(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-HN");
}

/** Fecha y hora: "12/06/2026, 14:30" */
export function fechaHora(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-HN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
