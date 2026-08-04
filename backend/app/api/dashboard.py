"""
Módulo de Dashboard administrativo — estadísticas reales desde la base de datos.

  GET /api/v1/dashboard/metricas       -> tarjetas de métricas (QR hoy, activos, etc.)
  GET /api/v1/dashboard/visitas-tabla  -> tabla de visitas recientes con datos reales
"""
import datetime as dt

from flask import Blueprint, jsonify, current_app, request

from app.extensions import db
from app.models.visita import Visita, EventoAcceso, AccesoFisico
from app.models.cuenta import Cuenta, Unidad, Residente
from app.auth.security import roles_required, token_required, requiere_funcion_plan

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/metricas")
@roles_required("admin", "super_admin")
def metricas(usuario_actual):
    """Tarjetas de métricas del Centro de Monitoreo, calculadas en vivo."""
    # "Hoy" según la hora local de Honduras (UTC-6), no UTC. Antes el día
    # arrancaba a medianoche UTC = 6pm del día anterior en Honduras, así que
    # las métricas "de hoy" estaban corridas 6 horas.
    HN = dt.timezone(dt.timedelta(hours=-6))
    ahora_hn = dt.datetime.now(HN)
    inicio_hn = ahora_hn.replace(hour=0, minute=0, second=0, microsecond=0)
    # Convertir a UTC naive para comparar con created_at (que se guarda en UTC)
    hoy_inicio = inicio_hn.astimezone(dt.timezone.utc).replace(tzinfo=None)

    # Aislación multi-residencial: cada métrica se filtra por la residencial
    # del admin. super_admin/desarrollador ven todo. Los helpers scope_* hacen
    # los joins; residencial_id_filtro decide si aplica filtro.
    from app.utils.residencial import (residencial_id_filtro, scope_visitas,
                                       scope_eventos)
    rid = residencial_id_filtro(usuario_actual)

    # QR generados hoy
    qr_hoy = scope_visitas(Visita.query, usuario_actual).filter(
        Visita.created_at >= hoy_inicio).count()

    # Visitas activas (QR vigente, no usado ni expirado)
    activas = scope_visitas(Visita.query, usuario_actual).filter(
        Visita.estado == "activa").count()

    # QR utilizados (visitas con estado usada)
    usados = scope_visitas(Visita.query, usuario_actual).filter(
        Visita.estado == "usada").count()

    # QR expirados
    expirados = scope_visitas(Visita.query, usuario_actual).filter(
        Visita.estado == "expirada").count()

    # Totales generales — filtrados por residencial del admin
    unidades_q = Unidad.query.filter_by(activa=True)
    cuentas_q = Cuenta.query
    residentes_q = Residente.query.filter_by(activo=True)
    bloqueadas_q = Cuenta.query.filter_by(bloqueada=True)
    if rid is not None:
        unidades_q = unidades_q.filter(Unidad.residencial_id == rid)
        cuentas_q = cuentas_q.join(Unidad, Cuenta.unidad_id == Unidad.id).filter(
            Unidad.residencial_id == rid)
        bloqueadas_q = bloqueadas_q.join(Unidad, Cuenta.unidad_id == Unidad.id).filter(
            Unidad.residencial_id == rid)
        residentes_q = (residentes_q.join(Cuenta, Residente.cuenta_id == Cuenta.id)
                        .join(Unidad, Cuenta.unidad_id == Unidad.id)
                        .filter(Unidad.residencial_id == rid))
    total_unidades = unidades_q.count()
    total_cuentas = cuentas_q.count()
    total_residentes = residentes_q.count()
    cuentas_bloqueadas = bloqueadas_q.count()

    # Accesos registrados hoy
    accesos_hoy = scope_eventos(EventoAcceso.query, usuario_actual).filter(
        EventoAcceso.ocurrido_en >= hoy_inicio).count()

    # Visitas actualmente DENTRO de la residencial (entraron y no han salido)
    adentro_ahora = len(_visitas_adentro(usuario_actual))

    return jsonify({"data": {
        "qr_generados_hoy": qr_hoy,
        "visitantes_activos": activas,
        "qr_utilizados": usados,
        "qr_expirados": expirados,
        "total_unidades": total_unidades,
        "total_cuentas": total_cuentas,
        "total_residentes": total_residentes,
        "cuentas_bloqueadas": cuentas_bloqueadas,
        "accesos_hoy": accesos_hoy,
        "adentro_ahora": adentro_ahora,
    }})


@dashboard_bp.get("/visitas-tabla")
@roles_required("admin", "super_admin")
def visitas_tabla(usuario_actual):
    """Tabla de visitas recientes. El estado mostrado refleja el ÚLTIMO evento de acceso."""
    from sqlalchemy.orm import joinedload
    from app.utils.residencial import scope_visitas

    visitas = (scope_visitas(Visita.query, usuario_actual)
               .options(joinedload(Visita.eventos),
                        joinedload(Visita.residente))
               .order_by(Visita.created_at.desc())
               .limit(40).all())

    # Precargar en bloque las cuentas y unidades necesarias (evita N+1):
    # antes se hacía Cuenta.query.get() + Unidad.query.get() por cada visita.
    cuenta_ids = {v.cuenta_id for v in visitas if v.cuenta_id}
    cuentas = {c.id: c for c in Cuenta.query.filter(Cuenta.id.in_(cuenta_ids)).all()} if cuenta_ids else {}
    unidad_ids = {c.unidad_id for c in cuentas.values() if c.unidad_id}
    unidades = {u.id: u for u in Unidad.query.filter(Unidad.id.in_(unidad_ids)).all()} if unidad_ids else {}

    def _key(e):
        t = e.ocurrido_en
        if t is None:
            return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t

    filas = []
    for v in visitas:
        cuenta = cuentas.get(v.cuenta_id)
        unidad = unidades.get(cuenta.unidad_id) if cuenta else None
        residente_nombre = "—"
        if v.residente and v.residente.usuario:
            residente_nombre = f"{v.residente.usuario.nombre} {v.residente.usuario.apellido}"

        # Estado real basado en el último evento (ya cargado con joinedload)
        if v.eventos:
            ultimo_evento = max(v.eventos, key=_key)
            estado_real = "adentro" if ultimo_evento.direccion == "entrada" else "salio"
        else:
            estado_real = v.estado  # activa, expirada, revocada

        filas.append({
            "id": str(v.uuid_publico),
            "residente": residente_nombre,
            "unidad": unidad.identificador if unidad else "—",
            "visitante": v.nombre_visitante,
            "tipo": v.tipo,
            "estado": estado_real,
            "vigencia": v.valido_hasta.strftime("%Y-%m-%d %H:%M") if v.valido_hasta else "—",
            "creado": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "—",
        })
    return jsonify({"data": filas})


# =====================================================================
# VISITAS ACTUALMENTE DENTRO DE LA RESIDENCIAL
# =====================================================================
def _visitas_adentro(usuario_actual=None):
    """
    Devuelve las visitas que entraron pero aún no han salido.
    Una visita está 'adentro' si su último evento de acceso es una 'entrada'.

    Trae las visitas con entrada y carga TODOS sus eventos en una sola query
    (joinedload), en vez de una query por visita (evita N+1).

    Aislación multi-residencial: si se pasa usuario_actual, solo cuenta las
    visitas de SU residencial (admin); super_admin/desarrollador ven todas.
    """
    from sqlalchemy.orm import joinedload
    from app.utils.residencial import scope_visitas

    # IDs de visitas que tienen al menos un evento de entrada
    ids_con_entrada = [
        row[0] for row in (
            db.session.query(EventoAcceso.visita_id)
            .filter(EventoAcceso.direccion == "entrada")
            .distinct()
            .all()
        )
    ]
    if not ids_con_entrada:
        return []

    # Cargar esas visitas con todos sus eventos de una sola vez, filtradas por
    # la residencial del admin.
    visitas = (
        scope_visitas(Visita.query, usuario_actual)
        .options(joinedload(Visita.eventos))
        .filter(Visita.id.in_(ids_con_entrada))
        .all()
    )

    def _key(e):
        t = e.ocurrido_en
        if t is None:
            return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t

    adentro = []
    for v in visitas:
        if not v.eventos:
            continue
        eventos = sorted(v.eventos, key=_key)
        # Si el último evento es 'entrada', sigue adentro
        if eventos[-1].direccion == "entrada":
            adentro.append((v, eventos))
    return adentro


@dashboard_bp.get("/visitas-activas")
@roles_required("admin", "super_admin")
def visitas_activas(usuario_actual):
    """
    Lista detallada de visitas actualmente DENTRO de la residencial.
    Incluye: quién generó el QR, placa, horas de creación/entrada/salida,
    guardia que autorizó, y fotos tomadas en el ingreso.
    """
    adentro = _visitas_adentro(usuario_actual)

    filas = []
    for v, eventos in adentro:
        cuenta = Cuenta.query.get(v.cuenta_id)
        unidad = Unidad.query.get(cuenta.unidad_id) if cuenta else None

        residente_nombre = "—"
        if v.residente and v.residente.usuario:
            residente_nombre = f"{v.residente.usuario.nombre} {v.residente.usuario.apellido}"

        entrada = next((e for e in eventos if e.direccion == "entrada"), None)
        salida = next((e for e in reversed(eventos) if e.direccion == "salida"), None)

        guardia_nombre = None
        foto_identidad = None
        foto_placa = None
        foto_numero = None
        if entrada:
            guardia_nombre = (
                f"{entrada.guardia.nombre} {entrada.guardia.apellido}"
                if entrada.guardia else None
            )
            foto_identidad = entrada.foto_identidad
            foto_placa = entrada.foto_placa
            foto_numero = entrada.foto_numero_asignado

        filas.append({
            "id": str(v.uuid_publico),
            "visitante": v.nombre_visitante,
            "tipo": v.tipo,
            "empresa": v.empresa,
            "documento_id": v.documento_id,
            "telefono": v.telefono,
            "en_vehiculo": v.en_vehiculo,
            "placa": v.placa_vehiculo or (entrada.placa_vehiculo if entrada else None),
            "residente": residente_nombre,
            "unidad": unidad.identificador if unidad else "—",
            "guardia_autorizo": guardia_nombre,
            "hora_creacion": v.created_at.isoformat() if v.created_at else None,
            "hora_entrada": entrada.ocurrido_en.isoformat() if entrada and entrada.ocurrido_en else None,
            "hora_salida": salida.ocurrido_en.isoformat() if salida and salida.ocurrido_en else None,
            "foto_identidad": foto_identidad,
            "foto_placa": foto_placa,
            "foto_numero_asignado": foto_numero,
        })

    # Ordenar por hora de entrada (más reciente primero)
    filas.sort(key=lambda f: f["hora_entrada"] or "", reverse=True)
    return jsonify({"data": filas})


# =====================================================================
# SERVIR FOTOS TOMADAS POR EL GUARDIA (cédula, placa)
# =====================================================================
@dashboard_bp.get("/fotos/<nombre_archivo>")
@roles_required("admin", "super_admin", "guardia", "cajero", "desarrollador")
def ver_foto(usuario_actual, nombre_archivo):
    from app.utils.archivos import servir_archivo_seguro
    carpeta = current_app.config.get("UPLOAD_FOLDER", "/app/uploads")
    return servir_archivo_seguro(carpeta, nombre_archivo)


# =====================================================================
# HISTORIAL COMPLETO DE ACCESOS (con filtros)
# =====================================================================
@dashboard_bp.get("/historial")
@roles_required("admin", "super_admin")
def historial_accesos(usuario_actual):
    """
    Historial de eventos de acceso con filtros opcionales:
      ?desde=YYYY-MM-DD  ?hasta=YYYY-MM-DD  ?direccion=entrada|salida
      ?buscar=texto (placa, visitante, unidad)  ?pagina=1
    """
    from app.models.visita import Visita

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    direccion = request.args.get("direccion")
    estado_filtro = request.args.get("estado")  # 'adentro' para solo los que están dentro
    buscar = (request.args.get("buscar") or "").strip().lower()
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = 30

    # Solo eventos de VISITAS (los de tarjeta de residente van en su propio
    # historial). Antes traía todos; ahora que existen accesos por tarjeta,
    # cada historial filtra por su origen.
    from app.utils.residencial import scope_eventos
    q = scope_eventos(EventoAcceso.query, usuario_actual).filter(
        EventoAcceso.origen == "visita")
    if desde:
        try:
            q = q.filter(EventoAcceso.ocurrido_en >= dt.datetime.fromisoformat(desde))
        except ValueError:
            pass
    if hasta:
        try:
            fin = dt.datetime.fromisoformat(hasta) + dt.timedelta(days=1)
            q = q.filter(EventoAcceso.ocurrido_en < fin)
        except ValueError:
            pass
    if direccion in ("entrada", "salida"):
        q = q.filter(EventoAcceso.direccion == direccion)

    q = q.order_by(EventoAcceso.ocurrido_en.desc())

    # Para el filtro "adentro" necesitamos saber qué visitas están dentro ahora
    ids_adentro = set()
    if estado_filtro == "adentro":
        for v, _ev in _visitas_adentro():
            ids_adentro.add(v.id)

    total = q.count()
    eventos = q.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    filas = []
    for e in eventos:
        visita = Visita.query.get(e.visita_id) if e.visita_id else None
        visitante = visita.nombre_visitante if visita else "—"
        unidad = "—"
        if visita:
            cuenta = Cuenta.query.get(visita.cuenta_id)
            if cuenta and cuenta.unidad:
                unidad = cuenta.unidad.identificador
        guardia = f"{e.guardia.nombre} {e.guardia.apellido}" if e.guardia else "—"
        placa_declarada = e.placa_vehiculo or (visita.placa_vehiculo if visita else None)
        placa_observada = e.placa_observada
        no_coincide = bool(
            placa_declarada and placa_observada
            and placa_declarada.strip().upper() != placa_observada.strip().upper()
        )

        # Punto de acceso real por el que entró/salió (ACCESS-04, Día 35).
        # Antes no se mostraba en el historial — solo se sabía que existió
        # un evento, no por cuál portón.
        acceso = AccesoFisico.query.get(e.acceso_id) if e.acceso_id else None
        punto_acceso = acceso.punto_acceso if acceso else None
        tranca = acceso.nombre if acceso else None

        # Quién generó/autorizó la visita (el residente) — dato pedido
        # explícitamente por el usuario: "quién lo dejó entrar".
        autorizado_por = None
        if visita and visita.residente and visita.residente.usuario:
            u = visita.residente.usuario
            autorizado_por = f"{u.nombre} {u.apellido}"

        # ¿Esta visita está adentro ahora mismo?
        esta_adentro = visita.id in ids_adentro if visita else False

        # Si se filtra por "adentro", saltar los eventos de visitas que no están dentro
        if estado_filtro == "adentro" and not esta_adentro:
            continue

        fila = {
            "id": str(e.uuid_publico),
            "direccion": e.direccion,
            "visitante": visitante,
            "unidad": unidad,
            "guardia": guardia,
            "placa": placa_declarada,
            "placa_observada": placa_observada,
            "placa_no_coincide": no_coincide,
            "punto_acceso": punto_acceso,
            "tranca": tranca,
            "ocurrido_en": e.ocurrido_en.isoformat() if e.ocurrido_en else None,
            "esta_adentro": esta_adentro,
            "foto_identidad": e.foto_identidad,
            "foto_placa": e.foto_placa,
            "foto_numero_asignado": e.foto_numero_asignado,
            # Datos completos de la visita, para la vista de detalle
            "autorizado_por": autorizado_por,
            "tipo_visita": visita.tipo if visita else None,
            "documento_id": visita.documento_id if visita else None,
            "telefono": visita.telefono if visita else None,
            "empresa": visita.empresa if visita else None,
            "en_vehiculo": visita.en_vehiculo if visita else False,
            "visita_creada_en": visita.created_at.isoformat() if visita and visita.created_at else None,
        }
        # Filtro de texto en memoria (placa/visitante/unidad)
        if buscar:
            blob = f"{visitante} {unidad} {placa_declarada or ''}".lower()
            if buscar not in blob:
                continue
        filas.append(fila)

    return jsonify({"data": {
        "eventos": filas,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
    }})


@dashboard_bp.get("/historial-tarjetas")
@roles_required("admin", "super_admin", "guardia", "desarrollador")
@requiere_funcion_plan("control_fisico")
def historial_accesos_tarjeta(usuario_actual):
    """
    Historial de accesos de RESIDENTES por tarjeta RFID (origen='residente').
    Estos eventos los genera el agente de acceso (Raspberry Pi) al validar una
    tarjeta. Filtros: rango de fechas, dirección, búsqueda por residente/casa.
    """
    from app.models.cuenta import Tarjeta, Residente
    from sqlalchemy.orm import joinedload

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    direccion = request.args.get("direccion")
    buscar = (request.args.get("buscar") or "").strip().lower()
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = 30

    from app.utils.residencial import scope_eventos
    q = scope_eventos(EventoAcceso.query, usuario_actual).filter(
        EventoAcceso.origen == "residente")

    if desde:
        try:
            q = q.filter(EventoAcceso.ocurrido_en >= dt.datetime.fromisoformat(desde))
        except ValueError:
            pass
    if hasta:
        try:
            fin = dt.datetime.fromisoformat(hasta) + dt.timedelta(days=1)
            q = q.filter(EventoAcceso.ocurrido_en < fin)
        except ValueError:
            pass
    if direccion in ("entrada", "salida"):
        q = q.filter(EventoAcceso.direccion == direccion)

    q = q.order_by(EventoAcceso.ocurrido_en.desc())
    total = q.count()
    eventos = q.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    # Precargar tarjetas, residentes y accesos para no hacer N+1
    tarjeta_ids = {e.tarjeta_id for e in eventos if e.tarjeta_id}
    tarjetas = {t.id: t for t in Tarjeta.query.filter(Tarjeta.id.in_(tarjeta_ids)).all()} if tarjeta_ids else {}
    res_ids = {e.residente_id for e in eventos if e.residente_id}
    residentes = ({r.id: r for r in Residente.query
                   .options(joinedload(Residente.usuario))
                   .filter(Residente.id.in_(res_ids)).all()} if res_ids else {})
    acc_ids = {e.acceso_id for e in eventos if e.acceso_id}
    accesos = {a.id: a for a in AccesoFisico.query.filter(AccesoFisico.id.in_(acc_ids)).all()} if acc_ids else {}

    filas = []
    for e in eventos:
        tarjeta = tarjetas.get(e.tarjeta_id)
        residente = residentes.get(e.residente_id)
        acceso = accesos.get(e.acceso_id)
        nombre = "—"
        unidad = "—"
        if residente and residente.usuario:
            nombre = f"{residente.usuario.nombre} {residente.usuario.apellido}"
        if tarjeta:
            cuenta = Cuenta.query.get(tarjeta.cuenta_id)
            if cuenta:
                unidad = cuenta.nombre_completo if hasattr(cuenta, "nombre_completo") else "—"
                if not unidad or unidad == "—":
                    unidad = cuenta.unidad.identificador if cuenta.unidad else "—"
        fila = {
            "id": str(e.uuid_publico),
            "direccion": e.direccion,
            "residente": nombre,
            "unidad": unidad,
            "tarjeta": tarjeta.card_uid if tarjeta else "—",
            "tipo_acceso": tarjeta.tipo_acceso if tarjeta else None,
            "acceso": acceso.nombre if acceso else "—",
            "ocurrido_en": e.ocurrido_en.isoformat() if e.ocurrido_en else None,
        }
        if buscar:
            blob = f"{nombre} {unidad} {fila['tarjeta']}".lower()
            if buscar not in blob:
                continue
        filas.append(fila)

    return jsonify({"data": {
        "eventos": filas,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
    }})
