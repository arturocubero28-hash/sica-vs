"""
Módulo de Comunicados — /api/v1/comunicados/

Admin crea/borra anuncios. Residentes los leen en su Home.
"""
import os

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.comunicado import Comunicado
from app.auth.security import token_required, roles_required
from app.utils.archivos import guardar_imagen_segura, servir_archivo_seguro, EXT_IMAGEN

comunicados_bp = Blueprint("comunicados", __name__)


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
    if len(titulo) > 160:
        return jsonify({"error": {"code": "titulo_largo",
                                  "message": "El título es demasiado largo"}}), 400

    nombre_imagen = None
    if "imagen" in request.files and request.files["imagen"].filename:
        nombre_imagen, error = guardar_imagen_segura(
            request.files["imagen"], _carpeta(), EXT_IMAGEN
        )
        if error:
            return jsonify({"error": {"code": "imagen_invalida", "message": error}}), 400

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
    return servir_archivo_seguro(_carpeta(), nombre_archivo)
