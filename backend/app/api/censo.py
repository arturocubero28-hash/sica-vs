"""
Módulo de Censo (Padrón) — Día 69.

POR QUÉ EXISTE
--------------
El patronato no tiene cómo obligar a nadie a enrolarse en el sistema ni a
pagar la cuota. Pero igual necesita saber quién entra y quién sale de la
residencial. Si las casas que no participan quedan fuera del sistema, sus
accesos se registran como aperturas manuales anónimas y el valor principal
del proyecto —la trazabilidad— se pierde justo donde más hace falta.

La solución es cargar el censo completo de la colonia, participe o no cada
casa. Eso exige separar dos cosas que antes del Día 69 estaban pegadas:

    estar en el padrón  →  la persona existe y el guardia la identifica
    tener cuenta        →  además usa la app y se le generan cuotas

Una casa en modo 'censo' NO genera cuotas, NO entra en mora, NO recibe
avisos de cobro y NO figura en los reportes financieros. Sus habitantes
existen como personas identificables, con foto, pero sin credenciales.

CÓMO SE MODELA
--------------
La persona SIEMPRE vive en Usuario. Una persona del padrón es un Usuario
sin correo y sin contraseña: no son credenciales falsas, simplemente no
existen, así que no hay forma de que entre al sistema.

Se descartaron dos alternativas:
  - correos inventados (casa42@censo.local): ensucian la tabla de usuarios,
    chocan con el índice único de correo y se cuelan en listados y conteos;
  - mover la identidad a Residente: tras convertir a la persona en usuario,
    su nombre y foto quedarían duplicados en dos tablas y cada pantalla
    tendría que preguntar de dónde leer.

Convertir a una persona del padrón en usuario es llenarle el correo y
mandarle el enlace de activación. Un UPDATE, sin mover un solo dato.

La estructura de la casa es idéntica en los dos modos: un titular y sus
dependientes.

RUTAS
-----
    GET  /api/v1/censo                              -> casas del padrón
    POST /api/v1/censo/casas                        -> alta de casa + titular
    POST /api/v1/censo/casas/<uuid>/personas        -> agrega un dependiente
    POST /api/v1/censo/casas/<uuid>/convertir       -> censo -> completa
    POST /api/v1/censo/personas/<uuid>/dar-acceso   -> persona -> usuario
"""
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Unidad, Cuenta, Residente, Tarifa
from app.auth.security import roles_required
from app.utils.residencial import residencial_id_heredado, pertenece_a_mi_residencial

censo_bp = Blueprint("censo", __name__)


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _validar_dni(dni_raw):
    """Mismo criterio que el alta normal: 13 dígitos, formato hondureño.
    Devuelve None si está bien, o el mensaje de error."""
    dni = (dni_raw or "").strip()
    if not dni:
        return None
    solo_num = dni.replace("-", "").replace(" ", "")
    if not solo_num.isdigit() or len(solo_num) != 13:
        return "El número de identidad debe tener 13 dígitos (0000-0000-00000)"
    return None


def _crear_persona_censo(data, usuario_actual):
    """
    Crea un Usuario SIN credenciales: la persona del padrón.

    Espejo de _crear_usuario_pendiente() de cuentas.py, con dos diferencias
    deliberadas: no pide correo (no lo tiene) y no genera token de
    activación (no hay nada que activar todavía).

    Devuelve (usuario, None) o (None, mensaje_error).
    """
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return None, "El nombre es obligatorio"

    err = _validar_dni(data.get("dni"))
    if err:
        return None, err

    u = Usuario(
        nombre=nombre,
        apellido=(data.get("apellido") or "").strip(),
        email=None,              # la persona del padrón no tiene correo
        telefono=(data.get("telefono") or None),
        dni=(data.get("dni") or None),
        direccion_exacta=(data.get("direccion_exacta") or None),
        contacto_emergencia_nombre=(data.get("contacto_emergencia_nombre") or None),
        contacto_emergencia_telefono=(data.get("contacto_emergencia_telefono") or None),
        rol="residente",
        es_censo=True,
        # activo=False a propósito: si algún camino del sistema llegara a
        # preguntar "¿este usuario está activo?" para conceder algo, una
        # persona del padrón debe fallar ese chequeo. El login ya la rechaza
        # antes por no tener credenciales, pero esto es defensa en
        # profundidad: no se confía en una sola barrera.
        activo=False,
        residencial_id=residencial_id_heredado(usuario_actual),
    )
    # Sin password_hash: queda en NULL. check_password() devuelve False
    # siempre en ese caso (ver models/usuario.py), así que no hay manera de
    # autenticarse como esta persona.
    db.session.add(u)
    db.session.flush()
    return u, None


# ─────────────────────────────────────────────────────────────────────────
# LISTADO
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.get("")
@roles_required("admin", "super_admin")
def listar_censo(usuario_actual):
    """Casas del padrón de esta residencial, con su gente."""
    rid = residencial_id_heredado(usuario_actual)
    q = (Cuenta.query
         .join(Unidad, Cuenta.unidad_id == Unidad.id)
         .filter(Cuenta.modo_participacion == "censo",
                 Cuenta.activa.is_(True)))
    if rid is not None:
        q = q.filter(Unidad.residencial_id == rid)
    cuentas = q.all()
    return jsonify({"data": {
        "casas": [c.to_dict(detalle=True) for c in cuentas],
        "total": len(cuentas),
    }})


# ─────────────────────────────────────────────────────────────────────────
# ALTA DE CASA EN EL PADRÓN
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/casas")
@roles_required("admin", "super_admin")
def crear_casa_censo(usuario_actual):
    """
    Da de alta una casa en el padrón, con su titular.

    Body:
      {
        "identificador": "Casa 24",          (o "unidad_id" si ya existe)
        "titular": { "nombre", "apellido", "dni", "telefono" }
      }

    NO se piden tarifa ni día de pago: esta casa no paga nada. Tampoco se
    aplica la regla anti-mora que sí corre en el alta normal — esa regla
    impide que alguien con deuda en otra casa se dé de alta en una nueva, y
    acá no se está contrayendo ninguna obligación. Bloquear el censo por una
    deuda dejaría a esa familia fuera de la trazabilidad, que es
    exactamente lo contrario de lo que se busca.
    """
    data = request.get_json(silent=True) or {}
    rid = residencial_id_heredado(usuario_actual)

    unidad = None
    if data.get("unidad_id"):
        unidad = Unidad.query.filter_by(uuid_publico=data.get("unidad_id")).first()
        if unidad and rid is not None and unidad.residencial_id != rid:
            return _err("unidad_ajena", "Esa unidad no pertenece a tu residencial", 403)

    if not unidad:
        ident = (data.get("identificador") or "").strip()
        if not ident:
            return _err("datos_incompletos",
                        "Indicá el identificador de la casa (ej. \"Casa 24\")", 400)
        existente = Unidad.query.filter(
            db.func.lower(Unidad.identificador) == ident.lower()).first()
        if existente:
            return _err("duplicado",
                        f"Ya existe una unidad llamada \"{existente.identificador}\".", 409)
        unidad = Unidad(tipo="casa", identificador=ident, activa=True,
                        residencial_id=rid)
        db.session.add(unidad)
        db.session.flush()

    titular_data = data.get("titular") or {}
    persona, error = _crear_persona_censo(titular_data, usuario_actual)
    if persona is None:
        return _err("titular_invalido", error, 400)

    cuenta = Cuenta(
        unidad_id=unidad.id,
        apartamento=None,
        tarifa_id=None,          # no paga cuota
        dia_pago=None,
        modo_participacion="censo",
    )
    db.session.add(cuenta)
    db.session.flush()

    residente = Residente(
        usuario_id=persona.id, cuenta_id=cuenta.id,
        rol_cuenta="titular",
        relacion=titular_data.get("relacion", "propietario"),
    )
    db.session.add(residente)
    db.session.commit()

    return jsonify({"data": {"casa": cuenta.to_dict(detalle=True)}}), 201


# ─────────────────────────────────────────────────────────────────────────
# AGREGAR DEPENDIENTE
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/casas/<cuenta_uuid>/personas")
@roles_required("admin", "super_admin")
def agregar_persona_censo(usuario_actual, cuenta_uuid):
    """
    Agrega un dependiente a una casa del padrón.

    Se respeta el mismo límite de personas por unidad que en el alta normal:
    una casa del censo tiene la misma estructura que cualquier otra, un
    titular y sus dependientes.
    """
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Casa no encontrada", 404)
    if not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("casa_ajena", "Esa casa no pertenece a tu residencial", 403)
    if not cuenta.es_censo:
        return _err("no_es_censo",
                    "Esta casa ya participa del sistema. Agregá el miembro "
                    "desde el alta normal de residentes.", 400)

    unidad = cuenta.unidad
    extra_actuales = len([r for r in cuenta.residentes if r.activo]) - 1
    if unidad:
        max_extra = unidad.max_residentes_extra
        if max_extra is None:
            max_extra = 4 if unidad.tipo == "casa" else 1
        if extra_actuales >= max_extra:
            return _err("limite_residentes",
                        f"Esta {unidad.tipo} ya tiene el máximo de {max_extra} "
                        f"persona(s) adicional(es) al titular.", 400)

    data = request.get_json(silent=True) or {}
    persona, error = _crear_persona_censo(data, usuario_actual)
    if persona is None:
        return _err("persona_invalida", error, 400)

    residente = Residente(
        usuario_id=persona.id, cuenta_id=cuenta.id,
        rol_cuenta="miembro", relacion=data.get("relacion", "familiar"),
    )
    db.session.add(residente)
    db.session.commit()

    return jsonify({"data": {"residente": residente.to_dict()}}), 201


# ─────────────────────────────────────────────────────────────────────────
# CONVERSIÓN: CASA DEL PADRÓN → CASA COMPLETA
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/casas/<cuenta_uuid>/convertir")
@roles_required("admin", "super_admin")
def convertir_casa(usuario_actual, cuenta_uuid):
    """
    La familia decidió sumarse: la casa pasa de 'censo' a 'completa'.

    Body: { "tarifa_id": 1, "dia_pago": 5 }

    SOBRE LA RETROACTIVIDAD — el punto más importante de este endpoint.
    Las cuotas arrancan en el mes en curso y NUNCA hacia atrás. No hace
    falta lógica para lograrlo: tanto el cron (generar_cuotas_mensuales)
    como la generación manual crean solo el período del mes actual y jamás
    rellenan meses anteriores. Cobrarle a una familia los meses en que no
    participaba sería la forma más rápida de perderla, y de paso de perder
    la credibilidad del sistema entero.

    Se guarda fecha_conversion como constancia de desde cuándo se le cobra.
    """
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Casa no encontrada", 404)
    if not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("casa_ajena", "Esa casa no pertenece a tu residencial", 403)
    if not cuenta.es_censo:
        return _err("ya_completa", "Esta casa ya participa del sistema", 400)

    data = request.get_json(silent=True) or {}

    # Si la residencial no tiene cuotas en su plan, la casa pasa a completa
    # igual (gana app y credenciales) pero sin tarifa — mismo criterio que
    # el alta normal en crear_cuenta.
    from app.utils.residencial import plan_permite
    sin_cuotas = not plan_permite(usuario_actual.residencial_id, "cuotas")

    tarifa = None
    dia_pago = None
    if not sin_cuotas:
        tarifa = Tarifa.query.get(data.get("tarifa_id"))
        if not tarifa or not pertenece_a_mi_residencial(tarifa, usuario_actual):
            return _err("tarifa_invalida", "La tarifa indicada no existe", 400)
        dia_pago = data.get("dia_pago")
        if not isinstance(dia_pago, int) or not (1 <= dia_pago <= 30):
            return _err("dia_pago_invalido", "El día de pago debe estar entre 1 y 30", 400)

    cuenta.modo_participacion = "completa"
    cuenta.tarifa_id = tarifa.id if tarifa else None
    cuenta.dia_pago = dia_pago
    cuenta.fecha_conversion = dt.date.today()
    db.session.commit()

    return jsonify({"data": {
        "casa": cuenta.to_dict(detalle=True),
        "nota": "Las cuotas empiezan a generarse desde el mes en curso. "
                "No se generan cuotas de meses anteriores.",
    }})


# ─────────────────────────────────────────────────────────────────────────
# CONVERSIÓN: PERSONA DEL PADRÓN → USUARIO DE LA APP
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/personas/<residente_uuid>/dar-acceso")
@roles_required("admin", "super_admin")
def dar_acceso_persona(usuario_actual, residente_uuid):
    """
    Le da acceso al sistema a una persona que ya estaba en el padrón.

    Body: { "email": "persona@correo.com" }

    Es exactamente el UPDATE que justifica todo el diseño: no se crea una
    persona nueva ni se migra nada. La misma fila de Usuario que el guardia
    ya venía usando para identificarla pasa a tener correo y contraseña.
    Su historial de accesos previo queda intacto y sigue siendo suyo.
    """
    residente = Residente.query.filter_by(uuid_publico=residente_uuid).first()
    if not residente:
        return _err("no_encontrada", "Persona no encontrada", 404)

    cuenta = residente.cuenta
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("persona_ajena", "Esa persona no pertenece a tu residencial", 403)

    persona = residente.usuario
    if not persona:
        return _err("sin_usuario", "Esta persona no tiene ficha de usuario", 400)
    if not persona.es_censo:
        return _err("ya_tiene_acceso", "Esta persona ya tiene acceso al sistema", 400)

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return _err("datos_incompletos", "El correo es obligatorio para dar acceso", 400)
    if Usuario.query.filter_by(email=email).first():
        return _err("email_duplicado", f"Ya existe un usuario con el email {email}", 409)

    # El límite de usuarios del plan se evalúa ACÁ y no al cargar el censo:
    # la gente del padrón no consume licencias porque no usa el sistema. Es
    # al darle acceso cuando pasa a ser un usuario de verdad.
    from app.utils.residencial import limite_usuarios_alcanzado
    if limite_usuarios_alcanzado(usuario_actual.residencial_id):
        return _err("limite_usuarios",
                    "Tu plan actual no permite más usuarios. "
                    "Pedile a tu proveedor que te suba de plan.", 402)

    import secrets
    persona.email = email
    persona.es_censo = False
    # Contraseña temporal inutilizable: se reemplaza en la activación, igual
    # que en el alta normal de un residente.
    persona.set_password(secrets.token_urlsafe(32))
    persona.activo = False       # pendiente hasta que defina su contraseña

    token_activacion = jwt.encode(
        {"sub": email, "proposito": "activacion",
         "exp": dt.datetime.utcnow() + dt.timedelta(hours=48)},
        current_app.config["JWT_SECRET"], algorithm="HS256"
    )
    db.session.commit()

    # Después del commit, nunca antes: un correo de activación para un
    # usuario que no quedó guardado es peor que no mandar nada (misma
    # lección del Día 61).
    try:
        from app.tasks.correo_task import enviar_correo_activacion_task
        from app.models.residencial import Residencial
        residencial = (Residencial.query.get(usuario_actual.residencial_id)
                       if usuario_actual.residencial_id else None)
        enviar_correo_activacion_task.delay(
            email, persona.nombre, token_activacion,
            residencial.nombre if residencial else "SICA-VS")
    except Exception:
        pass

    resp = {"residente": residente.to_dict()}
    # El token solo se devuelve fuera de producción, igual que en el resto
    # del sistema (hallazgo C1 del pentest del Día 14: devolverlo en
    # producción es una toma de cuenta con solo conocer el correo).
    if current_app.config.get("ENV") != "production":
        resp["token_activacion"] = token_activacion
    return jsonify({"data": resp}), 200
