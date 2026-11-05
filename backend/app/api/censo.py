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
    # Día 73 — joinedload de residentes y de la unidad.
    #
    # to_dict(detalle=True) recorre los residentes de cada casa, y la
    # relación es lazy="select": sin esto, una consulta por casa para traer
    # su gente (y el usuario de cada residente sale por su propio
    # lazy="joined"). Con veinte casas no se nota; con las cientos que el
    # padrón está pensado para tener, son cientos de viajes a la base para
    # armar una sola pantalla.
    from sqlalchemy.orm import joinedload
    q = (Cuenta.query
         .join(Unidad, Cuenta.unidad_id == Unidad.id)
         .options(joinedload(Cuenta.residentes), joinedload(Cuenta.unidad))
         .filter(Cuenta.modo_participacion == "censo",
                 Cuenta.activa.is_(True)))
    if rid is not None:
        q = q.filter(Unidad.residencial_id == rid)
    # .all() a secas: Query (el estilo legacy que usa el proyecto) ya
    # deduplica las entidades al traer una colección con joinedload. El
    # .unique() del estilo 2.0 no existe acá.
    cuentas = q.all()

    # Día 69 — métrica de adopción. El sentido del padrón es poder decirle al
    # patronato, con un número y no con una impresión, cuánta gente de la
    # colonia está dentro del sistema y cuánta además participa pagando.
    # Son dos cosas distintas y conviene no confundirlas: una casa del censo
    # YA está trazada (sus accesos quedan registrados) aunque no aporte un
    # lempira.
    base = Cuenta.query.join(Unidad, Cuenta.unidad_id == Unidad.id).filter(
        Cuenta.activa.is_(True))
    if rid is not None:
        base = base.filter(Unidad.residencial_id == rid)
    # Las cuentas CONTENEDORAS de edificio quedan fuera de los conteos: son
    # estructura, no hogares. Un edificio de ocho apartamentos son ocho
    # familias, no nueve, y contarlo de más desinflaría el porcentaje de
    # participación que se le reporta al patronato.
    base = base.filter(db.not_(
        db.and_(Unidad.tipo == "edificio", Cuenta.apartamento.is_(None))))
    total_censo = base.filter(Cuenta.modo_participacion == "censo").count()
    # 'completa' por defecto: las cuentas creadas antes del Día 69 no tienen
    # el campo seteado explícitamente, y son todas de participación completa.
    total_completas = base.filter(
        db.or_(Cuenta.modo_participacion == "completa",
               Cuenta.modo_participacion.is_(None))).count()
    # Cuántas pasaron de censo a cuenta completa (tienen fecha de conversión).
    # Es el número que dice si el padrón sirve como puerta de entrada.
    total_convertidas = base.filter(Cuenta.fecha_conversion.isnot(None)).count()
    total_casas = total_censo + total_completas

    return jsonify({"data": {
        "casas": [c.to_dict(detalle=True) for c in cuentas],
        "total": len(cuentas),
        "resumen": {
            "censo": total_censo,
            "completas": total_completas,
            "total": total_casas,
            "convertidas": total_convertidas,
            "pct_completas": (round(total_completas * 100 / total_casas)
                              if total_casas else 0),
        },
    }})


# ─────────────────────────────────────────────────────────────────────────
# ALTA DE CASA EN EL PADRÓN
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/casas")
@roles_required("admin", "super_admin")
def crear_casa_censo(usuario_actual):
    """
    Da de alta en el padrón una casa, un edificio o un apartamento, con su
    titular. Sigue EXACTAMENTE la misma estructura que el alta normal
    (cuentas.crear_cuenta), porque convertir del padrón a cuenta completa es
    un cambio de modo, no una migración: si la estructura no coincide, la
    conversión produce datos que el resto del sistema no sabe mostrar.

    Body:
      { "tipo": "casa", "identificador": "Casa 24", "titular": {...} }

      { "tipo": "edificio", "identificador": "Edificio Las Palmas",
        "dueno_vive": false, "max_apartamentos": 12, "titular": {...} }
          -> el dueño SOLO ADMINISTRA: cuenta contenedora a su nombre, sin
             apartamento y sin cuota (igual que es_solo_contenedor).

      { "tipo": "edificio", "identificador": "Edificio Las Palmas",
        "dueno_vive": true, "apartamento": "1A", "titular": {...} }
          -> el dueño VIVE en el 1A: ese apartamento queda a su nombre como
             administrador del edificio. No hay contenedora (igual que el
             alta normal con "el dueño vive en el edificio").

      { "tipo": "apartamento", "unidad_id": "<edificio>",
        "apartamento": "2B", "titular": {...} }
          -> un inquilino. El edificio tiene que estar registrado antes, con
             su dueño -- igual que en el alta normal.

    En todos los casos el dueño queda en Unidad.propietario_id, que es de
    donde cuelgan "Mi Edificio" y los códigos de enrolamiento cuando la
    cuenta pase a participar.

    NO se piden tarifa ni día de pago: en el padrón nadie paga. Tampoco se
    aplica la regla anti-mora del alta normal: acá no se contrae ninguna
    obligación, y bloquear el censo por una deuda dejaría a esa familia
    fuera de la trazabilidad, que es lo contrario de lo que se busca.
    """
    data = request.get_json(silent=True) or {}
    rid = residencial_id_heredado(usuario_actual)

    tipo = data.get("tipo") if data.get("tipo") in ("casa", "edificio", "apartamento") else "casa"
    apartamento = (str(data.get("apartamento") or "")).strip() or None
    dueno_vive = bool(data.get("dueno_vive"))
    ident = (data.get("identificador") or "").strip()

    def _buscar_por_nombre(nombre):
        q = Unidad.query.filter(db.func.lower(Unidad.identificador) == nombre.lower())
        if rid is not None:
            q = q.filter(Unidad.residencial_id == rid)
        return q.first()

    # ── Validaciones, todas ANTES de crear a la persona ──────────────────
    unidad = None
    contenedora_vacia = None

    if tipo == "apartamento":
        if not apartamento:
            return _err("apartamento_requerido", "Indicá el número de apartamento (ej. 2B)", 400)
        if data.get("unidad_id"):
            unidad = Unidad.query.filter_by(uuid_publico=data.get("unidad_id")).first()
        elif ident:
            unidad = _buscar_por_nombre(ident)
        if not unidad or unidad.tipo != "edificio":
            # Igual que en el alta normal: el apartamento cuelga de un
            # edificio que ya existe con su dueño. Crear el edificio desde
            # acá lo dejaría sin dueño, y ese edificio no sabría a quién
            # pertenece cuando pase a participar.
            return _err("edificio_no_registrado",
                        "Ese edificio no está registrado. Registralo primero con "
                        "su dueño (opción \"Edificio\") y después sus apartamentos.", 400)
        if rid is not None and unidad.residencial_id != rid:
            return _err("unidad_ajena", "Ese edificio no pertenece a tu residencial", 403)

    elif tipo == "edificio":
        if not ident:
            return _err("datos_incompletos",
                        "Indicá el nombre del edificio (ej. \"Edificio Las Palmas\")", 400)
        if dueno_vive and not apartamento:
            return _err("apartamento_requerido",
                        "Si el dueño vive en el edificio, indicá en qué apartamento", 400)
        existente = _buscar_por_nombre(ident)
        if existente:
            if existente.tipo != "edificio":
                return _err("duplicado",
                            f"Ya existe una casa llamada \"{existente.identificador}\".", 409)
            if existente.propietario_id:
                return _err("duplicado",
                            f"\"{existente.identificador}\" ya está registrado con su dueño. "
                            "Agregá los apartamentos con la opción \"Apartamento\".", 409)
            # Edificio sin dueño: lo dejó el padrón del Día 69, que creaba el
            # edificio desde el primer apartamento. Se adopta en vez de
            # rechazarlo, para no obligar a borrar nada.
            unidad = existente
        cont = (Cuenta.query.filter_by(unidad_id=unidad.id, apartamento=None, activa=True).first()
                if unidad else None)
        if cont is not None:
            if any(r.activo for r in cont.residentes):
                return _err("duplicado", "Ese edificio ya tiene administrador registrado", 409)
            contenedora_vacia = cont

    else:  # casa
        if not ident:
            return _err("datos_incompletos", "Indicá el identificador de la casa (ej. \"Casa 24\")", 400)
        if _buscar_por_nombre(ident):
            return _err("duplicado", f"Ya existe una unidad llamada \"{ident}\".", 409)

    # No repetir el apartamento dentro del edificio. Se miran TODAS las
    # cuentas activas, de censo y completas: el apto 3 es el apto 3,
    # participe o no esa familia.
    # Sin distinguir mayúsculas: "1a" y "1A" son el mismo apartamento, y
    # el guardia también los busca así en el portón.
    if apartamento and unidad is not None and Cuenta.query.filter(
            Cuenta.unidad_id == unidad.id, Cuenta.activa.is_(True),
            db.func.lower(Cuenta.apartamento) == apartamento.lower()).first():
        return _err("duplicado",
                    f"El apartamento {apartamento} ya está registrado en {unidad.identificador}", 409)

    # Límite de apartamentos del edificio, si se definió (igual que el alta
    # normal, Día 29). Cuenta solo apartamentos, no la contenedora.
    if apartamento and unidad is not None and unidad.max_apartamentos:
        aptos = Cuenta.query.filter(Cuenta.unidad_id == unidad.id, Cuenta.activa.is_(True),
                                    Cuenta.apartamento.isnot(None)).count()
        if aptos >= unidad.max_apartamentos:
            return _err("limite_apartamentos",
                        f"{unidad.identificador} ya tiene {aptos} apartamento(s) de un "
                        f"máximo de {unidad.max_apartamentos}.", 400)

    # ── Crear ────────────────────────────────────────────────────────────
    titular_data = data.get("titular") or {}
    persona, error = _crear_persona_censo(titular_data, usuario_actual)
    if persona is None:
        return _err("titular_invalido", error, 400)

    if unidad is None:
        max_aptos = data.get("max_apartamentos")
        unidad = Unidad(
            tipo="edificio" if tipo == "edificio" else "casa",
            identificador=ident, activa=True, residencial_id=rid,
            max_apartamentos=(int(max_aptos) if tipo == "edificio" and str(max_aptos or "").isdigit()
                              else None),
        )
        db.session.add(unidad)
        db.session.flush()

    if tipo == "edificio" and not dueno_vive:
        # El dueño SOLO ADMINISTRA: cuenta contenedora a su nombre. Sin
        # apartamento y sin tarifa: no paga cuota ni en el padrón ni cuando
        # participe (es_contenedor_edificio exige justamente eso).
        cuenta = contenedora_vacia or Cuenta(
            unidad_id=unidad.id, apartamento=None,
            tarifa_id=None, dia_pago=None, modo_participacion="censo")
        if contenedora_vacia is None:
            db.session.add(cuenta)
            db.session.flush()
    else:
        cuenta = Cuenta(
            unidad_id=unidad.id,
            apartamento=apartamento if tipo in ("edificio", "apartamento") else None,
            tarifa_id=None, dia_pago=None, modo_participacion="censo",
        )
        db.session.add(cuenta)
        db.session.flush()
        if tipo == "edificio" and contenedora_vacia is not None:
            # El dueño vive ahí: en el alta normal ese edificio NO tiene
            # contenedora, el apartamento del dueño hace de administración.
            # Si quedó una vacía del padrón anterior, se da de baja para no
            # tener las dos cosas a la vez.
            contenedora_vacia.activa = False

    if tipo == "edificio":
        # Queda como dueño/responsable del edificio, igual que
        # es_dueno_edificio en el alta normal. Si vive ahí, esto además hace
        # que su apartamento se reconozca como administración
        # (tipo_cuenta() = 'edificio_admin').
        unidad.propietario_id = persona.id

    residente = Residente(
        usuario_id=persona.id, cuenta_id=cuenta.id,
        rol_cuenta="titular",
        relacion=titular_data.get("relacion",
                                  "propietario" if tipo != "apartamento" else "inquilino"),
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
#
# Día 73 — todo esto está partido en dos tipos de pieza:
#
#   _preparar_*  validan y devuelven lo que van a hacer, SIN tocar nada.
#   _aplicar_*   hacen el cambio en la sesión, SIN guardar.
#
# Por qué: "sumar al sistema" desde el padrón eran DOS llamadas separadas
# (convertir la casa, y después darle acceso al titular), cada una con su
# propio commit. Si la segunda fallaba —el correo rebotó, la identidad
# estaba mal—, la primera ya había quedado guardada: la casa cobrando
# cuota y la persona marcada como "con acceso". Al corregir y reintentar,
# fallaba con "esta persona ya tiene acceso al sistema". Pasó en producción.
#
# Con las piezas separadas, /sumar valida TODO primero, y recién si todo
# pasa —incluida la confirmación de que el correo llegó— aplica todo y
# guarda una sola vez. O se hace todo, o no se hace nada.


def _preparar_conversion(cuenta, data, usuario_actual):
    """
    Valida la conversión de una casa. Devuelve (plan, None) o (None, error).
    No modifica nada.

    SOBRE LA RETROACTIVIDAD — el punto más importante de la conversión.
    Las cuotas arrancan en el mes en curso y NUNCA hacia atrás. Cobrarle a
    una familia los meses en que no participaba sería la forma más rápida
    de perderla, y de paso de perder la credibilidad del sistema entero.
    """
    if not cuenta.es_censo:
        return None, _err("ya_completa", "Esta casa ya participa del sistema", 400)

    # Si la residencial no tiene cuotas en su plan, la casa pasa a completa
    # igual (gana app y credenciales) pero sin tarifa — mismo criterio que
    # el alta normal en crear_cuenta.
    from app.utils.residencial import plan_permite
    sin_cuotas = not plan_permite(usuario_actual.residencial_id, "cuotas")

    # Día 70 — la cuenta contenedora de un edificio (dueño que solo
    # administra) NUNCA paga cuota: ni en el padrón ni participando. Es la
    # misma regla que el alta normal con es_solo_contenedor.
    es_contenedora = cuenta.es_contenedor_edificio()

    tarifa = None
    dia_pago = None
    if not sin_cuotas and not es_contenedora:
        # Sin id no se consulta: Query.get(None) avisa que la búsqueda no
        # puede encontrar nada, y el caso ya está cubierto por el "not tarifa".
        tid = data.get("tarifa_id")
        tarifa = Tarifa.query.get(tid) if tid else None
        if not tarifa or not pertenece_a_mi_residencial(tarifa, usuario_actual):
            return None, _err("tarifa_invalida", "La tarifa indicada no existe", 400)
        dia_pago = data.get("dia_pago")
        if not isinstance(dia_pago, int) or not (1 <= dia_pago <= 30):
            return None, _err("dia_pago_invalido", "El día de pago debe estar entre 1 y 30", 400)

    return {"tarifa": tarifa, "dia_pago": dia_pago, "es_contenedora": es_contenedora}, None


def _aplicar_conversion(cuenta, plan, usuario_actual):
    """
    Pasa la casa a 'completa' y le genera la primera cuota prorrateada.
    NO hace commit. Devuelve la nota para mostrarle al administrador.
    """
    tarifa = plan["tarifa"]
    cuenta.modo_participacion = "completa"
    cuenta.tarifa_id = tarifa.id if tarifa else None
    cuenta.dia_pago = plan["dia_pago"]
    cuenta.fecha_conversion = dt.date.today()

    # Si es un apartamento, su edificio tiene que salir del padrón con él:
    # si la contenedora siguiera en censo, el edificio se seguiría listando
    # en el padrón aunque ya tenga apartamentos participando. No se le pone
    # tarifa: una contenedora no cobra cuota nunca.
    if cuenta.apartamento and cuenta.unidad and cuenta.unidad.tipo == "edificio":
        contenedora = Cuenta.query.filter_by(
            unidad_id=cuenta.unidad_id, apartamento=None, activa=True).first()
        if contenedora is not None and contenedora.es_censo:
            contenedora.modo_participacion = "completa"
            contenedora.fecha_conversion = dt.date.today()

    if plan["es_contenedora"]:
        return ("El edificio ya participa del sistema. Como el dueño solo "
                "administra, no se le genera cuota.")

    base = ("Las cuotas empiezan a generarse desde el mes en curso. "
            "No se generan cuotas de meses anteriores.")
    if not tarifa:
        return base

    # ── Día 73 — PRIMERA CUOTA PRORRATEADA ────────────────────────────────
    #
    # BUG REAL encontrado en producción: una casa que nacía del padrón
    # quedaba SIN DEUDA. El alta normal sí genera la cuota prorrateada; la
    # conversión no, así que el mes en que la familia se sumaba le salía
    # gratis y las dos puertas de entrada cobraban distinto. No es
    # retroactividad: es el pedazo de mes EN CURSO que sí va a usar.
    #
    # Mismo cálculo y mismo vencimiento (cfg.dia_pago) que el alta normal y
    # que el cron mensual: una sola regla para los tres caminos.
    from app.models.cuenta import Cuota, ConfigResidencial
    from app.utils.cuotas import calcular_cuota_prorrateada
    cfg = ConfigResidencial.get(usuario_actual.residencial_id)
    datos = calcular_cuota_prorrateada(tarifa.monto, cfg.dia_pago)
    if datos is None:
        # Último día del mes comercial: no queda fracción que cobrar.
        return (base + " No se generó cuota de este mes porque ya no quedan "
                "días por cobrar; la primera será la del mes que viene.")
    db.session.flush()   # para que cuenta.id exista si la cuenta es nueva
    ya_existe = Cuota.query.filter_by(cuenta_id=cuenta.id, periodo=datos["periodo"]).first()
    if ya_existe is None:
        db.session.add(Cuota(
            cuenta_id=cuenta.id, periodo=datos["periodo"],
            monto=datos["monto"], fecha_vencimiento=datos["fecha_vencimiento"],
            estado="pendiente",
        ))
    return (base + f" Se le generó la cuota de este mes prorrateada: "
            f"L {datos['monto']} por {datos['dias_restantes']} días, "
            f"con vencimiento el {datos['fecha_vencimiento'].strftime('%d/%m/%Y')}.")


def _preparar_acceso(residente, data, usuario_actual):
    """
    Valida que a esta persona del padrón se le pueda dar acceso. Devuelve
    (datos, None) o (None, error). No modifica nada.

    LA FICHA TIENE QUE ESTAR COMPLETA (Día 73). El padrón se llena con lo
    mínimo a propósito: al guardia le alcanza con saber quién entra. Pero
    quien pasa a tener app y cuota se vuelve residente con todas las de la
    ley, y su ficha tiene que valer lo mismo que la de quien entró por el
    alta normal. Si no, el padrón es la puerta de atrás para tener
    residentes a medio registrar.
    """
    persona = residente.usuario
    if not persona:
        return None, _err("sin_usuario", "Esta persona no tiene ficha de usuario", 400)
    if not persona.es_censo:
        return None, _err("ya_tiene_acceso", "Esta persona ya tiene acceso al sistema", 400)

    email = (data.get("email") or "").strip().lower()
    if not email:
        return None, _err("datos_incompletos", "El correo es obligatorio para dar acceso", 400)
    if Usuario.query.filter_by(email=email).first():
        return None, _err("email_duplicado", f"Ya existe un usuario con el email {email}", 409)

    obligatorios = [
        ("apellido", "El apellido es obligatorio"),
        ("telefono", "El teléfono es obligatorio"),
        ("dni", "El número de identidad es obligatorio"),
        ("direccion_exacta", "La dirección exacta es obligatoria"),
        ("profesion", "La profesión es obligatoria"),
        ("contacto_emergencia_nombre", "El contacto de emergencia es obligatorio"),
        ("contacto_emergencia_telefono", "El teléfono del contacto de emergencia es obligatorio"),
    ]
    # Lo que la persona YA trae del padrón cuenta como válido.
    valores = {}
    for campo, mensaje in obligatorios:
        valor = (data.get(campo) or "").strip() or (getattr(persona, campo, None) or "")
        if not valor:
            return None, _err("datos_incompletos", mensaje, 400)
        valores[campo] = valor

    err = _validar_dni(valores["dni"])
    if err:
        return None, _err("dni_invalido", err, 400)

    # El límite de usuarios del plan se evalúa ACÁ y no al cargar el censo:
    # la gente del padrón no consume licencias porque no usa el sistema.
    from app.utils.residencial import limite_usuarios_alcanzado
    if limite_usuarios_alcanzado(usuario_actual.residencial_id):
        return None, _err("limite_usuarios",
                          "Tu plan actual no permite más usuarios. "
                          "Pedile a tu proveedor que te suba de plan.", 402)

    opcionales = {c: (data.get(c) or "").strip()
                  for c in ("rtn", "ocupacion", "centro_estudios", "lugar_trabajo")
                  if (data.get(c) or "").strip()}
    return {"persona": persona, "email": email,
            "valores": valores, "opcionales": opcionales}, None


def _aplicar_acceso(datos):
    """
    Le pone correo y ficha a la persona, y la deja pendiente de activar.
    NO hace commit. Devuelve el token de activación.

    Es el UPDATE que justifica todo el diseño del padrón: no se crea una
    persona nueva. La misma fila de Usuario que el guardia ya venía usando
    pasa a tener correo y contraseña, y su historial de accesos sigue
    siendo suyo.
    """
    import secrets
    persona = datos["persona"]
    persona.email = datos["email"]
    persona.es_censo = False
    for campo, valor in {**datos["valores"], **datos["opcionales"]}.items():
        setattr(persona, campo, valor)
    # Contraseña temporal inutilizable: se reemplaza en la activación.
    persona.set_password(secrets.token_urlsafe(32))
    persona.activo = False
    return jwt.encode(
        {"sub": datos["email"], "proposito": "activacion",
         "exp": dt.datetime.utcnow() + dt.timedelta(hours=48)},
        current_app.config["JWT_SECRET"], algorithm="HS256")


def _enviar_activacion(email, nombre, token, usuario_actual):
    """Siempre DESPUÉS del commit: un correo para un usuario que no quedó
    guardado es peor que no mandar nada (lección del Día 61)."""
    try:
        from app.tasks.correo_task import enviar_correo_activacion_task
        from app.models.residencial import Residencial
        residencial = (Residencial.query.get(usuario_actual.residencial_id)
                       if usuario_actual.residencial_id else None)
        enviar_correo_activacion_task.delay(
            email, nombre, token, residencial.nombre if residencial else "Residencial")
    except Exception:
        current_app.logger.exception("No se pudo encolar el correo de activación a %s", email)


def _cuenta_mia(cuenta_uuid, usuario_actual):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return None, _err("no_encontrada", "Casa no encontrada", 404)
    if not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return None, _err("casa_ajena", "Esa casa no pertenece a tu residencial", 403)
    return cuenta, None


@censo_bp.post("/casas/<cuenta_uuid>/convertir")
@roles_required("admin", "super_admin")
def convertir_casa(usuario_actual, cuenta_uuid):
    """
    Convierte la casa SIN tocar a su gente. Body: { tarifa_id, dia_pago }

    Día 73 — solo para cuando el titular ya tiene acceso (o es la
    contenedora de un edificio). Si el titular todavía es gente de padrón,
    se rechaza: así es como quedaban casas cobrando cuota con un titular
    sin correo, que nunca podía entrar a ver qué debía. Para ese caso está
    /sumar, que hace las dos cosas juntas o ninguna.
    """
    cuenta, err = _cuenta_mia(cuenta_uuid, usuario_actual)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    plan, err = _preparar_conversion(cuenta, data, usuario_actual)
    if err:
        return err

    tit = cuenta.titular()
    if (not plan["es_contenedora"] and tit is not None and tit.usuario is not None
            and tit.usuario.es_censo):
        return _err("titular_sin_acceso",
                    "El titular todavía no tiene acceso a la app. Sumá la casa con "
                    "su ficha y su correo, así no queda cobrando cuota a alguien "
                    "que no puede entrar.", 400)

    nota = _aplicar_conversion(cuenta, plan, usuario_actual)
    db.session.commit()
    return jsonify({"data": {"casa": cuenta.to_dict(detalle=True), "nota": nota}})


@censo_bp.post("/casas/<cuenta_uuid>/sumar")
@roles_required("admin", "super_admin")
def sumar_casa(usuario_actual, cuenta_uuid):
    """
    Día 73 — la casa se suma al sistema Y su titular recibe acceso, en una
    sola operación: o se hace todo, o no se hace nada.

    Body: { tarifa_id, dia_pago, verificacion_id, email, apellido, telefono,
            dni, direccion_exacta, profesion, contacto_emergencia_nombre,
            contacto_emergencia_telefono }

    Exige que el correo esté VERIFICADO como entregado (ver
    api/verificacion_correo.py): si rebotó, no se tocó nada y se corrige
    la dirección sin dejar restos.
    """
    from app.api.verificacion_correo import exigir_verificacion, marcar_usada

    cuenta, err = _cuenta_mia(cuenta_uuid, usuario_actual)
    if err:
        return err
    data = request.get_json(silent=True) or {}

    tit = cuenta.titular()
    if tit is None:
        return _err("sin_titular", "Esta casa no tiene titular registrado", 400)

    # 1. Validar TODO, sin tocar nada.
    plan, err = _preparar_conversion(cuenta, data, usuario_actual)
    if err:
        return err
    acceso, err = _preparar_acceso(tit, data, usuario_actual)
    if err:
        return err
    verif, err = exigir_verificacion(acceso["email"], data.get("verificacion_id"))
    if err:
        return err

    # 2. Aplicar todo y guardar UNA vez.
    nota = _aplicar_conversion(cuenta, plan, usuario_actual)
    token = _aplicar_acceso(acceso)
    marcar_usada(verif)
    db.session.commit()

    # 3. Recién ahora, el correo de activación.
    _enviar_activacion(acceso["email"], acceso["persona"].nombre, token, usuario_actual)

    resp = {"casa": cuenta.to_dict(detalle=True), "residente": tit.to_dict(), "nota": nota}
    # El token solo se devuelve fuera de producción (hallazgo C1, Día 14).
    if current_app.config.get("ENV") != "production":
        resp["token_activacion"] = token
    return jsonify({"data": resp}), 200


# ─────────────────────────────────────────────────────────────────────────
# CONVERSIÓN: PERSONA DEL PADRÓN → USUARIO DE LA APP
# ─────────────────────────────────────────────────────────────────────────
@censo_bp.post("/personas/<residente_uuid>/dar-acceso")
@roles_required("admin", "super_admin")
def dar_acceso_persona(usuario_actual, residente_uuid):
    """
    Le da acceso a la app a una persona del padrón (no al titular de una
    casa que se está sumando: para eso está /sumar).

    Body: { email, verificacion_id, y la ficha completa }

    Día 73 — exige el correo verificado como entregado, igual que /sumar.
    """
    from app.api.verificacion_correo import exigir_verificacion, marcar_usada

    residente = Residente.query.filter_by(uuid_publico=residente_uuid).first()
    if not residente:
        return _err("no_encontrada", "Persona no encontrada", 404)
    cuenta = residente.cuenta
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("persona_ajena", "Esa persona no pertenece a tu residencial", 403)

    data = request.get_json(silent=True) or {}
    acceso, err = _preparar_acceso(residente, data, usuario_actual)
    if err:
        return err
    verif, err = exigir_verificacion(acceso["email"], data.get("verificacion_id"))
    if err:
        return err

    token = _aplicar_acceso(acceso)
    marcar_usada(verif)
    db.session.commit()

    _enviar_activacion(acceso["email"], acceso["persona"].nombre, token, usuario_actual)

    resp = {"residente": residente.to_dict()}
    if current_app.config.get("ENV") != "production":
        resp["token_activacion"] = token
    return jsonify({"data": resp}), 200
