"""
Módulo de Suscripción — /api/v1/suscripcion/

Lo que el ADMIN de una residencial ve y hace respecto a lo que le paga
al desarrollador por el servicio. Distinto de /cuotas (lo que los
RESIDENTES le pagan a SU administrador) — dos negocios separados, con
el mismo patrón de "subir comprobante -> revisar -> aprobar/rechazar"
a propósito, para que se sienta familiar.

Endpoints (todos exclusivos de admin/super_admin — un residente, guardia
o cajero no tiene por qué ver ni tocar nada de esto):
  GET  /mi-estado    → toda la info de la suscripción (plan, fechas, uso)
  GET  /mis-pagos     → historial de pagos de suscripción
  POST /pagar         → sube un comprobante (o pide upgrade de plan)
"""
import os
import datetime as dt

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.residencial import Residencial
from app.models.plan import Plan
from app.models.suscripcion_pago import SuscripcionPago
from app.auth.security import roles_required
from app.utils.archivos import guardar_imagen_segura, EXT_DOCUMENTO
from app.services.cuota_almacenamiento import registrar_archivo_existente


def _carpeta_pagos_suscripcion():
    """Mismo patrón que _carpeta_comprobantes() en cuotas.py — carpeta_destino
    tiene que ser una ruta local completa, no un fragmento de subcarpeta
    (guardar_imagen_segura la usa tal cual en los dos modos, local y nube)."""
    carpeta = os.path.join(current_app.config["UPLOAD_FOLDER"], "suscripcion")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


suscripcion_bp = Blueprint("suscripcion", __name__)


def _mi_residencial(usuario_actual):
    if not usuario_actual.residencial_id:
        return None
    return Residencial.query.get(usuario_actual.residencial_id)


@suscripcion_bp.get("/planes-disponibles")
@roles_required("admin", "super_admin")
def planes_disponibles(usuario_actual):
    """
    Día 50, Etapa 7 — para que el admin pueda elegir a qué plan pedir
    upgrade al pagar. Distinto de GET /dev/planes (exclusivo
    desarrollador, que además trae cuántas residenciales tiene cada
    plan) — acá solo se listan los planes ACTIVOS con lo que el admin
    necesita para decidir: nombre, límites, precio.
    """
    planes = Plan.query.filter_by(activo=True).order_by(Plan.orden.asc(), Plan.id.asc()).all()
    return jsonify({"data": [p.to_dict() for p in planes]})


@suscripcion_bp.post("/subir-plan")
@roles_required("admin", "super_admin")
def subir_plan(usuario_actual):
    """
    Día 50 (corrección del usuario) — upgrade INMEDIATO, sin comprobante.

    Decisión de negocio confirmada con el usuario: cuando el admin pide
    subir de plan, el cambio se aplica ya mismo (empieza a disfrutar los
    beneficios de inmediato) — pero el PAGO del precio nuevo recién se
    cobra en su próxima fecha de pago normal, sin tocarla ni adelantarla.
    El desarrollador "pierde" ese período sin cobrar el precio más alto,
    pero gana con la tarifa nueva de ahí en adelante.

    Por eso este endpoint NO pide comprobante — es solo cambiar el plan,
    no un pago. Solo permite subir a un plan MÁS CARO (un downgrade es
    una conversación distinta, que pasa por el desarrollador directo).

    A pedido del usuario: pide la contraseña del admin para confirmar
    (es un compromiso de pago real, aunque diferido — merece la misma
    verificación que cualquier acción sensible de la cuenta).
    """
    residencial = _mi_residencial(usuario_actual)
    if not residencial:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400
    if not residencial.plan_id:
        return jsonify({"error": {"code": "sin_plan",
                                  "message": "Tu residencial todavía no tiene un plan asignado — "
                                             "contactá a tu proveedor"}}), 400

    body = request.get_json(silent=True) or {}

    password = body.get("password") or ""
    if not password or not usuario_actual.check_password(password):
        return jsonify({"error": {"code": "password_incorrecta",
                                  "message": "Contraseña incorrecta"}}), 401

    plan_id_pedido = (body.get("plan_id") or "").strip()
    if not plan_id_pedido:
        return jsonify({"error": {"code": "plan_requerido", "message": "Elegí un plan"}}), 400
    plan_nuevo = Plan.query.filter_by(uuid_publico=plan_id_pedido).first()
    if not plan_nuevo:
        return jsonify({"error": {"code": "plan_no_encontrado", "message": "No se encontró ese plan"}}), 404
    if plan_nuevo.precio_mensual <= residencial.plan.precio_mensual:
        return jsonify({"error": {"code": "no_es_upgrade",
                                  "message": "Ese plan no es más caro que el actual — "
                                             "para bajar de plan, contactá a tu proveedor"}}), 400

    # Día 55 — capturar el BOOL (no el objeto Plan) ANTES de cambiar el
    # plan, para que no lo afecte la recarga de la relación tras el flush.
    anterior_tenia_cuotas = bool(residencial.plan and residencial.plan.permite_cuotas)
    residencial.plan_id = plan_nuevo.id
    # fecha_proximo_pago NO se toca a propósito — el precio nuevo se cobra
    # recién en el ciclo que ya tenía, no antes.
    # Día 55 — Sprint 2a: si este upgrade activa cuotas por primera vez,
    # marcar para que el admin vea el wizard de configuración.
    from app.utils.residencial import marcar_config_cuotas_si_corresponde
    db.session.flush()
    marcar_config_cuotas_si_corresponde(residencial, anterior_tenia_cuotas)
    db.session.commit()
    return jsonify({"data": residencial.to_dict(incluir_stats=True)})


@suscripcion_bp.get("/comprobantes/<nombre_archivo>")
@roles_required("desarrollador")
def ver_comprobante_suscripcion(usuario_actual, nombre_archivo):
    """
    Día 50, Etapa 8 — el desarrollador ve el comprobante antes de
    aprobar/rechazar. Exclusivo desarrollador (es él quien revisa estos
    pagos, no hay staff de residencial de por medio acá).

    Mismo criterio de seguridad que ver_comprobante en cuotas.py: solo
    se sirve si el nombre corresponde a un SuscripcionPago realmente
    registrado — nunca un archivo arbitrario de la carpeta aunque
    alguien adivine o construya un nombre.
    """
    from app.utils.archivos import servir_archivo_seguro
    pago = SuscripcionPago.query.filter_by(comprobante_archivo=nombre_archivo).first()
    if not pago:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Comprobante no encontrado"}}), 404
    return servir_archivo_seguro(_carpeta_pagos_suscripcion(), nombre_archivo)


@suscripcion_bp.get("/mi-estado")
@roles_required("admin", "super_admin")
def mi_estado(usuario_actual):
    """
    Toda la información de la suscripción del admin: plan, fecha de alta,
    próximo pago, fecha de suspensión (calculada: próximo pago + días de
    gracia), uso de casas/usuarios/almacenamiento contra su plan.

    Si la residencial no tiene plan asignado, se devuelve igual pero con
    "plan": null — el frontend decide no mostrar nada en ese caso (a
    pedido del usuario: "esto se les va a mostrar si tienen afiliación a
    un plan, si no tienen pues no se les muestra nada").
    """
    residencial = _mi_residencial(usuario_actual)
    if not residencial:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400

    datos = residencial.to_dict(incluir_stats=True)
    # Día 50: fecha de suspensión — calculada, nunca guardada (mismo
    # criterio que esta_suspendida()), para que el admin sepa exactamente
    # cuándo se corta el servicio si no paga a tiempo.
    fecha_suspension = None
    if residencial.fecha_proximo_pago:
        fecha_suspension = (residencial.fecha_proximo_pago +
                            dt.timedelta(days=residencial.dias_gracia or 0)).isoformat()
    datos["fecha_suspension"] = fecha_suspension
    datos["fecha_alta"] = residencial.created_at.isoformat() if residencial.created_at else None
    return jsonify({"data": datos})


@suscripcion_bp.get("/mis-pagos")
@roles_required("admin", "super_admin")
def mis_pagos(usuario_actual):
    residencial = _mi_residencial(usuario_actual)
    if not residencial:
        return jsonify({"data": []})
    pagos = (SuscripcionPago.query.filter_by(residencial_id=residencial.id)
            .order_by(SuscripcionPago.created_at.desc()).all())
    return jsonify({"data": [p.to_dict() for p in pagos]})


@suscripcion_bp.post("/pagar")
@roles_required("admin", "super_admin")
def pagar(usuario_actual):
    """
    El admin sube el comprobante de su pago mensual — o, si adjunta un
    plan_id distinto al que ya tiene, está pidiendo upgrade al mismo
    tiempo (es_upgrade=True, para que el desarrollador lo vea de entrada
    al revisar, sin tener que ir a comparar planes él mismo).

    A diferencia de un pago de cuota (que el admin de la residencial
    aprueba), este lo aprueba el DESARROLLADOR — es él quien recibe el
    dinero. Queda en 'en_revision' hasta que lo revise.
    """
    residencial = _mi_residencial(usuario_actual)
    if not residencial:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400
    if not residencial.plan_id:
        return jsonify({"error": {"code": "sin_plan",
                                  "message": "Tu residencial todavía no tiene un plan asignado — "
                                             "contactá a tu proveedor"}}), 400

    plan_pedido_id = request.form.get("plan_id", "").strip()
    if plan_pedido_id:
        plan = Plan.query.filter_by(uuid_publico=plan_pedido_id).first()
        if not plan:
            return jsonify({"error": {"code": "plan_no_encontrado",
                                      "message": "No se encontró ese plan"}}), 404
    else:
        plan = residencial.plan

    if "comprobante" not in request.files:
        return jsonify({"error": {"code": "comprobante_requerido",
                                  "message": "Adjuntá el comprobante del pago"}}), 400
    archivo = request.files["comprobante"]
    # tam ya NO se calcula acá a mano: guardar_imagen_segura() comprime la
    # imagen del lado del servidor y devuelve el tamaño REAL después de
    # comprimir — contar el tamaño de antes de comprimir hubiera inflado
    # la cuota de almacenamiento sin necesidad.
    nombre_archivo, error, tam = guardar_imagen_segura(
        archivo, _carpeta_pagos_suscripcion(), EXT_DOCUMENTO)
    if error:
        return jsonify({"error": {"code": "FORMATO_INVALIDO", "message": error}}), 400
    # Si esto falla, NO debe tumbar el pago (el comprobante ya se guardó
    # bien en disco/Spaces) — pero antes fallaba en silencio, sin dejar
    # rastro. Ahora, si algo sale mal acá, va a quedar registrado en los
    # logs del backend para poder diagnosticarlo.
    try:
        registrar_archivo_existente(residencial.id, nombre_archivo, tam, tipo="comprobante")
    except Exception as e:
        current_app.logger.error(
            "No se pudo registrar la cuota de almacenamiento para %s (residencial_id=%s): %s",
            nombre_archivo, residencial.id, e)

    pago = SuscripcionPago(
        residencial_id=residencial.id,
        plan_id=plan.id,
        monto=plan.precio_mensual,
        es_upgrade=(plan.id != residencial.plan_id),
        metodo="comprobante",
        comprobante_archivo=nombre_archivo,
        estado="en_revision",
        subido_por=usuario_actual.id,
    )
    db.session.add(pago)
    db.session.commit()
    return jsonify({"data": pago.to_dict()}), 201
