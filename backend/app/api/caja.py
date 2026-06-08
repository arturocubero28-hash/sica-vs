"""
Módulo de Caja — /api/v1/caja/

Cajero: abrir sesión, registrar pagos en ventanilla, arqueo, cerrar.
Admin: supervisión (ver todas las sesiones, totales).
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.caja import SesionCaja, ConfigCaja, AjusteCaja, SalidaCaja
from app.models.cuenta import Cuenta, Cuota, Pago
from app.models.usuario import Usuario
from app.auth.security import roles_required

caja_bp = Blueprint("caja", __name__)

METODOS_VENTANILLA = ("efectivo", "tarjeta_pos")


def _sesion_abierta_de(usuario):
    return SesionCaja.query.filter_by(cajero_id=usuario.id, estado="abierta").first()


# ── Estado de la caja del cajero actual ───────────────────────────────────────
@caja_bp.get("/estado")
@roles_required("cajero", "admin", "super_admin")
def estado_caja(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"data": {"abierta": False}})
    d = sesion.to_dict(con_pagos=True)
    # Salidas/ingresos pendientes de autorización de esta sesión
    d["salidas_pendientes"] = SalidaCaja.query.filter_by(
        sesion_id=sesion.id, estado="pendiente").count()
    return jsonify({"data": {"abierta": True, "sesion": d}})


# ── Saldo de apertura sugerido (no editable) ──────────────────────────────────
@caja_bp.get("/saldo-apertura")
@roles_required("cajero", "admin", "super_admin")
def saldo_apertura(usuario_actual):
    """Devuelve el fondo con que debe abrir la próxima caja (del cierre anterior)."""
    from app.models.caja import ConfigCaja
    sugerido = ConfigCaja.saldo_apertura_sugerido()
    ultima = (SesionCaja.query.filter_by(estado="cerrada")
              .order_by(SesionCaja.cerrada_en.desc()).first())
    return jsonify({"data": {
        "saldo_apertura": round(sugerido, 2),
        "tiene_cierre_anterior": ultima is not None and ultima.efectivo_contado is not None,
        "cerrada_en": ultima.cerrada_en.isoformat() if ultima and ultima.cerrada_en else None,
    }})


# ── Abrir caja ────────────────────────────────────────────────────────────────
@caja_bp.post("/abrir")
@roles_required("cajero", "admin", "super_admin")
def abrir_caja(usuario_actual):
    if _sesion_abierta_de(usuario_actual):
        return jsonify({"error": {"code": "ya_abierta",
                                  "message": "Ya tenés una caja abierta. Cerrala antes de abrir otra."}}), 400

    # Regla de integridad: no puede haber OTRA caja abierta en el sistema.
    otra_abierta = SesionCaja.query.filter_by(estado="abierta").first()
    if otra_abierta:
        return jsonify({"error": {"code": "otra_caja_abierta",
                                  "message": f"Ya hay una caja abierta por {otra_abierta.cajero.nombre if otra_abierta.cajero else 'otro usuario'}. Debe cerrarse antes de abrir otra."}}), 400

    # El fondo de apertura NO lo decide el cajero: viene del cierre anterior
    # (o del saldo inicial del sistema si es la primera vez).
    from app.models.caja import ConfigCaja
    monto_inicial = ConfigCaja.saldo_apertura_sugerido()

    sesion = SesionCaja(cajero_id=usuario_actual.id, monto_inicial=monto_inicial, estado="abierta")
    db.session.add(sesion)
    db.session.commit()
    return jsonify({"data": sesion.to_dict()}), 201


# ── Registrar pago en ventanilla ──────────────────────────────────────────────
@caja_bp.post("/pago")
@roles_required("cajero", "admin", "super_admin")
def registrar_pago(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja",
                                  "message": "Abrí la caja antes de registrar pagos"}}), 400

    data = request.get_json(silent=True) or {}
    cuota_uuid = data.get("cuota_id")
    metodo = data.get("metodo")
    referencia = (data.get("referencia") or "")[:120]

    if metodo not in METODOS_VENTANILLA:
        return jsonify({"error": {"code": "metodo_invalido",
                                  "message": "Método debe ser efectivo o tarjeta_pos"}}), 400

    cuota = Cuota.query.filter_by(uuid_publico=cuota_uuid).first()
    if not cuota:
        return jsonify({"error": {"code": "cuota_no_encontrada", "message": "Cuota no encontrada"}}), 404
    if cuota.estado == "pagada":
        return jsonify({"error": {"code": "ya_pagada", "message": "Esa cuota ya está pagada"}}), 400

    pago = Pago(
        cuota_id=cuota.id,
        cuenta_id=cuota.cuenta_id,
        subido_por=usuario_actual.id,
        metodo=metodo,
        monto=cuota.monto,
        referencia=referencia,
        estado="aprobado",                 # pago en ventanilla se aprueba al instante
        revisado_por=usuario_actual.id,
        revisado_en=dt.datetime.now(dt.timezone.utc),
        sesion_caja_id=sesion.id,
    )
    db.session.add(pago)

    # Marcar cuota pagada y desbloquear la cuenta
    cuota.estado = "pagada"
    cuenta = cuota.cuenta
    if cuenta:
        cuenta.estado = "al_dia"
        cuenta.bloqueada = False

    # Asignar número de recibo
    from app.api.recibos import asignar_recibo
    db.session.flush()
    asignar_recibo(pago)

    db.session.commit()
    return jsonify({"data": {"pago": pago.to_dict(), "sesion": sesion.to_dict()}}), 201


# ── Cerrar caja (arqueo) ──────────────────────────────────────────────────────
@caja_bp.post("/cerrar")
@roles_required("cajero", "admin", "super_admin")
def cerrar_caja(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja", "message": "No tenés una caja abierta"}}), 400

    data = request.get_json(silent=True) or {}

    # Verificar que no haya salidas/ingresos pendientes de autorización en esta sesión.
    # Si los hay, el arqueo no sería confiable. Se requiere forzar explícitamente.
    pendientes = SalidaCaja.query.filter_by(sesion_id=sesion.id, estado="pendiente").count()
    if pendientes > 0 and not data.get("forzar"):
        return jsonify({"error": {
            "code": "salidas_pendientes",
            "message": f"Tenés {pendientes} salida(s)/ingreso(s) pendiente(s) de autorización. "
                       "Esperá que el admin las resuelva antes de cerrar, o confirmá el cierre de todos modos.",
            "pendientes": pendientes,
        }}), 409

    try:
        efectivo_contado = float(data.get("efectivo_contado", 0))
        pos_contado = float(data.get("pos_contado", 0))
    except ValueError:
        return jsonify({"error": {"code": "monto_invalido", "message": "Montos contados inválidos"}}), 400

    sesion.efectivo_contado = efectivo_contado
    sesion.pos_contado = pos_contado
    sesion.nota_cierre = (data.get("nota") or "")[:255]
    sesion.estado = "cerrada"
    sesion.cerrada_en = dt.datetime.now(dt.timezone.utc)
    db.session.commit()
    return jsonify({"data": sesion.to_dict(con_pagos=True)})


# ── Cuotas pendientes de una cuenta (para buscar en ventanilla) ───────────────
@caja_bp.get("/buscar-cuenta")
@roles_required("cajero", "admin", "super_admin")
def buscar_cuenta(usuario_actual):
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"data": []})

    cuentas = Cuenta.query.filter_by(activa=True).all()
    resultados = []
    for c in cuentas:
        identificador = c.unidad.identificador if c.unidad else ""
        titular = c.titular()
        nombre_titular = f"{titular.usuario.nombre} {titular.usuario.apellido}" if titular and titular.usuario else ""
        blob = f"{identificador} {nombre_titular}".lower()
        if q not in blob:
            continue
        # Cuotas pendientes de esta cuenta
        pendientes = (Cuota.query
                      .filter(Cuota.cuenta_id == c.id, Cuota.estado != "pagada")
                      .order_by(Cuota.periodo.asc()).all())
        resultados.append({
            "cuenta_id": str(c.uuid_publico),
            "identificador": identificador or "Casa",
            "titular": nombre_titular or "— sin titular —",
            "cuotas_pendientes": [{
                "cuota_id": str(q2.uuid_publico),
                "mes_label": q2.periodo.strftime("%B %Y"),
                "monto": float(q2.monto),
                "estado": q2.estado,
            } for q2 in pendientes],
        })
        if len(resultados) >= 10:
            break
    return jsonify({"data": resultados})


# =====================================================================
# SUPERVISIÓN (admin)
# =====================================================================
@caja_bp.get("/sesiones")
@roles_required("admin", "super_admin", "desarrollador")
def listar_sesiones(usuario_actual):
    sesiones = SesionCaja.query.order_by(SesionCaja.abierta_en.desc()).limit(100).all()
    return jsonify({"data": [s.to_dict() for s in sesiones]})


@caja_bp.get("/resumen")
@roles_required("admin", "super_admin", "desarrollador")
def resumen_caja(usuario_actual):
    """
    Saldo de caja del sistema. Fórmula:

      saldo_actual = saldo_inicial_configurado
                   + efectivo cobrado (todos los pagos en efectivo, histórico)
                   - salidas autorizadas (depósitos al banco)
                   + ingresos autorizados (efectivo traído del banco)
                   + ajustes aprobados (descuadres sobrante/faltante)

    NOTA: el monto_inicial de cada sesión NO se suma aquí, porque el fondo de
    apertura proviene del cierre anterior (es dinero ya contado en el saldo
    base). Sumarlo duplicaría el efectivo.
    """
    cfg = ConfigCaja.get()
    saldo_inicial = float(cfg.saldo_inicial)

    sesiones = SesionCaja.query.all()
    total_efectivo = 0.0
    total_pos = 0.0
    total_salidas = 0.0
    total_ingresos = 0.0
    efectivo_en_cajas_abiertas = 0.0
    cajas_abiertas = 0

    for s in sesiones:
        r = s.resumen()
        total_efectivo += r["efectivo"]
        total_pos += r["pos"]
        total_salidas += r["salidas"]
        total_ingresos += r["ingresos"]
        if s.estado == "abierta":
            cajas_abiertas += 1
            # Efectivo físico en la caja abierta = fondo + cobros - salidas + ingresos
            efectivo_en_cajas_abiertas += float(s.monto_inicial) + r["efectivo"] - r["salidas"] + r["ingresos"]

    # Ajustes aprobados (descuadres + conteos físicos)
    ajustes_aprobados = AjusteCaja.query.filter_by(estado="aprobado").all()
    total_ajustes = sum(float(a.monto) for a in ajustes_aprobados if a.tipo in ("sobrante", "faltante", "conteo"))

    # Saldo global del sistema (no incluye monto_inicial de sesiones — ver nota)
    saldo_actual = saldo_inicial + total_efectivo - total_salidas + total_ingresos + total_ajustes

    descuadres_pendientes = AjusteCaja.query.filter(
        AjusteCaja.tipo.in_(["sobrante", "faltante"]), AjusteCaja.estado == "pendiente"
    ).count()
    salidas_pend = SalidaCaja.query.filter_by(estado="pendiente").count()

    return jsonify({"data": {
        "saldo_inicial": saldo_inicial,
        "saldo_actual": round(saldo_actual, 2),
        "total_efectivo_historico": round(total_efectivo, 2),
        "total_pos_historico": round(total_pos, 2),
        "total_salidas_historico": round(total_salidas, 2),
        "total_ingresos_historico": round(total_ingresos, 2),
        "total_ajustes": round(total_ajustes, 2),
        "efectivo_en_cajas_abiertas": round(efectivo_en_cajas_abiertas, 2),
        "cajas_abiertas": cajas_abiertas,
        "descuadres_pendientes": descuadres_pendientes,
        "salidas_pendientes": salidas_pend,
        "actualizado_en": cfg.actualizado_en.isoformat() if cfg.actualizado_en else None,
    }})


@caja_bp.get("/sesiones/<uuid_sesion>")
@roles_required("admin", "super_admin", "desarrollador")
def detalle_sesion(usuario_actual, uuid_sesion):
    s = SesionCaja.query.filter_by(uuid_publico=uuid_sesion).first()
    if not s:
        return jsonify({"error": {"code": "no_encontrada", "message": "Sesión no encontrada"}}), 404
    return jsonify({"data": s.to_dict(con_pagos=True)})


# =====================================================================
# AUTORIZACIÓN CON CLAVE DE DESARROLLADOR
# =====================================================================
def _validar_clave_dev(clave):
    """
    Verifica que la clave corresponda a la contraseña de un usuario
    con rol 'desarrollador' activo. Devuelve el usuario dev o None.
    """
    if not clave:
        return None
    devs = Usuario.query.filter_by(rol="desarrollador", activo=True).all()
    for dev in devs:
        if dev.check_password(clave):
            return dev
    return None


# =====================================================================
# PUNTO 3 — SALDO INICIAL (protegido con clave de desarrollador)
# =====================================================================
@caja_bp.post("/saldo-inicial")
@roles_required("admin", "super_admin", "desarrollador")
def modificar_saldo_inicial(usuario_actual):
    """
    CONFIGURACIÓN INICIAL del sistema (se usa una sola vez al implementar).
    Define el dinero base que había en caja cuando arrancó SICA-VS.
    Para correcciones de operación usar /caja/ajuste-conteo en su lugar.
    """
    data = request.get_json(silent=True) or {}
    clave = data.get("clave_dev")
    try:
        nuevo = float(data.get("saldo_inicial"))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Saldo inicial inválido"}}), 400

    dev = _validar_clave_dev(clave)
    if not dev:
        return jsonify({"error": {"code": "clave_invalida",
                                  "message": "Clave de desarrollador incorrecta"}}), 403

    cfg = ConfigCaja.get()
    anterior = float(cfg.saldo_inicial)
    cfg.saldo_inicial = nuevo
    cfg.actualizado_por = usuario_actual.id

    ajuste = AjusteCaja(
        tipo="saldo_inicial", monto=(nuevo - anterior),
        motivo=f"Saldo inicial del sistema: L{anterior:.2f} -> L{nuevo:.2f}",
        estado="aprobado", reportado_por=usuario_actual.id, aprobado_por=dev.id,
        resuelto_en=dt.datetime.now(dt.timezone.utc),
    )
    db.session.add(ajuste)
    db.session.commit()
    return jsonify({"data": {"saldo_inicial": nuevo}})


@caja_bp.post("/ajuste-conteo")
@roles_required("admin", "super_admin", "desarrollador")
def ajuste_conteo(usuario_actual):
    """
    AJUSTE POR CONTEO FÍSICO (operación normal).
    El responsable cuenta el efectivo real total en caja y declara ese monto.
    El sistema calcula la diferencia con el saldo registrado y crea un ajuste
    contable para que el saldo del sistema quede igual al conteo real.
    Requiere clave del desarrollador. Queda registrado con trazabilidad.
    """
    data = request.get_json(silent=True) or {}
    clave = data.get("clave_dev")
    motivo = (data.get("motivo") or "").strip()[:255]
    try:
        saldo_real = float(data.get("saldo_real"))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Saldo real inválido"}}), 400

    dev = _validar_clave_dev(clave)
    if not dev:
        return jsonify({"error": {"code": "clave_invalida",
                                  "message": "Clave de desarrollador incorrecta"}}), 403

    # Calcular el saldo actual que el sistema tiene registrado
    cfg = ConfigCaja.get()
    saldo_inicial = float(cfg.saldo_inicial)
    sesiones = SesionCaja.query.all()
    total_efectivo = total_salidas = total_ingresos = 0.0
    for s in sesiones:
        r = s.resumen()
        total_efectivo += r["efectivo"]; total_salidas += r["salidas"]; total_ingresos += r["ingresos"]
    ajustes_aprobados = AjusteCaja.query.filter_by(estado="aprobado").all()
    total_ajustes = sum(float(a.monto) for a in ajustes_aprobados if a.tipo in ("sobrante", "faltante", "conteo"))
    saldo_sistema = saldo_inicial + total_efectivo - total_salidas + total_ingresos + total_ajustes

    diferencia = round(saldo_real - saldo_sistema, 2)
    if abs(diferencia) < 0.01:
        return jsonify({"data": {"sin_cambios": True, "saldo_sistema": round(saldo_sistema, 2)}})

    ajuste = AjusteCaja(
        tipo="conteo", monto=diferencia,
        motivo=motivo or f"Ajuste por conteo físico: sistema L{saldo_sistema:.2f} -> real L{saldo_real:.2f}",
        estado="aprobado", reportado_por=usuario_actual.id, aprobado_por=dev.id,
        resuelto_en=dt.datetime.now(dt.timezone.utc),
    )
    db.session.add(ajuste)
    db.session.commit()
    return jsonify({"data": {
        "saldo_anterior": round(saldo_sistema, 2),
        "saldo_nuevo": saldo_real,
        "diferencia": diferencia,
    }})


# =====================================================================
# PUNTO 4 — DESCUADRES (cajero reporta, admin/dev aprueba)
# =====================================================================
@caja_bp.post("/descuadre")
@roles_required("cajero", "admin", "super_admin", "desarrollador")
def reportar_descuadre(usuario_actual):
    """El cajero reporta un sobrante o faltante. Queda pendiente de aprobación."""
    data = request.get_json(silent=True) or {}
    tipo = data.get("tipo")  # sobrante | faltante
    motivo = (data.get("motivo") or "")[:255]
    try:
        monto = abs(float(data.get("monto")))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Monto inválido"}}), 400

    if tipo not in ("sobrante", "faltante"):
        return jsonify({"error": {"code": "tipo_invalido", "message": "Tipo debe ser sobrante o faltante"}}), 400

    # Sobrante suma al saldo (+), faltante resta (-)
    monto_con_signo = monto if tipo == "sobrante" else -monto
    sesion = _sesion_abierta_de(usuario_actual)

    ajuste = AjusteCaja(
        tipo=tipo, monto=monto_con_signo, motivo=motivo,
        estado="pendiente", reportado_por=usuario_actual.id,
        sesion_caja_id=sesion.id if sesion else None,
    )
    db.session.add(ajuste)
    db.session.commit()
    return jsonify({"data": ajuste.to_dict()}), 201


@caja_bp.get("/descuadres")
@roles_required("admin", "super_admin", "desarrollador")
def listar_descuadres(usuario_actual):
    estado = request.args.get("estado")  # filtro opcional
    q = AjusteCaja.query.filter(AjusteCaja.tipo.in_(["sobrante", "faltante"]))
    if estado:
        q = q.filter_by(estado=estado)
    ajustes = q.order_by(AjusteCaja.created_at.desc()).limit(100).all()
    return jsonify({"data": [a.to_dict() for a in ajustes]})


@caja_bp.post("/descuadres/<uuid_ajuste>/resolver")
@roles_required("admin", "super_admin", "desarrollador")
def resolver_descuadre(usuario_actual, uuid_ajuste):
    """Admin/dev aprueba o rechaza un descuadre. Aprobar requiere clave de dev."""
    data = request.get_json(silent=True) or {}
    accion = data.get("accion")  # aprobar | rechazar
    clave = data.get("clave_dev")

    ajuste = AjusteCaja.query.filter_by(uuid_publico=uuid_ajuste).first()
    if not ajuste:
        return jsonify({"error": {"code": "no_encontrado", "message": "Descuadre no encontrado"}}), 404
    if ajuste.estado != "pendiente":
        return jsonify({"error": {"code": "ya_resuelto", "message": "Ese descuadre ya fue resuelto"}}), 400

    if accion == "aprobar":
        dev = _validar_clave_dev(clave)
        if not dev:
            return jsonify({"error": {"code": "clave_invalida",
                                      "message": "Clave de desarrollador incorrecta"}}), 403
        ajuste.estado = "aprobado"
        ajuste.aprobado_por = dev.id
    elif accion == "rechazar":
        ajuste.estado = "rechazado"
        ajuste.aprobado_por = usuario_actual.id
    else:
        return jsonify({"error": {"code": "accion_invalida", "message": "Acción inválida"}}), 400

    ajuste.resuelto_en = dt.datetime.now(dt.timezone.utc)
    db.session.commit()
    return jsonify({"data": ajuste.to_dict()})


# =====================================================================
# SALIDAS DE CAJA (depósitos al banco u otros conceptos)
# =====================================================================
@caja_bp.post("/salida")
@roles_required("cajero", "admin", "super_admin")
def solicitar_salida(usuario_actual):
    """El cajero solicita una salida de efectivo (ej. depósito al banco)."""
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja",
                                  "message": "No tenés una caja abierta"}}), 400
    data = request.get_json(silent=True) or {}
    concepto = (data.get("concepto") or "").strip()
    if not concepto:
        return jsonify({"error": {"code": "concepto_requerido",
                                  "message": "Indicá el concepto (ej. Depósito banco Ficohsa)"}}), 400
    try:
        monto = float(data.get("monto"))
        if monto <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Monto inválido"}}), 400

    salida = SalidaCaja(
        sesion_id=sesion.id, monto=monto, concepto=concepto,
        estado="pendiente", solicitado_por=usuario_actual.id,
    )
    db.session.add(salida)
    db.session.commit()
    return jsonify({"data": salida.to_dict()}), 201


@caja_bp.get("/salidas")
@roles_required("admin", "super_admin", "desarrollador")
def listar_salidas(usuario_actual):
    """Lista todas las salidas. El admin ve los depósitos al banco históricos."""
    estado = request.args.get("estado")
    q = SalidaCaja.query
    if estado:
        q = q.filter_by(estado=estado)
    salidas = q.order_by(SalidaCaja.created_at.desc()).limit(200).all()
    return jsonify({"data": [s.to_dict() for s in salidas]})


@caja_bp.post("/salidas/<uuid_salida>/autorizar")
@roles_required("admin", "super_admin")
def autorizar_salida(usuario_actual, uuid_salida):
    """Admin autoriza o rechaza una salida. Autorizar requiere su contraseña."""
    data = request.get_json(silent=True) or {}
    accion = data.get("accion")  # autorizar | rechazar
    clave = data.get("clave")

    salida = SalidaCaja.query.filter_by(uuid_publico=uuid_salida).first()
    if not salida:
        return jsonify({"error": {"code": "no_encontrada", "message": "Salida no encontrada"}}), 404
    if salida.estado != "pendiente":
        return jsonify({"error": {"code": "ya_resuelta", "message": "Esa salida ya fue resuelta"}}), 400

    if accion == "autorizar":
        if not usuario_actual.check_password(clave or ""):
            return jsonify({"error": {"code": "clave_invalida",
                                      "message": "Contraseña incorrecta"}}), 403
        salida.estado = "autorizada"
        salida.autorizado_por = usuario_actual.id
    elif accion == "rechazar":
        salida.estado = "rechazada"
        salida.autorizado_por = usuario_actual.id
    else:
        return jsonify({"error": {"code": "accion_invalida", "message": "Acción inválida"}}), 400

    salida.resuelto_en = dt.datetime.now(dt.timezone.utc)
    db.session.commit()
    return jsonify({"data": salida.to_dict()})


@caja_bp.get("/salidas/pendientes")
@roles_required("admin", "super_admin")
def salidas_pendientes(usuario_actual):
    """Salidas que están esperando autorización."""
    salidas = SalidaCaja.query.filter_by(estado="pendiente")\
                .order_by(SalidaCaja.created_at.asc()).all()
    return jsonify({"data": [s.to_dict() for s in salidas]})


# =====================================================================
# INGRESOS EXTRAORDINARIOS (traer dinero del banco a la caja)
# =====================================================================
@caja_bp.post("/ingreso")
@roles_required("cajero", "admin", "super_admin")
def solicitar_ingreso(usuario_actual):
    """El cajero registra un ingreso extraordinario (ej. traer efectivo del banco)."""
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja",
                                  "message": "No tenés una caja abierta"}}), 400
    data = request.get_json(silent=True) or {}
    concepto = (data.get("concepto") or "").strip()
    if not concepto:
        return jsonify({"error": {"code": "concepto_requerido",
                                  "message": "Indicá el concepto (ej. Retiro banco Ficohsa)"}}), 400
    try:
        monto = float(data.get("monto"))
        if monto <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Monto inválido"}}), 400

    # Reutilizamos SalidaCaja con tipo negativo para ingresos (pendiente autorización del admin)
    # El concepto lleva prefijo [INGRESO] para distinguirlo
    ingreso = SalidaCaja(
        sesion_id=sesion.id, monto=-monto,  # negativo indica INGRESO (suma al efectivo esperado)
        concepto=f"[INGRESO] {concepto}",
        estado="pendiente", solicitado_por=usuario_actual.id,
    )
    db.session.add(ingreso)
    db.session.commit()
    return jsonify({"data": ingreso.to_dict()}), 201
