"""
Módulo 2 — Endpoints de Unidades, Cuentas, Residentes y Tarjetas (Integrante 2).

Rutas (todas requieren rol admin/super_admin salvo lectura):
    GET  /api/v1/unidades
    POST /api/v1/unidades
    GET  /api/v1/cuentas
    POST /api/v1/cuentas                      -> crea cuenta + titular (con activación)
    GET  /api/v1/cuentas/<uuid>
    POST /api/v1/cuentas/<uuid>/residentes    -> agrega miembro (con activación)
    POST /api/v1/cuentas/<uuid>/tarjetas      -> asigna tarjeta
    GET  /api/v1/tarifas

Sobre la creación de usuarios de residentes:
    Al crear la cuenta, se crea el USUARIO del titular en estado "pendiente":
    sin contraseña utilizable. Se genera un token de activación que (más adelante,
    con Resend) se envía por correo para que el residente defina su contraseña.
    Por ahora el token se devuelve en la respuesta para pruebas.
"""
import uuid
import secrets
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Unidad, Cuenta, Residente, Tarjeta, Tarifa
from app.auth.security import roles_required, token_required

cuentas_bp = Blueprint("cuentas", __name__)


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _crear_usuario_pendiente(nombre, apellido, email, telefono=None, extra=None):
    """Crea un Usuario residente en estado pendiente de activación.
    Devuelve (usuario, token_activacion) o (None, mensaje_error)."""
    email = (email or "").strip().lower()
    if not email or not nombre:
        return None, "Nombre y email son obligatorios"
    if Usuario.query.filter_by(email=email).first():
        return None, f"Ya existe un usuario con el email {email}"

    extra = extra or {}
    u = Usuario(
        nombre=nombre.strip(),
        apellido=(apellido or "").strip(),
        email=email,
        telefono=telefono,
        dni=(extra.get("dni") or None),
        rtn=(extra.get("rtn") or None),
        direccion_exacta=(extra.get("direccion_exacta") or None),
        profesion=(extra.get("profesion") or None),
        contacto_emergencia_nombre=(extra.get("contacto_emergencia_nombre") or None),
        contacto_emergencia_telefono=(extra.get("contacto_emergencia_telefono") or None),
        rol="residente",
        activo=False,            # pendiente hasta que defina contraseña
    )
    # contraseña temporal aleatoria e inutilizable (se reemplaza en la activación)
    u.set_password(secrets.token_urlsafe(32))
    # Token JWT de activación (48h de vida)
    token_activacion = jwt.encode(
        {"sub": email, "proposito": "activacion",
         "exp": dt.datetime.utcnow() + dt.timedelta(hours=48)},
        current_app.config["JWT_SECRET"], algorithm="HS256"
    )
    db.session.add(u)
    db.session.flush()           # obtener u.id sin cerrar la transacción
    return u, token_activacion


# =====================================================================
# UNIDADES
# =====================================================================
@cuentas_bp.get("")
@token_required
def listar_unidades(usuario_actual):
    unidades = Unidad.query.filter_by(activa=True).order_by(Unidad.identificador).all()
    return jsonify({"data": [u.to_dict() for u in unidades]})


@cuentas_bp.post("")
@roles_required("admin", "super_admin")
def crear_unidad(usuario_actual):
    data = request.get_json(silent=True) or {}
    tipo = data.get("tipo")
    identificador = (data.get("identificador") or "").strip()

    if tipo not in ("casa", "edificio"):
        return _err("tipo_invalido", "El tipo debe ser 'casa' o 'edificio'", 400)
    if not identificador:
        return _err("datos_incompletos", "El identificador es obligatorio", 400)
    if Unidad.query.filter_by(identificador=identificador).first():
        return _err("duplicado", f"Ya existe la unidad '{identificador}'", 409)

    u = Unidad(tipo=tipo, identificador=identificador,
               direccion_ref=data.get("direccion_ref"))
    db.session.add(u)
    db.session.commit()
    return jsonify({"data": u.to_dict()}), 201


# =====================================================================
# CUENTAS
# =====================================================================
@cuentas_bp.get("/cuentas")
@token_required
def listar_cuentas(usuario_actual):
    cuentas = Cuenta.query.order_by(Cuenta.id.desc()).all()
    return jsonify({"data": [c.to_dict() for c in cuentas]})


@cuentas_bp.post("/cuentas")
@roles_required("admin", "super_admin")
def crear_cuenta(usuario_actual):
    """Crea una cuenta (casa o apartamento) junto con su titular.
    Body esperado:
      {
        "unidad_id": "<uuid de la unidad>",
        "apartamento": "1A" (opcional, solo si la unidad es edificio),
        "tarifa_id": 1,
        "dia_pago": 5,
        "titular": { "nombre": "...", "apellido": "...", "email": "...", "telefono": "...",
                     "relacion": "propietario" }
      }
    """
    data = request.get_json(silent=True) or {}

    unidad = Unidad.query.filter_by(uuid_publico=data.get("unidad_id")).first()
    if not unidad:
        return _err("unidad_no_encontrada", "La unidad indicada no existe", 404)

    tarifa = Tarifa.query.get(data.get("tarifa_id"))
    if not tarifa:
        return _err("tarifa_invalida", "La tarifa indicada no existe", 400)

    dia_pago = data.get("dia_pago")
    if not isinstance(dia_pago, int) or not (1 <= dia_pago <= 28):
        return _err("dia_pago_invalido", "El día de pago debe estar entre 1 y 28", 400)

    apartamento = data.get("apartamento")
    if unidad.tipo == "edificio" and not apartamento:
        return _err("apartamento_requerido",
                    "Para un edificio debes indicar el apartamento (ej. 1A)", 400)
    if unidad.tipo == "casa":
        apartamento = None  # una casa no lleva número de apartamento

    # evitar duplicado de apartamento en el mismo edificio
    if apartamento and Cuenta.query.filter_by(
            unidad_id=unidad.id, apartamento=apartamento).first():
        return _err("duplicado", f"El apartamento {apartamento} ya existe en esta unidad", 409)

    titular_data = data.get("titular") or {}
    usuario, token_o_error = _crear_usuario_pendiente(
        titular_data.get("nombre"), titular_data.get("apellido"),
        titular_data.get("email"), titular_data.get("telefono"),
        extra=titular_data,
    )
    if usuario is None:
        return _err("titular_invalido", token_o_error, 400)

    # crear la cuenta
    cuenta = Cuenta(
        unidad_id=unidad.id, apartamento=apartamento,
        tarifa_id=tarifa.id, dia_pago=dia_pago,
    )
    db.session.add(cuenta)
    db.session.flush()

    # vincular al titular
    residente = Residente(
        usuario_id=usuario.id, cuenta_id=cuenta.id,
        rol_cuenta="titular", relacion=titular_data.get("relacion", "propietario"),
    )
    db.session.add(residente)
    db.session.commit()

    return jsonify({"data": {
        "cuenta": cuenta.to_dict(detalle=True),
        "activacion": {
            "usuario_email": usuario.email,
            "token_activacion": token_o_error,   # en producción esto va por correo
            "nota": "Enviar al residente para que defina su contraseña",
        },
    }}), 201


@cuentas_bp.get("/cuentas/<cuenta_uuid>")
@token_required
def detalle_cuenta(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    return jsonify({"data": cuenta.to_dict(detalle=True)})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/baja")
@roles_required("admin", "super_admin")
def dar_baja_cuenta(usuario_actual, cuenta_uuid):
    """Da de baja una cuenta: deja de generar cuotas y se desactivan sus accesos."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    cuenta.activa = False
    cuenta.estado = "baja"
    # Desactivar el acceso de todos los residentes de la cuenta
    for r in cuenta.residentes:
        if r.usuario:
            r.usuario.activo = False
    db.session.commit()
    return jsonify({"data": cuenta.to_dict()})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/reactivar")
@roles_required("admin", "super_admin")
def reactivar_cuenta(usuario_actual, cuenta_uuid):
    """Reactiva una cuenta dada de baja."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    cuenta.activa = True
    cuenta.estado = "al_dia"
    for r in cuenta.residentes:
        if r.usuario:
            r.usuario.activo = True
    db.session.commit()
    return jsonify({"data": cuenta.to_dict()})


# =====================================================================
# RESIDENTES (miembros adicionales)
# =====================================================================
@cuentas_bp.post("/cuentas/<cuenta_uuid>/residentes")
@roles_required("admin", "super_admin")
def agregar_miembro(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    data = request.get_json(silent=True) or {}
    usuario, token_o_error = _crear_usuario_pendiente(
        data.get("nombre"), data.get("apellido"),
        data.get("email"), data.get("telefono"),
        extra=data,
    )
    if usuario is None:
        return _err("miembro_invalido", token_o_error, 400)

    residente = Residente(
        usuario_id=usuario.id, cuenta_id=cuenta.id,
        rol_cuenta="miembro", relacion=data.get("relacion", "familiar"),
    )
    db.session.add(residente)
    db.session.commit()

    return jsonify({"data": {
        "residente": residente.to_dict(),
        "activacion": {"usuario_email": usuario.email, "token_activacion": token_o_error},
    }}), 201


# =====================================================================
# TARJETAS
# =====================================================================
@cuentas_bp.post("/cuentas/<cuenta_uuid>/tarjetas")
@roles_required("admin", "super_admin")
def asignar_tarjeta(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    data = request.get_json(silent=True) or {}
    card_uid = (data.get("card_uid") or "").strip()
    if not card_uid:
        return _err("datos_incompletos", "El card_uid (código de la tarjeta) es obligatorio", 400)
    if Tarjeta.query.filter_by(card_uid=card_uid).first():
        return _err("duplicado", "Esa tarjeta ya está registrada", 409)

    # residente al que se asigna (opcional)
    residente = None
    if data.get("residente_id"):
        residente = Residente.query.filter_by(
            uuid_publico=data["residente_id"], cuenta_id=cuenta.id).first()
        if not residente:
            return _err("residente_invalido", "El residente no pertenece a esta cuenta", 400)

    tarjeta = Tarjeta(
        card_uid=card_uid, cuenta_id=cuenta.id,
        residente_id=residente.id if residente else None,
        etiqueta=data.get("etiqueta"),
    )
    db.session.add(tarjeta)
    db.session.commit()
    return jsonify({"data": tarjeta.to_dict()}), 201


# =====================================================================
# TARIFAS (catálogo para el formulario)
# =====================================================================
@cuentas_bp.get("/tarifas")
@token_required
def listar_tarifas(usuario_actual):
    tarifas = Tarifa.query.filter_by(activa=True).all()
    return jsonify({"data": [t.to_dict() for t in tarifas]})


@cuentas_bp.post("/tarifas")
@roles_required("admin", "super_admin")
def crear_tarifa(usuario_actual):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return _err("nombre_requerido", "El nombre de la tarifa es obligatorio", 400)
    try:
        monto = float(data.get("monto"))
        if monto < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _err("monto_invalido", "El monto debe ser un número válido", 400)
    tarifa = Tarifa(nombre=nombre, monto=monto,
                    descripcion=(data.get("descripcion") or "").strip() or None, activa=True)
    db.session.add(tarifa)
    db.session.commit()
    return jsonify({"data": tarifa.to_dict()}), 201


@cuentas_bp.put("/tarifas/<int:tarifa_id>")
@roles_required("admin", "super_admin")
def editar_tarifa(usuario_actual, tarifa_id):
    tarifa = Tarifa.query.get(tarifa_id)
    if not tarifa:
        return _err("no_encontrada", "Tarifa no encontrada", 404)
    data = request.get_json(silent=True) or {}
    if "nombre" in data:
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return _err("nombre_requerido", "El nombre no puede quedar vacío", 400)
        tarifa.nombre = nombre
    if "monto" in data:
        try:
            tarifa.monto = float(data.get("monto"))
        except (TypeError, ValueError):
            return _err("monto_invalido", "Monto inválido", 400)
    if "descripcion" in data:
        tarifa.descripcion = (data.get("descripcion") or "").strip() or None
    db.session.commit()
    return jsonify({"data": tarifa.to_dict()})


@cuentas_bp.delete("/tarifas/<int:tarifa_id>")
@roles_required("admin", "super_admin")
def desactivar_tarifa(usuario_actual, tarifa_id):
    tarifa = Tarifa.query.get(tarifa_id)
    if not tarifa:
        return _err("no_encontrada", "Tarifa no encontrada", 404)
    # No se borra: se desactiva (puede haber cuentas que la usan)
    en_uso = Cuenta.query.filter_by(tarifa_id=tarifa.id).count()
    tarifa.activa = False
    db.session.commit()
    return jsonify({"data": {"message": f"Tarifa desactivada"
                             + (f" ({en_uso} cuentas la seguían usando)" if en_uso else "")}})
