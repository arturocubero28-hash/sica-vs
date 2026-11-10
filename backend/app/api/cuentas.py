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
import os
import re
import secrets
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Unidad, Cuenta, Residente, Tarjeta, Tarifa, CodigoEnrolamiento, Cuota, SolicitudBaja, Pago
from app.auth.security import roles_required, token_required, requiere_funcion_plan
from app.utils.residencial import residencial_id_heredado
from app.utils.archivos import guardar_imagen_segura, servir_archivo_seguro, EXT_IMAGEN

cuentas_bp = Blueprint("cuentas", __name__)


def _bloque_activacion(usuario, token_o_error, nota=None):
    """
    Arma el bloque de activación de la respuesta. El token de activación se
    incluye SOLO en desarrollo (no hay correos aún). En producción se omite:
    ahí el token debe llegar al residente por correo (Resend), nunca en la
    respuesta de la API, para que un acceso indebido no active cuentas ajenas.
    """
    bloque = {"usuario_email": usuario.email}
    if nota:
        bloque["nota"] = nota
    if current_app.config.get("ENV") != "production":
        bloque["token_activacion"] = token_o_error
    return bloque


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _monto_pagado_cuota(cuota):
    """Suma los pagos APROBADOS de una cuota (Cuota no guarda monto_pagado directo)."""
    total = (Pago.query.filter_by(cuota_id=cuota.id, estado="aprobado")
             .with_entities(db.func.coalesce(db.func.sum(Pago.monto), 0)).scalar())
    return float(total or 0)


def _crear_usuario_pendiente(nombre, apellido, email, telefono=None, extra=None, usuario_actual=None):
    """Crea un Usuario residente en estado pendiente de activación.
    Devuelve (usuario, token_activacion) o (None, mensaje_error).

    usuario_actual: quien está creando este residente (el admin/supervisor).
    Bases multi-residencial (Día 37) — el residente hereda su residencial_id.
    """
    email = (email or "").strip().lower()
    if not email or not nombre:
        return None, "Nombre y email son obligatorios"
    if Usuario.query.filter_by(email=email).first():
        return None, f"Ya existe un usuario con el email {email}"

    # Día 50 — sistema de suscripciones. Acá adentro (no en cada llamador
    # por separado) porque esta función la usan DOS endpoints distintos
    # (crear cuenta nueva, y agregar un residente a una ya existente) — así
    # el límite se aplica igual en los dos casos, sin arriesgarse a que se
    # nos olvide agregarlo en alguno.
    if usuario_actual is not None:
        from app.utils.residencial import limite_usuarios_alcanzado
        if limite_usuarios_alcanzado(usuario_actual.residencial_id):
            return None, "Tu plan actual no permite más usuarios. Pedile a tu proveedor que te suba de plan."

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
        ocupacion=(extra.get("ocupacion") or None),
        centro_estudios=(extra.get("centro_estudios") or None),
        lugar_trabajo=(extra.get("lugar_trabajo") or None),
        contacto_emergencia_nombre=(extra.get("contacto_emergencia_nombre") or None),
        contacto_emergencia_telefono=(extra.get("contacto_emergencia_telefono") or None),
        rol="residente",
        activo=False,            # pendiente hasta que defina contraseña
        residencial_id=residencial_id_heredado(usuario_actual) if usuario_actual else None,
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
    # Aislación multi-residencial: un admin/supervisor solo ve las unidades de
    # SU residencial; super_admin/desarrollador ven todas (filtro None).
    from app.utils.residencial import residencial_id_filtro
    q = Unidad.query.filter_by(activa=True)
    rid = residencial_id_filtro(usuario_actual)
    if rid is not None:
        q = q.filter(Unidad.residencial_id == rid)
    unidades = q.order_by(Unidad.identificador).all()
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
    # Bug real encontrado (Día 51, probando planes): esta consulta buscaba
    # el identificador en TODA la base, sin filtrar por residencial -- una
    # residencial no podía usar "casa 2" si CUALQUIER OTRA residencial ya
    # tenía una unidad con ese mismo nombre. El identificador debe ser
    # único DENTRO de cada residencial, no global en todo el sistema.
    residencial_id = residencial_id_heredado(usuario_actual)
    if Unidad.query.filter_by(identificador=identificador, residencial_id=residencial_id).first():
        return _err("duplicado", f"Ya existe la unidad '{identificador}'", 409)

    u = Unidad(tipo=tipo, identificador=identificador,
               direccion_ref=data.get("direccion_ref"),
               # Bases multi-residencial (Día 37): hereda la residencial de
               # quien la crea. Hoy siempre el mismo valor en Villas del Sol.
               residencial_id=residencial_id)
    db.session.add(u)
    db.session.commit()
    return jsonify({"data": u.to_dict()}), 201


# =====================================================================
# CUENTAS
# =====================================================================
@cuentas_bp.get("/cuentas")
@roles_required("admin", "super_admin")
def listar_cuentas(usuario_actual):
    # Paginación OPCIONAL y retrocompatible: sin parámetros devuelve la lista
    # completa (como siempre). Con ?pagina=N devuelve esa página envuelta en un
    # objeto con metadatos. Pensado para cuando el volumen crezca (multi-
    # residencial) sin romper el frontend actual.
    from sqlalchemy import func
    pagina_arg = request.args.get("pagina")

    base = Cuenta.query.order_by(Cuenta.id.desc())

    # Aislación multi-residencial: un admin/supervisor solo ve las cuentas de
    # SU residencial (unidas por Unidad→residencial_id); super_admin y
    # desarrollador ven todas (filtro None). Ver residencial_id_filtro.
    from app.utils.residencial import residencial_id_filtro
    _rid = residencial_id_filtro(usuario_actual)
    if _rid is not None:
        base = base.join(Unidad, Cuenta.unidad_id == Unidad.id).filter(
            Unidad.residencial_id == _rid)

    # Conteo de cuotas pendientes/vencidas por cuenta, en UNA query (evita N+1).
    pendientes_raw = (db.session.query(Cuota.cuenta_id, func.count(Cuota.id))
                      .filter(Cuota.estado.notin_(["pagada", "en_arreglo", "anulada"]))
                      .group_by(Cuota.cuenta_id).all())
    pendientes_por_cuenta = {cid: n for cid, n in pendientes_raw}

    def serializar(cuentas):
        out = []
        for c in cuentas:
            d = c.to_dict()
            d["cuotas_pendientes"] = pendientes_por_cuenta.get(c.id, 0)
            out.append(d)
        return out

    if pagina_arg is not None:
        pagina = max(1, int(pagina_arg))
        por_pagina = 50
        total = base.count()
        cuentas = base.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return jsonify({"data": serializar(cuentas), "pagina": pagina,
                        "por_pagina": por_pagina, "total": total,
                        "total_paginas": (total + por_pagina - 1) // por_pagina})

    # Comportamiento clásico: lista completa
    return jsonify({"data": serializar(base.all())})


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

    # Día 73 — no se crea nada hasta que Resend confirme que el correo a
    # esta dirección LLEGÓ (ver api/verificacion_correo.py). Va al
    # principio de todo, antes de crear la unidad, la cuenta o el usuario:
    # si el correo rebota no tiene que quedar ningún resto que después
    # impida reintentar con la dirección corregida.
    from app.api.verificacion_correo import exigir_verificacion, marcar_usada
    verif, err = exigir_verificacion((data.get("titular") or {}).get("email"), data.get("verificacion_id"))
    if err:
        return err

    # Pedido REPETIDO con una verificación que ya creó esta cuenta (doble
    # clic, o la respuesta se perdió en la red después de guardar): se
    # devuelve lo que ya existe. Ni error ni duplicado.
    if verif is not None and verif.ya_creo_algo():
        # Import con otro nombre a propósito: más abajo en esta misma
        # función hay un "from app.models.usuario import Usuario" local, y
        # eso hace que Python trate "Usuario" como variable local en TODA
        # la función. Usarlo acá, antes de esa línea, revienta con
        # UnboundLocalError (pasó en la prueba de pedido repetido).
        from app.models.usuario import Usuario as _UsuarioYa
        ya = Cuenta.query.get(verif.cuenta_id) if verif.cuenta_id else None
        u_ya = _UsuarioYa.query.get(verif.usuario_id)
        if ya is not None and u_ya is not None:
            return jsonify({"data": {
                "cuenta": ya.to_dict(detalle=True),
                "activacion": {"usuario_email": u_ya.email},
                "repetido": True,
            }}), 200

    # Día 50 — sistema de suscripciones: el límite de CASAS se chequea acá
    # (es específico de esta operación). El límite de USUARIOS ya lo
    # verifica _crear_usuario_pendiente() más abajo, adentro de la función
    # compartida — no hace falta repetirlo acá.
    from app.utils.residencial import limite_casas_alcanzado
    if limite_casas_alcanzado(usuario_actual.residencial_id):
        return _err("limite_casas", "Tu plan actual no permite más casas. "
                    "Pedile a tu proveedor que te suba de plan.", 402)

    # La unidad puede venir ya existente (unidad_id) o crearse sobre la marcha
    # (unidad_nueva: {tipo, identificador}), para no requerir un paso previo.
    unidad = None
    if data.get("unidad_id"):
        unidad = Unidad.query.filter_by(uuid_publico=data.get("unidad_id")).first()
    if not unidad:
        nueva = data.get("unidad_nueva") or {}
        ident = (nueva.get("identificador") or "").strip()
        tipo = nueva.get("tipo") if nueva.get("tipo") in ("casa", "edificio") else "casa"
        if ident:
            # Día 74 — acotado a la residencial: el nombre "Casa 24" puede
            # existir en dos residenciales distintas sin ser la misma casa.
            _q_ex = Unidad.query.filter(db.func.lower(Unidad.identificador) == ident.lower())
            _rid_ex = residencial_id_heredado(usuario_actual)
            if _rid_ex is not None:
                _q_ex = _q_ex.filter(Unidad.residencial_id == _rid_ex)
            existente = _q_ex.first()
            # Día 74 — una casa cuya familia se mudó (sin cuenta activa) se
            # reutiliza: llega otra familia a la misma casa, con su cuenta
            # nueva. La cuenta vieja queda como historial con su deuda.
            casa_vacia = (existente is not None and existente.tipo == "casa" and tipo == "casa"
                          and Cuenta.query.filter_by(unidad_id=existente.id, activa=True).first() is None)
            if casa_vacia:
                unidad = existente
            elif existente:
                # Un EDIFICIO existente se reutiliza (se le suman apartamentos).
                # Una CASA no: dos cuentas en la misma casa sería un duplicado.
                if existente.tipo == "casa" or tipo == "casa":
                    return _err("duplicado",
                                f"Ya existe una unidad llamada \"{existente.identificador}\". "
                                f"Usá otro identificador.", 409)
                unidad = existente
            else:
                max_aptos = nueva.get("max_apartamentos")
                unidad = Unidad(tipo=tipo, identificador=ident, activa=True,
                                max_apartamentos=int(max_aptos) if max_aptos and tipo == "edificio" else None,
                                # Bases multi-residencial (Día 37)
                                residencial_id=residencial_id_heredado(usuario_actual))
                db.session.add(unidad)
                db.session.flush()
    if not unidad:
        return _err("unidad_no_encontrada", "Indicá la casa o edificio a dar de alta", 404)

    es_solo_contenedor = data.get("es_solo_contenedor", False)

    # Día 51 — niveles de plan: una residencial en plan Básico no tiene
    # cuotas en absoluto, así que exigirle una tarifa para dar de alta
    # una casa no tiene sentido — y ahora que listar/crear tarifas está
    # bloqueado para ese tipo de plan, exigirla la dejaría totalmente
    # trabada para crear casas nuevas, rompiendo la función principal
    # que Básico sí debe tener. Se trata igual que una cuenta contenedora
    # (sin tarifa ni día de pago), sin importar si la marcaron como tal.
    from app.utils.residencial import plan_permite
    sin_cuotas = not plan_permite(usuario_actual.residencial_id, "cuotas")

    tarifa = None
    dia_pago = 1
    if es_solo_contenedor or sin_cuotas:
        # El edificio como contenedor no paga cuota — la tarifa es opcional.
        # Mismo criterio para cualquier cuenta de una residencial sin cuotas.
        pass
    else:
        tarifa = Tarifa.query.get(data.get("tarifa_id"))
        # Día 48 — hallazgo de auditoría (menor, pero real): sin este
        # chequeo, se podía crear una cuenta con una tarifa de OTRA
        # residencial (un admin normalmente solo ve las suyas en el
        # desplegable, pero nada lo impedía a nivel de API).
        from app.utils.residencial import pertenece_a_mi_residencial
        if not tarifa or not pertenece_a_mi_residencial(tarifa, usuario_actual):
            return _err("tarifa_invalida", "La tarifa indicada no existe", 400)
        dia_pago = data.get("dia_pago")
        if not isinstance(dia_pago, int) or not (1 <= dia_pago <= 30):
            return _err("dia_pago_invalido", "El día de pago debe estar entre 1 y 30", 400)

    apartamento = data.get("apartamento")
    if unidad.tipo == "edificio" and not apartamento and not es_solo_contenedor:
        return _err("apartamento_requerido",
                    "Para un edificio debes indicar el apartamento (ej. 1A)", 400)
    if unidad.tipo == "casa":
        apartamento = None  # una casa no lleva número de apartamento

    # Validar límite de apartamentos en el edificio (Día 29)
    if unidad.tipo == "edificio" and unidad.max_apartamentos:
        aptos_existentes = Cuenta.query.filter_by(unidad_id=unidad.id, activa=True).filter(
            Cuenta.tipo_cuenta != "edificio_contenedor").count()
        if aptos_existentes >= unidad.max_apartamentos:
            return _err("limite_apartamentos",
                        f"Este edificio ya tiene {aptos_existentes} apartamento(s) "
                        f"registrado(s) de un máximo de {unidad.max_apartamentos}.", 400)

    # evitar duplicado de apartamento en el mismo edificio (solo cuentas activas)
    # Día 70 — sin distinguir mayúsculas: "1a" y "1A" son el mismo
    # apartamento. Antes se podían registrar los dos.
    if apartamento and Cuenta.query.filter(
            Cuenta.unidad_id == unidad.id, Cuenta.activa.is_(True),
            db.func.lower(Cuenta.apartamento) == str(apartamento).lower()).first():
        return _err("duplicado", f"El apartamento {apartamento} ya existe en esta unidad", 409)

    titular_data = data.get("titular") or {}

    # Validar formato del DNI si se proporciona (13 dígitos, formato hondureño)
    dni_raw = (titular_data.get("dni") or "").strip()
    if dni_raw:
        dni_solo_num = dni_raw.replace("-", "").replace(" ", "")
        if not dni_solo_num.isdigit() or len(dni_solo_num) != 13:
            return _err("dni_invalido",
                        "El número de identidad debe tener 13 dígitos (0000-0000-00000)", 400)

    # ── Regla anti-mora: una persona con deuda en otra casa no puede darse de
    # alta en una nueva unidad hasta ponerse al día. Se identifica por DNI.
    dni_titular = (titular_data.get("dni") or "").strip()
    if dni_titular:
        from app.models.usuario import Usuario
        from app.models.cuenta import Residente, Cuota
        dni_norm = dni_titular.replace("-", "").replace(" ", "")
        # Comparación en SQL: se normaliza el DNI almacenado quitando guiones y
        # espacios y se compara contra el normalizado. Usa el índice de dni.
        usuarios_dni = (Usuario.query
                        .filter(db.func.replace(db.func.replace(Usuario.dni, "-", ""), " ", "") == dni_norm)
                        .all())
        for u_prev in usuarios_dni:
            resids = Residente.query.filter_by(usuario_id=u_prev.id, activo=True).all()
            for r_prev in resids:
                cuenta_prev = r_prev.cuenta
                if not cuenta_prev:
                    continue
                # ¿Cuenta bloqueada por mora, o con cuotas vencidas sin pagar?
                # Día 74 — también si tiene un arreglo con abonos vencidos:
                # quien se mudó debiendo abonos sigue debiéndolos.
                from app.models.cuenta import ArregloPago
                arr_prev = ArregloPago.query.filter_by(cuenta_id=cuenta_prev.id, estado="activo").first()
                tiene_mora = (
                    (arr_prev is not None and arr_prev.atrasado())
                    or getattr(cuenta_prev, "bloqueada", False)
                    or cuenta_prev.estado in ("moroso", "en_mora")
                    or Cuota.query.filter(
                        Cuota.cuenta_id == cuenta_prev.id,
                        Cuota.estado.notin_(["pagada", "en_arreglo", "anulada"]),
                        Cuota.fecha_vencimiento < dt.date.today(),
                    ).first() is not None
                )
                if tiene_mora:
                    ident_prev = cuenta_prev.unidad.identificador if cuenta_prev.unidad else "otra unidad"
                    return _err(
                        "titular_moroso",
                        f"Esta persona (DNI {dni_titular}) tiene deudas pendientes en "
                        f"\"{ident_prev}\". Debe ponerse al día antes de registrarse en otra unidad.",
                        409)

    usuario, token_o_error = _crear_usuario_pendiente(
        titular_data.get("nombre"), titular_data.get("apellido"),
        titular_data.get("email"), titular_data.get("telefono"),
        extra=titular_data, usuario_actual=usuario_actual,
    )
    if usuario is None:
        return _err("titular_invalido", token_o_error, 400)

    # crear la cuenta
    tipo_acceso_virtual = data.get("tipo_acceso_virtual", "peatonal")
    if tipo_acceso_virtual not in ("peatonal", "vehicular"):
        tipo_acceso_virtual = "peatonal"
    cuenta = Cuenta(
        unidad_id=unidad.id, apartamento=apartamento if not es_solo_contenedor else None,
        tarifa_id=tarifa.id if tarifa else None, dia_pago=dia_pago,
        tipo_acceso_virtual=tipo_acceso_virtual,
    )
    db.session.add(cuenta)
    db.session.flush()

    # vincular al titular
    residente = Residente(
        usuario_id=usuario.id, cuenta_id=cuenta.id,
        rol_cuenta="titular", relacion=titular_data.get("relacion", "propietario"),
    )
    db.session.add(residente)

    # Si se indica, este titular queda como dueño/responsable del edificio
    if data.get("es_dueno_edificio") and unidad.tipo == "edificio":
        unidad.propietario_id = usuario.id

    # Si el inquilino llegó con un código de enrolamiento, marcarlo como usado
    codigo_enrol = (data.get("codigo_enrolamiento") or "").strip()
    if codigo_enrol:
        cod = CodigoEnrolamiento.query.filter_by(codigo=codigo_enrol, estado="activo").first()
        if cod:
            cod.estado = "usado"
            cod.usado_por_cuenta_id = cuenta.id
            cod.usado_en = dt.datetime.now(dt.timezone.utc)

    # Día 73 — PRIMERA CUOTA PRORRATEADA, ahora DENTRO de la misma
    # transacción. Antes se guardaba la cuenta, y la cuota aparte en un
    # try que tragaba cualquier error: si fallaba, la casa quedaba creada
    # sin su cuota del mes y nadie se enteraba. O se crea todo, o nada.
    # Solo si tiene tarifa (las contenedoras de edificio no pagan).
    if tarifa:
        from app.models.cuenta import Cuota, ConfigResidencial
        from app.utils.cuotas import calcular_cuota_prorrateada
        cfg = ConfigResidencial.get(usuario_actual.residencial_id)
        datos = calcular_cuota_prorrateada(tarifa.monto, cfg.dia_pago)
        if datos is not None:
            db.session.add(Cuota(
                cuenta_id=cuenta.id, periodo=datos["periodo"],
                monto=datos["monto"], fecha_vencimiento=datos["fecha_vencimiento"],
                estado="pendiente", cobra_desde_dia=datos["cobra_desde_dia"],
            ))

    marcar_usada(verif, usuario, cuenta.id)   # misma transacción
    db.session.commit()

    # Día 61 — el correo se manda DESPUÉS del commit, nunca antes.
    # Día 73 — y solo si no salió ya: con la verificación, el correo de
    # activación se mandó ANTES de crear (es lo que se verificó), así que
    # mandar otro le haría llegar dos enlaces a la persona.
    if verif is None:
        try:
            from app.tasks.correo_task import encolar_correo_activacion
            from app.models.residencial import Residencial
            residencial = Residencial.query.get(usuario_actual.residencial_id) if usuario_actual.residencial_id else None
            encolar_correo_activacion(
                usuario.email, usuario.nombre, token_o_error,
                residencial.nombre if residencial else "Residencial")
        except Exception:
            current_app.logger.exception("No se pudo encolar la activación de %s", usuario.email)

    return jsonify({"data": {
        "cuenta": cuenta.to_dict(detalle=True),
        "activacion": _bloque_activacion(usuario, token_o_error,
                                         nota="Enviar al residente para que defina su contraseña"),
    }}), 201


@cuentas_bp.get("/cuentas/<cuenta_uuid>")
@roles_required("admin", "super_admin")
def detalle_cuenta(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    return jsonify({"data": cuenta.to_dict(detalle=True)})


@cuentas_bp.put("/cuentas/<cuenta_uuid>")
@roles_required("admin", "super_admin")
def editar_cuenta(usuario_actual, cuenta_uuid):
    """Edita campos configurables de una cuenta (ej. habilitar QR recurrente).

    Día 51: gana "activa" -- el interruptor MANUAL para que el admin le
    corte el acceso a una casa a mano (deja de poder generar visitas),
    sin depender del sistema de cuotas/mora. Existía en el modelo desde
    hace tiempo pero nunca se conectó a ningún endpoint ni pantalla.
    A propósito NO se gatea con requiere_funcion_plan("cuotas") -- es
    justamente la herramienta que le queda a un admin de plan Básico,
    que no tiene el bloqueo automático.
    """
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    body = request.get_json(silent=True) or {}
    if "qr_recurrente_habilitado" in body:
        cuenta.qr_recurrente_habilitado = bool(body["qr_recurrente_habilitado"])
    if "tipo_acceso_virtual" in body:
        # Día 53 — Sprint 2: este campo es sobre qué trancas puede abrir la
        # tarjeta digital -- control físico puro, no cuotas. Chequeo
        # selectivo (no se puede gatear todo el endpoint, "activa" debe
        # seguir funcionando siempre, sin importar el plan).
        from app.utils.residencial import plan_permite
        if not plan_permite(usuario_actual.residencial_id, "control_fisico"):
            return _err("funcion_no_incluida",
                        "Tu plan actual no incluye control de accesos físico — "
                        "hablá con tu proveedor para subir de plan.", 402)
        valor = body["tipo_acceso_virtual"]
        if valor in ("peatonal", "vehicular"):
            cuenta.tipo_acceso_virtual = valor
    if "dia_pago" in body:
        dp = int(body["dia_pago"])
        if 1 <= dp <= 30:
            cuenta.dia_pago = dp
    # Día 55 — edición de la info de una casa ya creada. Los tres campos
    # nuevos (tarifa, días de gracia, identificador) son de cuotas, así que
    # se gatean con el mismo criterio: sin plan de cuotas no se tocan. Se
    # chequea una sola vez, solo si el body trae alguno de ellos.
    if any(k in body for k in ("tarifa_id", "dias_gracia", "identificador")):
        from app.utils.residencial import plan_permite
        if not plan_permite(usuario_actual.residencial_id, "cuotas"):
            return _err("funcion_no_incluida",
                        "Tu plan actual no incluye cuotas de residentes — "
                        "hablá con tu proveedor para subir de plan.", 402)

        if "tarifa_id" in body:
            # Cambiar la tarifa solo afecta las cuotas FUTURAS -- las ya
            # generadas conservan el monto con el que nacieron (decisión
            # de negocio confirmada con el usuario). Se valida que la
            # tarifa exista y sea de ESTA residencial.
            tid = body["tarifa_id"]
            if tid in (None, "", 0):
                cuenta.tarifa_id = None
            else:
                tarifa = Tarifa.query.filter_by(
                    id=int(tid), residencial_id=usuario_actual.residencial_id).first()
                if not tarifa:
                    return _err("tarifa_invalida", "La tarifa seleccionada no existe.", 400)
                cuenta.tarifa_id = tarifa.id

        if "dias_gracia" in body:
            dg = body["dias_gracia"]
            if dg in (None, ""):
                cuenta.dias_gracia = None   # vuelve a usar el global
            else:
                dg = int(dg)
                if 0 <= dg <= 30:
                    cuenta.dias_gracia = dg

        if "identificador" in body:
            nuevo_id = (body["identificador"] or "").strip()
            if nuevo_id and cuenta.unidad:
                # Misma validación de unicidad POR residencial del Día 52
                # (crear_unidad): el identificador es único dentro de la
                # residencial, no global en todo el sistema.
                choque = Unidad.query.filter(
                    Unidad.identificador == nuevo_id,
                    Unidad.residencial_id == cuenta.unidad.residencial_id,
                    Unidad.id != cuenta.unidad_id,
                ).first()
                if choque:
                    return _err("duplicado", f"Ya existe la unidad '{nuevo_id}' en esta residencial", 409)
                cuenta.unidad.identificador = nuevo_id

    if "activa" in body:
        cuenta.activa = bool(body["activa"])
    db.session.commit()
    return jsonify({"data": cuenta.to_dict()})


@cuentas_bp.put("/unidades/<unidad_uuid>")
@roles_required("admin", "super_admin")
def editar_unidad(usuario_actual, unidad_uuid):
    """Edita campos configurables de una unidad (ej. cuántos apartamentos
    puede tener un edificio, o el límite de residentes extra)."""
    unidad = Unidad.query.filter_by(uuid_publico=unidad_uuid).first()
    if not unidad:
        return _err("no_encontrada", "Unidad no encontrada", 404)
    body = request.get_json(silent=True) or {}
    if "max_apartamentos" in body:
        val = body["max_apartamentos"]
        unidad.max_apartamentos = int(val) if val not in (None, "") else None
    if "max_residentes_extra" in body:
        val = body["max_residentes_extra"]
        unidad.max_residentes_extra = int(val) if val not in (None, "") else None
    db.session.commit()
    return jsonify({"data": unidad.to_dict()})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/baja")
@roles_required("admin", "super_admin")
def dar_baja_cuenta(usuario_actual, cuenta_uuid):
    """
    Da de baja una cuenta: la familia se muda. Desactiva usuarios, tarjetas,
    credenciales y QR de visita. La cuenta NO se borra: queda como historial.

    Día 74 — antes exigía saldo en 0, sin excepción. Pero una familia que se
    va debiendo se va igual: con la regla vieja la casa quedaba "activa" y
    generando cuotas que nadie iba a pagar. Ahora se puede dar de baja con
    deuda si el administrador lo confirma (confirmar_deuda: true): la deuda
    queda a nombre del titular, y la regla anti-mora por DNI le impide
    darse de alta en otra casa hasta que la pague.

    Body: { motivo?, confirmar_deuda? }
    """
    from app.utils.residencial import pertenece_a_mi_residencial
    from app.services.ciclo_casa import estado_deuda, dar_de_baja

    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    # Día 74 — también se cierra un hueco: antes no se comprobaba que la
    # cuenta fuera de la residencial de quien la da de baja.
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    if not cuenta.activa:
        return _err("ya_de_baja", "Esta cuenta ya está dada de baja.", 400)

    data = request.get_json(silent=True) or {}
    from app.services.ciclo_casa import nivelar_cuotas, cuotas_fuera_de_arreglo, contar_accesos

    # Día 75 — si viene fecha_salida, la cuota del mes se nivela EN LA MISMA
    # transacción que la baja. Antes eran dos pasos (Nivelar saldo, y
    # después Dar de baja): si el admin nivelaba y no terminaba, la casa
    # quedaba en el sistema con el mes cobrado a medias.
    ajustes = []
    fecha_salida = None
    if data.get("fecha_salida"):
        try:
            fecha_salida = dt.date.fromisoformat(data["fecha_salida"])
        except ValueError:
            return _err("fecha_invalida", "Formato de fecha inválido (YYYY-MM-DD).", 400)
        if fecha_salida > dt.date.today():
            return _err("fecha_invalida", "La fecha de salida no puede ser futura.", 400)
        ajustes = nivelar_cuotas(cuotas_fuera_de_arreglo(cuenta), fecha_salida)
        db.session.flush()

    deuda = estado_deuda(cuenta)
    if data.get("simular"):
        afectados = contar_accesos(cuenta)
        db.session.rollback()
        return jsonify({"data": {"simulado": True, "ajustes": ajustes,
                                 "deuda": deuda, "afectados": afectados}})

    # Día 76 — con un comprobante sin revisar la casa parecía «sin deuda» y
    # se daba de baja. No se puede confirmar «igual»: primero se revisa.
    from app.services.ciclo_casa import impedimento_en_revision
    imp = impedimento_en_revision(cuenta, "darla de baja")
    if imp is not None:
        db.session.rollback()
        return _err(*imp)

    if deuda["total"] > 0 and not data.get("confirmar_deuda"):
        db.session.rollback()
        return _err("saldo_pendiente",
                    f"La casa debe L {deuda['total']:,.2f}. Si se muda igual, la deuda queda "
                    "a nombre del titular y no va a poder darse de alta en otra casa hasta "
                    "pagarla.", 400)

    tarjetas_desactivadas = dar_de_baja(cuenta, data.get("motivo") or "Mudanza", fecha_salida)
    db.session.commit()
    d = cuenta.to_dict()
    d["tarjetas_desactivadas"] = tarjetas_desactivadas
    d["deuda_pendiente"] = deuda["total"]
    d["ajustes"] = ajustes
    return jsonify({"data": d})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/volver-al-padron")
@roles_required("admin", "super_admin")
def volver_al_padron(usuario_actual, cuenta_uuid):
    """
    Día 74 — la casa deja de pagar mensualidad y vuelve al padrón. Sigue
    viviendo ahí: el guardia la sigue identificando, pero sin app.

    Body: { fecha?: "YYYY-MM-DD" (hoy por defecto), simular?: bool }

    Con simular: true hace todo el cálculo (nivelación incluida) y lo
    deshace, para que el panel le muestre al administrador qué va a pasar
    antes de confirmar. Las reglas están en services/ciclo_casa.py.
    """
    from app.utils.residencial import pertenece_a_mi_residencial
    from app.services import ciclo_casa

    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    data = request.get_json(silent=True) or {}
    try:
        fecha = dt.date.fromisoformat(data["fecha"]) if data.get("fecha") else dt.date.today()
    except ValueError:
        return _err("fecha_invalida", "Formato de fecha inválido (YYYY-MM-DD).", 400)

    resumen, err = ciclo_casa.volver_al_padron(cuenta, fecha, usuario_actual)

    if data.get("simular"):
        db.session.rollback()
        # Día 75 — al simular, un "todavía no se puede" con números (debe X,
        # tiene que cobrar Y) no es un error: es lo que el panel tiene que
        # explicar. Se devuelve 200 con puede=false y el impedimento.
        if resumen is not None:
            return jsonify({"data": {
                "simulado": True, "puede": err is None,
                "impedimento": {"code": err[0], "message": err[1]} if err else None,
                **resumen}})
    if err:
        db.session.rollback()
        code, msg, status = err
        return _err(code, msg, status)

    db.session.commit()
    return jsonify({"data": {"simulado": False, "casa": cuenta.to_dict(), **resumen}})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/nivelar-saldo")
@roles_required("admin", "super_admin")
def nivelar_saldo(usuario_actual, cuenta_uuid):
    """Prorratea la última cuota pendiente según la fecha de desocupación.
    Ej: cuota completa generada el 1 (30 días comerciales), se va el 15
    → la cuota se recalcula para cobrar solo 15 días. Si la fecha de
    desocupación es anterior al inicio del período, la cuota se anula."""
    data = request.get_json(silent=True) or {}
    fecha_str = data.get("fecha_desocupacion")
    if not fecha_str:
        return _err("fecha_requerida", "Indicá la fecha de desocupación.", 400)
    try:
        fecha_des = dt.date.fromisoformat(fecha_str)
    except ValueError:
        return _err("fecha_invalida", "Formato de fecha inválido (YYYY-MM-DD).", 400)

    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Buscar cuotas pendientes/parciales ordenadas por período
    cuotas = (Cuota.query.filter(
        Cuota.cuenta_id == cuenta.id,
        Cuota.estado.in_(["pendiente", "parcial", "vencida"]))
        .order_by(Cuota.periodo.asc()).all())

    if not cuotas:
        return _err("sin_cuotas", "No hay cuotas pendientes que nivelar. El saldo ya está en 0.", 400)

    from app.models.cuenta import ConfigResidencial
    cfg = ConfigResidencial.get(usuario_actual.residencial_id)
    dia_pago_cfg = cfg.dia_pago

    from app.services.ciclo_casa import nivelar_cuotas
    ajustes = nivelar_cuotas(cuotas, fecha_des)

    db.session.commit()
    return jsonify({"data": {
        "message": f"Saldo nivelado al {fecha_des.isoformat()}",
        "ajustes": ajustes,
    }})


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


@cuentas_bp.post("/cuentas/<cuenta_uuid>/pausar-acceso")
@roles_required("admin", "super_admin")
def pausar_acceso_cuenta(usuario_actual, cuenta_uuid):
    """Día 53 — Sprint 1: pausa liviana y reversible del acceso de una casa,
    SIN las exigencias de dar_baja_cuenta (saldo en 0, tarjetas, usuarios
    uno por uno). Pensada sobre todo para residenciales sin cuotas
    (Básico), donde 'dar de baja' formal no tiene mucho sentido —
    ver crear_visita() en visitas.py para el bloqueo real."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    cuenta.acceso_pausado = True
    db.session.commit()
    return jsonify({"data": cuenta.to_dict()})


@cuentas_bp.post("/cuentas/<cuenta_uuid>/reanudar-acceso")
@roles_required("admin", "super_admin")
def reanudar_acceso_cuenta(usuario_actual, cuenta_uuid):
    """Contraparte de pausar_acceso_cuenta — solo revierte el mismo flag."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    cuenta.acceso_pausado = False
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

    # Día 73 — no se crea nada hasta que Resend confirme que el correo LLEGÓ
    # (ver api/verificacion_correo.py).
    #
    # Va ANTES del límite de miembros a propósito: en un pedido repetido el
    # miembro recién creado ya cuenta para el límite, y el reintento
    # fallaría con "ya tiene el máximo" en vez de devolver lo que se creó.
    from app.api.verificacion_correo import exigir_verificacion, marcar_usada
    verif, err = exigir_verificacion(data.get("email"), data.get("verificacion_id"))
    if err:
        return err
    if verif is not None and verif.ya_creo_algo():
        r_ya = Residente.query.filter_by(cuenta_id=cuenta.id,
                                         usuario_id=verif.usuario_id).first()
        if r_ya is not None:
            return jsonify({"data": {
                "residente": r_ya.to_dict(),
                "activacion": {"usuario_email": r_ya.usuario.email if r_ya.usuario else None},
                "repetido": True,
            }}), 200
        return _err("correo_no_verificado",
                    "Esa verificación ya se usó para otra casa.", 400)

    # Validar límite de residentes adicionales (Día 29)
    # Default: casa → 4 extra, apartamento → 1 extra
    unidad = cuenta.unidad
    extra_actuales = len([r for r in cuenta.residentes if r.activo]) - 1  # sin contar titular
    if unidad:
        max_extra = unidad.max_residentes_extra
        if max_extra is None:
            max_extra = 4 if unidad.tipo == "casa" else 1
        if extra_actuales >= max_extra:
            return _err("limite_residentes",
                        f"Esta {unidad.tipo} ya tiene el máximo de {max_extra} "
                        f"persona(s) adicional(es) al titular.", 400)

    usuario, token_o_error = _crear_usuario_pendiente(
        data.get("nombre"), data.get("apellido"),
        data.get("email"), data.get("telefono"),
        extra=data, usuario_actual=usuario_actual,
    )
    if usuario is None:
        return _err("miembro_invalido", token_o_error, 400)

    residente = Residente(
        usuario_id=usuario.id, cuenta_id=cuenta.id,
        rol_cuenta="miembro", relacion=data.get("relacion", "familiar"),
    )
    db.session.add(residente)
    marcar_usada(verif, usuario, cuenta.id)   # misma transacción
    db.session.commit()

    # Día 61 — después del commit. Día 73 — y solo si el correo no salió ya
    # con la verificación (si no, le llegarían dos enlaces).
    if verif is None:
        try:
            from app.tasks.correo_task import encolar_correo_activacion
            from app.models.residencial import Residencial
            residencial = Residencial.query.get(usuario_actual.residencial_id) if usuario_actual.residencial_id else None
            encolar_correo_activacion(
                usuario.email, usuario.nombre, token_o_error,
                residencial.nombre if residencial else "Residencial")
        except Exception:
            current_app.logger.exception("No se pudo encolar la activación de %s", usuario.email)

    return jsonify({"data": {
        "residente": residente.to_dict(),
        "activacion": _bloque_activacion(usuario, token_o_error),
    }}), 201


def _carpeta_fotos_residentes():
    carpeta = os.path.join(current_app.config.get("UPLOAD_FOLDER", "/app/uploads"),
                           "residentes")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


@cuentas_bp.post("/cuentas/<cuenta_uuid>/residentes/<residente_uuid>/foto")
@roles_required("admin", "super_admin")
def subir_foto_residente(usuario_actual, cuenta_uuid, residente_uuid):
    """
    Día 69 — foto del miembro, pedida por el patronato (Día 68).

    SOLO administración la sube. El residente NUNCA puede cambiar su propia
    foto: es la que el guardia usa para verificar identidad cuando alguien
    llega sin teléfono y pide acceso con su código de emergencia. Si el
    propio residente pudiera reemplazarla, bastaría con poner la cara de
    otra persona para que el guardia le abriera a quien no corresponde —
    toda la verificación dejaría de servir.

    Sirve para cualquier miembro, del padrón o con cuenta completa: la foto
    vive en Usuario, que es donde vive la persona.

    Reemplazable: sube una foto nueva y la anterior se borra. La gente
    cambia, y una foto vieja que ya no se parece es peor que no tenerla.
    """
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    residente = Residente.query.filter_by(uuid_publico=residente_uuid,
                                          cuenta_id=cuenta.id).first()
    if not residente:
        return _err("no_encontrado", "Residente no encontrado en esta cuenta", 404)

    persona = residente.usuario
    if not persona:
        return _err("sin_usuario", "Este residente no tiene ficha de persona", 400)

    if "foto" not in request.files or not request.files["foto"].filename:
        return _err("sin_archivo", "Adjuntá una foto", 400)

    nombre_archivo, error, _tam = guardar_imagen_segura(
        request.files["foto"], _carpeta_fotos_residentes(), EXT_IMAGEN
    )
    if error:
        return _err("imagen_invalida", error, 400)

    anterior = persona.foto_url
    persona.foto_url = nombre_archivo
    db.session.commit()

    # Recién después del commit: si se borrara antes y el commit fallara,
    # la persona quedaría apuntando a un archivo que ya no existe.
    if anterior and anterior != nombre_archivo:
        try:
            os.remove(os.path.join(_carpeta_fotos_residentes(), anterior))
        except OSError:
            pass

    return jsonify({"data": residente.to_dict()})


@cuentas_bp.get("/residentes/foto/<path:nombre_archivo>")
@token_required
def ver_foto_residente(usuario_actual, nombre_archivo):
    """
    Sirve la foto de un residente, siempre autenticado.

    Nunca queda pública en el bucket: mismo modelo de acceso privado que se
    aplicó a las fotos de evidencia en FILES-05 (Día 37). Una foto de la
    cara de un residente es un dato personal, no una imagen de catálogo.

    Se usa <path:...> y no <string> porque en modo nube la clave guardada
    incluye el prefijo de subcarpeta y lleva una barra — el mismo bug real
    que tuvo el logo de la residencial el Día 59.
    """
    existe = Usuario.query.filter_by(foto_url=nombre_archivo).first()
    if not existe:
        return _err("no_encontrada", "Foto no encontrada", 404)

    # Un residente solo puede ver SU propia foto. El personal administrativo
    # y los guardias ven las de su residencial: el guardia la necesita para
    # verificar identidad en el portón.
    if usuario_actual.rol == "residente" and existe.id != usuario_actual.id:
        return _err("sin_permiso", "No podés ver la foto de otra persona", 403)
    if usuario_actual.rol not in ("super_admin", "desarrollador"):
        if (usuario_actual.residencial_id and existe.residencial_id
                and usuario_actual.residencial_id != existe.residencial_id):
            return _err("sin_permiso", "Esa persona no pertenece a tu residencial", 403)

    from app.services import storage
    clave = (nombre_archivo if nombre_archivo.startswith("residentes/")
             else f"residentes/{nombre_archivo}")
    return storage.servir_archivo(clave)


@cuentas_bp.delete("/cuentas/<cuenta_uuid>/residentes/<residente_uuid>")
@roles_required("admin", "super_admin")
def quitar_miembro(usuario_actual, cuenta_uuid, residente_uuid):
    """Elimina un miembro (no titular) de la cuenta.
    Borra el registro Residente y el Usuario asociado si no tiene otros vínculos."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    residente = Residente.query.filter_by(
        uuid_publico=residente_uuid, cuenta_id=cuenta.id
    ).first()
    if not residente:
        return _err("no_encontrado", "Residente no encontrado", 404)

    if residente.rol_cuenta == "titular":
        return _err("es_titular",
                     "No se puede quitar al titular. Para eso, dá de baja la cuenta completa.", 400)

    usuario = residente.usuario

    # Quitar tarjetas asignadas a este residente
    Tarjeta.query.filter_by(residente_id=residente.id).update(
        {"residente_id": None, "estado": "desasignada"})

    db.session.delete(residente)

    # Si el usuario no tiene más vínculos en otras cuentas, borrarlo
    otros = Residente.query.filter(
        Residente.usuario_id == usuario.id,
        Residente.id != residente.id,
    ).count()
    if otros == 0:
        db.session.delete(usuario)

    db.session.commit()
    return jsonify({"data": {"ok": True, "message": "Miembro eliminado"}}), 200


@cuentas_bp.post("/cuentas/<cuenta_uuid>/residentes/<residente_uuid>/regenerar-enlace")
@roles_required("admin", "super_admin")
def regenerar_enlace(usuario_actual, cuenta_uuid, residente_uuid):
    """Genera un nuevo token de activación (48h) para un residente que no ha activado."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    residente = Residente.query.filter_by(
        uuid_publico=residente_uuid, cuenta_id=cuenta.id
    ).first()
    if not residente:
        return _err("no_encontrado", "Residente no encontrado", 404)

    usuario = residente.usuario
    if usuario.activo and usuario.password_hash:
        return _err("ya_activo", "Este residente ya activó su cuenta. No necesita un nuevo enlace.", 400)

    token_activacion = jwt.encode(
        {"sub": usuario.email, "proposito": "activacion",
         "exp": dt.datetime.utcnow() + dt.timedelta(hours=48)},
        current_app.config["JWT_SECRET"], algorithm="HS256"
    )

    # Día 61 — no hay ninguna escritura pendiente en esta función (no
    # se hace db.session.add/commit acá), así que el correo puede
    # dispararse ya mismo, sin esperar nada.
    # Día 72 — el correo del residente ahora se puede corregir desde el
    # panel, así que este reenvío sale al correo que tenga AHORA. Se borra
    # el estado anterior (por ejemplo "rebotado" del correo mal escrito)
    # para que el panel no siga mostrando una advertencia ya resuelta.
    usuario.correo_estado = None
    usuario.correo_detalle = None
    usuario.correo_resend_id = None
    db.session.commit()

    try:
        from app.tasks.correo_task import encolar_correo_activacion
        from app.models.residencial import Residencial
        residencial = Residencial.query.get(usuario_actual.residencial_id) if usuario_actual.residencial_id else None
        encolar_correo_activacion(
            usuario.email, usuario.nombre, token_activacion,
            residencial.nombre if residencial else "Residencial", es_reenvio=True)
    except Exception:
        pass

    return jsonify({"data": {
        "activacion": _bloque_activacion(usuario, token_activacion,
                                         nota="Nuevo enlace generado (48h de validez)"),
    }}), 200


# =====================================================================
# TARJETAS
# =====================================================================
@cuentas_bp.post("/cuentas/<cuenta_uuid>/tarjetas")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
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

    tipo_acceso = (data.get("tipo_acceso") or "vehicular").strip()
    if tipo_acceso not in ("vehicular", "peatonal"):
        tipo_acceso = "vehicular"

    tarjeta = Tarjeta(
        card_uid=card_uid, cuenta_id=cuenta.id,
        residente_id=residente.id if residente else None,
        etiqueta=data.get("etiqueta"),
        tipo_acceso=tipo_acceso,
    )
    db.session.add(tarjeta)
    db.session.commit()
    return jsonify({"data": tarjeta.to_dict()}), 201


# =====================================================================
# TARIFAS (catálogo para el formulario)
# =====================================================================
@cuentas_bp.get("/tarifas")
@token_required
@requiere_funcion_plan("cuotas")
def listar_tarifas(usuario_actual):
    from app.utils.residencial import scope_directo
    tarifas = scope_directo(Tarifa.query, Tarifa, usuario_actual).filter_by(activa=True).all()
    return jsonify({"data": [t.to_dict() for t in tarifas]})


@cuentas_bp.post("/tarifas")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
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
    from app.utils.residencial import residencial_id_heredado
    tarifa = Tarifa(nombre=nombre, monto=monto,
                    descripcion=(data.get("descripcion") or "").strip() or None, activa=True,
                    residencial_id=residencial_id_heredado(usuario_actual))
    db.session.add(tarifa)
    db.session.commit()
    return jsonify({"data": tarifa.to_dict()}), 201


@cuentas_bp.put("/tarifas/<int:tarifa_id>")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
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
@requiere_funcion_plan("cuotas")
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


# =====================================================================
# ENROLAMIENTO DE INQUILINOS POR CÓDIGO (dueño de edificio)
# =====================================================================

def _edificios_de_propietario(usuario):
    """Edificios donde el usuario es el propietario/dueño registrado."""
    return Unidad.query.filter_by(tipo="edificio", propietario_id=usuario.id, activa=True).all()


@cuentas_bp.get("/mis-edificios/<edificio_uuid>/apartamentos")
@token_required
def apartamentos_del_edificio(usuario_actual, edificio_uuid):
    """Lista los apartamentos registrados bajo un edificio del que el usuario
    es propietario. Para que el dueño vea el estado de sus inquilinos desde
    la app móvil."""
    from app.models.cuenta import Unidad, Cuenta
    unidad = Unidad.query.filter_by(uuid_publico=edificio_uuid, tipo="edificio").first()
    if not unidad:
        return _err("no_encontrada", "Edificio no encontrado", 404)
    # Solo el propietario del edificio o un admin pueden ver esto
    if (unidad.propietario_id != usuario_actual.id
            and usuario_actual.rol not in ("admin", "super_admin")):
        return _err("sin_permiso", "No tenés permiso para ver este edificio", 403)

    cuentas = Cuenta.query.filter_by(unidad_id=unidad.id, activa=True).all()
    # Excluir la cuenta del contenedor (admin que no vive ahí) — no es un apto real
    cuentas = [c for c in cuentas if c.tipo_cuenta != "edificio_contenedor"]
    return jsonify({"data": [c.to_dict() for c in cuentas]})


@cuentas_bp.get("/mis-edificios")
@token_required
def mis_edificios(usuario_actual):
    """Edificios de los que el usuario actual es dueño (para su portal)."""
    edificios = _edificios_de_propietario(usuario_actual)
    return jsonify({"data": [u.to_dict() for u in edificios]})


@cuentas_bp.post("/enrolamiento/generar")
@token_required
def generar_codigo_enrolamiento(usuario_actual):
    """El dueño de un edificio genera un código numérico de un solo uso
    para que su inquilino se enrole en la oficina de administración."""
    data = request.get_json(silent=True) or {}
    edificio_uuid = data.get("edificio_id")
    apartamento = (data.get("apartamento") or "").strip()
    nota = (data.get("nota") or "").strip()

    if not apartamento:
        return _err("apartamento_requerido", "El número de apartamento es obligatorio.", 400)
    if not nota:
        return _err("nota_requerida", "El nombre del inquilino es obligatorio.", 400)

    edificio = Unidad.query.filter_by(uuid_publico=edificio_uuid, tipo="edificio").first()
    if not edificio:
        return _err("edificio_invalido", "Edificio no encontrado", 404)
    # Solo el dueño del edificio (o un admin) puede generar códigos
    if edificio.propietario_id != usuario_actual.id and usuario_actual.rol not in ("admin", "super_admin"):
        return _err("sin_permiso", "No sos el dueño de este edificio", 403)

    # Validar límite de apartamentos
    if edificio.max_apartamentos:
        aptos_existentes = Cuenta.query.filter_by(unidad_id=edificio.id, activa=True).filter(
            Cuenta.tipo_cuenta != "edificio_contenedor").count()
        # También contar códigos activos pendientes de usar
        codigos_activos = CodigoEnrolamiento.query.filter_by(
            unidad_id=edificio.id, estado="activo").count()
        ocupados = aptos_existentes + codigos_activos
        if ocupados >= edificio.max_apartamentos:
            return _err("limite_apartamentos",
                        f"Este edificio ya tiene {aptos_existentes} apartamento(s) registrado(s) "
                        f"y {codigos_activos} código(s) pendiente(s), de un máximo de "
                        f"{edificio.max_apartamentos}. Solicitá a la administración dar de baja "
                        f"una cuenta antes de generar un nuevo código.", 400)

    # Generar código numérico único de 6 dígitos.
    # O4.1 (Auditoría Día 42): se usa secrets (criptográficamente seguro) en
    # vez de random (predecible). Era el único uso de random inseguro en todo
    # el backend. Aunque validar el código requiere rol admin (lo que ya
    # mitigaba el riesgo), se empareja con el estándar del resto del proyecto
    # por defensa en profundidad.
    for _ in range(20):
        codigo = f"{secrets.randbelow(1000000):06d}"
        if not CodigoEnrolamiento.query.filter_by(codigo=codigo).first():
            break
    else:
        return _err("error_codigo", "No se pudo generar un código único, intentá de nuevo", 500)

    cod = CodigoEnrolamiento(
        codigo=codigo, unidad_id=edificio.id, generado_por=usuario_actual.id,
        apartamento_sugerido=apartamento,
        nota=nota,
        estado="activo",
    )
    db.session.add(cod)
    db.session.commit()
    return jsonify({"data": cod.to_dict()}), 201


@cuentas_bp.get("/enrolamiento/mis-codigos")
@token_required
def mis_codigos_enrolamiento(usuario_actual):
    """Lista los códigos que el dueño generó, con su estado."""
    codigos = (CodigoEnrolamiento.query
               .filter_by(generado_por=usuario_actual.id)
               .order_by(CodigoEnrolamiento.created_at.desc()).all())
    return jsonify({"data": [c.to_dict() for c in codigos]})


@cuentas_bp.delete("/enrolamiento/<uuid_codigo>")
@token_required
def borrar_codigo_enrolamiento(usuario_actual, uuid_codigo):
    """El dueño borra un código que aún no se ha usado."""
    cod = CodigoEnrolamiento.query.filter_by(uuid_publico=uuid_codigo).first()
    if not cod:
        return _err("no_encontrado", "Código no encontrado", 404)
    if cod.generado_por != usuario_actual.id and usuario_actual.rol not in ("admin", "super_admin"):
        return _err("sin_permiso", "No podés borrar este código", 403)
    if cod.estado == "usado":
        return _err("ya_usado", "Este código ya fue usado, no se puede borrar", 400)
    db.session.delete(cod)
    db.session.commit()
    return jsonify({"data": {"message": "Código eliminado"}})


@cuentas_bp.get("/enrolamiento/validar/<codigo>")
@roles_required("admin", "super_admin")
def validar_codigo_enrolamiento(usuario_actual, codigo):
    """La administración valida un código que el inquilino trae a la oficina.
    Devuelve el edificio al que pertenece para precargar el alta."""
    cod = CodigoEnrolamiento.query.filter_by(codigo=codigo.strip()).first()
    if not cod:
        return _err("codigo_invalido", "Código no encontrado", 404)
    if cod.estado == "usado":
        return _err("codigo_usado", "Este código ya fue utilizado", 400)
    edificio = cod.unidad
    dueno = cod.generador
    return jsonify({"data": {
        "codigo_id": str(cod.uuid_publico),
        "edificio_id": str(edificio.uuid_publico) if edificio else None,
        "edificio_nombre": edificio.identificador if edificio else None,
        "apartamento_sugerido": cod.apartamento_sugerido,
        "nota": cod.nota,
        "dueno_nombre": f"{dueno.nombre} {dueno.apellido}" if dueno else None,
    }})


# =====================================================================
# CONFIGURACIÓN GLOBAL DE LA RESIDENCIAL (Día 29)
# =====================================================================

@cuentas_bp.get("/estado-config-cuotas")
@roles_required("admin", "super_admin")
def estado_config_cuotas(usuario_actual):
    """
    Día 55 — Sprint 2a. El frontend del admin consulta esto al entrar para
    saber si debe mostrar el wizard obligatorio de configuración de cuotas.
    Devuelve la marca cuotas_config_pendiente, más datos que el wizard
    necesita para armar sus pasos: cuántas casas hay sin tarifa, y si ya
    existe alguna tarifa creada (para saber si el paso de crear tarifa es
    obligatorio o solo opcional).
    """
    from app.models.residencial import Residencial
    from app.models.cuenta import Cuenta, Unidad, Tarifa

    residencial = Residencial.query.get(usuario_actual.residencial_id)
    pendiente = bool(residencial and residencial.cuotas_config_pendiente)

    # Casas activas de esta residencial que todavía no tienen tarifa (las
    # que el wizard deberá listar en su paso 3). Hay que excluir el
    # contenedor de edificio, que no paga cuota -- pero tipo_cuenta es una
    # @property calculada, no filtrable en SQL. Un contenedor se
    # caracteriza por unidad tipo 'edificio' + sin apartamento + sin
    # tarifa; como acá ya filtramos por tarifa NULL, basta con excluir las
    # cuentas que son la raíz de un edificio (tipo edificio y sin
    # apartamento propio) para no contar los contenedores.
    casas_sin_tarifa = (Cuenta.query.join(Unidad, Cuenta.unidad_id == Unidad.id)
                        .filter(Unidad.residencial_id == usuario_actual.residencial_id,
                                Cuenta.activa == True,  # noqa: E712
                                Cuenta.tarifa_id.is_(None),
                                db.not_(db.and_(Unidad.tipo == "edificio",
                                                Cuenta.apartamento.is_(None))))
                        .count())
    hay_tarifas = (Tarifa.query.filter_by(
        residencial_id=usuario_actual.residencial_id, activa=True).count() > 0)

    return jsonify({"data": {
        "config_pendiente": pendiente,
        "casas_sin_tarifa": casas_sin_tarifa,
        "hay_tarifas": hay_tarifas,
    }})


@cuentas_bp.post("/activar-cuotas")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def activar_cuotas(usuario_actual):
    """
    Día 55 — Sprint 2b. Paso final del wizard de activación de cuotas al
    subir de plan. Genera la primera cuota PRORRATEADA (Opción A) para cada
    casa activa con tarifa de la residencial, y apaga la marca
    cuotas_config_pendiente.

    Regla de negocio (confirmada con el usuario): la responsabilidad del
    sistema arranca el día del cambio -- cada casa empieza limpia, no se
    mira ningún historial previo. El cliente es responsable de que sus
    residentes tengan deuda cero antes de entrar.

    Idempotente por (cuenta, período): si una casa ya tiene cuota de este
    período (por el índice único cuenta_id+periodo), se la saltea sin
    romper -- así reintentar el wizard no duplica cuotas.
    """
    from app.models.cuenta import Cuenta, Unidad, Cuota, ConfigResidencial
    from app.models.residencial import Residencial
    from app.utils.cuotas import calcular_cuota_prorrateada

    residencial = Residencial.query.get(usuario_actual.residencial_id)
    if not residencial:
        return _err("sin_residencial", "No se encontró la residencial.", 400)

    cfg = ConfigResidencial.get(usuario_actual.residencial_id)
    hoy = dt.date.today()
    periodo_actual = dt.date(hoy.year, hoy.month, 1)

    # Casas activas con tarifa (las que pagan). El contenedor de edificio no
    # tiene tarifa, así que queda naturalmente afuera de este filtro.
    casas = (Cuenta.query.join(Unidad, Cuenta.unidad_id == Unidad.id)
             .filter(Unidad.residencial_id == usuario_actual.residencial_id,
                     Cuenta.activa == True,  # noqa: E712
                     Cuenta.tarifa_id.isnot(None))
             .all())

    # Períodos ya existentes, para no duplicar si se reintenta el wizard.
    ya_tienen = {row[0] for row in db.session.query(Cuota.cuenta_id)
                 .filter(Cuota.periodo == periodo_actual,
                         Cuota.cuenta_id.in_([c.id for c in casas] or [0])).all()}

    generadas = 0
    sin_prorrateo = 0
    for casa in casas:
        if casa.id in ya_tienen:
            continue
        if not casa.tarifa:
            continue
        # Día de pago: el de la casa si tiene override, si no el global de
        # la residencial. (Día 62: ya no se calcula la gracia acá -- dejó
        # de hacer falta cuando el vencimiento pasó a ser solo el día de
        # pago, sin sumarle la gracia.)
        dia_pago = casa.dia_pago or cfg.dia_pago

        datos = calcular_cuota_prorrateada(casa.tarifa.monto, dia_pago, hoy=hoy)
        if datos is None:
            # Hoy pasó el día 30 (mes comercial) -> no queda fracción; el
            # cron mensual generará la cuota completa cuando corresponda.
            sin_prorrateo += 1
            continue

        cuota = Cuota(
            cuenta_id=casa.id, periodo=datos["periodo"], monto=datos["monto"],
            fecha_vencimiento=datos["fecha_vencimiento"], estado="pendiente",
            cobra_desde_dia=datos["cobra_desde_dia"],
        )
        db.session.add(cuota)
        generadas += 1

    # Wizard completado -> apagar la marca.
    residencial.cuotas_config_pendiente = False
    db.session.commit()

    return jsonify({"data": {
        "cuotas_generadas": generadas,
        "casas_sin_prorrateo": sin_prorrateo,
        "total_casas_con_tarifa": len(casas),
    }})


@cuentas_bp.get("/config-residencial")
@roles_required("admin", "super_admin", "desarrollador")
@requiere_funcion_plan("cuotas")
def leer_config_residencial(usuario_actual):
    from app.models.cuenta import ConfigResidencial
    cfg = ConfigResidencial.get(usuario_actual.residencial_id)
    return jsonify({"data": cfg.to_dict()})


@cuentas_bp.put("/config-residencial")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def editar_config_residencial(usuario_actual):
    """Edita día de pago y/o días de gracia. Al cambiar el día de pago,
    se aplica a TODAS las cuentas activas de ESTA residencial automáticamente.

    Día 54 — bug real encontrado por el usuario: esta función tenía DOS
    problemas de aislamiento multi-tenant a la vez, no solo uno.
    1) ConfigResidencial.get() sin residencial_id -- una sola fila
       compartida por todas las residenciales (ver el modelo).
    2) Cuenta.query.filter_by(activa=True) SIN filtrar por residencial --
       cambiar el día de pago desde UNA residencial lo aplicaba a las
       cuentas de TODAS las residenciales del sistema. Corregido con un
       join a Unidad para filtrar por residencial_id real.
    """
    from app.models.cuenta import ConfigResidencial, Cuenta, Unidad
    cfg = ConfigResidencial.get(usuario_actual.residencial_id)
    body = request.get_json(silent=True) or {}

    cambio_dia = False
    if "dia_pago" in body:
        dp = int(body["dia_pago"])
        if 1 <= dp <= 30:
            cfg.dia_pago = dp
            cambio_dia = True
    if "dias_gracia" in body:
        dg = int(body["dias_gracia"])
        if 0 <= dg <= 15:
            cfg.dias_gracia = dg

    # Si cambió el día de pago, aplicar a TODAS las cuentas activas DE ESTA
    # RESIDENCIAL (no de todo el sistema).
    actualizadas = 0
    if cambio_dia:
        cuentas = (Cuenta.query.join(Unidad, Cuenta.unidad_id == Unidad.id)
                   .filter(Cuenta.activa == True,  # noqa: E712
                           Unidad.residencial_id == usuario_actual.residencial_id)
                   .all())
        for c in cuentas:
            c.dia_pago = cfg.dia_pago
            actualizadas += 1

    db.session.commit()
    return jsonify({"data": {**cfg.to_dict(), "cuentas_actualizadas": actualizadas}})


# =====================================================================
# MI RESIDENCIAL — nombre y logo (bases multi-residencial, Día 37)
#
# Distinto de ConfigResidencial (arriba): eso es la configuración de pagos
# de la ÚNICA residencial que existe hoy. Esto es la identidad visual
# (nombre, logo) de LA residencial a la que pertenece el usuario que
# consulta — el mismo endpoint sirve para uno o para mil clientes del
# futuro SaaS sin cambiar nada, porque siempre resuelve por
# usuario_actual.residencial_id.
# =====================================================================
def _carpeta_logos():
    carpeta = os.path.join(current_app.config.get("UPLOAD_FOLDER", "/app/uploads"), "residenciales")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


@cuentas_bp.get("/mi-residencial")
@token_required
def ver_mi_residencial(usuario_actual):
    """Cualquier usuario autenticado puede ver el nombre/logo de su
    residencial (para mostrarlo en el encabezado de la app/web)."""
    from app.models.residencial import Residencial
    if not usuario_actual.residencial_id:
        return jsonify({"data": None})
    r = Residencial.query.get(usuario_actual.residencial_id)
    if not r:
        return jsonify({"data": None})
    return jsonify({"data": r.to_dict()})


@cuentas_bp.put("/mi-residencial")
@roles_required("admin", "super_admin")
def editar_mi_residencial(usuario_actual):
    """El admin (o supervisor, vía roles_required) edita el nombre y los
    colores de su residencial. El logo se sube aparte (multipart) en el
    endpoint de abajo."""
    import re
    from app.models.residencial import Residencial
    if not usuario_actual.residencial_id:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400
    r = Residencial.query.get(usuario_actual.residencial_id)
    if not r:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Residencial no encontrada"}}), 404

    body = request.get_json(silent=True) or {}
    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if not nombre:
            return jsonify({"error": {"code": "nombre_requerido",
                                      "message": "El nombre no puede quedar vacío"}}), 400
        if len(nombre) > 160:
            return jsonify({"error": {"code": "nombre_largo",
                                      "message": "El nombre no puede superar 160 caracteres"}}), 400
        r.nombre = nombre

    # Día 47 — colores personalizables. Se valida el formato acá (no como
    # constraint de base) porque el valor termina inyectado directo en CSS
    # del lado del cliente (document.documentElement.style.setProperty) —
    # un formato inesperado ahí podría romper el estilo de toda la app o,
    # en el peor caso, dar pie a un intento de inyección. Solo se acepta
    # hex de 6 dígitos: #RRGGBB, nada de nombres de color CSS ni funciones
    # (rgb(), var(), url(), etc.) que un navegador también interpretaría.
    patron_hex = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for campo in ("color_primario", "color_secundario"):
        if campo in body:
            valor = (body[campo] or "").strip()
            if valor == "":
                setattr(r, campo, None)  # "" = volver al color de fábrica
                continue
            if not patron_hex.match(valor):
                return jsonify({"error": {"code": "color_invalido",
                                          "message": f"El color debe tener formato hexadecimal "
                                                     f"(ej. #022E45): {campo}"}}), 400
            setattr(r, campo, valor.upper())

    # Día 76 — contacto de servicio al cliente (sección "Ayuda" del
    # residente). "" lo borra: la sección muestra entonces solo lo que haya.
    if "telefono_ayuda" in body:
        tel = re.sub(r"\s+", " ", (body["telefono_ayuda"] or "").strip())
        if tel:
            digitos = re.sub(r"\D", "", tel)
            if not re.fullmatch(r"[0-9+\-() ]{7,30}", tel) or not 7 <= len(digitos) <= 15:
                return jsonify({"error": {"code": "telefono_invalido",
                                          "message": "El teléfono solo puede tener números, espacios, "
                                                     "guiones y un + al principio (ej. 2550-1234)."}}), 400
        r.telefono_ayuda = tel or None
    if "email_ayuda" in body:
        correo = (body["email_ayuda"] or "").strip().lower()
        if correo and (len(correo) > 160 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo)):
            return jsonify({"error": {"code": "email_invalido",
                                      "message": "El correo de ayuda no tiene un formato válido."}}), 400
        r.email_ayuda = correo or None

    db.session.commit()
    return jsonify({"data": r.to_dict()})


# =====================================================================
# Día 76 — CUENTAS BANCARIAS AUTORIZADAS PARA PAGAR
#
# El admin las configura; cualquier usuario de la residencial las ve (los
# residentes, en la app y el portal, junto a sus cuotas). Ver
# app/models/cuenta_bancaria.py.
# =====================================================================
def _datos_cuenta_bancaria(body, parcial=False):
    """Valida el cuerpo. Devuelve (dict_de_campos, None) o (None, respuesta)."""
    import re
    from app.models.cuenta_bancaria import TIPOS_CUENTA

    def err(code, msg):
        return None, (jsonify({"error": {"code": code, "message": msg}}), 400)

    campos = {}
    if not parcial or "banco" in body:
        banco = re.sub(r"\s+", " ", (body.get("banco") or "").strip())
        if not 2 <= len(banco) <= 80:
            return err("banco_invalido", "Escribí el nombre del banco.")
        campos["banco"] = banco
    if not parcial or "numero" in body:
        numero = re.sub(r"\s+", " ", (body.get("numero") or "").strip())
        digitos = re.sub(r"\D", "", numero)
        if not re.fullmatch(r"[0-9\- ]{4,40}", numero) or len(digitos) < 4:
            return err("numero_invalido",
                       "El número de cuenta solo puede tener números, espacios y guiones.")
        campos["numero"] = numero
    if "titular" in body:
        titular = re.sub(r"\s+", " ", (body.get("titular") or "").strip())
        if len(titular) > 120:
            return err("titular_largo", "El nombre del titular no puede superar 120 caracteres.")
        campos["titular"] = titular or None
    if "tipo" in body:
        tipo = (body.get("tipo") or "").strip().lower() or None
        if tipo is not None and tipo not in TIPOS_CUENTA:
            return err("tipo_invalido", "El tipo de cuenta tiene que ser ahorro o cheques.")
        campos["tipo"] = tipo
    return campos, None


def _cuentas_bancarias_de(residencial_id):
    from app.models.cuenta_bancaria import CuentaBancaria
    return (CuentaBancaria.query.filter_by(residencial_id=residencial_id)
            .order_by(CuentaBancaria.orden.asc(), CuentaBancaria.created_at.asc()).all())


@cuentas_bp.get("/mi-residencial/cuentas-bancarias")
@token_required
def listar_cuentas_bancarias(usuario_actual):
    """Cualquier usuario de la residencial: el residente las necesita para
    saber a dónde transferir."""
    if not usuario_actual.residencial_id:
        return jsonify({"data": []})
    return jsonify({"data": [c.to_dict() for c in _cuentas_bancarias_de(usuario_actual.residencial_id)]})


@cuentas_bp.post("/mi-residencial/cuentas-bancarias")
@roles_required("admin", "super_admin")
def crear_cuenta_bancaria(usuario_actual):
    from app.models.cuenta_bancaria import CuentaBancaria, MAX_CUENTAS
    if not usuario_actual.residencial_id:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400
    campos, err = _datos_cuenta_bancaria(request.get_json(silent=True) or {})
    if err:
        return err
    existentes = _cuentas_bancarias_de(usuario_actual.residencial_id)
    if len(existentes) >= MAX_CUENTAS:
        return jsonify({"error": {"code": "demasiadas_cuentas",
                                  "message": f"Se pueden configurar hasta {MAX_CUENTAS} cuentas."}}), 400
    if any(c.banco.lower() == campos["banco"].lower()
           and re.sub(r"\D", "", c.numero) == re.sub(r"\D", "", campos["numero"]) for c in existentes):
        return jsonify({"error": {"code": "cuenta_repetida",
                                  "message": "Esa cuenta ya está en la lista."}}), 409
    c = CuentaBancaria(residencial_id=usuario_actual.residencial_id,
                       orden=(max((x.orden for x in existentes), default=0) + 1), **campos)
    db.session.add(c)
    db.session.commit()
    return jsonify({"data": c.to_dict()}), 201


@cuentas_bp.put("/mi-residencial/cuentas-bancarias/<cuenta_uuid>")
@roles_required("admin", "super_admin")
def editar_cuenta_bancaria(usuario_actual, cuenta_uuid):
    c = _cuenta_bancaria_mia(cuenta_uuid, usuario_actual)
    if c is None:
        return jsonify({"error": {"code": "no_encontrada", "message": "Cuenta no encontrada"}}), 404
    campos, err = _datos_cuenta_bancaria(request.get_json(silent=True) or {}, parcial=True)
    if err:
        return err
    for k, v in campos.items():
        setattr(c, k, v)
    db.session.commit()
    return jsonify({"data": c.to_dict()})


@cuentas_bp.delete("/mi-residencial/cuentas-bancarias/<cuenta_uuid>")
@roles_required("admin", "super_admin")
def borrar_cuenta_bancaria(usuario_actual, cuenta_uuid):
    c = _cuenta_bancaria_mia(cuenta_uuid, usuario_actual)
    if c is None:
        return jsonify({"error": {"code": "no_encontrada", "message": "Cuenta no encontrada"}}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"data": {"borrada": True}})


def _cuenta_bancaria_mia(cuenta_uuid, usuario_actual):
    """Solo cuentas de la residencial de quien opera."""
    import uuid as _uuid
    from app.models.cuenta_bancaria import CuentaBancaria
    try:
        u = _uuid.UUID(str(cuenta_uuid))
    except ValueError:
        return None
    c = CuentaBancaria.query.filter_by(uuid_publico=u).first()
    if c is None or c.residencial_id != usuario_actual.residencial_id:
        return None
    return c


@cuentas_bp.post("/mi-residencial/logo")
@roles_required("admin", "super_admin")
def subir_logo_residencial(usuario_actual):
    """Sube/reemplaza el logo de la residencial del admin. Mismo patrón de
    guardado seguro que comunicados (valida tipo real de archivo, genera
    nombre propio) y mismo modelo de acceso privado que FILES-05 (se sirve
    autenticado, no queda público en el bucket)."""
    from app.models.residencial import Residencial
    if not usuario_actual.residencial_id:
        return jsonify({"error": {"code": "sin_residencial",
                                  "message": "Tu usuario no tiene una residencial asignada"}}), 400
    r = Residencial.query.get(usuario_actual.residencial_id)
    if not r:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Residencial no encontrada"}}), 404

    if "logo" not in request.files or not request.files["logo"].filename:
        return jsonify({"error": {"code": "sin_archivo",
                                  "message": "Adjuntá una imagen para el logo"}}), 400

    nombre_archivo, error, _tam = guardar_imagen_segura(
        request.files["logo"], _carpeta_logos(), EXT_IMAGEN
    )
    if error:
        return jsonify({"error": {"code": "imagen_invalida", "message": error}}), 400

    # Reemplaza el logo anterior si existía (no se acumulan archivos viejos)
    if r.logo_archivo:
        try:
            os.remove(os.path.join(_carpeta_logos(), r.logo_archivo))
        except OSError:
            pass

    r.logo_archivo = nombre_archivo
    db.session.commit()
    return jsonify({"data": r.to_dict()})


@cuentas_bp.get("/mi-residencial/logo/<path:nombre_archivo>")
@token_required
def ver_logo_residencial(usuario_actual, nombre_archivo):
    """Sirve el archivo del logo. Cualquier usuario autenticado puede verlo
    (es la marca visual que ve toda la residencial, no un dato privado).

    Día 59 — BUG REAL: el convertidor de ruta era <nombre_archivo> (string
    simple), que NO admite barras "/" dentro del segmento. En modo nube
    (Spaces), logo_archivo se guarda CON el prefijo de subcarpeta
    ("residenciales/xxxx.jpeg" — ver guardar_imagen_segura en
    utils/archivos.py), así que la URL real que arma el frontend
    (urlLogoResidencial, que usa residencial.logo_archivo tal cual) SIEMPRE
    tenía una barra en producción -- y esa ruta nunca coincidía con
    ninguna vista registrada, 404 directo, sin llegar siquiera al
    query de abajo. <path:nombre_archivo> sí admite barras.
    """
    from app.models.residencial import Residencial
    existe = Residencial.query.filter_by(logo_archivo=nombre_archivo).first()
    if not existe:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Logo no encontrado"}}), 404
    # No se usa servir_archivo_seguro(carpeta, nombre_archivo) a propósito:
    # esa función, en modo nube, RECONSTRUYE la clave sumando la subcarpeta
    # (derivada de `carpeta`) + nombre_archivo -- una lógica pensada para
    # cuando nombre_archivo es SOLO el nombre del archivo, sin prefijo. Pero
    # acá, con el fix de <path:nombre_archivo> de arriba, nombre_archivo YA
    # llega completo con el prefijo en modo nube ("residenciales/xxx.jpeg",
    # tal como está guardado en la base) -- sumarle la subcarpeta de nuevo
    # duplicaría el prefijo ("residenciales/residenciales/xxx.jpeg") y
    # rompería la búsqueda en Spaces. Se llama directo a storage.py con la
    # clave ya normalizada (mismo criterio que en recibos.py/caja.py).
    from app.services import storage
    clave = nombre_archivo if nombre_archivo.startswith("residenciales/") else f"residenciales/{nombre_archivo}"
    return storage.servir_archivo(clave)

# =====================================================================
# SOLICITUDES DE BAJA (admin de edificio pide dar de baja a un inquilino)
# =====================================================================
@cuentas_bp.post("/solicitudes-baja")
@token_required
def crear_solicitud_baja(usuario_actual):
    """Un admin de edificio solicita dar de baja a una cuenta de inquilino."""
    data = request.get_json(silent=True) or {}
    cuenta_uuid = data.get("cuenta_id")
    motivo = (data.get("motivo") or "").strip()
    fecha_des = data.get("fecha_desocupacion")

    if not cuenta_uuid or not motivo or not fecha_des:
        return _err("datos_incompletos",
                     "Completá el motivo y la fecha de desocupación.", 400)

    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Verificar que el solicitante es el dueño del edificio de esta cuenta
    if cuenta.unidad:
        if (cuenta.unidad.propietario_id != usuario_actual.id
                and usuario_actual.rol not in ("admin", "super_admin")):
            return _err("sin_permiso", "No tenés permiso para solicitar esta baja.", 403)

    # La cuenta debe estar al día
    if cuenta.bloqueada:
        return _err("cuenta_con_deuda",
                     "La cuenta tiene deuda pendiente. Debe estar al día para solicitar la baja.", 400)

    # No duplicar solicitudes pendientes
    existente = SolicitudBaja.query.filter_by(
        cuenta_id=cuenta.id, estado="pendiente").first()
    if existente:
        return _err("ya_solicitada", "Ya existe una solicitud de baja pendiente para esta cuenta.", 400)

    solicitud = SolicitudBaja(
        cuenta_id=cuenta.id,
        solicitada_por=usuario_actual.id,
        motivo=motivo,
        fecha_desocupacion=dt.date.fromisoformat(fecha_des),
    )
    db.session.add(solicitud)
    db.session.commit()
    return jsonify({"data": solicitud.to_dict()}), 201


@cuentas_bp.get("/solicitudes-baja")
@roles_required("admin", "super_admin")
def listar_solicitudes_baja(usuario_actual):
    """Lista todas las solicitudes de baja (para el panel admin)."""
    estado = request.args.get("estado", "pendiente")
    from app.utils.residencial import scope_por_cuenta
    q = scope_por_cuenta(SolicitudBaja.query, SolicitudBaja, usuario_actual)
    if estado != "todas":
        q = q.filter(SolicitudBaja.estado == estado)
    solicitudes = q.order_by(SolicitudBaja.created_at.desc()).all()
    return jsonify({"data": [s.to_dict() for s in solicitudes]})


@cuentas_bp.post("/solicitudes-baja/<solicitud_uuid>/resolver")
@roles_required("admin", "super_admin")
def resolver_solicitud_baja(usuario_actual, solicitud_uuid):
    """El admin aprueba o rechaza una solicitud de baja."""
    data = request.get_json(silent=True) or {}
    accion = data.get("accion")  # "aprobar" o "rechazar"
    respuesta = (data.get("respuesta") or "").strip()

    solicitud = SolicitudBaja.query.filter_by(uuid_publico=solicitud_uuid).first()
    if not solicitud:
        return _err("no_encontrada", "Solicitud no encontrada", 404)
    if solicitud.estado != "pendiente":
        return _err("ya_resuelta", "Esta solicitud ya fue resuelta.", 400)

    if accion == "aprobar":
        # Dar de baja la cuenta — mismas validaciones universales que /baja
        cuenta = solicitud.cuenta

        # Día 76 — un comprobante sin revisar no es un pago todavía.
        from app.services.ciclo_casa import impedimento_en_revision
        imp = impedimento_en_revision(cuenta, "aprobar la baja")
        if imp is not None:
            return _err(*imp)

        # REQUISITO: saldo en 0
        cuotas_pendientes = Cuota.query.filter(
            Cuota.cuenta_id == cuenta.id,
            Cuota.estado.in_(["pendiente", "parcial", "vencida", "en_arreglo"]),
        ).all()
        if cuotas_pendientes:
            total = sum(float(c.monto) - _monto_pagado_cuota(c) for c in cuotas_pendientes)
            return _err("saldo_pendiente",
                         f"No se puede aprobar: la cuenta tiene {len(cuotas_pendientes)} cuota(s) "
                         f"pendiente(s) por L {total:.2f}. Usá 'Nivelar saldo' y registrá el pago "
                         f"antes de aprobar la baja.", 400)

        cuenta.activa = False
        cuenta.estado = "baja"

        # Suspender acceso a crear QR: desactivar usuarios de la cuenta
        for r in cuenta.residentes:
            if r.usuario:
                r.usuario.activo = False

        # Desactivar todas las tarjetas
        for t in Tarjeta.query.filter_by(cuenta_id=cuenta.id).all():
            if t.estado == "activa":
                t.estado = "desactivada"
                t.fecha_baja = dt.date.today()

        solicitud.estado = "aprobada"
    elif accion == "rechazar":
        if not respuesta:
            return _err("respuesta_requerida",
                         "Indicá el motivo del rechazo.", 400)
        solicitud.estado = "rechazada"
    else:
        return _err("accion_invalida", "La acción debe ser 'aprobar' o 'rechazar'.", 400)

    solicitud.respuesta_admin = respuesta or None
    solicitud.resuelto_en = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": solicitud.to_dict()})
