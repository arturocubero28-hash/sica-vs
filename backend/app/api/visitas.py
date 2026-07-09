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
import os
import uuid as uuid_lib
import base64

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.visita import Visita, CodigoQR, EventoAcceso
from app.models.cuenta import Cuenta, Residente
from app.auth.security import token_required, roles_required

visitas_bp = Blueprint("visitas", __name__)


def _mi_residente(usuario):
    """Encuentra el registro de Residente activo vinculado a este usuario."""
    return Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()


EXTENSIONES_IMAGEN_VALIDAS = {"webp", "jpg", "jpeg", "png"}


def _guardar_foto_multipart(archivo, prefijo):
    """Guarda una foto subida como multipart (app móvil o web) y devuelve el nombre.
    Preserva la extensión real del archivo (webp, jpg, png) en vez de forzar .jpg —
    la app comprime a WebP antes de subir, así que forzar .jpg guardaría bytes
    WebP con extensión incorrecta."""
    if not archivo or not archivo.filename:
        return None
    try:
        os.makedirs("/app/uploads", exist_ok=True)
        ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else "jpg"
        if ext not in EXTENSIONES_IMAGEN_VALIDAS:
            ext = "jpg"
        nombre = f"{prefijo}_{uuid_lib.uuid4().hex[:12]}.{ext}"
        ruta = f"/app/uploads/{nombre}"
        archivo.save(ruta)
        return nombre
    except Exception:
        return None


def _guardar_foto_base64(b64_data, prefijo):
    """Guarda una foto base64 en /app/uploads y devuelve la ruta."""
    if not b64_data:
        return None
    try:
        os.makedirs("/app/uploads", exist_ok=True)
        nombre = f"{prefijo}_{uuid_lib.uuid4().hex[:12]}.jpg"
        ruta = f"/app/uploads/{nombre}"
        img_bytes = base64.b64decode(b64_data.split(",")[-1])
        with open(ruta, "wb") as f:
            f.write(img_bytes)
        return nombre
    except Exception:
        return None


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
    """Recibe { token } y devuelve los datos de la visita si es válido."""
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
@visitas_bp.post("/accesos/visita")
@roles_required("guardia", "admin", "super_admin")
def registrar_acceso_visita(usuario_actual):
    """Registra la entrada o salida de una visita.
    Acepta JSON (web, fotos en base64) o multipart/form-data (app móvil,
    fotos como archivos). Retrocompatible con ambos.
    """
    # Leer campos desde JSON o desde form (multipart)
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict()
    visita = Visita.query.filter_by(uuid_publico=data.get("visita_id")).first()
    if not visita:
        return jsonify({"error": {"code": "visita_invalida",
                                  "message": "Visita no encontrada"}}), 404

    direccion = data.get("direccion", "entrada")
    if direccion not in ("entrada", "salida"):
        direccion = "entrada"

    # La foto de identidad es OBLIGATORIA para registrar una entrada.
    tiene_foto_id = data.get("foto_identidad") or request.files.get("foto_identidad")
    if direccion == "entrada" and not tiene_foto_id:
        return jsonify({"error": {"code": "foto_requerida",
                                  "message": "La foto de identidad es obligatoria para dar acceso"}}), 400

    tiene_foto_pl = data.get("foto_placa") or request.files.get("foto_placa")
    if direccion == "entrada" and visita.en_vehiculo and not tiene_foto_pl:
        return jsonify({"error": {"code": "foto_placa_requerida",
                                  "message": "La foto de la placa es obligatoria para vehículos"}}), 400

    # Guardar fotos — acepta multipart (app móvil) o base64 en JSON (web)
    foto_id = (_guardar_foto_multipart(request.files.get("foto_identidad"), "id")
               or _guardar_foto_base64(data.get("foto_identidad"), "id"))
    foto_pl = (_guardar_foto_multipart(request.files.get("foto_placa"), "placa")
               or _guardar_foto_base64(data.get("foto_placa"), "placa"))
    foto_num = (_guardar_foto_multipart(request.files.get("foto_numero_asignado"), "numero")
                or _guardar_foto_base64(data.get("foto_numero_asignado"), "numero"))

    evento = EventoAcceso(
        origen="visita",
        direccion=direccion,
        acceso_id=data.get("acceso_id", 1),
        visita_id=visita.id,
        guardia_id=usuario_actual.id,
        foto_identidad=foto_id,
        foto_placa=foto_pl,
        foto_numero_asignado=foto_num,
        en_vehiculo=visita.en_vehiculo,
        placa_vehiculo=visita.placa_vehiculo,
    )
    db.session.add(evento)

    # Actualizar estado de la visita y QR
    if visita.tipo == "unica" and direccion == "entrada":
        visita.estado = "usada"
    # Al registrar salida de visita única, queda como completada (sigue 'usada')

    # El repartidor es de un solo ciclo: al registrar su SALIDA queda usado
    # y no se puede volver a escanear.
    if visita.tipo == "repartidor" and direccion == "salida":
        visita.estado = "usada"
    if visita.qr:
        visita.qr.usos += 1

    db.session.commit()

    # Notificar al residente que autorizó la visita (async, no bloquea el registro)
    try:
        from app.services import notificaciones as _notif
        if visita.cuenta_id:
            nombre = visita.nombre_visitante or "Tu visita"
            tipo = visita.tipo  # unica | recurrente | repartidor

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
