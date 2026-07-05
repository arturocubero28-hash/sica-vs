"""
Módulo de Cuotas y Pagos — /api/v1/cuotas/

Endpoints:
  Residente:
    GET  /mias                        → sus cuotas con estado
    GET  /mias/<uuid_cuota>           → detalle con pagos
    POST /mias/<uuid_cuota>/pagar     → subir comprobante
  Admin:
    GET  /pendientes                  → pagos en revisión
    GET  /todas                       → todas las cuotas (filtrable por estado)
    POST /pagos/<uuid_pago>/revisar   → aprobar o rechazar
    GET  /comprobantes/<archivo>      → servir imagen del comprobante
"""
import os
import datetime as dt

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.cuenta import Cuota, Pago, Residente, Cuenta
from app.auth.security import token_required, roles_required
from app.utils.archivos import guardar_imagen_segura, servir_archivo_seguro, EXT_DOCUMENTO

cuotas_bp = Blueprint("cuotas", __name__)


def _carpeta_comprobantes():
    carpeta = os.path.join(current_app.config["UPLOAD_FOLDER"], "comprobantes")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


# ── RESIDENTE: ver sus cuotas ─────────────────────────────────────────────────
@cuotas_bp.get("/mias")
@token_required
def mis_cuotas(usuario_actual):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuotas = (
        Cuota.query
        .filter_by(cuenta_id=residente.cuenta_id)
        .order_by(Cuota.periodo.desc())
        .all()
    )

    # Serializar cuotas; para las pagadas, adjuntar el pago aprobado (con su
    # número de recibo y fecha) para que el residente pueda ver/descargar el
    # recibo desde el histórico.
    cuotas_dict = []
    for c in cuotas:
        d = c.to_dict()
        if c.estado == "pagada":
            pago_ap = (c.pagos.filter_by(estado="aprobado")
                       .order_by(Pago.revisado_en.desc()).first())
            if pago_ap:
                d["pago"] = {
                    "id": str(pago_ap.uuid_publico),
                    "numero_recibo": pago_ap.numero_recibo,
                    "metodo": pago_ap.metodo,
                    "revisado_en": pago_ap.revisado_en.isoformat() if pago_ap.revisado_en else None,
                }
        elif c.estado == "pendiente":
            # Si el último pago fue rechazado, mostrar el motivo para que el
            # residente sepa por qué y pueda corregir antes de reintentar.
            pago_rechazado = (c.pagos.filter_by(estado="rechazado")
                              .order_by(Pago.revisado_en.desc()).first())
            if pago_rechazado and pago_rechazado.nota_admin:
                d["nota_admin"] = pago_rechazado.nota_admin
        cuotas_dict.append(d)

    # Si la cuenta tiene un arreglo de pago activo, incluir sus abonos para que
    # el residente pueda pagarlos por comprobante desde la app (igual que una
    # cuota). Las cuotas originales quedan "en_arreglo" (congeladas); lo que se
    # paga ahora son los abonos del calendario.
    from app.models.cuenta import ArregloPago
    arreglo = ArregloPago.query.filter_by(
        cuenta_id=residente.cuenta_id, estado="activo"
    ).first()
    abonos = []
    if arreglo:
        for a in sorted(arreglo.abonos, key=lambda x: x.numero):
            abonos.append({
                "abono_id": str(a.uuid_publico),
                "arreglo_id": str(arreglo.uuid_publico),
                "numero": a.numero,
                "total_abonos": arreglo.num_abonos,
                "monto": float(a.monto),
                "fecha_pactada": a.fecha_pactada.isoformat(),
                "estado": a.estado,
            })

    # Historial de pagos APROBADOS del residente (cuotas normales Y abonos de
    # arreglo), con su recibo, para la pestaña de historial. Se arma desde los
    # Pago para incluir todo lo pagado, no solo cuotas.
    from app.models.cuenta import AbonoArreglo, ArregloPago as _Arr
    pagos_ap = (Pago.query
                .filter(Pago.cuenta_id == residente.cuenta_id, Pago.estado == "aprobado")
                .order_by(Pago.revisado_en.desc().nullslast(), Pago.created_at.desc())
                .all())
    historial = []
    for p in pagos_ap:
        # Etiqueta de a qué corresponde el pago
        if p.cuota_id and p.cuota:
            etiqueta = p.cuota.periodo.strftime("%B %Y")
        elif p.abono_id:
            ab = AbonoArreglo.query.get(p.abono_id)
            etiqueta = f"Abono {ab.numero}" if ab else "Abono de arreglo"
        else:
            etiqueta = "Pago"
        historial.append({
            "id": str(p.uuid_publico),
            "etiqueta": etiqueta,
            "monto": float(p.monto),
            "metodo": p.metodo,
            "numero_recibo": p.numero_recibo,
            "fecha": (p.revisado_en or p.created_at).isoformat(),
        })

    return jsonify({"data": {
        "cuotas": cuotas_dict,
        "bloqueada": residente.cuenta.bloqueada if residente.cuenta else False,
        "arreglo": ({"id": str(arreglo.uuid_publico),
                     "saldo_pendiente": arreglo.saldo_pendiente(),
                     "abonos": abonos} if arreglo else None),
        "historial": historial,
    }})


# ── RESIDENTE: detalle de una cuota ──────────────────────────────────────────
@cuotas_bp.get("/mias/<uuid_cuota>")
@token_required
def detalle_cuota(usuario_actual, uuid_cuota):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuota = Cuota.query.filter_by(uuid_publico=uuid_cuota).first()
    if not cuota or cuota.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "NO_ENCONTRADA", "message": "Cuota no encontrada"}}), 404

    return jsonify({"data": cuota.to_dict(con_pagos=True)})


# ── RESIDENTE: subir comprobante ──────────────────────────────────────────────
@cuotas_bp.post("/mias/<uuid_cuota>/pagar")
@token_required
def subir_comprobante(usuario_actual, uuid_cuota):
    residente = Residente.query.filter_by(
        usuario_id=usuario_actual.id, activo=True
    ).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    cuota = Cuota.query.filter_by(uuid_publico=uuid_cuota).first()
    if not cuota or cuota.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "NO_ENCONTRADA", "message": "Cuota no encontrada"}}), 404

    if cuota.estado == "pagada":
        return jsonify({"error": {"code": "YA_PAGADA", "message": "Esta cuota ya está pagada"}}), 400

    # Evitar doble comprobante: si ya hay uno en revisión, no aceptar otro
    if cuota.estado == "en_revision":
        return jsonify({"error": {"code": "YA_EN_REVISION",
                                  "message": "Ya subiste un comprobante para esta cuota. "
                                             "Esperá a que la administración lo revise."}}), 409

    # Validar archivo
    if "comprobante" not in request.files:
        return jsonify({"error": {"code": "SIN_ARCHIVO", "message": "Adjuntá el comprobante"}}), 400

    # Validar monto
    monto_str = request.form.get("monto", "")
    try:
        monto = float(monto_str)
        if monto <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": {"code": "MONTO_INVALIDO", "message": "Indicá un monto válido"}}), 400

    referencia = request.form.get("referencia", "")[:120]

    # Guardar archivo de forma segura (valida tipo real, genera nombre propio)
    nombre_archivo, error = guardar_imagen_segura(
        request.files["comprobante"], _carpeta_comprobantes(), EXT_DOCUMENTO
    )
    if error:
        return jsonify({"error": {"code": "FORMATO_INVALIDO", "message": error}}), 400

    pago = Pago(
        cuota_id=cuota.id,
        cuenta_id=residente.cuenta_id,
        subido_por=usuario_actual.id,
        monto=monto,
        referencia=referencia,
        comprobante_archivo=nombre_archivo,
        estado="en_revision",
    )
    db.session.add(pago)
    cuota.estado = "en_revision"
    db.session.commit()

    return jsonify({"data": pago.to_dict()}), 201


# ── RESIDENTE: subir comprobante de un ABONO de arreglo ───────────────────────
@cuotas_bp.post("/abonos/<uuid_abono>/pagar")
@token_required
def subir_comprobante_abono(usuario_actual, uuid_abono):
    """El residente sube el comprobante de un abono de su arreglo de pago.
    Crea un Pago en revisión vinculado al abono; el admin lo aprueba luego."""
    from app.models.cuenta import AbonoArreglo, ArregloPago
    residente = Residente.query.filter_by(usuario_id=usuario_actual.id, activo=True).first()
    if not residente:
        return jsonify({"error": {"code": "SIN_CUENTA", "message": "No tenés cuenta asociada"}}), 404

    abono = AbonoArreglo.query.filter_by(uuid_publico=uuid_abono).first()
    if not abono:
        return jsonify({"error": {"code": "NO_ENCONTRADO", "message": "Abono no encontrado"}}), 404
    arreglo = ArregloPago.query.get(abono.arreglo_id)
    if not arreglo or arreglo.cuenta_id != residente.cuenta_id:
        return jsonify({"error": {"code": "NO_ENCONTRADO", "message": "Abono no encontrado"}}), 404
    if abono.estado == "pagado":
        return jsonify({"error": {"code": "YA_PAGADO", "message": "Ese abono ya está pagado"}}), 400

    if "comprobante" not in request.files:
        return jsonify({"error": {"code": "SIN_ARCHIVO", "message": "Adjuntá el comprobante"}}), 400
    try:
        monto = float(request.form.get("monto", ""))
        if monto <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": {"code": "MONTO_INVALIDO", "message": "Indicá un monto válido"}}), 400

    referencia = request.form.get("referencia", "")[:120]
    nombre_archivo, error = guardar_imagen_segura(
        request.files["comprobante"], _carpeta_comprobantes(), EXT_DOCUMENTO)
    if error:
        return jsonify({"error": {"code": "FORMATO_INVALIDO", "message": error}}), 400

    pago = Pago(
        cuota_id=None,
        abono_id=abono.id,
        cuenta_id=residente.cuenta_id,
        subido_por=usuario_actual.id,
        monto=monto,
        referencia=referencia or f"Abono {abono.numero}/{arreglo.num_abonos}",
        comprobante_archivo=nombre_archivo,
        estado="en_revision",
    )
    db.session.add(pago)
    db.session.commit()
    return jsonify({"data": pago.to_dict()}), 201
@cuotas_bp.get("/comprobantes/<nombre_archivo>")
@roles_required("admin", "super_admin", "cajero", "desarrollador")
def ver_comprobante(usuario_actual, nombre_archivo):
    # Solo se sirve el archivo si corresponde a un comprobante realmente
    # registrado en un pago. Evita servir archivos arbitrarios de la carpeta
    # aunque alguien adivine o construya un nombre.
    existe = Pago.query.filter_by(comprobante_archivo=nombre_archivo).first()
    if not existe:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Comprobante no encontrado"}}), 404
    return servir_archivo_seguro(_carpeta_comprobantes(), nombre_archivo)


# ── ADMIN: contar pagos pendientes (para notificaciones) ──────────────────────
@cuotas_bp.get("/pendientes/count")
@roles_required("admin")
def contar_pendientes(usuario_actual):
    n = Pago.query.filter_by(estado="en_revision").count()
    return jsonify({"data": {"pendientes": n}})


# ── ADMIN: lista de pagos en revisión (comprobantes subidos) ──────────────────
@cuotas_bp.get("/pendientes")
@roles_required("admin")
def pagos_pendientes(usuario_actual):
    pagos = (
        Pago.query
        .filter_by(estado="en_revision")
        .order_by(Pago.created_at.asc())
        .all()
    )
    resultado = []
    for p in pagos:
        d = p.to_dict()
        d["unidad"] = p.cuenta.unidad.identificador if p.cuenta and p.cuenta.unidad else None
        d["periodo"] = p.cuota.periodo.isoformat() if p.cuota else None
        d["mes_label"] = p.cuota.periodo.strftime("%B %Y") if p.cuota else None
        resultado.append(d)
    return jsonify({"data": resultado})


# ── ADMIN: todas las cuotas ───────────────────────────────────────────────────
@cuotas_bp.get("/todas")
@roles_required("admin")
def todas_las_cuotas(usuario_actual):
    estado = request.args.get("estado")  # filtro opcional
    q = Cuota.query
    if estado:
        q = q.filter_by(estado=estado)
    cuotas = q.order_by(Cuota.periodo.desc()).all()

    resultado = []
    for c in cuotas:
        d = c.to_dict()
        d["unidad"] = c.cuenta.unidad.identificador if c.cuenta and c.cuenta.unidad else None
        resultado.append(d)
    return jsonify({"data": resultado})


# ── ADMIN: aprobar o rechazar pago ────────────────────────────────────────────
@cuotas_bp.post("/pagos/<uuid_pago>/revisar")
@roles_required("admin")
def revisar_pago(usuario_actual, uuid_pago):
    pago = Pago.query.filter_by(uuid_publico=uuid_pago).first()
    if not pago:
        return jsonify({"error": {"code": "NO_ENCONTRADO", "message": "Pago no encontrado"}}), 404

    body = request.get_json() or {}
    accion = body.get("accion")  # "aprobar" | "rechazar"

    if accion not in ("aprobar", "rechazar"):
        return jsonify({
            "error": {"code": "ACCION_INVALIDA", "message": "accion debe ser 'aprobar' o 'rechazar'"}
        }), 400

    nota = (body.get("nota") or "").strip()
    # Al rechazar, la nota es obligatoria: el residente necesita saber por qué
    # se rechazó su comprobante para poder corregir y reintentar.
    if accion == "rechazar" and not nota:
        return jsonify({
            "error": {"code": "NOTA_REQUERIDA",
                      "message": "Indicá el motivo del rechazo para que el residente lo sepa"}
        }), 400

    pago.estado = "aprobado" if accion == "aprobar" else "rechazado"
    pago.nota_admin = nota
    pago.revisado_por = usuario_actual.id
    pago.revisado_en = dt.datetime.utcnow()

    # Obtener la cuenta asociada al pago (necesaria tanto para aprobar como rechazar)
    cuenta = pago.cuenta

    if accion == "aprobar":
        if pago.abono_id:
            # Pago de un abono de arreglo: marcar el abono pagado y, si se
            # completó el arreglo, pasar las cuotas congeladas a pagadas.
            from app.models.cuenta import AbonoArreglo, ArregloPago
            abono = AbonoArreglo.query.get(pago.abono_id)
            if abono:
                abono.estado = "pagado"
                abono.pagado_en = dt.datetime.utcnow()
                abono.pago_id = pago.id
                arr = ArregloPago.query.get(abono.arreglo_id)
                if arr and not [a for a in arr.abonos if a.estado in ("pendiente", "vencido")]:
                    arr.estado = "completado"
                    arr.completado_en = dt.datetime.utcnow()
                    arr.motivo_cierre = "Todos los abonos pagados"
                    for c in arr.cuotas:
                        c.estado = "pagada"
        elif pago.cuota:
            pago.cuota.estado = "pagada"
        # Desbloqueo automático SOLO si ya no quedan cuotas vencidas sin pagar.
        # (Si el residente pagó una cuota pero aún debe otras, sigue bloqueado.)
        if cuenta:
            cuenta.intentar_desbloquear()
        # Asignar número de recibo
        from app.api.recibos import asignar_recibo
        asignar_recibo(pago)
    else:
        # Rechazado: lo pendiente vuelve a su estado anterior para que el
        # residente pueda reintentar el pago desde la app.
        if pago.abono_id:
            from app.models.cuenta import AbonoArreglo
            abono = AbonoArreglo.query.get(pago.abono_id)
            if abono and abono.estado not in ("pagado",):
                # Si ya venció su fecha, vuelve a 'vencido'; si no, 'pendiente'.
                abono.estado = "vencido" if abono.fecha_pactada < dt.date.today() else "pendiente"
        elif pago.cuota:
            pago.cuota.estado = "pendiente"

    db.session.commit()

    # Notificar al residente el resultado de la revisión de su comprobante (async)
    try:
        from app.services import notificaciones as _notif
        if cuenta:
            monto_txt = f"L {pago.monto:,.2f}"
            if accion == "aprobar":
                _notif.notificar_cuenta_async(
                    cuenta.id,
                    "Pago aprobado ✓",
                    f"Tu pago de {monto_txt} fue aprobado. ¡Gracias!",
                    {"tipo": "pago_aprobado"},
                )
            else:
                motivo = f" Motivo: {nota}" if nota else ""
                _notif.notificar_cuenta_async(
                    cuenta.id,
                    "Comprobante rechazado",
                    f"Tu comprobante de {monto_txt} fue rechazado.{motivo}",
                    {"tipo": "pago_rechazado"},
                )
    except Exception:
        pass  # Nunca romper la aprobación por un fallo de notificación

    return jsonify({"data": pago.to_dict()})
@cuotas_bp.post("/generar")
@roles_required("admin")
def generar_cuotas_manual(usuario_actual):
    """Dispara la generación de cuotas del mes en curso sin esperar a Celery."""
    import datetime as _dt
    import calendar as _cal
    hoy = _dt.date.today()
    periodo = _dt.date(hoy.year, hoy.month, 1)

    cuentas = Cuenta.query.filter_by(activa=True).all()
    # Una sola query trae todos los cuenta_id que YA tienen cuota este periodo,
    # en vez de una query de existencia por cada cuenta (evita N+1).
    ya_tienen = {row[0] for row in db.session.query(Cuota.cuenta_id)
                 .filter(Cuota.periodo == periodo).all()}
    creadas = 0
    for cuenta in cuentas:
        if cuenta.id in ya_tienen:
            continue
        if not cuenta.tarifa:
            continue
        # Vencimiento según el día de pago de la cuenta (sin pasarse del último día del mes)
        ultimo_dia = _cal.monthrange(hoy.year, hoy.month)[1]
        dia = min(cuenta.dia_pago or 15, ultimo_dia)
        vencimiento = _dt.date(hoy.year, hoy.month, dia)
        cuota = Cuota(
            cuenta_id=cuenta.id, periodo=periodo,
            monto=float(cuenta.tarifa.monto),
            fecha_vencimiento=vencimiento, estado="pendiente",
        )
        db.session.add(cuota)
        creadas += 1

    db.session.commit()
    return jsonify({"data": {"generadas": creadas, "total_cuentas": len(cuentas)}})


@cuotas_bp.post("/avisar-vencimiento")
@roles_required("admin", "super_admin", "desarrollador")
def avisar_vencimiento_manual(usuario_actual):
    """Dispara manualmente el aviso de cuotas por vencer (para pruebas, sin
    esperar al horario de las 8:00 AM)."""
    from app.tasks.mora import avisar_cuotas_por_vencer
    resultado = avisar_cuotas_por_vencer()
    return jsonify({"data": resultado})


@cuotas_bp.post("/revisar-mora")
@roles_required("admin", "super_admin", "desarrollador")
def revisar_mora_manual(usuario_actual):
    """Dispara manualmente la revisión de mora y sus avisos escalonados
    (para pruebas, sin esperar al horario nocturno)."""
    from app.tasks.mora import revisar_mora
    resultado = revisar_mora()
    return jsonify({"data": resultado})


@cuotas_bp.get("/historial-pagos")
@roles_required("admin", "super_admin", "desarrollador")
def historial_pagos(usuario_actual):
    """
    Historial de pagos para auditoría (admin): cuándo se pagó, cuánto,
    método, quién cobró/registró, y a qué casa corresponde.
    Filtros: rango de fechas, método, búsqueda por casa o titular.
    """
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    metodo = request.args.get("metodo")
    buscar = (request.args.get("buscar") or "").strip().lower()
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = 30

    q = Pago.query.filter(Pago.estado == "aprobado")

    if desde:
        try:
            q = q.filter(Pago.created_at >= dt.datetime.fromisoformat(desde))
        except ValueError:
            pass
    if hasta:
        try:
            fin = dt.datetime.fromisoformat(hasta) + dt.timedelta(days=1)
            q = q.filter(Pago.created_at < fin)
        except ValueError:
            pass
    if metodo:
        q = q.filter(Pago.metodo == metodo)

    q = q.order_by(Pago.created_at.desc())
    todos = q.all()

    # Filtro por casa/titular (en memoria, porque cruza relaciones)
    filtrados = []
    for p in todos:
        cuenta = p.cuenta
        identificador = ""
        titular_nombre = ""
        if cuenta:
            identificador = cuenta.unidad.identificador if cuenta.unidad else ""
            t = cuenta.titular()
            if t and t.usuario:
                titular_nombre = f"{t.usuario.nombre} {t.usuario.apellido}"
        if buscar:
            blob = f"{identificador} {titular_nombre}".lower()
            if buscar not in blob:
                continue
        cobrador = p.uploader
        # Para pagos en ventanilla (efectivo/POS), subido_por es el cajero.
        # Para transferencias, subido_por es el residente → mostramos "Pago del residente"
        if p.metodo in ("efectivo", "tarjeta_pos"):
            cobrado_por = f"{cobrador.nombre} {cobrador.apellido}" if cobrador else "—"
        elif p.metodo == "transferencia":
            cobrado_por = "Pago del residente"
        else:
            cobrado_por = "En línea"
        filtrados.append({
            "id": str(p.uuid_publico),
            "fecha": p.created_at.isoformat() if p.created_at else None,
            "monto": float(p.monto),
            "metodo": p.metodo,
            "referencia": p.referencia,
            "identificador": identificador or "—",
            "titular": titular_nombre or "—",
            "cobrado_por": cobrado_por,
            # Imagen del comprobante (solo transferencias lo tienen): permite
            # volver a verlo desde el historial, no solo el recibo.
            "comprobante_archivo": p.comprobante_archivo or None,
        })

    total = len(filtrados)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    ini = (pagina - 1) * por_pagina
    pagina_items = filtrados[ini:ini + por_pagina]

    return jsonify({"data": {
        "pagos": pagina_items,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total": total,
    }})
