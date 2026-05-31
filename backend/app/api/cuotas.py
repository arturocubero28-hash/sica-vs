"""
Módulo de Cuotas y Pagos — /api/v1/cuotas/

Endpoints:
  Residente:
    GET  /mias                        → sus cuotas con estado
    GET  /mias/<uuid_cuota>           → detalle con pagos
    POST /mias/<uuid_cuota>/pagar     → subir comprobante
  Admin:
    GET  /pendientes                  → pagos en revisión
    GET  /todas                       → todas las cuotas (filtrable por estado)
    POST /pagos/<uuid_pago>/revisar   → aprobar o rechazar
    GET  /comprobantes/<archivo>      → servir imagen del comprobante
"""
import os
import uuid as uuid_lib
import datetime as dt

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.cuenta import Cuota, Pago, Residente, Cuenta
from app.auth.security import token_required, roles_required

cuotas_bp = Blueprint("cuotas", __name__)

ALLOWED_EXT = {"png", "jpg", "jpeg", "pdf"}


def _ext_valida(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _carpeta_comprobantes():
    carpeta = os.path.join(current_app.config["UPLOAD_FOLDER"], "comprobantes")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


# ── RESIDENTE: ver sus cuotas ─────────────────────────────────────────────────
@cuotas_bp.get("/mias")
@token_required
def mis_cuotas(usuario_actual):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuotas = (
        Cuota.query
        .filter_by(cuenta_id=residente.cuenta_id)
        .order_by(Cuota.periodo.desc())
        .all()
    )
    return jsonify({"data": [c.to_dict() for c in cuotas]})


# ── RESIDENTE: detalle de una cuota ──────────────────────────────────────────
@cuotas_bp.get("/mias/<uuid_cuota>")
@token_required
def detalle_cuota(usuario_actual, uuid_cuota):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuota = Cuota.query.filter_by(uuid_publico=uuid_cuota).first()
    if not cuota or cuota.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "NO_ENCONTRADA", "message": "Cuota no encontrada"}}), 404

    return jsonify({"data": cuota.to_dict(con_pagos=True)})


# ── RESIDENTE: subir comprobante ──────────────────────────────────────────────
@cuotas_bp.post("/mias/<uuid_cuota>/pagar")
@token_required
def subir_comprobante(usuario_actual, uuid_cuota):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuota = Cuota.query.filter_by(uuid_publico=uuid_cuota).first()
    if not cuota or cuota.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "NO_ENCONTRADA", "message": "Cuota no encontrada"}}), 404

    if cuota.estado == "pagada":
        return jsonify({"error": {"code": "YA_PAGADA", "message": "Esta cuota ya está pagada"}}), 400

    # Validar archivo
    if "comprobante" not in request.files:
        return jsonify({"error": {"code": "SIN_ARCHIVO", "message": "Adjuntá el comprobante"}}), 400

    archivo = request.files["comprobante"]
    if not archivo.filename or not _ext_valida(archivo.filename):
        return jsonify({"error": {"code": "FORMATO_INVALIDO", "message": "Solo PNG, JPG o PDF"}}), 400

    # Validar monto
    monto_str = request.form.get("monto", "")
    try:
        monto = float(monto_str)
        if monto <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": {"code": "MONTO_INVALIDO", "message": "Indicá un monto válido"}}), 400

    referencia = request.form.get("referencia", "")

    # Guardar archivo con nombre único
    ext = archivo.filename.rsplit(".", 1)[1].lower()
    nombre_archivo = f"{uuid_lib.uuid4()}.{ext}"
    archivo.save(os.path.join(_carpeta_comprobantes(), nombre_archivo))

    pago = Pago(
        cuota_id=cuota.id,
        cuenta_id=residente.cuenta_id,
        subido_por=usuario_actual.id,
        monto=monto,
        referencia=referencia,
        comprobante_archivo=nombre_archivo,
        estado="en_revision",
    )
    db.session.add(pago)
    cuota.estado = "en_revision"
    db.session.commit()

    return jsonify({"data": pago.to_dict()}), 201


# ── ADMIN: servir imagen del comprobante ──────────────────────────────────────
@cuotas_bp.get("/comprobantes/<nombre_archivo>")
@token_required
def ver_comprobante(usuario_actual, nombre_archivo):
    return send_from_directory(_carpeta_comprobantes(), nombre_archivo)


# ── ADMIN: pagos en revisión ──────────────────────────────────────────────────
@cuotas_bp.get("/pendientes")
@token_required
@roles_required("admin")
def pagos_pendientes(usuario_actual):
    pagos = (
        Pago.query
        .filter_by(estado="en_revision")
        .order_by(Pago.created_at.asc())
        .all()
    )
    resultado = []
    for p in pagos:
        d = p.to_dict()
        d["unidad"] = p.cuenta.unidad.identificador if p.cuenta and p.cuenta.unidad else None
        d["periodo"] = p.cuota.periodo.isoformat() if p.cuota else None
        d["mes_label"] = p.cuota.periodo.strftime("%B %Y") if p.cuota else None
        resultado.append(d)
    return jsonify({"data": resultado})


# ── ADMIN: todas las cuotas ───────────────────────────────────────────────────
@cuotas_bp.get("/todas")
@token_required
@roles_required("admin")
def todas_las_cuotas(usuario_actual):
    estado = request.args.get("estado")  # filtro opcional
    q = Cuota.query
    if estado:
        q = q.filter_by(estado=estado)
    cuotas = q.order_by(Cuota.periodo.desc()).all()

    resultado = []
    for c in cuotas:
        d = c.to_dict()
        d["unidad"] = c.cuenta.unidad.identificador if c.cuenta and c.cuenta.unidad else None
        resultado.append(d)
    return jsonify({"data": resultado})


# ── ADMIN: aprobar o rechazar pago ────────────────────────────────────────────
@cuotas_bp.post("/pagos/<uuid_pago>/revisar")
@token_required
@roles_required("admin")
def revisar_pago(usuario_actual, uuid_pago):
    pago = Pago.query.filter_by(uuid_publico=uuid_pago).first()
    if not pago:
        return jsonify({"error": {"code": "NO_ENCONTRADO", "message": "Pago no encontrado"}}), 404

    body = request.get_json() or {}
    accion = body.get("accion")  # "aprobar" | "rechazar"

    if accion not in ("aprobar", "rechazar"):
        return jsonify({
            "error": {"code": "ACCION_INVALIDA", "message": "accion debe ser 'aprobar' o 'rechazar'"}
        }), 400

    pago.estado = "aprobado" if accion == "aprobar" else "rechazado"
    pago.nota_admin = body.get("nota", "")
    pago.revisado_por = usuario_actual.id
    pago.revisado_en = dt.datetime.utcnow()

    if accion == "aprobar":
        pago.cuota.estado = "pagada"
        # Desbloqueo automático de la cuenta
        cuenta = pago.cuenta
        cuenta.estado = "al_dia"
        cuenta.bloqueada = False

    db.session.commit()
    return jsonify({"data": pago.to_dict()})
