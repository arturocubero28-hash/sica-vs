/**
 * Día 76 — copiar texto al portapapeles.
 *
 * navigator.clipboard solo existe en HTTPS (o localhost) y algunos
 * navegadores de Android viejos no lo tienen: en ese caso se usa el método
 * antiguo con un <textarea> oculto. Devuelve si se pudo copiar.
 */
export async function copiarTexto(texto: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(texto);
      return true;
    }
  } catch { /* sigue con el método antiguo */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = texto;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/** El número de cuenta tal como lo pide la app del banco: solo los dígitos. */
export const soloDigitos = (s: string) => s.replace(/\D/g, "");
