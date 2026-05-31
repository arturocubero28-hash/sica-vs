"""
Módulo de Dashboard administrativo — estadísticas reales desde la base de datos.

  GET /api/v1/dashboard/metricas       -> tarjetas de métricas (QR hoy, activos, etc.)
  GET /api/v1/dashboard/visitas-tabla  -> tabla de visitas recientes con datos reales
"""
import datetime as dt

from flask import Blueprint, jsonify
from sqlalchemy import func

from app.extensions import db
from app.models.visita import Visita, CodigoQR, EventoAcceso
from app.models.cuenta import Cuenta, Unidad, Residente
from app.auth.security import roles_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/metricas")
@roles_required("admin", "super_admin")
def metricas(usuario_actual):
    """Tarjetas de métricas del Centro de Monitoreo, calculadas en vivo."""
    hoy_inicio = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

    # QR generados hoy
    qr_hoy = Visita.query.filter(Visita.created_at >= hoy_inicio).count()

    # Visitas activas (QR vigente, no usado ni expirado)
    activas = Visita.query.filter(Visita.estado == "activa").count()

    # QR utilizados (visitas con estado usada)
    usados = Visita.query.filter(Visita.estado == "usada").count()

    # QR expirados
    expirados = Visita.query.filter(Visita.estado == "expirada").count()

    # Totales generales del sistema
    total_unidades = Unidad.query.filter_by(activa=True).count()
    total_cuentas = Cuenta.query.count()
    total_residentes = Residente.query.filter_by(activo=True).count()
    cuentas_bloqueadas = Cuenta.query.filter_by(bloqueada=True).count()

    # Accesos registrados hoy
    accesos_hoy = EventoAcceso.query.filter(EventoAcceso.ocurrido_en >= hoy_inicio).count()

    return jsonify({"data": {
        "qr_generados_hoy": qr_hoy,
        "visitantes_activos": activas,
        "qr_utilizados": usados,
        "qr_expirados": expirados,
        "total_unidades": total_unidades,
        "total_cuentas": total_cuentas,
        "total_residentes": total_residentes,
        "cuentas_bloqueadas": cuentas_bloqueadas,
        "accesos_hoy": accesos_hoy,
    }})


@dashboard_bp.get("/visitas-tabla")
@roles_required("admin", "super_admin")
def visitas_tabla(usuario_actual):
    """Tabla de visitas recientes con el residente que las generó."""
    visitas = (Visita.query
               .order_by(Visita.created_at.desc())
               .limit(40).all())

    filas = []
    for v in visitas:
        cuenta = Cuenta.query.get(v.cuenta_id)
        unidad = Unidad.query.get(cuenta.unidad_id) if cuenta else None
        residente_nombre = "—"
        if v.residente and v.residente.usuario:
            residente_nombre = f"{v.residente.usuario.nombre} {v.residente.usuario.apellido}"
        filas.append({
            "id": str(v.uuid_publico),
            "residente": residente_nombre,
            "unidad": unidad.identificador if unidad else "—",
            "visitante": v.nombre_visitante,
            "tipo": v.tipo,
            "estado": v.estado,
            "vigencia": v.valido_hasta.strftime("%Y-%m-%d %H:%M") if v.valido_hasta else "—",
            "creado": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "—",
        })
    return jsonify({"data": filas})
