"""
Módulo de Arreglos de Pago — /api/v1/arreglos/

Permite negociar planes de pago para cuentas morosas:
- Congela cuotas vencidas (dejan de generar mora / bloqueo)
- Genera un calendario de abonos (sin recargo: solo difiere la deuda)
- Reactiva el acceso al crear el arreglo
- Cobro de abonos en ventanilla (efectivo / POS)
- Incumplimiento: si un abono pasa sus días de gracia, el arreglo se marca
  incumplido, las cuotas se descongelan y la cuenta se bloquea de nuevo.
"""
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.cuenta import Cuenta, Cuota, Pago, ArregloPago, AbonoArreglo
from app.auth.security import roles_required

arreglos_bp = Blueprint("arreglos", __name__)

METODOS_VENTANILLA = ("efectivo", "tarjeta_pos")


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _money(x):
    """Redondea a 2 decimales de forma contable."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────────────────────
# Listar arreglos (con filtro por estado)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("")
@roles_required("admin", "super_admin", "cajero")
def listar_arreglos(usuario_actual):
    estado = request.args.get("estado")
    q = ArregloPago.query
    if estado:
        q = q.filter_by(estado=estado)
    q = q.order_by(ArregloPago.created_at.desc())
    arreglos = q.all()
    return jsonify({"data": [a.to_dict() for a in arreglos]})


# ─────────────────────────────────────────────────────────────────────────────
# Detalle de un arreglo
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("/<uuid>")
@roles_required("admin", "super_admin", "cajero")
def detalle_arreglo(usuario_actual, uuid):
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo:
        return _err("no_encontrado", "Arreglo no encontrado", 404)
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Cuotas pendientes de una cuenta (para armar el arreglo)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("/cuenta/<cuenta_uuid>/cuotas-pendientes")
@roles_required("admin", "super_admin")
def cuotas_pendientes_cuenta(usuario_actual, cuenta_uuid):
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Cuotas no pagadas y que NO estén ya en un arreglo activo
    cuotas = (Cuota.query
              .filter(Cuota.cuenta_id == cuenta.id,
                      Cuota.estado.notin_(["pagada", "en_arreglo"]))
              .order_by(Cuota.periodo.asc())
              .all())
    return jsonify({"data": [c.to_dict() for c in cuotas]})


# ─────────────────────────────────────────────────────────────────────────────
# Crear un arreglo de pago
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("")
@roles_required("admin", "super_admin")
def crear_arreglo(usuario_actual):
    """
    Body:
    {
      cuenta_id: uuid,
      cuotas: [uuid, ...],        # cuotas a incluir
      abono_inicial: float,       # opcional, default 0
      num_abonos: int,
      dias_gracia: int,           # default 15
      primer_vencimiento: "YYYY-MM-DD",  # opcional, default +30 días
      nota: str
    }
    """
    data = request.get_json(silent=True) or {}
    cuenta = Cuenta.query.filter_by(uuid_publico=data.get("cuenta_id")).first()
    if not cuenta:
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Regla anti-abuso: una cuenta no puede tener dos arreglos activos
    activo = ArregloPago.query.filter_by(cuenta_id=cuenta.id, estado="activo").first()
    if activo:
        return _err("arreglo_existente",
                    "Esta cuenta ya tiene un arreglo activo. Debe completarse o cancelarse primero.", 409)

    cuota_uuids = data.get("cuotas") or []
    if not cuota_uuids:
        return _err("sin_cuotas", "Debe incluir al menos una cuota en el arreglo", 400)

    cuotas = Cuota.query.filter(
        Cuota.uuid_publico.in_(cuota_uuids),
        Cuota.cuenta_id == cuenta.id,
    ).all()
    if len(cuotas) != len(cuota_uuids):
        return _err("cuota_invalida", "Alguna cuota no existe o no pertenece a esta cuenta", 400)
    for c in cuotas:
        if c.estado in ("pagada", "en_arreglo"):
            return _err("cuota_no_elegible",
                        f"La cuota de {c.periodo.strftime('%B %Y')} no se puede incluir (ya pagada o en otro arreglo)", 400)

    # ── Cálculos financieros ──────────────────────────────────────────────
    deuda_total = _money(sum(Decimal(str(c.monto)) for c in cuotas))
    abono_inicial = _money(data.get("abono_inicial") or 0)
    if abono_inicial < 0 or abono_inicial > deuda_total:
        return _err("abono_invalido", "El abono inicial debe estar entre 0 y la deuda total", 400)

    try:
        num_abonos = int(data.get("num_abonos"))
    except (TypeError, ValueError):
        return _err("num_abonos_invalido", "Número de abonos inválido", 400)
    if num_abonos < 1 or num_abonos > 36:
        return _err("num_abonos_invalido", "El número de abonos debe estar entre 1 y 36", 400)

    saldo_financiado = _money(deuda_total - abono_inicial)
    if saldo_financiado <= 0:
        return _err("sin_saldo",
                    "El abono inicial cubre toda la deuda; no se necesita arreglo (cobre las cuotas directamente)", 400)

    dias_gracia = int(data.get("dias_gracia") or 15)
    if dias_gracia < 1 or dias_gracia > 90:
        dias_gracia = 15

    # Monto por abono: dividir parejo, y el último abono absorbe el redondeo
    monto_base = _money(saldo_financiado / num_abonos)

    # Intervalo entre abonos (en días). Configurable; default 30 (mensual aprox).
    try:
        intervalo_dias = int(data.get("intervalo_dias") or 30)
    except (TypeError, ValueError):
        intervalo_dias = 30
    if intervalo_dias < 1 or intervalo_dias > 90:
        intervalo_dias = 30

    # ── Crear el arreglo ──────────────────────────────────────────────────
    arreglo = ArregloPago(
        cuenta_id=cuenta.id,
        deuda_total=deuda_total,
        abono_inicial=abono_inicial,
        saldo_financiado=saldo_financiado,
        num_abonos=num_abonos,
        monto_por_abono=monto_base,
        dias_gracia=dias_gracia,
        intervalo_dias=intervalo_dias,
        estado="activo",
        creado_por=usuario_actual.id,
        nota=(data.get("nota") or "")[:500],
    )
    db.session.add(arreglo)
    db.session.flush()

    # Congelar las cuotas: pasan a "en_arreglo" y se vinculan
    for c in cuotas:
        c.estado = "en_arreglo"
        c.arreglo_id = arreglo.id

    # ── Generar el calendario de abonos ───────────────────────────────────
    # Numeración: si hay prima, es el abono #1 (vence hoy, a cobrar ya); los
    # abonos del saldo financiado siguen después con el intervalo configurado.
    hoy = dt.date.today()
    numero = 1

    # La PRIMA es el primer abono (vence hoy). NO se auto-cobra: la cobra el
    # cajero o el residente la paga por comprobante, igual que los demás.
    if abono_inicial > 0:
        db.session.add(AbonoArreglo(
            arreglo_id=arreglo.id,
            numero=numero,
            monto=abono_inicial,
            fecha_pactada=hoy,
            estado="pendiente",
        ))
        numero += 1

    # Abonos del saldo financiado, espaciados por intervalo_dias
    acumulado = Decimal("0.00")
    for i in range(1, num_abonos + 1):
        if i < num_abonos:
            monto_abono = monto_base
            acumulado += monto_base
        else:
            monto_abono = _money(saldo_financiado - acumulado)
        fecha_abono = hoy + dt.timedelta(days=intervalo_dias * i)
        db.session.add(AbonoArreglo(
            arreglo_id=arreglo.id,
            numero=numero,
            monto=monto_abono,
            fecha_pactada=fecha_abono,
            estado="pendiente",
        ))
        numero += 1

    # Reactivar el acceso de la cuenta (el arreglo restaura el servicio)
    cuenta.estado = "al_dia"
    cuenta.bloqueada = False

    db.session.commit()
    return jsonify({"data": arreglo.to_dict(con_detalle=True)}), 201


# ─────────────────────────────────────────────────────────────────────────────
# Cobrar un abono (en ventanilla)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("/<uuid>/abonos/<abono_uuid>/cobrar")
@roles_required("cajero", "super_admin")
def cobrar_abono(usuario_actual, uuid, abono_uuid):
    """Registra el pago de un abono EN VENTANILLA (solo cajero).

    El admin no cobra: solo crea y visualiza arreglos. Los abonos se cobran
    desde Caja (cajero) o los paga el residente por comprobante (luego el
    admin lo aprueba, igual que una cuota normal).
    """
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo:
        return _err("no_encontrado", "Arreglo no encontrado", 404)
    if arreglo.estado != "activo":
        return _err("arreglo_no_activo",
                    f"El arreglo está {arreglo.estado}; no se pueden cobrar abonos", 400)

    abono = AbonoArreglo.query.filter_by(uuid_publico=abono_uuid, arreglo_id=arreglo.id).first()
    if not abono:
        return _err("abono_no_encontrado", "Abono no encontrado", 404)
    if abono.estado == "pagado":
        return _err("ya_pagado", "Ese abono ya fue pagado", 400)

    data = request.get_json(silent=True) or {}
    metodo = data.get("metodo")
    if metodo not in METODOS_VENTANILLA:
        return _err("metodo_invalido", "Método debe ser efectivo o tarjeta_pos", 400)

    # Vincular a sesión de caja abierta del cajero (si aplica)
    sesion_id = None
    try:
        from app.models.caja import SesionCaja
        sesion = SesionCaja.query.filter_by(cajero_id=usuario_actual.id, estado="abierta").first()
        if sesion:
            sesion_id = sesion.id
    except Exception:
        pass

    # Registrar el pago (aprobado al instante, como cualquier cobro de ventanilla)
    pago = Pago(
        cuota_id=None,
        cuenta_id=arreglo.cuenta_id,
        subido_por=usuario_actual.id,
        metodo=metodo,
        monto=abono.monto,
        referencia=(data.get("referencia") or f"Abono {abono.numero}/{arreglo.num_abonos} arreglo")[:120],
        estado="aprobado",
        revisado_por=usuario_actual.id,
        revisado_en=dt.datetime.now(dt.timezone.utc),
        sesion_caja_id=sesion_id,
    )
    db.session.add(pago)
    db.session.flush()

    # Asignar número de recibo al abono cobrado
    from app.api.recibos import asignar_recibo
    asignar_recibo(pago)

    abono.estado = "pagado"
    abono.pagado_en = dt.datetime.now(dt.timezone.utc)
    abono.pago_id = pago.id

    # ¿Se completó el arreglo?
    pendientes = [a for a in arreglo.abonos if a.estado == "pendiente"]
    if not pendientes:
        arreglo.estado = "completado"
        arreglo.completado_en = dt.datetime.now(dt.timezone.utc)
        arreglo.motivo_cierre = "Todos los abonos pagados"
        # Las cuotas incluidas pasan a pagadas
        for c in arreglo.cuotas:
            c.estado = "pagada"
        # Asegurar que la cuenta queda al día
        cuenta = arreglo.cuenta
        if cuenta:
            cuenta.estado = "al_dia"
            cuenta.bloqueada = False

    db.session.commit()
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Cancelar un arreglo manualmente (admin)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("/<uuid>/cancelar")
@roles_required("admin", "super_admin")
def cancelar_arreglo(usuario_actual, uuid):
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo:
        return _err("no_encontrado", "Arreglo no encontrado", 404)
    if arreglo.estado != "activo":
        return _err("no_activo", "Solo se puede cancelar un arreglo activo", 400)

    data = request.get_json(silent=True) or {}
    _descongelar_y_bloquear(arreglo, "cancelado",
                            data.get("motivo") or "Cancelado manualmente por la administración")
    db.session.commit()
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Helper: descongelar cuotas y bloquear cuenta (incumplimiento / cancelación)
# ─────────────────────────────────────────────────────────────────────────────
def _descongelar_y_bloquear(arreglo, nuevo_estado, motivo):
    """
    Las cuotas vuelven a estado vencido (se descongelan). La cuenta se bloquea.
    Lo ya abonado NO se pierde: queda registrado en los pagos. El residente
    debe el saldo pendiente.
    """
    arreglo.estado = nuevo_estado
    arreglo.motivo_cierre = motivo[:255]
    hoy = dt.date.today()
    for c in arreglo.cuotas:
        if c.estado == "en_arreglo":
            # Vuelve a vencida (descongelada)
            c.estado = "vencida" if c.fecha_vencimiento < hoy else "pendiente"
    cuenta = arreglo.cuenta
    if cuenta:
        cuenta.estado = "en_mora"
        cuenta.bloqueada = True
