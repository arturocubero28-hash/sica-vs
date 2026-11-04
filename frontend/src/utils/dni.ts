/**
 * Identidad hondureña (DNI): 13 dígitos, con el formato 0000-0000-00000.
 *
 * Día 73 — estaba dentro de UnidadesPanel. Al pedir la ficha completa para
 * dar acceso desde el padrón hacía falta la misma función en otro módulo, y
 * copiarla significaba que una corrección futura se aplicara en un solo
 * lado. El backend valida el mismo criterio (_validar_dni en censo.py y el
 * alta normal): 13 dígitos, los guiones son cosmética.
 */

/** Formatea mientras se escribe: solo números, guiones automáticos. */
export function formatearDNI(valor: string): string {
  const soloNums = valor.replace(/\D/g, "").slice(0, 13);
  const p1 = soloNums.slice(0, 4);
  const p2 = soloNums.slice(4, 8);
  const p3 = soloNums.slice(8, 13);
  let out = p1;
  if (p2) out += "-" + p2;
  if (p3) out += "-" + p3;
  return out;
}

/** ¿Está completo (13 dígitos)? */
export function dniCompleto(valor: string): boolean {
  return valor.replace(/\D/g, "").length === 13;
}
