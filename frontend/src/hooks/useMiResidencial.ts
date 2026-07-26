import { useState, useEffect } from "react";
import { getMiResidencial } from "../api/client";

/**
 * useMiResidencial — nombre y logo de la residencial del usuario logueado.
 *
 * Día 46: varias pantallas (reportes, dashboard, mensajes de WhatsApp)
 * tenían "Villas del Sol" escrito directamente en el código, en vez de usar
 * la residencial real que cada admin configura en Mi Perfil. Este hook
 * centraliza esa consulta para no repetirla en cada componente.
 *
 * Devuelve un nombre por defecto ("Residencial") mientras carga o si el
 * usuario no tiene residencial asignada, para que ningún texto quede vacío.
 */
export function useMiResidencial() {
  const [nombre, setNombre] = useState<string>("Residencial");
  const [logo, setLogo] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    getMiResidencial()
      .then((r) => {
        if (!activo) return;
        if (r?.nombre) setNombre(r.nombre);
        if (r?.logo_archivo) setLogo(r.logo_archivo);
      })
      .catch(() => { /* se queda con el nombre por defecto */ })
      .finally(() => { if (activo) setCargando(false); });
    return () => { activo = false; };
  }, []);

  return { nombre, logo, cargando };
}
