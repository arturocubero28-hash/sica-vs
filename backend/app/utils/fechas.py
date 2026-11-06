"""
Día 75 — nombres de mes en español.

strftime("%B") usa el idioma del sistema operativo, y en los contenedores
de producción eso es inglés: el panel mostraba "November 2026". No se cambia
el locale del contenedor porque afecta a todo el proceso y depende de que
el paquete de idioma esté instalado; un diccionario no falla nunca.
"""
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def mes_es(fecha):
    """'Noviembre 2026' para cualquier fecha de noviembre de 2026."""
    return f"{MESES[fecha.month - 1].capitalize()} {fecha.year}"
