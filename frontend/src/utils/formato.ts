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

/** Fecha relativa amigable: "hace 5 min", "hace 2 h", "ayer", "hace 3 días", o fecha si es viejo */
export function fechaRelativa(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const ahora = new Date();
  const seg = Math.floor((ahora.getTime() - d.getTime()) / 1000);
  if (seg < 60) return "hace un momento";
  const min = Math.floor(seg / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  const dias = Math.floor(h / 24);
  if (dias === 1) return "ayer";
  if (dias < 7) return `hace ${dias} días`;
  if (dias < 30) return `hace ${Math.floor(dias / 7)} sem`;
  return d.toLocaleDateString("es-HN");
}
