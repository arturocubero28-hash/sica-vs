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
    # Multi-residencial (Día 46): un residente/guardia/admin solo ve los
    # comunicados de SU residencial. A diferencia del resto de los scopes
    # (pensados solo para el panel admin), acá se filtra para TODOS los roles
    # que consumen este contenido, no solo admin.
    from app.utils.residencial import residencial_id_de_usuario, scope_directo
    rid = residencial_id_de_usuario(usuario_actual)
    q = Comunicado.query
    if rid is not None:
        q = q.filter(Comunicado.residencial_id == rid)
    comunicados = q.order_by(Comunicado.created_at.desc()).all()
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
        nombre_imagen, error, _tam = guardar_imagen_segura(
            request.files["imagen"], _carpeta(), EXT_IMAGEN
        )
        if error:
            return jsonify({"error": {"code": "imagen_invalida", "message": error}}), 400

    from app.utils.residencial import residencial_id_heredado
    com = Comunicado(
        titulo=titulo, cuerpo=cuerpo, imagen=nombre_imagen,
        creado_por=usuario_actual.id,
        residencial_id=residencial_id_heredado(usuario_actual),
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
@comunicados_bp.get("/imagenes/<path:nombre_archivo>")
@token_required
def ver_imagen(usuario_actual, nombre_archivo):
    # Día 62 — mismo bug de doble prefijo encontrado en comprobantes de
    # cuotas (ver cuotas.py, ver_comprobante): servir_archivo_seguro, en
    # modo nube, le vuelve a sumar la subcarpeta "comunicados/" a un
    # nombre_archivo que YA la trae (así quedó guardado en la base desde
    # que se subió la imagen) -- duplicaba el prefijo y rompía la
    # búsqueda en Spaces con NoSuchKey. Mismo fix: llamar directo a
    # storage.py con la clave ya normalizada.
    from app.services import storage
    clave = nombre_archivo if nombre_archivo.startswith("comunicados/") else f"comunicados/{nombre_archivo}"
    return storage.servir_archivo(clave)
