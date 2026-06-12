"""
Módulo de Dashboard administrativo — estadísticas reales desde la base de datos.

  GET /api/v1/dashboard/metricas       -> tarjetas de métricas (QR hoy, activos, etc.)
  GET /api/v1/dashboard/visitas-tabla  -> tabla de visitas recientes con datos reales
"""
import datetime as dt

from flask import Blueprint, jsonify, current_app, request

from app.extensions import db
from app.models.visita import Visita, EventoAcceso
from app.models.cuenta import Cuenta, Unidad, Residente
from app.auth.security import roles_required, token_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/metricas")
@roles_required("admin", "super_admin")
def metricas(usuario_actual):
    """Tarjetas de métricas del Centro de Monitoreo, calculadas en vivo."""
    hoy_inicio = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # QR generados hoy
    qr_hoy = Visita.query.filter(Visita.created_at >= hoy_inicio).count()

    # Visitas activas (QR vigente, no usado ni expirado)
    activas = Visita.query.filter(Visita.estado == "activa").count()

    # QR utilizados (visitas con estado usada)
    usados = Visita.query.filter(Visita.estado == "usada").count()

    # QR expirados
    expirados = Visita.query.filter(Visita.estado == "expirada").count()

    # Totales generales del sistema
    total_unidades = Unidad.query.filter_by(activa=True).count()
    total_cuentas = Cuenta.query.count()
    total_residentes = Residente.query.filter_by(activo=True).count()
    cuentas_bloqueadas = Cuenta.query.filter_by(bloqueada=True).count()

    # Accesos registrados hoy
    accesos_hoy = EventoAcceso.query.filter(EventoAcceso.ocurrido_en >= hoy_inicio).count()

    # Visitas actualmente DENTRO de la residencial (entraron y no han salido)
    adentro_ahora = len(_visitas_adentro())

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
    visitas = (Visita.query
               .order_by(Visita.created_at.desc())
               .limit(40).all())

    filas = []
    for v in visitas:
        cuenta = Cuenta.query.get(v.cuenta_id)
        unidad = Unidad.query.get(cuenta.unidad_id) if cuenta else None
        residente_nombre = "—"
        if v.residente and v.residente.usuario:
            residente_nombre = f"{v.residente.usuario.nombre} {v.residente.usuario.apellido}"

        # Determinar estado real basado en el último evento de acceso
        ultimo_evento = (
            EventoAcceso.query
            .filter_by(visita_id=v.id)
            .order_by(EventoAcceso.ocurrido_en.desc())
            .first()
        )
        if ultimo_evento:
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
def _visitas_adentro():
    """
    Devuelve las visitas que entraron pero aún no han salido.
    Una visita está 'adentro' si su último evento de acceso es una 'entrada'.

    Trae las visitas con entrada y carga TODOS sus eventos en una sola query
    (joinedload), en vez de una query por visita (evita N+1).
    """
    from sqlalchemy.orm import joinedload

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

    # Cargar esas visitas con todos sus eventos de una sola vez
    visitas = (
        Visita.query
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
    adentro = _visitas_adentro()

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
@token_required
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

    q = EventoAcceso.query
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
        placa = e.placa_vehiculo or (visita.placa_vehiculo if visita else None)

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
            "placa": placa,
            "ocurrido_en": e.ocurrido_en.isoformat() if e.ocurrido_en else None,
            "esta_adentro": esta_adentro,
            "foto_identidad": e.foto_identidad,
            "foto_placa": e.foto_placa,
            "foto_numero_asignado": e.foto_numero_asignado,
        }
        # Filtro de texto en memoria (placa/visitante/unidad)
        if buscar:
            blob = f"{visitante} {unidad} {placa or ''}".lower()
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
