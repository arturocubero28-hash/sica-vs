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
from app.auth.security import roles_required, requiere_funcion_plan
from app.extensions import limiter
from app.utils.fechas import mes_es

arreglos_bp = Blueprint("arreglos", __name__)

METODOS_VENTANILLA = ("efectivo", "tarjeta_pos")


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _arreglo_es_mio(arreglo, usuario_actual):
    """
    Día 48: True si el arreglo pertenece a la residencial del usuario.
    Mismo criterio que pertenece_a_mi_residencial (utils/residencial.py),
    pero ArregloPago no tiene residencial_id directo — se resuelve vía
    cuenta→unidad, como el resto de las entidades financieras.
    """
    if usuario_actual.rol in ("super_admin", "desarrollador"):
        return True
    rid_usuario = usuario_actual.residencial_id
    if rid_usuario is None:
        return True
    cuenta = arreglo.cuenta
    unidad = cuenta.unidad if cuenta else None
    rid_arreglo = unidad.residencial_id if unidad else None
    if rid_arreglo is None:
        return True
    return rid_arreglo == rid_usuario


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")

PROPOSITOS = ("ponerse_al_dia", "volver_al_padron")


def _pide_descuento():
    """Para el limitador: solo se cuentan los pedidos que traen descuento
    (son los que prueban una contraseña de administrador)."""
    data = request.get_json(silent=True) or {}
    try:
        return float(data.get("descuento_pct") or 0) <= 0
    except (TypeError, ValueError):
        return False


def _validar_segundo_admin(data, usuario_actual):
    """
    Día 74 — el descuento lo autoriza OTRA persona: un segundo administrador
    escribe su correo y su contraseña en la misma pantalla. Así nadie puede
    perdonarse deudas a solas, y queda constancia de quién lo aprobó.

    Devuelve (usuario_autorizador, None) o (None, respuesta_de_error).
    """
    from app.models.usuario import Usuario
    aut = data.get("autorizacion") or {}
    email = (aut.get("email") or "").strip().lower()
    password = aut.get("password") or ""
    if not email or not password:
        return None, _err("autorizacion_requerida",
                          "Un descuento lo tiene que autorizar un segundo administrador "
                          "con su correo y su contraseña.", 400)
    u = Usuario.query.filter(db.func.lower(Usuario.email) == email).first()
    # Mismo mensaje para "no existe" y "contraseña mala": no se le confirma a
    # nadie qué correos son de administradores.
    if u is None or not u.check_password(password):
        return None, _err("autorizacion_invalida",
                          "El correo o la contraseña del administrador que autoriza no son correctos.", 403)
    if u.id == usuario_actual.id:
        return None, _err("autorizacion_propia",
                          "El descuento no lo puede autorizar la misma persona que arma el arreglo. "
                          "Tiene que ser otro administrador.", 403)
    if not u.activo or u.rol not in ("admin", "super_admin"):
        return None, _err("autorizacion_sin_permiso",
                          "Esa persona no es un administrador activo.", 403)
    if (u.rol != "super_admin" and usuario_actual.residencial_id is not None
            and u.residencial_id != usuario_actual.residencial_id):
        return None, _err("autorizacion_sin_permiso",
                          "Ese administrador no es de esta residencial.", 403)
    return u, None


def _money(x):
    """Redondea a 2 decimales de forma contable."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────────────────────
# Listar arreglos (con filtro por estado)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("")
@roles_required("admin", "super_admin", "cajero")
@requiere_funcion_plan("cuotas")
def listar_arreglos(usuario_actual):
    from app.utils.residencial import scope_por_cuenta
    estado = request.args.get("estado")
    q = scope_por_cuenta(ArregloPago.query, ArregloPago, usuario_actual)
    if estado:
        q = q.filter(ArregloPago.estado == estado)
    q = q.order_by(ArregloPago.created_at.desc())
    arreglos = q.all()
    return jsonify({"data": [a.to_dict() for a in arreglos]})


# ─────────────────────────────────────────────────────────────────────────────
# Detalle de un arreglo
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("/<uuid>")
@roles_required("admin", "super_admin", "cajero")
@requiere_funcion_plan("cuotas")
def detalle_arreglo(usuario_actual, uuid):
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    # Día 48 — hallazgo de auditoría: sin este chequeo, un admin/cajero de
    # otra residencial podía ver el detalle de un arreglo de pago ajeno
    # (deuda, plan de cuotas de un residente) con solo conocer el UUID.
    if not arreglo or not _arreglo_es_mio(arreglo, usuario_actual):
        return _err("no_encontrado", "Arreglo no encontrado", 404)
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Cuotas pendientes de una cuenta (para armar el arreglo)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.get("/cuenta/<cuenta_uuid>/cuotas-pendientes")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def cuotas_pendientes_cuenta(usuario_actual, cuenta_uuid):
    from app.utils.residencial import pertenece_a_mi_residencial
    from app.services.ciclo_casa import tramo_nivelado
    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    # Día 75 — también de la residencial de quien pregunta (antes no se miraba).
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Cuotas no pagadas y que NO estén ya en un arreglo activo
    cuotas = (Cuota.query
              .filter(Cuota.cuenta_id == cuenta.id,
                      Cuota.estado.notin_(["pagada", "en_arreglo", "anulada"]))
              .order_by(Cuota.periodo.asc())
              .all())
    # Día 75 — para un arreglo «para volver al padrón», la cuota del mes en
    # curso entra nivelada hasta hoy. Se manda el cálculo para que el panel
    # lo muestre antes de firmar (es el mismo que aplica crear_arreglo).
    hoy = dt.date.today()
    datos = []
    for c in cuotas:
        d = c.to_dict()
        if (c.periodo.year, c.periodo.month) == (hoy.year, hoy.month) and c.fecha_vencimiento >= hoy:
            d["al_salir_hoy"] = tramo_nivelado(c, hoy)
        datos.append(d)
    return jsonify({"data": datos})


# ─────────────────────────────────────────────────────────────────────────────
# Crear un arreglo de pago
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("")
@limiter.limit("20 per hour", exempt_when=_pide_descuento)
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
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
      nota: str,
      proposito: "ponerse_al_dia" | "volver_al_padron",   # Día 74, obligatorio
      descuento_pct: float,       # opcional, sobre la deuda; sin tope
      autorizacion: {email, password}   # obligatorio si hay descuento
    }
    """
    data = request.get_json(silent=True) or {}
    from app.utils.residencial import pertenece_a_mi_residencial
    cuenta = Cuenta.query.filter_by(uuid_publico=data.get("cuenta_id")).first()
    # Día 75 — también de la residencial de quien lo arma (antes no se miraba:
    # con el uuid de una casa ajena se le podía armar un arreglo).
    if not cuenta or not pertenece_a_mi_residencial(cuenta.unidad, usuario_actual):
        return _err("no_encontrada", "Cuenta no encontrada", 404)

    # Día 74 — para qué se firma. Se pregunta siempre: no todas las casas
    # que firman un arreglo quieren dejar de pagar, y la diferencia decide
    # si después pueden volver al padrón.
    proposito = data.get("proposito")
    if cuenta.es_censo:
        # Una casa que ya está en el padrón no tiene mensualidad que retomar:
        # el arreglo solo puede ser para saldar lo que dejó.
        proposito = "volver_al_padron"
    if proposito not in PROPOSITOS:
        return _err("proposito_requerido",
                    "Indicá para qué se firma el arreglo: ponerse al día y seguir pagando, "
                    "o saldar la deuda y volver al padrón.", 400)

    # Regla anti-abuso: una cuenta no puede tener dos arreglos activos
    activo = ArregloPago.query.filter_by(cuenta_id=cuenta.id, estado="activo").first()
    if activo:
        return _err("arreglo_existente",
                    "Esta cuenta ya tiene un arreglo activo. Debe completarse o cancelarse primero.", 409)

    cuota_uuids = data.get("cuotas") or []
    if not cuota_uuids:
        return _err("sin_cuotas", "Debe incluir al menos una cuota en el arreglo", 400)
    # Día 74 — se convierten a UUID antes de consultar: un texto que no es
    # un UUID hacía reventar la consulta con un 500 en vez de un 400.
    import uuid as _uuid
    try:
        cuota_uuids = [_uuid.UUID(str(x)) for x in cuota_uuids]
    except ValueError:
        return _err("cuota_invalida", "Alguna cuota no existe o no pertenece a esta cuenta", 400)

    cuotas = Cuota.query.filter(
        Cuota.uuid_publico.in_(cuota_uuids),
        Cuota.cuenta_id == cuenta.id,
    ).all()
    if len(cuotas) != len(cuota_uuids):
        return _err("cuota_invalida", "Alguna cuota no existe o no pertenece a esta cuenta", 400)
    for c in cuotas:
        if c.estado in ("pagada", "en_arreglo"):
            return _err("cuota_no_elegible",
                        f"La cuota de {mes_es(c.periodo)} no se puede incluir (ya pagada o en otro arreglo)", 400)

    # Día 75 — si la casa firma para volver al padrón, el arreglo salda TODO
    # lo que debe, incluidos los días que ya vivió este mes: la cuota del mes
    # en curso entra NIVELADA hasta hoy (no por el mes entero). Si el arreglo
    # se cancela o se incumple con la casa todavía en el sistema, esa cuota
    # vuelve a su monto completo (_descongelar_y_bloquear). Una cuota de un
    # mes que todavía no empezó no puede entrar.
    if proposito == "volver_al_padron":
        from app.services.ciclo_casa import nivelar_cuotas
        hoy_ = dt.date.today()
        for c in list(cuotas):
            mes_c, mes_h = (c.periodo.year, c.periodo.month), (hoy_.year, hoy_.month)
            if mes_c > mes_h:
                return _err("cuota_futura",
                            f"La cuota de {MESES[c.periodo.month - 1]} es de un mes que todavía no "
                            "empezó: no puede entrar en el arreglo.", 400)
            if mes_c == mes_h and c.fecha_vencimiento >= hoy_ and not c.nivelada:
                nivelar_cuotas([c], hoy_)
                if c.estado in ("pagada", "anulada"):
                    cuotas.remove(c)   # con lo ya pagado alcanzaba: no queda nada
        if not cuotas:
            db.session.rollback()
            return _err("sin_cuotas", "Con la cuota de este mes cobrada solo hasta hoy, no queda "
                        "nada por incluir en el arreglo.", 400)

    # ── Cálculos financieros ──────────────────────────────────────────────
    deuda_original = _money(sum(Decimal(str(c.monto)) for c in cuotas))

    # Día 74 — descuento sobre la deuda, autorizado por un segundo admin.
    try:
        descuento_pct = _money(data.get("descuento_pct") or 0)
    except Exception:
        return _err("descuento_invalido", "El porcentaje de descuento no es un número", 400)
    if descuento_pct < 0 or descuento_pct >= 100:
        return _err("descuento_invalido",
                    "El descuento tiene que ser mayor que 0 y menor que 100 %. "
                    "Perdonar toda la deuda no es un arreglo de pago.", 400)
    autorizador = None
    descuento_monto = Decimal("0.00")
    if descuento_pct > 0:
        autorizador, err = _validar_segundo_admin(data, usuario_actual)
        if err:
            return err
        descuento_monto = _money(deuda_original * descuento_pct / 100)
    deuda_total = _money(deuda_original - descuento_monto)
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
        proposito=proposito,
        deuda_original=deuda_original,
        descuento_pct=descuento_pct if autorizador else None,
        descuento_monto=descuento_monto if autorizador else None,
        descuento_autorizado_por=autorizador.id if autorizador else None,
        descuento_autorizado_en=dt.datetime.now(dt.timezone.utc) if autorizador else None,
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
@requiere_funcion_plan("cuotas")
def cobrar_abono(usuario_actual, uuid, abono_uuid):
    """Registra el pago de un abono EN VENTANILLA (solo cajero).

    El admin no cobra: solo crea y visualiza arreglos. Los abonos se cobran
    desde Caja (cajero) o los paga el residente por comprobante (luego el
    admin lo aprueba, igual que una cuota normal).
    """
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo or not _arreglo_es_mio(arreglo, usuario_actual):
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

    # ¿Se completó el arreglo? "vencido" también es impago: antes solo se
    # miraban los "pendiente", y un arreglo con abonos atrasados se daba por
    # completado al cobrar el último que estaba al día (Día 74).
    pendientes = [a for a in arreglo.abonos if a.estado in ("pendiente", "vencido")]
    if not pendientes:
        arreglo.estado = "completado"
        arreglo.completado_en = dt.datetime.now(dt.timezone.utc)
        arreglo.motivo_cierre = "Todos los abonos pagados"
        # Las cuotas incluidas pasan a pagadas
        for c in arreglo.cuotas:
            c.estado = "pagada"
        # Asegurar que la cuenta queda al día. intentar_desbloquear y no un
        # desbloqueo a secas: si debe cuotas fuera del arreglo, sigue igual.
        cuenta = arreglo.cuenta
        if cuenta:
            cuenta.intentar_desbloquear()

    db.session.commit()
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Día 74 — cambiar el propósito de un arreglo activo
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("/<uuid>/proposito")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def cambiar_proposito(usuario_actual, uuid):
    """
    Una familia firmó para ponerse al día y a mitad de camino decide volver
    al padrón (o al revés). No hace falta cancelar el arreglo -- cancelarlo
    descongela las cuotas y bloquea la casa --: se cambia el propósito y
    queda anotado en la nota.
    """
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo or not _arreglo_es_mio(arreglo, usuario_actual):
        return _err("no_encontrado", "Arreglo no encontrado", 404)
    if arreglo.estado != "activo":
        return _err("no_activo", "Solo se puede cambiar un arreglo activo", 400)
    data = request.get_json(silent=True) or {}
    nuevo = data.get("proposito")
    if nuevo not in PROPOSITOS:
        return _err("proposito_requerido", "Propósito inválido", 400)
    if arreglo.cuenta and arreglo.cuenta.es_censo and nuevo != "volver_al_padron":
        return _err("casa_en_padron",
                    "La casa ya está en el padrón. Para seguir pagando mensualidad, "
                    "primero tiene que volver a sumarse.", 400)
    # Día 75 — un arreglo para volver al padrón puede tener la cuota del mes
    # cobrada solo hasta el día que se firmó. Si ahora la casa sigue pagando,
    # ese monto ya no corresponde: hay que rehacer el arreglo.
    if nuevo == "ponerse_al_dia" and any(c.nivelada for c in arreglo.cuotas):
        mes = next(MESES[c.periodo.month - 1] for c in arreglo.cuotas if c.nivelada)
        return _err("tiene_cuota_nivelada",
                    f"Este arreglo incluye la cuota de {mes} cobrada solo hasta el día que se firmó, "
                    "porque la casa iba a volver al padrón. Para que siga pagando, cancelalo (esa "
                    "cuota vuelve a su monto completo) y firmá uno nuevo «para ponerse al día».", 409)
    if nuevo != arreglo.proposito:
        hoy = dt.date.today().strftime("%d/%m/%Y")
        quien = f"{usuario_actual.nombre} {usuario_actual.apellido}".strip()
        texto = {"ponerse_al_dia": "ponerse al día", "volver_al_padron": "volver al padrón"}[nuevo]
        arreglo.nota = (f"{arreglo.nota or ''}\n[{hoy}] {quien}: propósito cambiado a «{texto}».").strip()[:500]
        arreglo.proposito = nuevo
        db.session.commit()
    return jsonify({"data": arreglo.to_dict(con_detalle=True)})


# ─────────────────────────────────────────────────────────────────────────────
# Cancelar un arreglo manualmente (admin)
# ─────────────────────────────────────────────────────────────────────────────
@arreglos_bp.post("/<uuid>/cancelar")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def cancelar_arreglo(usuario_actual, uuid):
    arreglo = ArregloPago.query.filter_by(uuid_publico=uuid).first()
    if not arreglo or not _arreglo_es_mio(arreglo, usuario_actual):
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
    cuenta = arreglo.cuenta
    sigue_en_sistema = bool(cuenta and cuenta.activa and not cuenta.es_censo)
    from app.services.ciclo_casa import restaurar_nivelacion
    for c in arreglo.cuotas:
        if c.estado == "en_arreglo":
            # Vuelve a vencida (descongelada)
            c.estado = "vencida" if c.fecha_vencimiento < hoy else "pendiente"
            # Día 75 — la cuota del mes nivelada al firmar «para volver al
            # padrón» estaba cobrada solo hasta ese día porque la casa se iba.
            # Si la casa sigue en el sistema, vuelve a su monto completo.
            if sigue_en_sistema:
                restaurar_nivelacion(c)
    # Día 74 — una casa del padrón (o una que ya se mudó) NO se bloquea: no
    # tiene servicio de cuotas que cortar, y a la gente del padrón el guardia
    # la identifica igual. La deuda queda pendiente a su nombre y le impide
    # volver a sumarse al sistema hasta que la pague.
    # Día 75 — y solo si queda algo VENCIDO. Cancelar un arreglo que solo
    # tenía la cuota del mes en curso (todavía sin vencer) bloqueaba la casa
    # por una deuda que no estaba atrasada.
    hay_vencidas = any(c.estado == "vencida" for c in arreglo.cuotas)
    if cuenta and cuenta.activa and not cuenta.es_censo and hay_vencidas:
        cuenta.estado = "en_mora"
        cuenta.bloqueada = True
