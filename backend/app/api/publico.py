"""
Estadísticas públicas para la landing (sin autenticación).

Solo expone números agregados y no sensibles (cantidad de unidades activas),
para que la página de inicio muestre datos reales en vez de valores fijos.
"""
from flask import Blueprint, jsonify

from app.models.cuenta import Unidad
from app.models.visita import AccesoFisico

publico_bp = Blueprint("publico", __name__)


@publico_bp.get("/estadisticas")
def estadisticas():
    """Números agregados y no sensibles para la landing."""
    familias = Unidad.query.filter_by(activa=True).count()
    accesos = AccesoFisico.query.filter_by(activo=True).count()
    return jsonify({"data": {
        "familias": familias,
        "accesos": accesos,
    }})
