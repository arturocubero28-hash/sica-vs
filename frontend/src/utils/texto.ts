/**
 * Día 73 — formato de los nombres propios.
 *
 * Los nombres se escribían como venía: "maria del carmen LOPEZ", "juan".
 * Después aparecen en el panel del guardia, en los correos y en los
 * reportes del patronato, y ahí se nota.
 *
 * Se capitaliza mientras se escribe y no al guardar, para que la persona
 * vea lo que va a quedar. Tres cuidados:
 *
 *   - Las partículas de los apellidos hondureños van en minúscula cuando
 *     están en el medio: "Juan de la Cruz", no "Juan De La Cruz". Pero
 *     "De la Cruz" como apellido suelto sí empieza con mayúscula, así que
 *     la primera palabra siempre se capitaliza.
 *   - Los espacios del medio se respetan tal cual se escriben: si se
 *     colapsaran acá, no se podría escribir el espacio entre dos nombres
 *     (desaparecería apenas se teclea).
 *   - Lo que ya está en mayúsculas se baja: alguien con el bloq mayús
 *     puesto escribiría "LOPEZ" y quedaría así para siempre.
 */
const PARTICULAS = new Set([
  "de", "del", "la", "las", "los", "y", "e", "da", "do", "dos", "van", "von",
]);

export function capitalizarNombre(valor: string): string {
  if (!valor) return valor;
  return valor
    .toLocaleLowerCase("es")
    .split(" ")
    .map((palabra, i) => {
      if (!palabra) return palabra;          // espacio recién tecleado
      if (i > 0 && PARTICULAS.has(palabra)) return palabra;
      // Apellidos con apóstrofo o guion: O'Brien, Paz-Barahona.
      return palabra.replace(/(^|['’-])([a-záéíóúñü])/g,
        (_, sep, letra) => sep + letra.toLocaleUpperCase("es"));
    })
    .join(" ");
}
