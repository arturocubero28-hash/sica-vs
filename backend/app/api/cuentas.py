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
import secrets
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Unidad, Cuenta, Residente, Tarjeta, Tarifa, CodigoEnrolamiento, Cuota, SolicitudBaja, Pago
from app.auth.security import roles_required, token_required
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
               direccion_ref=data.get("direccion_ref"),
               # Bases multi-residencial (Día 37): hereda la residencial de
               # quien la crea. Hoy siempre el mismo valor en Villas del Sol.
               residencial_id=residencial_id_heredado(usuario_actual))
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

    # Conteo de cuotas pendientes/vencidas por cuenta, en UNA query (evita N+1).
    pendientes_raw = (db.session.query(Cuota.cuenta_id, func.count(Cuota.id))
                      .filter(Cuota.estado.notin_(["pagada", "en_arreglo"]))
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
            existente = Unidad.query.filter(
                db.func.lower(Unidad.identificador) == ident.lower()).first()
            if existente:
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

    tarifa = None
    dia_pago = 1
    if es_solo_contenedor:
        # El edificio como contenedor no paga cuota — la tarifa es opcional
        pass
    else:
        tarifa = Tarifa.query.get(data.get("tarifa_id"))
        if not tarifa:
            return _err("tarifa_invalida", "La tarifa indicada no existe", 400)
        dia_pago = data.get("dia_pago")
        if not isinstance(dia_pago, int) or not (1 <= dia_pago <= 28):
            return _err("dia_pago_invalido", "El día de pago debe estar entre 1 y 28", 400)

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
    if apartamento and Cuenta.query.filter_by(
            unidad_id=unidad.id, apartamento=apartamento, activa=True).first():
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
                tiene_mora = (
                    getattr(cuenta_prev, "bloqueada", False)
                    or cuenta_prev.estado in ("moroso", "en_mora")
                    or Cuota.query.filter(
                        Cuota.cuenta_id == cuenta_prev.id,
                        Cuota.estado.notin_(["pagada", "en_arreglo"]),
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

    db.session.commit()

    # Generar la PRIMERA CUOTA prorrateada (Día 29).
    # Solo si tiene tarifa asignada (las cuentas contenedoras de edificio no pagan).
    if tarifa:
        try:
            from app.models.cuenta import Cuota, ConfigResidencial
            import calendar
            hoy = dt.date.today()
            cfg = ConfigResidencial.get()
            dia_pago_cfg = cfg.dia_pago

            if hoy.day > dia_pago_cfg:
                # Mes comercial de 30 días SIEMPRE, también para contar los días
                # restantes (no calendario real). Así en meses de 31 días (como
                # julio) no se cobran de más. Ej: hoy es el 7, día de pago es el 1
                # → quedan 30-7=23 días comerciales, no los 25 días reales hasta
                # el 1 de agosto.
                efectivo_dia = min(hoy.day, 30)
                posicion_en_ciclo = ((efectivo_dia - dia_pago_cfg) % 30) + 1  # 1..30
                dias_restantes = 30 - posicion_en_ciclo

                if dias_restantes > 0:
                    monto_diario = float(tarifa.monto) / 30
                    monto_prorrateado = round(monto_diario * dias_restantes, 2)

                    if hoy.month == 12:
                        prox_pago = dt.date(hoy.year + 1, 1, dia_pago_cfg)
                    else:
                        prox_pago = dt.date(hoy.year, hoy.month + 1,
                                            min(dia_pago_cfg, calendar.monthrange(hoy.year, hoy.month + 1)[1]))
                    periodo = dt.date(hoy.year, hoy.month, 1)
                    vencimiento = prox_pago + dt.timedelta(days=cfg.dias_gracia)

                    cuota = Cuota(
                        cuenta_id=cuenta.id, periodo=periodo,
                        monto=monto_prorrateado, fecha_vencimiento=vencimiento,
                        estado="pendiente",
                    )
                    db.session.add(cuota)
                    db.session.commit()
        except Exception:
            pass

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
    """Edita campos configurables de una cuenta (ej. habilitar QR recurrente)."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)
    body = request.get_json(silent=True) or {}
    if "qr_recurrente_habilitado" in body:
        cuenta.qr_recurrente_habilitado = bool(body["qr_recurrente_habilitado"])
    if "tipo_acceso_virtual" in body:
        valor = body["tipo_acceso_virtual"]
        if valor in ("peatonal", "vehicular"):
            cuenta.tipo_acceso_virtual = valor
    if "dia_pago" in body:
        dp = int(body["dia_pago"])
        if 1 <= dp <= 28:
            cuenta.dia_pago = dp
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
    """Da de baja una cuenta. Requisito universal: saldo en 0 (sin cuotas
    pendientes). Al ejecutar: desactiva accesos (usuarios → no pueden crear QR)
    y desactiva todas las tarjetas de proximidad."""
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # ── REQUISITO: saldo en 0 — sin cuotas pendientes ni parciales ──
    cuotas_pendientes = Cuota.query.filter(
        Cuota.cuenta_id == cuenta.id,
        Cuota.estado.in_(["pendiente", "parcial", "vencida", "en_arreglo"]),
    ).all()
    if cuotas_pendientes:
        total_pendiente = sum(float(c.monto) - _monto_pagado_cuota(c) for c in cuotas_pendientes)
        return _err("saldo_pendiente",
                     f"No se puede dar de baja: la cuenta tiene {len(cuotas_pendientes)} cuota(s) "
                     f"pendiente(s) por L {total_pendiente:.2f}. El saldo debe estar en 0. "
                     f"Podés usar 'Nivelar saldo' para prorratear la última cuota.", 400)

    cuenta.activa = False
    cuenta.estado = "baja"

    # ── Suspender acceso a crear QR: desactivar usuarios ──
    for r in cuenta.residentes:
        if r.usuario:
            r.usuario.activo = False

    # ── Desactivar TODAS las tarjetas de la cuenta ──
    tarjetas_desactivadas = 0
    for t in Tarjeta.query.filter_by(cuenta_id=cuenta.id).all():
        if t.estado == "activa":
            t.estado = "desactivada"
            t.fecha_baja = dt.date.today()
            tarjetas_desactivadas += 1

    db.session.commit()
    d = cuenta.to_dict()
    d["tarjetas_desactivadas"] = tarjetas_desactivadas
    return jsonify({"data": d})


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
    cfg = ConfigResidencial.get()
    dia_pago_cfg = cfg.dia_pago

    ajustes = []
    for cuota in cuotas:
        periodo = cuota.periodo  # primer día del mes del período
        # Inicio real del ciclo: día de pago del mes del período
        inicio_ciclo = dt.date(periodo.year, periodo.month, min(dia_pago_cfg, 28))

        # Fijar el monto original SOLO la primera vez — evita que nivelaciones
        # repetidas sigan achicando el monto sobre un valor ya reducido.
        if cuota.monto_original is None:
            cuota.monto_original = cuota.monto
        baseline = float(cuota.monto_original)

        if fecha_des < inicio_ciclo:
            # Se fue antes de que empezara este ciclo → anular la cuota
            cuota.monto = _monto_pagado_cuota(cuota)  # dejarla en lo ya pagado
            cuota.estado = "pagada" if cuota.monto > 0 else "anulada"
            cuota.nivelada = True
            ajustes.append({
                "periodo": periodo.isoformat(),
                "accion": "anulada",
                "monto_original": baseline,
                "monto_final": float(cuota.monto),
            })
        else:
            # Días ocupados dentro del ciclo (mes comercial 30 días)
            dias_ocupados = min((fecha_des - inicio_ciclo).days + 1, 30)
            monto_diario = baseline / 30
            monto_nivelado = round(monto_diario * dias_ocupados, 2)
            pagado = _monto_pagado_cuota(cuota)

            cuota.monto = max(monto_nivelado, pagado)  # nunca menos de lo ya pagado
            cuota.nivelada = True
            if pagado >= cuota.monto:
                cuota.estado = "pagada"
            ajustes.append({
                "periodo": periodo.isoformat(),
                "accion": "prorrateada",
                "dias_ocupados": dias_ocupados,
                "monto_original": baseline,
                "monto_final": float(cuota.monto),
            })

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


# =====================================================================
# RESIDENTES (miembros adicionales)
# =====================================================================
@cuentas_bp.post("/cuentas/<cuenta_uuid>/residentes")
@roles_required("admin", "super_admin")
def agregar_miembro(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

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

    data = request.get_json(silent=True) or {}
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
    db.session.commit()

    return jsonify({"data": {
        "residente": residente.to_dict(),
        "activacion": _bloque_activacion(usuario, token_o_error),
    }}), 201


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

    return jsonify({"data": {
        "activacion": _bloque_activacion(usuario, token_activacion,
                                         nota="Nuevo enlace generado (48h de validez)"),
    }}), 200


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

    # Generar código numérico único de 6 dígitos
    import random
    for _ in range(20):
        codigo = f"{random.randint(0, 999999):06d}"
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

@cuentas_bp.get("/config-residencial")
@roles_required("admin", "super_admin", "desarrollador")
def leer_config_residencial(usuario_actual):
    from app.models.cuenta import ConfigResidencial
    cfg = ConfigResidencial.get()
    return jsonify({"data": cfg.to_dict()})


@cuentas_bp.put("/config-residencial")
@roles_required("admin", "super_admin")
def editar_config_residencial(usuario_actual):
    """Edita día de pago y/o días de gracia. Al cambiar el día de pago,
    se aplica a TODAS las cuentas activas automáticamente."""
    from app.models.cuenta import ConfigResidencial, Cuenta
    cfg = ConfigResidencial.get()
    body = request.get_json(silent=True) or {}

    cambio_dia = False
    if "dia_pago" in body:
        dp = int(body["dia_pago"])
        if 1 <= dp <= 28:
            cfg.dia_pago = dp
            cambio_dia = True
    if "dias_gracia" in body:
        dg = int(body["dias_gracia"])
        if 0 <= dg <= 15:
            cfg.dias_gracia = dg

    # Si cambió el día de pago, aplicar a TODAS las cuentas activas
    actualizadas = 0
    if cambio_dia:
        cuentas = Cuenta.query.filter_by(activa=True).all()
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
    """El admin (o supervisor, vía roles_required) edita el nombre de su
    residencial. El logo se sube aparte (multipart) en el endpoint de abajo."""
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
    db.session.commit()
    return jsonify({"data": r.to_dict()})


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

    nombre_archivo, error = guardar_imagen_segura(
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


@cuentas_bp.get("/mi-residencial/logo/<nombre_archivo>")
@token_required
def ver_logo_residencial(usuario_actual, nombre_archivo):
    """Sirve el archivo del logo. Cualquier usuario autenticado puede verlo
    (es la marca visual que ve toda la residencial, no un dato privado)."""
    from app.models.residencial import Residencial
    existe = Residencial.query.filter_by(logo_archivo=nombre_archivo).first()
    if not existe:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Logo no encontrado"}}), 404
    return servir_archivo_seguro(_carpeta_logos(), nombre_archivo)

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
    q = SolicitudBaja.query
    if estado != "todas":
        q = q.filter_by(estado=estado)
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
