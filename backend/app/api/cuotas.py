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
    return jsonify({"data": [c.to_dict() for c in cuotas]})


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


# ── ADMIN: servir imagen del comprobante ──────────────────────────────────────
@cuotas_bp.get("/comprobantes/<nombre_archivo>")
@token_required
def ver_comprobante(usuario_actual, nombre_archivo):
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

    pago.estado = "aprobado" if accion == "aprobar" else "rechazado"
    pago.nota_admin = body.get("nota", "")
    pago.revisado_por = usuario_actual.id
    pago.revisado_en = dt.datetime.utcnow()

    if accion == "aprobar":
        pago.cuota.estado = "pagada"
        # Desbloqueo automático de la cuenta
        cuenta = pago.cuenta
        cuenta.estado = "al_dia"
        cuenta.bloqueada = False
    else:
        # Rechazado: la cuota vuelve a pendiente para que el residente reintente
        pago.cuota.estado = "pendiente"

    db.session.commit()
    return jsonify({"data": pago.to_dict()})


# ── ADMIN: generar cuotas del mes manualmente (botón en el panel) ─────────────
@cuotas_bp.post("/generar")
@roles_required("admin")
def generar_cuotas_manual(usuario_actual):
    """Dispara la generación de cuotas del mes en curso sin esperar a Celery."""
    import datetime as _dt
    import calendar as _cal
    hoy = _dt.date.today()
    periodo = _dt.date(hoy.year, hoy.month, 1)

    cuentas = Cuenta.query.filter_by(activa=True).all()
    creadas = 0
    for cuenta in cuentas:
        existe = Cuota.query.filter_by(cuenta_id=cuenta.id, periodo=periodo).first()
        if existe:
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
