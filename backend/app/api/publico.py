"""
Estadísticas públicas para la landing (sin autenticación).

Solo expone números agregados y no sensibles (cantidad de unidades activas),
para que la página de inicio muestre datos reales en vez de valores fijos.
"""
from flask import Blueprint, jsonify

from app.extensions import db
from app.models.cuenta import Unidad
from app.models.visita import AccesoFisico

publico_bp = Blueprint("publico", __name__)


@publico_bp.get("/estadisticas")
def estadisticas():
    """Números agregados y no sensibles para la landing."""
    familias = Unidad.query.filter_by(activa=True).count()
    # Día 59 — bug real reportado: "Accesos" mostraba 6 cuando el usuario
    # había configurado 2 portones. Causa: se contaban las filas de
    # accesos_fisicos, pero UN punto de acceso (un portón) se guarda como
    # VARIAS filas ahí -- una tranca por dirección/tipo que tenga (peatonal,
    # entrada vehicular, salida vehicular), agrupadas por el campo
    # punto_acceso. 2 portones con las 3 trancas c/u = 6 filas, aunque para
    # cualquier persona (incluido quien lo configuró) "accesos" significa
    # portones, no relays individuales. Se cuenta ahora punto_acceso
    # DISTINCT, que sí refleja la cantidad de portones reales.
    #
    # coalesce(punto_acceso, 'tranca-' || id): punto_acceso es nullable (hay
    # trancas viejas, de antes de que este campo agrupador existiera). Sin
    # el coalesce, dos filas con punto_acceso NULL contarían como "el mismo"
    # punto de acceso (DISTINCT junta los NULL en un solo grupo) y
    # subestimarían el total -- con el coalesce, cada tranca sin grupo se
    # cuenta como su propio punto individual, en vez de perderse.
    accesos = (db.session.query(
                  db.func.coalesce(AccesoFisico.punto_acceso,
                                   db.func.concat("tranca-", AccesoFisico.id)))
               .filter(AccesoFisico.activo == True)  # noqa: E712
               .distinct().count())
    return jsonify({"data": {
        "familias": familias,
        "accesos": accesos,
    }})
