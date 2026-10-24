"""
Módulo de Guardias — /api/v1/guardias/

Solo conserva la creación de guardias (usada desde el módulo Usuarios del
frontend). Listar, editar y resetear contraseña de guardias se hace por los
endpoints genéricos de /api/v1/usuarios — los duplicados se eliminaron en la
limpieza de la auditoría del Día 11.
"""
import os

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.models.usuario import Usuario
from app.auth.security import roles_required
from app.utils.passwords import generar_password_temporal
from app.utils.residencial import residencial_id_heredado
from app.utils.archivos import guardar_imagen_segura, EXT_IMAGEN

guardias_bp = Blueprint("guardias", __name__)


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _carpeta_accesos():
    carpeta = os.path.join(current_app.config.get("UPLOAD_FOLDER", "/app/uploads"), "accesos")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _tranca_del_guardia(usuario_actual, acceso_id_raw):
    """
    Resuelve la tranca que el guardia quiere abrir, verificando que sea de
    SU punto y de SU residencial.

    Misma verificación que abrir_tranca_manual: cada endpoint que abre una
    tranca comprueba por su cuenta en vez de confiar en que los pasos
    anteriores del flujo ya lo garantizaron (criterio del Día 48).
    Devuelve (tranca, None) o (None, respuesta_de_error).
    """
    from app.models.visita import AccesoFisico

    acceso_id = (str(acceso_id_raw or "")).strip()
    if not acceso_id.isdigit():
        return None, _err("tranca_requerida", "Indicá qué tranca abrir", 400)

    tranca = AccesoFisico.query.filter_by(id=int(acceso_id), activo=True).first()
    if not tranca:
        return None, _err("tranca_invalida", "Esa tranca no existe o está inactiva", 400)
    if (tranca.punto_acceso != usuario_actual.punto_acceso_actual
            or tranca.residencial_id != usuario_actual.residencial_id):
        return None, _err("tranca_fuera_de_tu_punto",
                          "Esa tranca no pertenece a tu punto de acceso", 403)
    return tranca, None


def _tranca_por_tipo(usuario_actual, tipo_acceso, direccion):
    """
    Día 70 — encuentra la tranca del punto del guardia por tipo y dirección
    (los tres botones de "Dar acceso": entrada vehicular, salida vehicular,
    entrada peatonal). Mismas verificaciones que _tranca_del_guardia: solo
    trancas activas, de SU punto y de SU residencial.
    """
    from app.models.visita import AccesoFisico

    if tipo_acceso not in ("vehicular", "peatonal"):
        return None, _err("tipo_invalido", "El tipo de acceso debe ser vehicular o peatonal", 400)

    tranca = AccesoFisico.query.filter_by(
        punto_acceso=usuario_actual.punto_acceso_actual,
        residencial_id=usuario_actual.residencial_id,
        tipo=tipo_acceso, direccion=direccion, activo=True,
    ).order_by(AccesoFisico.id).first()
    if not tranca:
        return None, _err(
            "sin_tranca",
            f"Tu punto de acceso no tiene tranca de {direccion} {tipo_acceso}", 400)
    return tranca, None


@guardias_bp.post("")
@roles_required("admin", "super_admin")
def crear_guardia(usuario_actual):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not nombre or not apellido or not email:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Nombre, apellido y correo son obligatorios"}}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": {"code": "email_duplicado",
                                  "message": "Ya existe un usuario con ese correo"}}), 400

    # Día 50 — sistema de suscripciones.
    from app.utils.residencial import limite_usuarios_alcanzado
    if limite_usuarios_alcanzado(usuario_actual.residencial_id):
        return jsonify({"error": {"code": "limite_usuarios",
                                  "message": "Tu plan actual no permite más usuarios. "
                                             "Pedile a tu proveedor que te suba de plan."}}), 402

    # SEC-01: contraseña aleatoria por usuario — antes era una fija
    # compartida ('VillasDelSol2026') para todos los guardias nuevos.
    password_temporal = generar_password_temporal()

    guardia = Usuario(
        nombre=nombre, apellido=apellido, email=email,
        rol="guardia", activo=True,
        debe_cambiar_password=True,   # obligado a cambiar en el primer login
        # Bases multi-residencial (Día 37): hereda la residencial de quien
        # lo crea (el admin o supervisor). Hoy siempre el mismo valor.
        residencial_id=residencial_id_heredado(usuario_actual),
    )
    guardia.set_password(password_temporal)
    db.session.add(guardia)
    db.session.commit()

    d = guardia.to_dict()
    d["password_generica"] = password_temporal  # mostrar al admin para entregársela
    return jsonify({"data": d}), 201


@guardias_bp.post("/mi-punto-acceso")
@roles_required("guardia")
def fijar_mi_punto_acceso(usuario_actual):
    """
    El guardia elige en qué punto de acceso está trabajando este turno.
    Queda guardado en su usuario — normalmente se elige una sola vez, ya
    que cada guardia usa siempre el mismo teléfono asignado a un punto
    específico (ACCESS-04, Auditoría Día 35).
    """
    from app.models.visita import AccesoFisico

    data = request.get_json(silent=True) or {}
    nombre_punto = (data.get("punto_acceso") or "").strip()
    if not nombre_punto:
        return jsonify({"error": {"code": "punto_requerido",
                                  "message": "Indicá el punto de acceso"}}), 400

    # Día 48 — hallazgo de auditoría: antes se buscaba SOLO por el nombre
    # del punto (texto libre), sin filtrar por residencial. Si dos
    # residenciales nombran su punto igual (ej. "Portón Principal", muy
    # probable), un guardia podía quedar asignado al punto de OTRA
    # residencial sin darse cuenta — y de ahí en adelante ver y abrir
    # trancas ajenas (ver mis_trancas_disponibles y abrir_tranca_manual,
    # más abajo, con el mismo fix).
    existe = AccesoFisico.query.filter_by(
        punto_acceso=nombre_punto, activo=True,
        residencial_id=usuario_actual.residencial_id,
    ).first()
    if not existe:
        return jsonify({"error": {"code": "punto_invalido",
                                  "message": "Ese punto de acceso no existe o está inactivo"}}), 400

    usuario_actual.punto_acceso_actual = nombre_punto
    db.session.commit()
    return jsonify({"data": {"punto_acceso": nombre_punto}})


@guardias_bp.get("/mis-trancas")
@roles_required("guardia")
def mis_trancas_disponibles(usuario_actual):
    """
    Devuelve las trancas del punto de acceso donde está el guardia — para
    llenar el menú del botón 'Abrir' en la app (ACCESS-04, Auditoría Día 35).
    """
    from app.models.visita import AccesoFisico

    if not usuario_actual.punto_acceso_actual:
        return jsonify({"error": {"code": "sin_punto_asignado",
                                  "message": "No tenés un punto de acceso asignado"}}), 400

    # Día 48: mismo fix que fijar_mi_punto_acceso — filtrar también por
    # residencial, no solo por el nombre del punto.
    trancas = AccesoFisico.query.filter_by(
        punto_acceso=usuario_actual.punto_acceso_actual, activo=True,
        residencial_id=usuario_actual.residencial_id,
    ).order_by(AccesoFisico.tipo, AccesoFisico.direccion).all()

    return jsonify({"data": {
        "punto_acceso": usuario_actual.punto_acceso_actual,
        "trancas": [t.to_dict() for t in trancas],
    }})


@guardias_bp.post("/abrir-manual")
@roles_required("guardia")
def abrir_tranca_manual(usuario_actual):
    """
    Registra la apertura manual de una tranca SIN visita asociada — ej. el
    guardia deja salir a alguien que vio, o una emergencia. Exige que la
    app haya pedido confirmación explícita antes de llamar este endpoint;
    el registro queda auditado con quién, cuándo y cuál tranca exacta
    (ACCESS-04, Auditoría Día 35).

    Hoy esto solo REGISTRA la acción — no dispara nada físico todavía,
    porque el agente de la Raspberry Pi que acciona el relay real no está
    construido. Cuando exista, este mismo endpoint es el punto donde se
    le manda la orden a la Pi del punto correspondiente.
    """
    from app.models.visita import AccesoFisico, AperturaManual

    data = request.get_json(silent=True) or {}
    acceso_uuid = (data.get("acceso_id") or "").strip()
    if not acceso_uuid:
        return jsonify({"error": {"code": "tranca_requerida",
                                  "message": "Indicá qué tranca abrir"}}), 400

    acceso = AccesoFisico.query.filter_by(id=acceso_uuid, activo=True).first() \
        if acceso_uuid.isdigit() else None
    if not acceso:
        return jsonify({"error": {"code": "tranca_invalida",
                                  "message": "Esa tranca no existe o está inactiva"}}), 400

    # El guardia solo puede abrir trancas de SU punto asignado — no las de otro.
    # Día 48: se agrega también el chequeo de residencial (defensa en
    # profundidad) — aunque el punto de acceso ya venga filtrado por
    # residencial más arriba en el flujo (fijar_mi_punto_acceso,
    # mis_trancas_disponibles), este endpoint es el que REALMENTE abre la
    # tranca, así que verifica por su cuenta en vez de confiar en que los
    # pasos anteriores ya lo garantizaron.
    if acceso.punto_acceso != usuario_actual.punto_acceso_actual \
            or acceso.residencial_id != usuario_actual.residencial_id:
        return jsonify({"error": {"code": "tranca_fuera_de_tu_punto",
                                  "message": "Esa tranca no pertenece a tu punto de acceso"}}), 403

    apertura = AperturaManual(
        acceso_id=acceso.id,
        guardia_id=usuario_actual.id,
        motivo=(data.get("motivo") or "").strip()[:255] or None,
    )
    db.session.add(apertura)
    db.session.commit()

    return jsonify({"data": apertura.to_dict()}), 201


# =====================================================================
# ACCESO DE RESIDENTE POR CÓDIGO DE EMERGENCIA (Día 69)
# =====================================================================
# El residente llega sin batería en el teléfono, así que no puede mostrar
# su QR. Le dice al guardia su casa y su código de 6 dígitos; el guardia lo
# busca acá, ve su foto y su nombre, le pide la identificación, compara,
# saca una foto de respaldo y abre.
#
# POR QUÉ SE PIDE CASA **Y** CÓDIGO, Y NO SOLO EL CÓDIGO:
# si bastara el código, el guardia podría teclear números al azar y la app
# le devolvería la foto, el nombre y la casa de cualquier residente. Su
# pantalla se volvería un directorio de la residencial, recorrible a fuerza
# de probar. Pidiendo la casa primero, no hay nada que enumerar: hay que
# saber de antemano a quién se está buscando.
#
# QUÉ PROTEGE REALMENTE ESTE FLUJO:
# el código NO es una credencial fuerte — el guardia lo escucha en voz alta
# y lo va a recordar. Pero eso no es el agujero que parece: el guardia YA
# puede abrir la tranca manualmente cuando quiera. Lo que aporta este
# camino es el rastro: amarra esa apertura a un residente concreto, con
# foto de su identificación, el guardia que la hizo y la tranca que se
# abrió. Reemplaza una apertura anónima por una con nombre y evidencia.
@guardias_bp.post("/residente/buscar")
@roles_required("guardia")
@limiter.limit("20 per minute")
def buscar_residente_por_codigo(usuario_actual):
    """
    Busca a la persona que pide entrar sin teléfono. No abre nada todavía.

    DOS MODOS, según si el guardia escribió código o no:

      con código   -> residente que usa la app. Casa + código de 6 dígitos
                      devuelven a UNA persona.

      sin código   -> persona del PADRÓN (Día 70). Esa gente no tiene app,
                      así que tampoco puede tener código de emergencia: se
                      configura desde la app. Sin este modo, el guardia no
                      tenía forma de encontrarlas, y el padrón --hecho para
                      dar trazabilidad en el portón-- no servía en el portón.
                      Se devuelve la lista de personas del padrón de esa
                      casa, con nombre, identidad y foto, para que el
                      guardia compare contra la identificación que tiene en
                      la mano y elija.

    El modo sin código SOLO lista personas del padrón, nunca a quien usa la
    app: esa gente tiene código, y sin él no se la muestra. Así la pantalla
    del guardia no se convierte en un directorio de la residencial.

    En un edificio se exige el apartamento: listar a todo el edificio sería
    justo el directorio que se quiere evitar.
    """
    from app.models.cuenta import Cuenta, Residente, Unidad

    data = request.get_json(silent=True) or {}
    casa = (data.get("casa") or "").strip()
    codigo = (data.get("codigo") or "").strip()
    apartamento = (data.get("apartamento") or "").strip()

    if not casa:
        return _err("datos_incompletos", "Indicá la casa", 400)

    unidad = Unidad.query.filter(
        db.func.lower(Unidad.identificador) == casa.lower(),
        Unidad.residencial_id == usuario_actual.residencial_id,
    ).first()

    # Las búsquedas fallidas también se registran. Si un guardia anduvo
    # probando doce combinaciones en una noche, tiene que poder verse.
    def _fallo(mensaje):
        from flask import g
        g.email_intento = f"casa={casa[:40]}"
        current_app.logger.warning(
            "Busqueda de residente fallida — guardia=%s casa=%s apto=%s con_codigo=%s",
            usuario_actual.id, casa[:40], apartamento[:10], bool(codigo))
        return _err("no_encontrado", mensaje, 404)

    if not unidad:
        return _fallo("No encontramos esa casa")

    cuentas = Cuenta.query.filter_by(unidad_id=unidad.id, activa=True).all()

    # ── Modo padrón: sin código ──────────────────────────────────────────
    if not codigo:
        if unidad.tipo == "edificio":
            if not apartamento:
                return _err("apartamento_requerido",
                            "Es un edificio: indicá también el apartamento", 400)
            cuentas = [c for c in cuentas
                       if (c.apartamento or "").lower() == apartamento.lower()]

        # Día 71 — se lista a TODA persona de la casa que no tiene cómo
        # usar el camino del código: la gente del padrón y también quien ya
        # tiene cuenta pero todavía no definió su código (o ni activó la
        # cuenta). Antes solo salía la gente del padrón, y un miembro al que
        # la administración le acababa de dar acceso -- deja de ser del
        # padrón pero aún no tiene código -- no aparecía por ningún lado:
        # el guardia no podía identificarlo.
        #
        # Quien SÍ tiene código sigue sin listarse: para esa persona existe
        # el código, y mostrarla haría de esta pantalla un directorio.
        personas = []
        for cuenta in cuentas:
            for residente in cuenta.residentes:
                u = residente.usuario
                if not (residente.activo and u):
                    continue
                if u.es_censo or not u.tiene_codigo_emergencia:
                    personas.append((cuenta, residente))

        if not personas:
            return _fallo("No hay nadie en esa casa para identificar sin código. "
                          "Si la persona usa la app, pedile su código de emergencia.")

        # El titular primero: suele ser a quien el guardia conoce, y ayuda
        # a ubicar al resto de la familia.
        personas.sort(key=lambda par: (par[1].rol_cuenta != "titular",
                                       (par[1].usuario.nombre or "").lower()))

        # Cada consulta del padrón queda registrada aunque no termine en un
        # acceso: muestra nombres e identidades, y tiene que poder
        # auditarse quién miró qué casa y cuándo.
        current_app.logger.info(
            "Consulta de padron — guardia=%s casa=%s apto=%s personas=%s",
            usuario_actual.id, unidad.identificador, apartamento[:10], len(personas))

        return jsonify({"data": {
            "modo": "padron",
            "casa": unidad.identificador,
            "apartamento": apartamento or None,
            "personas": [_persona_para_guardia(c, r) for c, r in personas],
        }})

    # ── Modo código: residente con app ───────────────────────────────────
    for cuenta in cuentas:
        for residente in cuenta.residentes:
            if not residente.activo or not residente.usuario:
                continue
            if residente.usuario.check_codigo_emergencia(codigo):
                return jsonify({"data": {
                    "modo": "codigo",
                    "residente": residente.to_dict(),
                    "casa": unidad.identificador,
                    # Se avisa de la mora como INFORMACIÓN, nunca como
                    # bloqueo: impedirle a una familia entrar a su propia
                    # casa por deber la cuota es terreno legal delicado, y
                    # el patronato tampoco tiene cómo obligar a nadie a
                    # pagar. Decisión tomada con el usuario el Día 68.
                    "cuenta_en_mora": bool(cuenta.bloqueada),
                }})

    return _fallo("No encontramos esa casa ni ese código")


def _persona_para_guardia(cuenta, residente):
    """Lo que el guardia necesita para identificar a alguien en el portón:
    nombre, identidad, foto y qué es de la casa. Nada más: ni correo, ni
    teléfono, ni RTN, ni dirección, ni contacto de emergencia."""
    u = residente.usuario
    return {
        "id": str(residente.uuid_publico),
        "nombre": f"{u.nombre} {u.apellido}".strip(),
        "dni": u.dni,
        "foto_url": u.foto_url,
        "rol_cuenta": residente.rol_cuenta,
        "relacion": residente.relacion,
        "apartamento": cuenta.apartamento,
        "es_censo": bool(u.es_censo),
        "origen": "padron" if u.es_censo else "sin_codigo",
    }


@guardias_bp.post("/residente/registrar")
@roles_required("guardia")
def registrar_acceso_residente(usuario_actual):
    """
    Registra la entrada o salida del residente, después de que el guardia
    verificó su identificación contra la foto en ficha.

    La foto de la identificación es OBLIGATORIA en las entradas: es la
    evidencia de que el guardia efectivamente verificó, y sin ella este
    camino sería una apertura manual con más pasos.
    """
    from app.models.cuenta import Residente
    from app.models.visita import EventoAcceso

    residente_uuid = (request.form.get("residente_id") or "").strip()
    direccion = (request.form.get("direccion") or "entrada").strip()
    if direccion not in ("entrada", "salida"):
        return _err("direccion_invalida", "La dirección debe ser entrada o salida", 400)

    residente = Residente.query.filter_by(uuid_publico=residente_uuid).first()
    if not residente or not residente.usuario:
        return _err("no_encontrado", "Residente no encontrado", 404)

    cuenta = residente.cuenta
    unidad = cuenta.unidad if cuenta else None
    if not unidad or unidad.residencial_id != usuario_actual.residencial_id:
        return _err("residente_ajeno", "Ese residente no pertenece a tu residencial", 403)

    # Día 70 — la app ya no elige la tranca de un desplegable: el guardia
    # toca "Entrada vehicular", "Salida vehicular" o "Entrada peatonal", y
    # acá se busca la tranca de SU punto que corresponde a ese tipo y esa
    # dirección. Se sigue aceptando acceso_id para no romper versiones de
    # la app que ya estén instaladas.
    tipo_acceso = (request.form.get("tipo_acceso") or "").strip()
    if tipo_acceso:
        tranca, error = _tranca_por_tipo(usuario_actual, tipo_acceso, direccion)
    else:
        tranca, error = _tranca_del_guardia(usuario_actual, request.form.get("acceso_id"))
    if error:
        return error

    foto_nombre = None
    if "foto_identidad" in request.files and request.files["foto_identidad"].filename:
        foto_nombre, err_foto, _t = guardar_imagen_segura(
            request.files["foto_identidad"], _carpeta_accesos(), EXT_IMAGEN)
        if err_foto:
            return _err("imagen_invalida", err_foto, 400)
    elif direccion == "entrada":
        return _err("foto_requerida",
                    "La foto de la identificación es obligatoria para registrar la entrada", 400)

    # El historial tiene que distinguir los dos caminos: con código, la
    # persona demostró algo que solo ella sabe; del padrón, la única prueba
    # es que el guardia comparó la identificación contra la ficha.
    u = residente.usuario
    if u.es_censo:
        metodo = "padron_identidad"
    elif u.tiene_codigo_emergencia:
        metodo = "codigo_emergencia"
    else:
        # Día 71 — tiene cuenta pero no código: el guardia la identificó
        # igual que a la gente del padrón, solo con la identificación.
        metodo = "identidad_sin_codigo"

    evento = EventoAcceso(
        origen="residente",
        direccion=direccion,
        acceso_id=tranca.id,
        residente_id=residente.id,
        guardia_id=usuario_actual.id,
        foto_identidad=foto_nombre,
        # Así el historial distingue este acceso de uno hecho con tarjeta,
        # con QR o por la Raspberry Pi.
        metodo=metodo,
    )
    db.session.add(evento)
    db.session.commit()

    return jsonify({"data": {
        "evento": evento.to_dict(),
        "mensaje": f"{direccion.capitalize()} registrada para {residente.usuario.nombre}",
    }}), 201


# =====================================================================
# ACCESO DE PROVEEDORES (Día 69)
# =====================================================================
# Camión de agua, de gas, de refrescos. Antes esto era una apertura manual
# anónima: quedaba registrado que el guardia abrió una tranca, pero no
# quién entró, con qué vehículo ni con autorización de quién.
@guardias_bp.get("/autorizadores")
@roles_required("guardia", "admin", "super_admin")
def listar_autorizadores(usuario_actual):
    """Personas habilitadas para autorizar la entrada de un proveedor."""
    from app.models.visita import AutorizadorProveedor

    q = AutorizadorProveedor.query.filter_by(activo=True)
    if usuario_actual.residencial_id:
        q = q.filter_by(residencial_id=usuario_actual.residencial_id)
    return jsonify({"data": [a.to_dict() for a in q.order_by(AutorizadorProveedor.nombre).all()]})


@guardias_bp.post("/autorizadores")
@roles_required("admin", "super_admin")
def crear_autorizador(usuario_actual):
    from app.models.visita import AutorizadorProveedor

    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return _err("datos_incompletos", "El nombre es obligatorio", 400)

    autorizador = AutorizadorProveedor(
        nombre=nombre,
        cargo=(data.get("cargo") or "").strip() or None,
        residencial_id=residencial_id_heredado(usuario_actual),
    )
    db.session.add(autorizador)
    db.session.commit()
    return jsonify({"data": autorizador.to_dict()}), 201


@guardias_bp.delete("/autorizadores/<autorizador_uuid>")
@roles_required("admin", "super_admin")
def desactivar_autorizador(usuario_actual, autorizador_uuid):
    """Se desactiva, no se borra: los accesos ya registrados tienen que
    seguir mostrando quién los autorizó."""
    from app.models.visita import AutorizadorProveedor

    a = AutorizadorProveedor.query.filter_by(uuid_publico=autorizador_uuid).first()
    if not a:
        return _err("no_encontrado", "Autorizador no encontrado", 404)
    if a.residencial_id and a.residencial_id != usuario_actual.residencial_id:
        return _err("ajeno", "Ese autorizador no pertenece a tu residencial", 403)
    a.activo = False
    db.session.commit()
    return jsonify({"data": {"message": "Autorizador desactivado"}})


@guardias_bp.post("/proveedor/registrar")
@roles_required("guardia")
def registrar_acceso_proveedor(usuario_actual):
    """
    Registra la entrada de un camión de servicio, con evidencia.

    Quién autorizó se elige de la lista que configura administración, no se
    escribe a mano: un campo de texto libre lo llenaría el guardia con
    cualquier cosa y no serviría para auditar nada.
    """
    from app.models.visita import EventoAcceso, AutorizadorProveedor

    empresa = (request.form.get("empresa") or "").strip()
    conductor = (request.form.get("conductor") or "").strip()
    placa = (request.form.get("placa") or "").strip().upper()
    autorizador_uuid = (request.form.get("autorizado_por") or "").strip()
    direccion = (request.form.get("direccion") or "entrada").strip()

    if direccion not in ("entrada", "salida"):
        return _err("direccion_invalida", "La dirección debe ser entrada o salida", 400)
    if not empresa or not conductor:
        return _err("datos_incompletos", "Indicá la empresa y el nombre del conductor", 400)

    autorizador = None
    if autorizador_uuid:
        autorizador = AutorizadorProveedor.query.filter_by(
            uuid_publico=autorizador_uuid, activo=True).first()
        if not autorizador:
            return _err("autorizador_invalido", "Esa autorización no es válida", 400)
        if (autorizador.residencial_id
                and autorizador.residencial_id != usuario_actual.residencial_id):
            return _err("autorizador_ajeno",
                        "Ese autorizador no pertenece a tu residencial", 403)
    elif direccion == "entrada":
        return _err("autorizacion_requerida",
                    "Indicá quién autoriza la entrada de este proveedor", 400)

    tranca, error = _tranca_del_guardia(usuario_actual, request.form.get("acceso_id"))
    if error:
        return error

    foto_nombre = None
    if "foto_identidad" in request.files and request.files["foto_identidad"].filename:
        foto_nombre, err_foto, _t = guardar_imagen_segura(
            request.files["foto_identidad"], _carpeta_accesos(), EXT_IMAGEN)
        if err_foto:
            return _err("imagen_invalida", err_foto, 400)
    elif direccion == "entrada":
        return _err("foto_requerida",
                    "La foto de la identificación del conductor es obligatoria", 400)

    evento = EventoAcceso(
        origen="proveedor",
        direccion=direccion,
        acceso_id=tranca.id,
        guardia_id=usuario_actual.id,
        foto_identidad=foto_nombre,
        metodo="proveedor",
        proveedor_empresa=empresa[:120],
        proveedor_conductor=conductor[:120],
        placa_observada=placa[:20] or None,
        en_vehiculo=bool(placa),
        autorizado_por_id=autorizador.id if autorizador else None,
    )
    db.session.add(evento)
    db.session.commit()

    return jsonify({"data": {
        "evento": evento.to_dict(),
        "mensaje": f"{direccion.capitalize()} registrada para {empresa}",
    }}), 201
