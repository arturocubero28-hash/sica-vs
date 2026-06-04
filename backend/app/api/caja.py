"""
Módulo de Caja — /api/v1/caja/

Cajero: abrir sesión, registrar pagos en ventanilla, arqueo, cerrar.
Admin: supervisión (ver todas las sesiones, totales).
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.caja import SesionCaja
from app.models.cuenta import Cuenta, Cuota, Pago
from app.auth.security import roles_required

caja_bp = Blueprint("caja", __name__)

METODOS_VENTANILLA = ("efectivo", "tarjeta_pos")


def _sesion_abierta_de(usuario):
    return SesionCaja.query.filter_by(cajero_id=usuario.id, estado="abierta").first()


# ── Estado de la caja del cajero actual ───────────────────────────────────────
@caja_bp.get("/estado")
@roles_required("cajero", "admin", "super_admin")
def estado_caja(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"data": {"abierta": False}})
    return jsonify({"data": {"abierta": True, "sesion": sesion.to_dict(con_pagos=True)}})


# ── Abrir caja ────────────────────────────────────────────────────────────────
@caja_bp.post("/abrir")
@roles_required("cajero", "admin", "super_admin")
def abrir_caja(usuario_actual):
    if _sesion_abierta_de(usuario_actual):
        return jsonify({"error": {"code": "ya_abierta",
                                  "message": "Ya tenés una caja abierta. Cerrala antes de abrir otra."}}), 400
    data = request.get_json(silent=True) or {}
    try:
        monto_inicial = float(data.get("monto_inicial", 0))
        if monto_inicial < 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": {"code": "monto_invalido", "message": "Monto inicial inválido"}}), 400

    sesion = SesionCaja(cajero_id=usuario_actual.id, monto_inicial=monto_inicial, estado="abierta")
    db.session.add(sesion)
    db.session.commit()
    return jsonify({"data": sesion.to_dict()}), 201


# ── Registrar pago en ventanilla ──────────────────────────────────────────────
@caja_bp.post("/pago")
@roles_required("cajero", "admin", "super_admin")
def registrar_pago(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja",
                                  "message": "Abrí la caja antes de registrar pagos"}}), 400

    data = request.get_json(silent=True) or {}
    cuota_uuid = data.get("cuota_id")
    metodo = data.get("metodo")
    referencia = (data.get("referencia") or "")[:120]

    if metodo not in METODOS_VENTANILLA:
        return jsonify({"error": {"code": "metodo_invalido",
                                  "message": "Método debe ser efectivo o tarjeta_pos"}}), 400

    cuota = Cuota.query.filter_by(uuid_publico=cuota_uuid).first()
    if not cuota:
        return jsonify({"error": {"code": "cuota_no_encontrada", "message": "Cuota no encontrada"}}), 404
    if cuota.estado == "pagada":
        return jsonify({"error": {"code": "ya_pagada", "message": "Esa cuota ya está pagada"}}), 400

    pago = Pago(
        cuota_id=cuota.id,
        cuenta_id=cuota.cuenta_id,
        subido_por=usuario_actual.id,
        metodo=metodo,
        monto=cuota.monto,
        referencia=referencia,
        estado="aprobado",                 # pago en ventanilla se aprueba al instante
        revisado_por=usuario_actual.id,
        revisado_en=dt.datetime.now(dt.timezone.utc),
        sesion_caja_id=sesion.id,
    )
    db.session.add(pago)

    # Marcar cuota pagada y desbloquear la cuenta
    cuota.estado = "pagada"
    cuenta = cuota.cuenta
    if cuenta:
        cuenta.estado = "al_dia"
        cuenta.bloqueada = False

    db.session.commit()
    return jsonify({"data": {"pago": pago.to_dict(), "sesion": sesion.to_dict()}}), 201


# ── Cerrar caja (arqueo) ──────────────────────────────────────────────────────
@caja_bp.post("/cerrar")
@roles_required("cajero", "admin", "super_admin")
def cerrar_caja(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja", "message": "No tenés una caja abierta"}}), 400

    data = request.get_json(silent=True) or {}
    try:
        efectivo_contado = float(data.get("efectivo_contado", 0))
        pos_contado = float(data.get("pos_contado", 0))
    except ValueError:
        return jsonify({"error": {"code": "monto_invalido", "message": "Montos contados inválidos"}}), 400

    sesion.efectivo_contado = efectivo_contado
    sesion.pos_contado = pos_contado
    sesion.nota_cierre = (data.get("nota") or "")[:255]
    sesion.estado = "cerrada"
    sesion.cerrada_en = dt.datetime.now(dt.timezone.utc)
    db.session.commit()
    return jsonify({"data": sesion.to_dict(con_pagos=True)})


# ── Cuotas pendientes de una cuenta (para buscar en ventanilla) ───────────────
@caja_bp.get("/buscar-cuenta")
@roles_required("cajero", "admin", "super_admin")
def buscar_cuenta(usuario_actual):
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"data": []})

    cuentas = Cuenta.query.filter_by(activa=True).all()
    resultados = []
    for c in cuentas:
        identificador = c.unidad.identificador if c.unidad else ""
        titular = c.titular()
        nombre_titular = f"{titular.usuario.nombre} {titular.usuario.apellido}" if titular and titular.usuario else ""
        blob = f"{identificador} {nombre_titular}".lower()
        if q not in blob:
            continue
        # Cuotas pendientes de esta cuenta
        pendientes = (Cuota.query
                      .filter(Cuota.cuenta_id == c.id, Cuota.estado != "pagada")
                      .order_by(Cuota.periodo.asc()).all())
        resultados.append({
            "cuenta_id": str(c.uuid_publico),
            "identificador": identificador or "Casa",
            "titular": nombre_titular or "— sin titular —",
            "cuotas_pendientes": [{
                "cuota_id": str(q2.uuid_publico),
                "mes_label": q2.periodo.strftime("%B %Y"),
                "monto": float(q2.monto),
                "estado": q2.estado,
            } for q2 in pendientes],
        })
        if len(resultados) >= 10:
            break
    return jsonify({"data": resultados})


# =====================================================================
# SUPERVISIÓN (admin)
# =====================================================================
@caja_bp.get("/sesiones")
@roles_required("admin", "super_admin")
def listar_sesiones(usuario_actual):
    sesiones = SesionCaja.query.order_by(SesionCaja.abierta_en.desc()).limit(100).all()
    return jsonify({"data": [s.to_dict() for s in sesiones]})


@caja_bp.get("/sesiones/<uuid_sesion>")
@roles_required("admin", "super_admin")
def detalle_sesion(usuario_actual, uuid_sesion):
    s = SesionCaja.query.filter_by(uuid_publico=uuid_sesion).first()
    if not s:
        return jsonify({"error": {"code": "no_encontrada", "message": "Sesión no encontrada"}}), 404
    return jsonify({"data": s.to_dict(con_pagos=True)})
