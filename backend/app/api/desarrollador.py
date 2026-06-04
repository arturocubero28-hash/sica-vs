"""
Módulo del Desarrollador — /api/v1/dev/

Panel exclusivo del rol 'desarrollador': métricas de salud del sistema,
conteos de la base de datos y actividad. También es quien posee la clave
de autorización para acciones sensibles (ej. modificar el saldo de caja).
"""
import datetime as dt
import os

from flask import Blueprint, jsonify

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Cuenta, Cuota, Pago
from app.models.visita import Visita, EventoAcceso
from app.models.caja import SesionCaja
from app.auth.security import roles_required

dev_bp = Blueprint("desarrollador", __name__)


@dev_bp.get("/metricas")
@roles_required("desarrollador")
def metricas(usuario_actual):
    """Métricas de salud y volumen del sistema."""
    ahora = dt.datetime.now(dt.timezone.utc)
    hace_24h = ahora - dt.timedelta(hours=24)

    # Conteos por tabla
    conteos = {
        "usuarios": Usuario.query.count(),
        "cuentas": Cuenta.query.count(),
        "cuotas": Cuota.query.count(),
        "pagos": Pago.query.count(),
        "visitas": Visita.query.count(),
        "eventos_acceso": EventoAcceso.query.count(),
        "sesiones_caja": SesionCaja.query.count(),
    }

    # Usuarios por rol
    roles = {}
    for u in Usuario.query.all():
        roles[u.rol] = roles.get(u.rol, 0) + 1

    # Actividad reciente (últimas 24h)
    eventos_24h = EventoAcceso.query.filter(EventoAcceso.ocurrido_en >= hace_24h).count()
    pagos_24h = Pago.query.filter(Pago.created_at >= hace_24h).count()

    # Salud de la base de datos
    db_ok = True
    db_error = None
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = False
        db_error = str(e)

    return jsonify({"data": {
        "estado_sistema": "operativo" if db_ok else "degradado",
        "db_conectada": db_ok,
        "db_error": db_error,
        "timestamp": ahora.isoformat(),
        "conteos": conteos,
        "usuarios_por_rol": roles,
        "actividad_24h": {
            "eventos_acceso": eventos_24h,
            "pagos": pagos_24h,
        },
        "cajas_abiertas": SesionCaja.query.filter_by(estado="abierta").count(),
    }})


@dev_bp.get("/logs")
@roles_required("desarrollador")
def logs(usuario_actual):
    """
    Últimos eventos del sistema como bitácora técnica.
    Por ahora deriva la actividad de eventos de acceso y pagos recientes
    (logging persistente a archivo se puede añadir luego).
    """
    items = []

    for e in EventoAcceso.query.order_by(EventoAcceso.ocurrido_en.desc()).limit(25).all():
        items.append({
            "tipo": "acceso",
            "descripcion": f"Evento de acceso ({e.direccion})",
            "timestamp": e.ocurrido_en.isoformat() if e.ocurrido_en else None,
        })
    for p in Pago.query.order_by(Pago.created_at.desc()).limit(25).all():
        items.append({
            "tipo": "pago",
            "descripcion": f"Pago {p.estado} · {p.metodo} · L {float(p.monto):.2f}",
            "timestamp": p.created_at.isoformat() if p.created_at else None,
        })

    items.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return jsonify({"data": items[:40]})
