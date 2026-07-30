"""
Módulo 3 — Endpoints de Visitas, QR y Acceso de Guardia.

Residente:
    POST /api/v1/visitas                    -> genera visita + QR
    GET  /api/v1/visitas/mias               -> historial de visitas del residente
    GET  /api/v1/mi-cuenta                  -> estado de cuenta del residente

Guardia:
    POST /api/v1/qr/validar                 -> valida un token QR
    POST /api/v1/accesos/visita             -> registra entrada/salida de visita
    GET  /api/v1/accesos/recientes          -> últimos eventos de acceso
"""
import datetime as dt
import base64

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.visita import Visita, CodigoQR, EventoAcceso, AccesoFisico
from app.models.cuenta import Cuenta, Residente
from app.auth.security import token_required, roles_required
from app.services.cuota_almacenamiento import guardar_foto_con_cuota
from app.services.storage import eliminar_archivo

visitas_bp = Blueprint("visitas", __name__)


def _mi_residente(usuario):
    """Encuentra el registro de Residente activo vinculado a este usuario."""
    return Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()


EXTENSIONES_IMAGEN_VALIDAS = {"webp", "jpg", "jpeg", "png"}


class ErrorGuardadoFoto(Exception):
    """
    PHOTO-15 (Auditoría Día 39): fallo al persistir una foto de evidencia.

    Antes, los helpers de guardado atrapaban cualquier excepción y devolvían
    None. Como la comprobación de "foto obligatoria" se hacía ANTES de
    guardar (mirando si el dato venía en la petición), un fallo de disco,
    de permisos o un base64 corrupto producía una entrada registrada SIN
    evidencia fotográfica, y nadie se enteraba.

    Ahora el fallo se propaga y el endpoint decide: si la foto era
    obligatoria, se revierte todo; si era opcional, se continúa sin ella.
    """
    pass


def _guardar_foto_multipart(archivo, prefijo, residencial_id=None):
    """Guarda una foto subida como multipart (app móvil o web) y devuelve la clave.
    Preserva la extensión real del archivo (webp, jpg, png) en vez de forzar .jpg —
    la app comprime a WebP antes de subir, así que forzar .jpg guardaría bytes
    WebP con extensión incorrecta.

    PHOTO-15: si el archivo viene pero no se puede guardar, lanza
    ErrorGuardadoFoto en vez de devolver None — así el endpoint puede
    distinguir "no mandó foto" de "mandó foto y falló el guardado".

    Día 50 — sistema de suscripciones: antes escribía directo a
    /app/uploads con os.open(), sin pasar por services/storage.py (la
    abstracción que ya sabe guardar en DigitalOcean Spaces según
    configuración). Eso significaba que, aunque se activara Spaces en
    producción, las fotos de accesos igual quedaban solo en el disco
    local del servidor, sin que nadie se diera cuenta. Ahora pasa por
    guardar_foto_con_cuota(), que además registra el tamaño contra la
    residencial dueña y aplica su cuota de almacenamiento.
    """
    if not archivo or not archivo.filename:
        return None
    try:
        ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else "jpg"
        if ext not in EXTENSIONES_IMAGEN_VALIDAS:
            ext = "jpg"
        contenido_tipo = archivo.mimetype or "image/jpeg"
        clave = guardar_foto_con_cuota(
            archivo.stream, residencial_id, subcarpeta="",
            content_type=contenido_tipo, extension=ext,
        )
        if not clave:
            raise ErrorGuardadoFoto(f"El archivo {prefijo} quedó vacío al guardarse")
        return clave
    except Exception as e:
        if isinstance(e, ErrorGuardadoFoto):
            raise
        current_app.logger.error("PHOTO-15: fallo guardando foto %s: %s", prefijo, e)
        raise ErrorGuardadoFoto(f"No se pudo guardar la foto de {prefijo}") from e


def _guardar_foto_base64(b64_data, prefijo, residencial_id=None):
    """Guarda una foto base64 y devuelve la clave (ver nota de Día 50 en
    _guardar_foto_multipart — mismo cambio de fondo acá).

    PHOTO-15: mismo criterio — si el dato viene pero falla el guardado,
    lanza ErrorGuardadoFoto en vez de devolver None.
    """
    if not b64_data:
        return None
    try:
        img_bytes = base64.b64decode(b64_data.split(",")[-1])
        if not img_bytes:
            raise ErrorGuardadoFoto(f"La foto de {prefijo} llegó vacía")
        import io
        clave = guardar_foto_con_cuota(
            io.BytesIO(img_bytes), residencial_id, subcarpeta="",
            content_type="image/jpeg", extension="jpg",
        )
        if not clave:
            raise ErrorGuardadoFoto(f"El archivo {prefijo} quedó vacío al guardarse")
        return clave
    except Exception as e:
        if isinstance(e, ErrorGuardadoFoto):
            raise
        current_app.logger.error("PHOTO-15: fallo guardando foto base64 %s: %s", prefijo, e)
        raise ErrorGuardadoFoto(f"No se pudo guardar la foto de {prefijo}") from e


def _borrar_ruta(clave):
    """PHOTO-15: borra una foto ya guardada por su clave, sin fallar si no existe.
    Día 50: usa la abstracción de storage (eliminar_archivo), no os.remove()
    directo — funciona igual en modo local o en modo Spaces."""
    if not clave:
        return
    try:
        eliminar_archivo(clave)
    except Exception as e:
        current_app.logger.warning("PHOTO-15: no se pudo limpiar %s: %s", clave, e)


def _borrar_fotos(*claves):
    """
    PHOTO-15: limpia archivos ya guardados cuando la transacción se
    revierte. Sin esto, un fallo a mitad de camino deja huérfanos que
    nadie referencia y nadie borra nunca.

    Día 50: usa eliminar_archivo() (funciona en local o en Spaces, no
    solo /app/uploads), y además deshace el registro de cuota — si no
    se revirtiera también el FotoAcceso y el contador de la residencial,
    un rollback dejaría "fantasmas" contando espacio que en realidad se
    liberó.
    """
    for clave in claves:
        if not clave:
            continue
        try:
            eliminar_archivo(clave)
            from app.models.foto_acceso import FotoAcceso
            registro = FotoAcceso.query.filter_by(clave=clave).first()
            if registro:
                residencial = registro.residencial
                if residencial:
                    residencial.almacenamiento_usado_bytes = max(
                        0, (residencial.almacenamiento_usado_bytes or 0) - registro.tamano_bytes)
                db.session.delete(registro)
                db.session.commit()
        except Exception as e:
            current_app.logger.warning("PHOTO-15: no se pudo limpiar %s: %s", clave, e)


def _generar_codigo_numerico():
    """Genera un código numérico único de 6 dígitos para delivery.
    Fácil de dictar por teléfono. Reintenta si colisiona."""
    import secrets
    for _ in range(20):
        codigo = f"{secrets.randbelow(900000) + 100000}"  # 6 dígitos, 100000-999999
        existe = CodigoQR.query.filter_by(codigo_numerico=codigo, revocado=False).first()
        if not existe:
            return codigo
    # fallback extremadamente improbable: usar 7 dígitos
    return f"{secrets.randbelow(9000000) + 1000000}"


# =====================================================================
# RESIDENTE: crear visita con QR
# =====================================================================
@visitas_bp.post("")
@token_required
def crear_visita(usuario_actual):
    """Genera una visita y su código QR.
    Body:
      { tipo: "unica"|"recurrente"|"repartidor",
        nombre_visitante, documento_id?, telefono?,
        empresa? (solo repartidor),
        placa_vehiculo?, en_vehiculo: bool,
        valido_hasta? (ISO, solo recurrente),
        modo_recurrencia?: "libre"|"una_por_dia" (solo recurrente)
      }
    """
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"error": {"code": "no_residente",
                                  "message": "No tienes una cuenta de residente activa"}}), 403

    cuenta = residente.cuenta
    if cuenta.bloqueada:
        return jsonify({"error": {"code": "cuenta_bloqueada",
                                  "message": "Tu cuenta está bloqueada por mora. No puedes generar QR."}}), 403

    data = request.get_json(silent=True) or {}
    tipo = data.get("tipo")
    if tipo not in ("unica", "recurrente", "repartidor"):
        return jsonify({"error": {"code": "tipo_invalido",
                                  "message": "El tipo debe ser unica, recurrente o repartidor"}}), 400

    # QR recurrentes: solo si la administración lo habilitó para esta cuenta
    if tipo == "recurrente":
        residente = Residente.query.filter_by(
            usuario_id=usuario_actual.id, activo=True).first()
        cuenta_res = residente.cuenta if residente else None
        if not cuenta_res or not cuenta_res.qr_recurrente_habilitado:
            return jsonify({"error": {"code": "recurrente_no_habilitado",
                                      "message": "La generación de QR recurrentes no está "
                                                  "habilitada para tu cuenta. Solicitalo a "
                                                  "la administración."}}), 403

    nombre = (data.get("nombre_visitante") or "").strip()
    if not nombre:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "El nombre del visitante es obligatorio"}}), 400

    ahora = dt.datetime.utcnow()

    # Red de seguridad anti-duplicado: si esta cuenta acaba de crear una visita
    # idéntica (mismo tipo y nombre) en los últimos 10 segundos, devolver esa
    # misma en vez de crear otra. Evita duplicados por doble clic o reintento.
    reciente = (Visita.query
                .filter(Visita.cuenta_id == cuenta.id,
                        Visita.tipo == tipo,
                        Visita.nombre_visitante == nombre,
                        Visita.created_at >= ahora - dt.timedelta(seconds=10))
                .order_by(Visita.created_at.desc())
                .first())
    if reciente:
        return jsonify({"data": reciente.to_dict()}), 200

    # Calcular vigencia según tipo
    if tipo == "unica":
        valido_hasta = ahora + dt.timedelta(hours=24)
    elif tipo == "recurrente":
        hasta_str = data.get("valido_hasta")
        if not hasta_str:
            return jsonify({"error": {"code": "datos_incompletos",
                                      "message": "Para visita recurrente, indica valido_hasta"}}), 400
        try:
            valido_hasta = dt.datetime.fromisoformat(hasta_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido"}}), 400
    else:  # repartidor
        valido_hasta = ahora + dt.timedelta(hours=6)

    visita = Visita(
        cuenta_id=cuenta.id,
        generada_por=residente.id,
        tipo=tipo,
        nombre_visitante=nombre,
        documento_id=data.get("documento_id"),
        telefono=data.get("telefono"),
        empresa=data.get("empresa") if tipo == "repartidor" else None,
        placa_vehiculo=data.get("placa_vehiculo"),
        en_vehiculo=bool(data.get("en_vehiculo")),
        valido_desde=ahora,
        valido_hasta=valido_hasta,
        modo_recurrencia=data.get("modo_recurrencia") if tipo == "recurrente" else None,
    )
    db.session.add(visita)
    db.session.flush()

    qr = CodigoQR(visita_id=visita.id)
    # Para repartidores/delivery: generar un código numérico corto y dictable
    if tipo == "repartidor":
        qr.codigo_numerico = _generar_codigo_numerico()
    db.session.add(qr)
    db.session.commit()

    return jsonify({"data": visita.to_dict()}), 201


# =====================================================================
# RESIDENTE: mis visitas
# =====================================================================
@visitas_bp.get("/mias")
@token_required
def mis_visitas(usuario_actual):
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"data": []})

    visitas = (Visita.query
               .filter_by(cuenta_id=residente.cuenta_id)
               .order_by(Visita.created_at.desc())
               .limit(50).all())
    return jsonify({"data": [v.to_dict() for v in visitas]})


# =====================================================================
# RESIDENTE: cancelar / revocar una visita propia
# =====================================================================
@visitas_bp.post("/<visita_uuid>/cancelar")
@token_required
def cancelar_visita(usuario_actual, visita_uuid):
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"error": {"code": "no_residente",
                                  "message": "No tienes una cuenta de residente activa"}}), 403

    visita = Visita.query.filter_by(uuid_publico=visita_uuid).first()
    if not visita or visita.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Visita no encontrada"}}), 404

    if visita.estado in ("usada", "expirada", "revocada"):
        return jsonify({"error": {"code": "no_cancelable",
                                  "message": f"No se puede cancelar una visita {visita.estado}"}}), 400

    visita.estado = "revocada"
    # Invalidar también el QR asociado si existe
    if visita.qr:
        visita.qr.revocado = True

    db.session.commit()
    return jsonify({"data": visita.to_dict()})


# =====================================================================
# RESIDENTE: mi cuenta (estado de cuenta simplificado)
# =====================================================================
@visitas_bp.get("/mi-cuenta")
@token_required
def mi_cuenta(usuario_actual):
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"error": {"code": "no_residente",
                                  "message": "No tienes una cuenta de residente activa"}}), 403

    cuenta = residente.cuenta
    return jsonify({"data": {
        "cuenta": cuenta.to_dict(),
        "residente": residente.to_dict(),
    }})


# =====================================================================
# GUARDIA: validar QR
# =====================================================================
@visitas_bp.post("/qr/validar")
@roles_required("guardia", "admin", "super_admin")
def validar_qr(usuario_actual):
    """
    Recibe { token } y devuelve los datos de la visita para que el guardia
    vea nombre, foto de la cuota, dirección sugerida, etc. ANTES de confirmar.

    IMPORTANTE (ACCESS-03, Auditoría Día 35): este endpoint es solo una
    PREVISUALIZACIÓN — no bloquea la fila ni consume el QR. La validación
    real y definitiva ocurre en POST /accesos/visita, que recibe el mismo
    token, vuelve a chequear todo dentro de una transacción con bloqueo de
    fila, y ahí sí es imposible que quede en un estado inconsistente. Nunca
    asumas que porque este endpoint devolvió 'válido', el registro va a
    tener éxito — siempre puede rechazarse en el paso final (por ejemplo,
    si otro guardia lo registró en el segundo exacto entre ambas llamadas).
    """
    data = request.get_json(silent=True) or {}
    token_str = (data.get("token") or "").strip()

    if not token_str:
        return jsonify({"error": {"code": "token_vacio",
                                  "message": "Escanea un código QR o ingresa el código de delivery"}}), 400

    # Si es solo dígitos, buscar por código numérico (delivery). Si no, por token UUID.
    if token_str.isdigit():
        qr = CodigoQR.query.filter_by(codigo_numerico=token_str).first()
    else:
        qr = CodigoQR.query.filter_by(token=token_str).first()
    if not qr:
        return jsonify({"error": {"code": "qr_invalido",
                                  "message": "Código no encontrado"}}), 404

    if qr.revocado:
        return jsonify({"error": {"code": "qr_revocado",
                                  "message": "Este código fue revocado"}}), 400

    visita = qr.visita
    ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

    # CRÍTICO (aislación multi-residencial): el guardia solo puede validar QR de
    # visitas de SU residencial. Sin esto, un guardia de otra residencial podía
    # previsualizar y luego registrar el acceso de una visita ajena.
    from app.utils.residencial import visita_en_residencial_de
    if not visita_en_residencial_de(visita, usuario_actual):
        return jsonify({"error": {"code": "qr_otra_residencial",
                                  "message": "Este código no pertenece a tu residencial"}}), 403

    # ¿La visita está adentro? (último evento fue una entrada sin salida posterior)
    ultimo_evento = (
        EventoAcceso.query
        .filter_by(visita_id=visita.id)
        .order_by(EventoAcceso.ocurrido_en.desc())
        .first()
    )
    esta_adentro = bool(ultimo_evento and ultimo_evento.direccion == "entrada")

    # Si está adentro, SIEMPRE se permite registrar la salida, aunque el código
    # haya vencido o la visita esté marcada como usada/expirada. Físicamente la
    # persona está dentro y hay que poder registrar que salió.
    if esta_adentro:
        cuenta_in = Cuenta.query.get(visita.cuenta_id)
        return jsonify({"data": {
            "visita": visita.to_dict(),
            "valido": True,
            "adentro": True,
            "direccion_sugerida": "salida",
            "cuenta_bloqueada": bool(cuenta_in and cuenta_in.bloqueada),
            "mensaje": "Esta visita está adentro. Puede registrar su SALIDA.",
        }})

    if visita.estado == "expirada":
        return jsonify({"error": {"code": "qr_expirado", "message": "Este código expiró"}}), 400

    if visita.valido_hasta:
        hasta = visita.valido_hasta
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=dt.timezone.utc)
        if ahora > hasta:
            visita.estado = "expirada"
            db.session.commit()
            return jsonify({"error": {"code": "qr_expirado",
                                      "message": "Este código expiró"}}), 400

    if visita.tipo == "unica" and visita.estado == "usada":
        # Visita única ya usada y NO adentro (ya salió): no se puede reutilizar
        return jsonify({"error": {"code": "qr_usado",
                                  "message": "Este código de visita única ya fue utilizado"}}), 400

    # El repartidor también es de un solo uso: entra una vez y sale una vez.
    # Si ya tiene un ciclo completo (entró y salió), no se puede reutilizar.
    if visita.tipo == "repartidor" and visita.estado == "usada":
        return jsonify({"error": {"code": "qr_usado",
                                  "message": "Este código de repartidor ya fue utilizado"}}), 400

    # Estado de la cuenta del residente: si está bloqueada por mora, NO se
    # rechaza la entrada (la mora es del residente, no del visitante), pero se
    # avisa al guardia para que tome la decisión informado.
    cuenta = Cuenta.query.get(visita.cuenta_id)
    cuenta_bloqueada = bool(cuenta and cuenta.bloqueada)

    # Si llegamos aquí, la visita NO está adentro (eso se manejó al inicio).
    # Es una entrada válida nueva.
    return jsonify({"data": {
        "visita": visita.to_dict(),
        "valido": True,
        "adentro": False,
        "direccion_sugerida": "entrada",
        "cuenta_bloqueada": cuenta_bloqueada,
        "mensaje": ("QR válido, pero la cuenta del residente tiene mora."
                    if cuenta_bloqueada else
                    "QR válido. Puede proceder con la validación."),
    }})


# =====================================================================
# GUARDIA: registrar acceso de visita
# =====================================================================
# =====================================================================
# GUARDIA: registrar acceso de visita
#
# ACCESS-03 / ACCESS-04 (Auditoría Día 35): antes esto eran DOS llamadas
# separadas — validar_qr() y luego registrar_acceso_visita() con el
# visita_id suelto. Entre ambas no había ninguna garantía atómica:
#   - Dos guardias/dispositivos podían validar el mismo QR casi
#     simultáneamente y ambos registrar una entrada.
#   - Se podía llamar directo a este endpoint con un visita_id conocido,
#     SIN pasar nunca por validar_qr() — el token nunca se revisaba aquí.
#   - acceso_id venía del cliente sin validar nada (línea hardcodeada
#     'acceso_id': '1' en la app).
#   - La placa que el guardia observaba se descartaba; se guardaba
#     siempre la que el residente declaró al crear la visita.
#
# Ahora este único endpoint recibe el TOKEN del QR (no el visita_id) y
# hace todo dentro de una sola transacción con bloqueo de fila:
#   1. SELECT ... FOR UPDATE sobre el CodigoQR — nadie más puede tocar
#      esta visita hasta que termine esta transacción.
#   2. Revalida token, revocación, expiración y estado de uso — las
#      mismas reglas que antes vivían en validar_qr(), pero ahora
#      dentro del candado.
#   3. Decide entrada/salida en el servidor según el último evento.
#   4. Determina el punto de acceso físico en el servidor (ya no lo
#      envía el cliente).
#   5. Guarda la placa declarada y la observada por separado.
#   6. Marca el QR como usado y confirma todo junto.
# =====================================================================
@visitas_bp.post("/accesos/visita")
@roles_required("guardia", "admin", "super_admin")
def registrar_acceso_visita(usuario_actual):
    """Valida el token QR y registra la entrada/salida en una sola operación
    atómica. Acepta JSON (web, fotos en base64) o multipart/form-data (app
    móvil, fotos como archivos). Retrocompatible con ambos formatos.
    """
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict()

    token_str = (data.get("token") or "").strip()
    if not token_str:
        return jsonify({"error": {"code": "token_requerido",
                                  "message": "Falta el token del código QR"}}), 400

    # PASO 1 — bloquear la fila del QR. Mientras dure esta transacción,
    # ninguna otra petición concurrente puede leer/escribir esta misma
    # fila: PostgreSQL hace esperar a la segunda petición hasta que la
    # primera confirme o revierta. Esto elimina la condición de carrera
    # de doble registro con el mismo QR.
    #
    # of=CodigoQR/Visita: Visita tiene relaciones lazy="joined" (qr,
    # residente, cuenta, etc.) que SQLAlchemy arma como LEFT OUTER JOIN
    # automáticamente. PostgreSQL no permite FOR UPDATE sobre el lado
    # nulo de un outer join ('FeatureNotSupported'), así que hay que
    # decirle explícitamente que bloquee SOLO la tabla principal, no
    # las tablas unidas — encontrado en pruebas del Día 36.
    if token_str.isdigit():
        qr = (CodigoQR.query.filter_by(codigo_numerico=token_str)
              .with_for_update(of=CodigoQR).first())
    else:
        qr = (CodigoQR.query.filter_by(token=token_str)
              .with_for_update(of=CodigoQR).first())
    if not qr:
        return jsonify({"error": {"code": "qr_invalido",
                                  "message": "Código no encontrado"}}), 404
    if qr.revocado:
        return jsonify({"error": {"code": "qr_revocado",
                                  "message": "Este código fue revocado"}}), 400

    # QR-CONC-20 (Auditoría Día 39 · Día 41): NO usar Visita.query.get().
    #
    # La prueba de concurrencia real encontró que 2 de 20 peticiones
    # simultáneas lograban registrar entrada con el mismo QR. La causa:
    #
    #   Query.get() consulta primero el IDENTITY MAP de la sesión y solo va
    #   a la base si el objeto no está cargado. La Visita YA estaba en
    #   memoria — CodigoQR la trae por relación lazy="joined" en la consulta
    #   de arriba. Así que .get() devolvía la copia en memoria SIN ejecutar
    #   el SELECT ... FOR UPDATE y SIN releer el estado actualizado.
    #
    #   Efecto: la segunda petición esperaba correctamente el candado sobre
    #   CodigoQR, pero al despertar seguía viendo la Visita en estado
    #   'activa' (como estaba al cargarla), no el 'usada' que acababa de
    #   escribir la primera. Y registraba una segunda entrada.
    #
    # filter_by().first() siempre emite la consulta, así que el FOR UPDATE
    # se aplica de verdad y se lee el estado recién confirmado.
    #
    # session.refresh() adicional: garantiza que los atributos ya cargados
    # en memoria se descarten y se relean de la base. Sin esto, aunque la
    # consulta se emita, SQLAlchemy podría conservar valores viejos de una
    # carga previa dentro de la misma sesión.
    visita = (Visita.query
              .filter_by(id=qr.visita_id)
              .with_for_update(of=Visita)
              .first())
    if not visita:
        db.session.rollback()
        return jsonify({"error": {"code": "visita_invalida",
                                  "message": "La visita asociada no existe"}}), 404

    # CRÍTICO (aislación multi-residencial): el guardia solo registra accesos de
    # visitas de SU residencial. Este es el endpoint que REALMENTE abre la
    # tranca, así que el chequeo acá es el que de verdad importa. rollback para
    # soltar el candado de fila antes de salir.
    from app.utils.residencial import visita_en_residencial_de
    if not visita_en_residencial_de(visita, usuario_actual):
        db.session.rollback()
        return jsonify({"error": {"code": "qr_otra_residencial",
                                  "message": "Este código no pertenece a tu residencial"}}), 403

    db.session.refresh(visita)
    ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

    # PASO 2 — mismas reglas de validación que antes vivían en validar_qr(),
    # ahora dentro del candado de la transacción.
    ultimo_evento = (
        EventoAcceso.query
        .filter_by(visita_id=visita.id)
        .order_by(EventoAcceso.ocurrido_en.desc())
        .first()
    )
    esta_adentro = bool(ultimo_evento and ultimo_evento.direccion == "entrada")

    if esta_adentro:
        # Si está adentro, SIEMPRE se permite la salida, sin importar
        # vencimiento o estado de uso — la persona está físicamente dentro.
        direccion = "salida"
    else:
        if visita.estado == "expirada":
            return jsonify({"error": {"code": "qr_expirado", "message": "Este código expiró"}}), 400
        if visita.valido_hasta:
            hasta = visita.valido_hasta
            if hasta.tzinfo is None:
                hasta = hasta.replace(tzinfo=dt.timezone.utc)
            if ahora > hasta:
                visita.estado = "expirada"
                db.session.commit()
                return jsonify({"error": {"code": "qr_expirado",
                                          "message": "Este código expiró"}}), 400
        if visita.tipo == "unica" and visita.estado == "usada":
            return jsonify({"error": {"code": "qr_usado",
                                      "message": "Este código de visita única ya fue utilizado"}}), 400
        if visita.tipo == "repartidor" and visita.estado == "usada":
            return jsonify({"error": {"code": "qr_usado",
                                      "message": "Este código de repartidor ya fue utilizado"}}), 400
        direccion = "entrada"

    # PASO 3 — evidencia fotográfica obligatoria para entradas.
    #
    # PHOTO-15 (Auditoría Día 39): esta comprobación previa mira si la foto
    # VINO en la petición, pero no garantiza que se haya podido GUARDAR.
    # Antes, los helpers devolvían None ante cualquier fallo (disco lleno,
    # permisos, base64 corrupto) y el evento se registraba igual, sin
    # evidencia. Ahora se comprueba dos veces: acá que venga, y después
    # del guardado que realmente esté en disco.
    tiene_foto_id = data.get("foto_identidad") or request.files.get("foto_identidad")
    if direccion == "entrada" and not tiene_foto_id:
        return jsonify({"error": {"code": "foto_requerida",
                                  "message": "La foto de identidad es obligatoria para dar acceso"}}), 400

    placa_observada = (data.get("placa_observada") or data.get("placa_vehiculo") or "").strip() or None
    tiene_foto_pl = data.get("foto_placa") or request.files.get("foto_placa")
    if direccion == "entrada" and visita.en_vehiculo and not tiene_foto_pl:
        return jsonify({"error": {"code": "foto_placa_requerida",
                                  "message": "La foto de la placa es obligatoria para vehículos"}}), 400

    # PHOTO-15: el guardado va dentro de un try. Si falla una foto que era
    # obligatoria, se revierte la transacción, se limpian los archivos que
    # sí alcanzaron a escribirse, y se devuelve error — nunca se registra
    # una entrada sin su evidencia.
    foto_id = foto_pl = foto_num = None
    try:
        foto_id = (_guardar_foto_multipart(request.files.get("foto_identidad"), "id", usuario_actual.residencial_id)
                   or _guardar_foto_base64(data.get("foto_identidad"), "id", usuario_actual.residencial_id))
        foto_pl = (_guardar_foto_multipart(request.files.get("foto_placa"), "placa", usuario_actual.residencial_id)
                   or _guardar_foto_base64(data.get("foto_placa"), "placa", usuario_actual.residencial_id))
        foto_num = (_guardar_foto_multipart(request.files.get("foto_numero_asignado"), "numero", usuario_actual.residencial_id)
                    or _guardar_foto_base64(data.get("foto_numero_asignado"), "numero", usuario_actual.residencial_id))
    except ErrorGuardadoFoto as e:
        db.session.rollback()
        _borrar_fotos(foto_id, foto_pl, foto_num)
        current_app.logger.error("PHOTO-15: acceso rechazado por fallo de evidencia: %s", e)
        return jsonify({"error": {"code": "error_guardando_foto",
                                  "message": "No se pudo guardar la evidencia fotográfica. "
                                             "Intentá de nuevo."}}), 500

    # PHOTO-15: verificación posterior al guardado. Cubre el caso en que el
    # helper devolvió None sin lanzar excepción (por ejemplo, un archivo
    # multipart sin filename que no entra por ninguna de las dos ramas).
    if direccion == "entrada" and not foto_id:
        db.session.rollback()
        _borrar_fotos(foto_pl, foto_num)
        return jsonify({"error": {"code": "foto_requerida",
                                  "message": "La foto de identidad es obligatoria para dar acceso"}}), 400

    if direccion == "entrada" and visita.en_vehiculo and not foto_pl:
        db.session.rollback()
        _borrar_fotos(foto_id, foto_num)
        return jsonify({"error": {"code": "foto_placa_requerida",
                                  "message": "La foto de la placa es obligatoria para vehículos"}}), 400

    # PASO 4 — el punto de acceso lo decide el PUNTO ASIGNADO AL GUARDIA que
    # está registrando, no el cliente. ACCESS-04 (Auditoría Día 35): antes
    # la app enviaba siempre '1' sin ninguna validación, y todos los eventos
    # quedaban atribuidos al mismo punto sin importar cuál guardia realmente
    # los registró. Villas del Sol opera con dos puntos de acceso y un
    # guardia fijo por teléfono en cada uno; el guardia elige su punto una
    # vez (POST /guardias/mi-punto-acceso) y queda fijo mientras usa la app.
    if not usuario_actual.punto_acceso_actual:
        # PHOTO-15: este return ocurre DESPUÉS de haber guardado las fotos,
        # así que hay que limpiarlas o quedan huérfanas en /app/uploads.
        db.session.rollback()
        _borrar_fotos(foto_id, foto_pl, foto_num)
        return jsonify({"error": {"code": "sin_punto_asignado",
                                  "message": "No tenés un punto de acceso asignado. "
                                             "Elegí en cuál estás desde el menú del guardia."}}), 400

    tipo_punto = "vehicular" if visita.en_vehiculo else "peatonal"
    direccion_tranca = direccion  # la tranca de entrada/salida vehicular usa la misma dirección del evento
    q_acceso = AccesoFisico.query.filter_by(
        activo=True, tipo=tipo_punto, punto_acceso=usuario_actual.punto_acceso_actual)
    if tipo_punto == "vehicular":
        q_acceso = q_acceso.filter_by(direccion=direccion_tranca)
    acceso = q_acceso.first()
    if not acceso:
        # PHOTO-15: mismo caso — limpiar antes de salir.
        db.session.rollback()
        _borrar_fotos(foto_id, foto_pl, foto_num)
        return jsonify({"error": {"code": "tranca_no_disponible",
                                  "message": f"Tu punto de acceso no tiene tranca "
                                             f"{tipo_punto} de {direccion_tranca} configurada. "
                                             f"Avisá al administrador."}}), 400

    evento = EventoAcceso(
        origen="visita",
        direccion=direccion,
        acceso_id=acceso.id,
        visita_id=visita.id,
        guardia_id=usuario_actual.id,
        foto_identidad=foto_id,
        foto_placa=foto_pl,
        foto_numero_asignado=foto_num,
        en_vehiculo=visita.en_vehiculo,
        placa_vehiculo=visita.placa_vehiculo,     # la que el residente declaró
        placa_observada=placa_observada,           # la que el guardia observó/digitó
    )
    db.session.add(evento)

    # PASO 5 — actualizar estado de visita y consumir el QR, todo dentro
    # de la misma transacción bloqueada.
    if visita.tipo == "unica" and direccion == "entrada":
        visita.estado = "usada"
    if visita.tipo == "repartidor" and direccion == "salida":
        visita.estado = "usada"
    qr.usos += 1

    # PHOTO-15: si el commit falla (deadlock, caída de la base, violación de
    # constraint), las fotos ya están escritas en disco pero el evento no
    # existe — quedarían huérfanas. Se limpian y se devuelve error.
    try:
        db.session.commit()  # libera el bloqueo de fila aquí
    except Exception as e:
        db.session.rollback()
        _borrar_fotos(foto_id, foto_pl, foto_num)
        current_app.logger.error("PHOTO-15: fallo al confirmar el acceso: %s", e)
        return jsonify({"error": {"code": "error_registrando_acceso",
                                  "message": "No se pudo registrar el acceso. Intentá de nuevo."}}), 500

    # Notificar al residente (async, fuera de la transacción crítica)
    try:
        from app.services import notificaciones as _notif
        if visita.cuenta_id:
            nombre = visita.nombre_visitante or "Tu visita"
            tipo = visita.tipo

            if direccion == "entrada":
                if tipo == "repartidor":
                    empresa = f" ({visita.empresa})" if visita.empresa else ""
                    titulo = "Repartidor ingresó 📦"
                    cuerpo = f"{nombre}{empresa} acaba de ingresar a entregar."
                else:
                    titulo = "Visita ingresó 🚪"
                    cuerpo = f"{nombre} acaba de ingresar a la residencial."
            else:
                if tipo == "repartidor":
                    titulo = "Repartidor salió"
                    cuerpo = f"{nombre} ya completó la entrega y salió."
                else:
                    titulo = "Visita salió"
                    cuerpo = f"{nombre} acaba de salir de la residencial."

            _notif.notificar_cuenta_async(
                visita.cuenta_id, titulo, cuerpo,
                {"tipo": "visita_evento", "direccion": direccion,
                 "tipo_qr": tipo},
            )
    except Exception:
        pass  # No romper el registro de acceso por un fallo de notificación

    return jsonify({"data": {
        "evento": evento.to_dict(),
        "mensaje": f"Acceso registrado: {direccion}",
    }}), 201


# =====================================================================
# GUARDIA/ADMIN: eventos recientes
# =====================================================================
@visitas_bp.get("/accesos/recientes")
@roles_required("guardia", "admin", "super_admin")
def accesos_recientes(usuario_actual):
    eventos = (EventoAcceso.query
               .order_by(EventoAcceso.ocurrido_en.desc())
               .limit(30).all())
    resultado = []
    for e in eventos:
        try:
            d = e.to_dict()
            # Enriquecer con nombre del visitante y unidad si viene de una visita
            if e.visita_id:
                visita = Visita.query.get(e.visita_id)
                if visita:
                    d["nombre_visitante"] = visita.nombre_visitante
                    d["tipo_qr"] = visita.tipo
                    if visita.cuenta and getattr(visita.cuenta, "unidad", None):
                        d["unidad"] = visita.cuenta.unidad.identificador
            elif e.residente_id:
                from app.models.cuenta import Residente
                res = Residente.query.get(e.residente_id)
                if res and res.usuario:
                    d["nombre_visitante"] = f"{res.usuario.nombre} {res.usuario.apellido}"
                    d["tipo_qr"] = "residente"
                    if res.cuenta and getattr(res.cuenta, "unidad", None):
                        d["unidad"] = res.cuenta.unidad.identificador
            resultado.append(d)
        except Exception:
            # Un evento con datos corruptos no debe romper toda la lista
            continue
    return jsonify({"data": resultado})


# ─────────────────────────────────────────────────────────────────────────
# NOTA (Día 31): el endpoint GET /<visita_uuid>/qr-imagen fue ELIMINADO.
#
# Generaba con PIL una tarjeta de 1200×1760 px por cada apertura del QR
# (~150 ms de CPU, sin caché). Con 500 familias saturaba los workers de
# Gunicorn en horas pico y dejaba esperando al guardia que escaneaba.
#
# La tarjeta ahora se renderiza en el cliente a partir del campo `qr_token`
# que ya viajaba en el JSON de la visita:
#   - Web:    frontend/src/components/TarjetaQR.tsx  (Canvas API)
#   - Móvil:  lib/widgets/tarjeta_qr.dart            (qr_flutter + RepaintBoundary)
#
# El servidor ya no genera ni sirve ninguna imagen de QR.
# ─────────────────────────────────────────────────────────────────────────
