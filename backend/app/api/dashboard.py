"""
Módulo de Dashboard administrativo — estadísticas reales desde la base de datos.

  GET /api/v1/dashboard/metricas       -> tarjetas de métricas (QR hoy, activos, etc.)
  GET /api/v1/dashboard/visitas-tabla  -> tabla de visitas recientes con datos reales
"""
import datetime as dt
import os

from flask import Blueprint, jsonify, send_file, current_app
from sqlalchemy import func

from app.extensions import db
from app.models.visita import Visita, CodigoQR, EventoAcceso
from app.models.cuenta import Cuenta, Unidad, Residente
from app.auth.security import roles_required, token_required

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

    # Visitas actualmente DENTRO de la residencial (entraron y no han salido)
    adentro_ahora = len(_visitas_adentro())

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
        "adentro_ahora": adentro_ahora,
    }})


@dashboard_bp.get("/visitas-tabla")
@roles_required("admin", "super_admin")
def visitas_tabla(usuario_actual):
    """Tabla de visitas recientes. El estado mostrado refleja el ÚLTIMO evento de acceso."""
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

        # Determinar estado real basado en el último evento de acceso
        ultimo_evento = (
            EventoAcceso.query
            .filter_by(visita_id=v.id)
            .order_by(EventoAcceso.ocurrido_en.desc())
            .first()
        )
        if ultimo_evento:
            estado_real = "adentro" if ultimo_evento.direccion == "entrada" else "salio"
        else:
            estado_real = v.estado  # activa, expirada, revocada

        filas.append({
            "id": str(v.uuid_publico),
            "residente": residente_nombre,
            "unidad": unidad.identificador if unidad else "—",
            "visitante": v.nombre_visitante,
            "tipo": v.tipo,
            "estado": estado_real,
            "vigencia": v.valido_hasta.strftime("%Y-%m-%d %H:%M") if v.valido_hasta else "—",
            "creado": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "—",
        })
    return jsonify({"data": filas})


# =====================================================================
# VISITAS ACTUALMENTE DENTRO DE LA RESIDENCIAL
# =====================================================================
def _visitas_adentro():
    """
    Devuelve las visitas que entraron pero aún no han salido.
    Una visita está 'adentro' si su último evento de acceso es una 'entrada'.
    """
    # Visitas que tienen al menos un evento de entrada
    visitas_con_entrada = (
        Visita.query
        .join(EventoAcceso, EventoAcceso.visita_id == Visita.id)
        .filter(EventoAcceso.direccion == "entrada")
        .distinct()
        .all()
    )

    adentro = []
    for v in visitas_con_entrada:
        eventos = (
            EventoAcceso.query
            .filter_by(visita_id=v.id)
            .order_by(EventoAcceso.ocurrido_en.asc())
            .all()
        )
        if not eventos:
            continue
        # Si el último evento es 'entrada', sigue adentro
        if eventos[-1].direccion == "entrada":
            adentro.append((v, eventos))
    return adentro


@dashboard_bp.get("/visitas-activas")
@roles_required("admin", "super_admin")
def visitas_activas(usuario_actual):
    """
    Lista detallada de visitas actualmente DENTRO de la residencial.
    Incluye: quién generó el QR, placa, horas de creación/entrada/salida,
    guardia que autorizó, y fotos tomadas en el ingreso.
    """
    adentro = _visitas_adentro()

    filas = []
    for v, eventos in adentro:
        cuenta = Cuenta.query.get(v.cuenta_id)
        unidad = Unidad.query.get(cuenta.unidad_id) if cuenta else None

        residente_nombre = "—"
        if v.residente and v.residente.usuario:
            residente_nombre = f"{v.residente.usuario.nombre} {v.residente.usuario.apellido}"

        entrada = next((e for e in eventos if e.direccion == "entrada"), None)
        salida = next((e for e in reversed(eventos) if e.direccion == "salida"), None)

        guardia_nombre = None
        foto_identidad = None
        foto_placa = None
        if entrada:
            guardia_nombre = (
                f"{entrada.guardia.nombre} {entrada.guardia.apellido}"
                if entrada.guardia else None
            )
            foto_identidad = entrada.foto_identidad
            foto_placa = entrada.foto_placa

        filas.append({
            "id": str(v.uuid_publico),
            "visitante": v.nombre_visitante,
            "tipo": v.tipo,
            "empresa": v.empresa,
            "documento_id": v.documento_id,
            "telefono": v.telefono,
            "en_vehiculo": v.en_vehiculo,
            "placa": v.placa_vehiculo or (entrada.placa_vehiculo if entrada else None),
            "residente": residente_nombre,
            "unidad": unidad.identificador if unidad else "—",
            "guardia_autorizo": guardia_nombre,
            "hora_creacion": v.created_at.isoformat() if v.created_at else None,
            "hora_entrada": entrada.ocurrido_en.isoformat() if entrada and entrada.ocurrido_en else None,
            "hora_salida": salida.ocurrido_en.isoformat() if salida and salida.ocurrido_en else None,
            "foto_identidad": foto_identidad,
            "foto_placa": foto_placa,
        })

    # Ordenar por hora de entrada (más reciente primero)
    filas.sort(key=lambda f: f["hora_entrada"] or "", reverse=True)
    return jsonify({"data": filas})


# =====================================================================
# SERVIR FOTOS TOMADAS POR EL GUARDIA (cédula, placa)
# =====================================================================
@dashboard_bp.get("/fotos/<nombre_archivo>")
@token_required
def ver_foto(usuario_actual, nombre_archivo):
    carpeta = current_app.config.get("UPLOAD_FOLDER", "/app/uploads")
    ruta = os.path.join(carpeta, nombre_archivo)
    if not os.path.exists(ruta):
        return jsonify({"error": {"code": "no_encontrada", "message": "Foto no encontrada"}}), 404
    return send_file(ruta)
