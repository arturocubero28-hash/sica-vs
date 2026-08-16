import { useState, useEffect } from "react";
import { getMiResidencial } from "../api/client";

/**
 * useMiResidencial — nombre, logo, dirección y colores de la residencial
 * del usuario logueado.
 *
 * Día 46: varias pantallas (reportes, dashboard, mensajes de WhatsApp)
 * tenían "Villas del Sol" escrito directamente en el código, en vez de usar
 * la residencial real que cada admin configura en Mi Perfil. Este hook
 * centraliza esa consulta para no repetirla en cada componente.
 *
 * Día 59 — se agregan direccion/colorPrimario/colorSecundario: los PDFs
 * generados en el navegador (Reportería, Historial) estaban hardcodeados
 * con "Villas del Sol" y el azul de fábrica sin importar la residencial
 * real -- ver utils/pdfReporte.ts, que usa estos valores para armar el
 * mismo tipo de encabezado con marca real que ya usa el recibo de pago
 * (logo, nombre, colores reales).
 *
 * Devuelve un nombre por defecto ("Residencial") mientras carga o si el
 * usuario no tiene residencial asignada, para que ningún texto quede vacío.
 * Los colores por defecto son los de fábrica del sistema.
 */
export function useMiResidencial() {
  const [nombre, setNombre] = useState<string>("Residencial");
  const [logo, setLogo] = useState<string | null>(null);
  const [direccion, setDireccion] = useState<string | null>(null);
  const [colorPrimario, setColorPrimario] = useState<string>("#022E45");
  const [colorSecundario, setColorSecundario] = useState<string>("#F48723");
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    getMiResidencial()
      .then((r) => {
        if (!activo) return;
        if (r?.nombre) setNombre(r.nombre);
        if (r?.logo_archivo) setLogo(r.logo_archivo);
        if (r?.direccion) setDireccion(r.direccion);
        if (r?.color_primario) setColorPrimario(r.color_primario);
        if (r?.color_secundario) setColorSecundario(r.color_secundario);
      })
      .catch(() => { /* se queda con el nombre/colores por defecto */ })
      .finally(() => { if (activo) setCargando(false); });
    return () => { activo = false; };
  }, []);

  return { nombre, logo, direccion, colorPrimario, colorSecundario, cargando };
}
