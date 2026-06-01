"""
Módulo de Comunicados — /api/v1/comunicados/

Admin crea/borra anuncios. Residentes los leen en su Home.
"""
import os
import uuid as uuid_lib

from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.comunicado import Comunicado
from app.auth.security import token_required, roles_required

comunicados_bp = Blueprint("comunicados", __name__)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


def _ext_valida(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _carpeta():
    carpeta = os.path.join(current_app.config.get("UPLOAD_FOLDER", "/app/uploads"), "comunicados")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


# ── TODOS los autenticados: listar comunicados ────────────────────────────────
@comunicados_bp.get("")
@token_required
def listar(usuario_actual):
    comunicados = Comunicado.query.order_by(Comunicado.created_at.desc()).all()
    return jsonify({"data": [c.to_dict() for c in comunicados]})


# ── ADMIN: crear comunicado ───────────────────────────────────────────────────
@comunicados_bp.post("")
@roles_required("admin", "super_admin")
def crear(usuario_actual):
    titulo = (request.form.get("titulo") or "").strip()
    cuerpo = (request.form.get("cuerpo") or "").strip()

    if not titulo or not cuerpo:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Título y contenido son obligatorios"}}), 400

    nombre_imagen = None
    if "imagen" in request.files:
        archivo = request.files["imagen"]
        if archivo and archivo.filename:
            if not _ext_valida(archivo.filename):
                return jsonify({"error": {"code": "formato_invalido",
                                          "message": "Solo imágenes PNG, JPG, WEBP o GIF"}}), 400
            ext = archivo.filename.rsplit(".", 1)[1].lower()
            nombre_imagen = f"{uuid_lib.uuid4()}.{ext}"
            archivo.save(os.path.join(_carpeta(), nombre_imagen))

    com = Comunicado(
        titulo=titulo, cuerpo=cuerpo, imagen=nombre_imagen,
        creado_por=usuario_actual.id,
    )
    db.session.add(com)
    db.session.commit()
    return jsonify({"data": com.to_dict()}), 201


# ── ADMIN: borrar comunicado ──────────────────────────────────────────────────
@comunicados_bp.delete("/<uuid_com>")
@roles_required("admin", "super_admin")
def borrar(usuario_actual, uuid_com):
    com = Comunicado.query.filter_by(uuid_publico=uuid_com).first()
    if not com:
        return jsonify({"error": {"code": "no_encontrado", "message": "Comunicado no encontrado"}}), 404

    # Borrar imagen del disco si existe
    if com.imagen:
        try:
            os.remove(os.path.join(_carpeta(), com.imagen))
        except OSError:
            pass

    db.session.delete(com)
    db.session.commit()
    return jsonify({"data": {"eliminado": True}})


# ── Servir imagen del comunicado ──────────────────────────────────────────────
@comunicados_bp.get("/imagenes/<nombre_archivo>")
@token_required
def ver_imagen(usuario_actual, nombre_archivo):
    ruta = os.path.join(_carpeta(), secure_filename(nombre_archivo))
    if not os.path.exists(ruta):
        return jsonify({"error": {"code": "no_encontrada", "message": "Imagen no encontrada"}}), 404
    return send_file(ruta)
