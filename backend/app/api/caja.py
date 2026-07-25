"""
Módulo de Caja — /api/v1/caja/

Cajero: abrir sesión, registrar pagos en ventanilla, arqueo, cerrar.
Admin: supervisión (ver todas las sesiones, totales).
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.caja import SesionCaja, ConfigCaja, AjusteCaja, SalidaCaja
from app.models.cuenta import Cuenta, Cuota, Pago, Tarjeta, Residente, TipoTarjeta, MovimientoStock, VentaTarjeta
from app.models.usuario import Usuario
from app.auth.security import roles_required
from app.utils import dinero

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
    #
    # O3.1 (Auditoría Día 42): este chequeo tiene una carrera teórica —dos
    # aperturas simultáneas podrían ambas pasar el SELECT—, pero se decidió
    # NO protegerlo. La garantía fuerte requeriría un índice único parcial
    # (migración a la base), y el escenario es muy improbable: exige que dos
    # cajeros hagan clic en "abrir" en el mismo milisegundo, con muy pocos
    # cajeros operando. El costo de la migración no justifica el riesgo.
    # Si en el futuro hay muchos cajeros concurrentes, reconsiderar.
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

    # O3.1 (Auditoría Día 42): SELECT ... FOR UPDATE sobre la cuota.
    # Sin el candado, dos peticiones simultáneas (doble-clic del cajero, o
    # dos cajeros a la vez) podían leer ambas cuota.estado != "pagada",
    # crear cada una su Pago y cobrar DOS VECES la misma cuota. Es el mismo
    # patrón que ACCESS-03/QR-CONC-20, pero con dinero.
    #
    # with_for_update() bloquea la fila hasta el commit: la segunda petición
    # espera, y al despertar ve la cuota ya "pagada" y sale por el 400 de
    # abajo. Se usa filter_by().first() (no .get()) porque .get() puede
    # devolver una copia de la sesión sin ejecutar el FOR UPDATE — lección
    # aprendida en QR-CONC-20.
    cuota = (Cuota.query
             .filter_by(uuid_publico=cuota_uuid)
             .with_for_update()
             .first())
    if not cuota:
        return jsonify({"error": {"code": "cuota_no_encontrada", "message": "Cuota no encontrada"}}), 404
    if cuota.estado == "pagada":
        return jsonify({"error": {"code": "ya_pagada", "message": "Esa cuota ya está pagada"}}), 400
    if cuota.estado == "en_arreglo":
        return jsonify({"error": {"code": "en_arreglo",
                                  "message": "Esa cuota está dentro de un arreglo de pago. Cobrá el abono del arreglo, no la cuota directamente."}}), 400

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

    # Marcar cuota pagada y, si ya no quedan cuotas vencidas, desbloquear.
    # Si aún debe otras cuotas, la cuenta permanece bloqueada (evita que pagar
    # una sola cuota reactive el acceso teniendo otras vencidas).
    cuota.estado = "pagada"
    cuenta = cuota.cuenta
    if cuenta:
        cuenta.intentar_desbloquear()

    # Asignar número de recibo
    from app.api.recibos import asignar_recibo
    db.session.flush()
    asignar_recibo(pago)

    db.session.commit()
    return jsonify({"data": {"pago": pago.to_dict(), "sesion": sesion.to_dict()}}), 201


# ── Vender tarjeta en caja (cobra + asigna a la casa + baja stock) ─────────────
@caja_bp.post("/vender-tarjeta")
@roles_required("cajero", "admin", "super_admin")
def vender_tarjeta(usuario_actual):
    sesion = _sesion_abierta_de(usuario_actual)
    if not sesion:
        return jsonify({"error": {"code": "sin_caja",
                                  "message": "Abrí la caja antes de vender tarjetas"}}), 400

    data = request.get_json(silent=True) or {}
    tipo_uuid = data.get("tipo_tarjeta_id")
    cuenta_uuid = data.get("cuenta_id")
    card_uid = (data.get("card_uid") or "").strip()
    metodo = data.get("metodo")
    residente_uuid = data.get("residente_id")

    if metodo not in METODOS_VENTANILLA:
        return jsonify({"error": {"code": "metodo_invalido",
                                  "message": "Método debe ser efectivo o tarjeta_pos"}}), 400

    # O3.1 (Auditoría Día 42): candado sobre el TipoTarjeta para que dos
    # ventas simultáneas del último ítem no dejen el stock en negativo.
    # Sin el FOR UPDATE, ambas leen tipo.stock == 1, ambas restan, y queda
    # en -1. Con el candado, la segunda espera y ve stock 0.
    tipo = (TipoTarjeta.query
            .filter_by(uuid_publico=tipo_uuid)
            .with_for_update()
            .first())
    if not tipo or not tipo.activo:
        return jsonify({"error": {"code": "tipo_invalido",
                                  "message": "Tipo de tarjeta no encontrado o inactivo"}}), 404
    if tipo.stock <= 0:
        return jsonify({"error": {"code": "sin_stock",
                                  "message": f"No hay stock de '{tipo.nombre}'. Registrá una entrada primero."}}), 400

    cuenta = Cuenta.query.filter_by(uuid_publico=cuenta_uuid).first()
    if not cuenta:
        return jsonify({"error": {"code": "cuenta_no_encontrada", "message": "Casa no encontrada"}}), 404

    if not card_uid:
        return jsonify({"error": {"code": "card_uid_requerido",
                                  "message": "Ingresá el código (UID) de la tarjeta física"}}), 400
    if Tarjeta.query.filter_by(card_uid=card_uid).first():
        return jsonify({"error": {"code": "tarjeta_duplicada",
                                  "message": "Esa tarjeta ya está registrada en el sistema"}}), 409

    # Residente opcional (portador de la tarjeta)
    residente = None
    if residente_uuid:
        residente = Residente.query.filter_by(uuid_publico=residente_uuid, cuenta_id=cuenta.id).first()
        if not residente:
            return jsonify({"error": {"code": "residente_invalido",
                                      "message": "El portador no pertenece a esta casa"}}), 400

    precio = dinero.a_decimal(tipo.precio)

    # 1. Crear la tarjeta física asignada a la casa
    tarjeta = Tarjeta(
        card_uid=card_uid, cuenta_id=cuenta.id,
        residente_id=residente.id if residente else None,
        tipo_acceso=tipo.tipo_acceso,
        etiqueta=data.get("etiqueta") or tipo.nombre,
    )
    db.session.add(tarjeta)
    db.session.flush()

    # 2. Registrar el cobro como Pago (suma al arqueo, sin cuota)
    pago = Pago(
        cuota_id=None, cuenta_id=cuenta.id, subido_por=usuario_actual.id,
        metodo=metodo, monto=precio,
        referencia=f"Venta tarjeta: {tipo.nombre}",
        estado="aprobado", revisado_por=usuario_actual.id,
        revisado_en=dt.datetime.now(dt.timezone.utc),
        sesion_caja_id=sesion.id,
    )
    db.session.add(pago)
    db.session.flush()

    # 3. Bajar stock + registrar movimiento
    tipo.stock -= 1
    db.session.add(MovimientoStock(
        tipo_tarjeta_id=tipo.id, tipo_movimiento="venta",
        cantidad=-1, stock_resultante=tipo.stock,
        nota=f"Venta a {cuenta.uuid_publico} ({card_uid})",
        registrado_por=usuario_actual.id,
    ))

    # 4. Registro auditable de la venta
    venta = VentaTarjeta(
        tipo_tarjeta_id=tipo.id, tarjeta_id=tarjeta.id, cuenta_id=cuenta.id,
        pago_id=pago.id, sesion_caja_id=sesion.id, precio=precio,
        metodo=metodo, vendido_por=usuario_actual.id,
    )
    db.session.add(venta)

    db.session.commit()
    return jsonify({"data": {
        "venta": venta.to_dict(),
        "tarjeta": tarjeta.to_dict(),
        "stock_restante": tipo.stock,
        "sesion": sesion.to_dict(),
    }}), 201



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
        efectivo_contado = dinero.a_decimal(data.get("efectivo_contado", 0))
        pos_contado = dinero.a_decimal(data.get("pos_contado", 0))
    except (ValueError, ArithmeticError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Montos contados inválidos"}}), 400

    # Desglose de billetes (opcional pero recomendado). Si viene, se valida que
    # el total de billetes coincida con el efectivo contado.
    import json as _json
    desglose = data.get("desglose_billetes")
    if desglose and isinstance(desglose, dict):
        DENOMINACIONES = [500, 200, 100, 50, 20, 10, 5, 2, 1]
        total_billetes = sum(int(desglose.get(str(d), 0) or 0) * d for d in DENOMINACIONES)
        # Si el cajero contó billetes, el efectivo contado se toma del desglose
        if total_billetes > 0:
            efectivo_contado = dinero.a_decimal(total_billetes)
        sesion.desglose_billetes = _json.dumps({str(d): int(desglose.get(str(d), 0) or 0)
                                                for d in DENOMINACIONES})

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
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"data": []})

    from sqlalchemy import or_
    from sqlalchemy.orm import joinedload
    from app.models.cuenta import Unidad, Residente

    patron = f"%{q}%"
    # Filtrar en SQL por identificador de unidad o nombre/apellido del titular,
    # en vez de cargar las 500 cuentas y filtrar en Python. Precarga unidad y
    # residentes->usuario para no disparar lazy loads por cada resultado.
    cuentas = (
        Cuenta.query
        .filter(Cuenta.activa.is_(True))
        .outerjoin(Unidad, Cuenta.unidad_id == Unidad.id)
        .outerjoin(Residente, (Residente.cuenta_id == Cuenta.id) &
                              (Residente.rol_cuenta == "titular"))
        .outerjoin(Usuario, Residente.usuario_id == Usuario.id)
        .filter(or_(
            Unidad.identificador.ilike(patron),
            Usuario.nombre.ilike(patron),
            Usuario.apellido.ilike(patron),
            (Usuario.nombre + " " + Usuario.apellido).ilike(patron),
        ))
        .options(joinedload(Cuenta.unidad),
                 joinedload(Cuenta.residentes).joinedload(Residente.usuario))
        .distinct()
        .limit(10)
        .all()
    )

    # Precargar las cuotas pendientes de todas las cuentas encontradas (una query)
    cuenta_ids = [c.id for c in cuentas]
    cuotas_por_cuenta = {}
    if cuenta_ids:
        cuotas = (Cuota.query
                  .filter(Cuota.cuenta_id.in_(cuenta_ids),
                          Cuota.estado.notin_(["pagada", "en_arreglo"]))
                  .order_by(Cuota.periodo.asc()).all())
        for q2 in cuotas:
            cuotas_por_cuenta.setdefault(q2.cuenta_id, []).append(q2)

    # Precargar abonos pendientes de arreglos ACTIVOS de esas cuentas, para que
    # el cajero pueda cobrarlos junto con las cuotas normales (mismo flujo).
    from app.models.cuenta import ArregloPago, AbonoArreglo
    abonos_por_cuenta = {}
    if cuenta_ids:
        arreglos_act = (ArregloPago.query
                        .filter(ArregloPago.cuenta_id.in_(cuenta_ids),
                                ArregloPago.estado == "activo").all())
        for arr in arreglos_act:
            pend = [a for a in arr.abonos if a.estado in ("pendiente", "vencido")]
            for a in sorted(pend, key=lambda x: x.numero):
                abonos_por_cuenta.setdefault(arr.cuenta_id, []).append({
                    "arreglo_id": str(arr.uuid_publico),
                    "abono_id": str(a.uuid_publico),
                    "numero": a.numero,
                    "total_abonos": arr.num_abonos,
                    "monto": dinero.a_float(a.monto),
                    "fecha_pactada": a.fecha_pactada.isoformat(),
                    "estado": a.estado,
                })

    resultados = []
    for c in cuentas:
        identificador = c.unidad.identificador if c.unidad else ""
        titular = c.titular()
        nombre_titular = f"{titular.usuario.nombre} {titular.usuario.apellido}" if titular and titular.usuario else ""
        pendientes = cuotas_por_cuenta.get(c.id, [])
        # Residentes activos de la casa, para elegir portador al vender tarjeta
        residentes_casa = [
            {"id": str(r.uuid_publico),
             "nombre": f"{r.usuario.nombre} {r.usuario.apellido}" if r.usuario else "—"}
            for r in c.residentes if r.activo
        ]
        resultados.append({
            "cuenta_id": str(c.uuid_publico),
            "identificador": identificador or "Casa",
            "titular": nombre_titular or "— sin titular —",
            "residentes": residentes_casa,
            "cuotas_pendientes": [{
                "cuota_id": str(q2.uuid_publico),
                "mes_label": q2.periodo.strftime("%B %Y"),
                "monto": dinero.a_float(q2.monto),
                "estado": q2.estado,
            } for q2 in pendientes],
            "abonos_arreglo": abonos_por_cuenta.get(c.id, []),
        })
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
    Saldo de caja del sistema. La fórmula vive en UN solo lugar:
    models/caja.py -> calcular_saldo_global(). Acá solo se arma la respuesta.
    """
    from app.models.caja import calcular_saldo_global
    g = calcular_saldo_global()
    cfg = ConfigCaja.get()

    descuadres_pendientes = AjusteCaja.query.filter(
        AjusteCaja.tipo.in_(["sobrante", "faltante"]), AjusteCaja.estado == "pendiente"
    ).count()
    salidas_pend = SalidaCaja.query.filter_by(estado="pendiente").count()

    return jsonify({"data": {
        "saldo_inicial": g["saldo_inicial"],
        "saldo_actual": g["saldo_actual"],
        "total_efectivo_historico": g["total_efectivo"],
        "total_pos_historico": g["total_pos"],
        "total_salidas_historico": g["total_salidas"],
        "total_ingresos_historico": g["total_ingresos"],
        "total_ajustes": g["total_ajustes"],
        "efectivo_en_cajas_abiertas": g["efectivo_en_cajas_abiertas"],
        "cajas_abiertas": g["cajas_abiertas"],
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


# ── Constancia PDF del turno del cajero ──────────────────────────────────────
@caja_bp.get("/sesiones/<uuid_sesion>/pdf")
@roles_required("cajero", "admin", "super_admin", "desarrollador")
def constancia_pdf(usuario_actual, uuid_sesion):
    """Genera la constancia PDF del turno del cajero con arqueo."""
    s = SesionCaja.query.filter_by(uuid_publico=uuid_sesion).first()
    if not s:
        return jsonify({"error": {"code": "no_encontrada", "message": "Sesión no encontrada"}}), 404

    import io
    import datetime as dt
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Table, TableStyle
    from flask import send_file

    AZUL   = colors.HexColor("#022E45")
    GRIS   = colors.HexColor("#6b7280")
    GRIS_C = colors.HexColor("#f4f7fb")

    buf = io.BytesIO()
    W, H = letter
    cv = rl_canvas.Canvas(buf, pagesize=letter)

    # Encabezado
    cv.setFillColor(AZUL)
    cv.rect(0, H - 22*mm, W, 22*mm, fill=1, stroke=0)
    cv.setFillColor(colors.white)
    cv.setFont("Helvetica-Bold", 14)
    cv.drawString(15*mm, H - 10*mm, "Residencial Villas del Sol")
    cv.setFont("Helvetica", 9)
    cv.drawString(15*mm, H - 16*mm, "CONSTANCIA DE TURNO DE CAJA")
    cv.setFont("Helvetica-Bold", 10)
    cv.drawRightString(W - 15*mm, H - 10*mm, f"Sesión #{str(s.uuid_publico)[:8].upper()}")
    cv.setFont("Helvetica", 8)
    cv.drawRightString(W - 15*mm, H - 16*mm, "ABIERTA" if s.estado == "abierta" else "CERRADA")

    y = H - 32*mm
    cajero = s.cajero
    nombre_cajero = f"{cajero.nombre} {cajero.apellido}" if cajero else "—"
    abierta_str = s.abierta_en.strftime("%d/%m/%Y %I:%M %p") if s.abierta_en else "—"
    cerrada_str = s.cerrada_en.strftime("%d/%m/%Y %I:%M %p") if s.cerrada_en else "En curso"

    def fila_d(label, valor, yp):
        cv.setFont("Helvetica-Bold", 8); cv.setFillColor(GRIS)
        cv.drawString(15*mm, yp, label)
        cv.setFont("Helvetica", 9); cv.setFillColor(AZUL)
        cv.drawString(55*mm, yp, str(valor))

    fila_d("Cajero:", nombre_cajero, y);                y -= 6*mm
    fila_d("Apertura:", abierta_str, y);                y -= 6*mm
    fila_d("Cierre:", cerrada_str, y);                  y -= 6*mm
    fila_d("Fondo inicial:", f"L {dinero.a_decimal(s.monto_inicial):,.2f}", y); y -= 8*mm

    cv.setStrokeColor(colors.HexColor("#e3e9f2")); cv.setLineWidth(0.6)
    cv.line(15*mm, y, W - 15*mm, y); y -= 8*mm

    # Detalle de cobros
    cv.setFont("Helvetica-Bold", 10); cv.setFillColor(AZUL)
    cv.drawString(15*mm, y, "Detalle de cobros del turno"); y -= 7*mm

    pagos = Pago.query.filter_by(sesion_caja_id=s.id, estado="aprobado").order_by(Pago.created_at).all()
    met_label = {"efectivo": "Efectivo", "tarjeta_pos": "Tarjeta POS",
                 "transferencia": "Transf.", "linea": "En línea", "pasarela": "En línea"}
    total_ef = total_pos = dinero.CERO

    if not pagos:
        cv.setFont("Helvetica-Oblique", 9); cv.setFillColor(GRIS)
        cv.drawString(15*mm, y, "No hay cobros registrados en este turno."); y -= 6*mm
    else:
        tdata = [["#", "Casa", "Titular", "Método", "Monto"]]
        for i, p in enumerate(pagos, 1):
            cuenta = p.cuenta
            unidad = cuenta.unidad.identificador if cuenta and cuenta.unidad else "—"
            tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None) if cuenta else None
            titular = (f"{tit.usuario.nombre} {tit.usuario.apellido}"[:24] if tit and tit.usuario else "—")
            monto = dinero.a_decimal(p.monto)
            if p.metodo == "efectivo": total_ef += monto
            elif p.metodo == "tarjeta_pos": total_pos += monto
            tdata.append([str(i), unidad, titular, met_label.get(p.metodo, p.metodo), f"L {monto:,.2f}"])
        tb = Table(tdata, colWidths=[8*mm, 28*mm, 70*mm, 22*mm, 32*mm])
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), AZUL), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, GRIS_C]),
            ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#e3e9f2")),
            ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING", (0,0), (-1,-1), 4), ("ALIGN", (4,1), (4,-1), "RIGHT"),
        ]))
        tb.wrapOn(cv, W - 30*mm, H)
        tb.drawOn(cv, 15*mm, y - tb._height)
        y -= tb._height + 8*mm

    # Salidas e ingresos extraordinarios (autorizados) del turno
    salidas = SalidaCaja.query.filter_by(sesion_id=s.id).order_by(SalidaCaja.created_at).all()
    if salidas:
        cv.setFont("Helvetica-Bold", 10); cv.setFillColor(AZUL)
        cv.drawString(15*mm, y, "Salidas e ingresos extraordinarios"); y -= 7*mm
        sdata = [["Tipo", "Concepto", "Estado", "Monto"]]
        for sa in salidas:
            monto = dinero.a_decimal(sa.monto)
            es_ingreso = monto < 0
            tipo = "Ingreso" if es_ingreso else "Salida"
            concepto = (sa.concepto or "—").replace("[INGRESO]", "").strip()[:40]
            sdata.append([tipo, concepto, sa.estado.capitalize(), f"L {abs(monto):,.2f}"])
        ts = Table(sdata, colWidths=[20*mm, 80*mm, 28*mm, 32*mm])
        ts.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#5b6b7a")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, GRIS_C]),
            ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#e3e9f2")),
            ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING", (0,0), (-1,-1), 4), ("ALIGN", (3,1), (3,-1), "RIGHT"),
        ]))
        ts.wrapOn(cv, W - 30*mm, H)
        if y - ts._height < 40*mm:
            cv.showPage(); y = H - 25*mm
        ts.drawOn(cv, 15*mm, y - ts._height)
        y -= ts._height + 8*mm

    # Desglose de billetes contados al cierre
    if s.desglose_billetes:
        import json as _json2
        try:
            desg = _json2.loads(s.desglose_billetes)
        except Exception:
            desg = {}
        if desg and any(int(v or 0) > 0 for v in desg.values()):
            if y < 70*mm:
                cv.showPage(); y = H - 25*mm
            cv.setFont("Helvetica-Bold", 10); cv.setFillColor(AZUL)
            cv.drawString(15*mm, y, "Desglose de billetes contados"); y -= 7*mm
            DEN = [500, 200, 100, 50, 20, 10, 5, 2, 1]
            bdata = [["Denominación", "Cantidad", "Subtotal"]]
            total_b = 0
            for den in DEN:
                cant = int(desg.get(str(den), 0) or 0)
                if cant > 0:
                    sub = cant * den
                    total_b += sub
                    bdata.append([f"L {den}", str(cant), f"L {sub:,.2f}"])
            bdata.append(["", "TOTAL", f"L {total_b:,.2f}"])
            tbil = Table(bdata, colWidths=[35*mm, 30*mm, 35*mm])
            tbil.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), AZUL), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
                ("ROWBACKGROUNDS", (0,1), (-2,-2), [colors.white, GRIS_C]),
                ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#e3e9f2")),
                ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                ("LEFTPADDING", (0,0), (-1,-1), 6), ("ALIGN", (1,0), (-1,-1), "RIGHT"),
                ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff3e6")),
                ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
            ]))
            tbil.wrapOn(cv, W - 30*mm, H)
            tbil.drawOn(cv, 15*mm, y - tbil._height)
            y -= tbil._height + 8*mm
    cv.line(15*mm, y, W - 15*mm, y); y -= 8*mm
    cv.setFont("Helvetica-Bold", 10); cv.setFillColor(AZUL)
    cv.drawString(15*mm, y, "Resumen del arqueo"); y -= 7*mm

    d = s.to_dict()
    ef_esperado = dinero.a_decimal(d.get("efectivo_esperado", 0))
    ef_contado  = dinero.a_decimal(s.efectivo_contado or 0)
    dif         = ef_contado - ef_esperado if s.cerrada_en else 0

    def fila_a(label, valor, color_v=None):
        nonlocal y
        cv.setFont("Helvetica-Bold", 8); cv.setFillColor(GRIS)
        cv.drawString(60*mm, y, label)
        cv.setFont("Helvetica-Bold", 9); cv.setFillColor(color_v or AZUL)
        cv.drawRightString(W - 15*mm, y, valor); y -= 6*mm

    fila_a("Fondo inicial de apertura:", f"L {dinero.a_decimal(s.monto_inicial):,.2f}")
    fila_a("Cobros en efectivo:", f"L {total_ef:,.2f}")
    fila_a("Cobros con tarjeta POS:", f"L {total_pos:,.2f}")
    fila_a("Efectivo esperado en caja:", f"L {ef_esperado:,.2f}")
    if s.cerrada_en:
        fila_a("Efectivo contado al cierre:", f"L {ef_contado:,.2f}")
        if abs(dif) < 0.01:
            fila_a("Diferencia:", "L 0.00  (CUADRA ✓)", color_v=colors.HexColor("#1d8a4a"))
        elif dif < 0:
            fila_a("Diferencia:", f"L {dif:,.2f}  (FALTA)", color_v=colors.HexColor("#c81e1e"))
        else:
            fila_a("Diferencia:", f"L {dif:,.2f}  (SOBRA)", color_v=colors.HexColor("#d89000"))

    # Firmas
    y -= 16*mm
    if y < 45*mm:
        cv.showPage(); y = H - 30*mm
    cv.setStrokeColor(AZUL); cv.setLineWidth(0.5)
    cv.line(20*mm, y, 90*mm, y)
    cv.line(120*mm, y, W - 20*mm, y)
    cv.setFont("Helvetica", 8); cv.setFillColor(GRIS)
    cv.drawCentredString(55*mm, y - 5*mm, "Firma del cajero")
    cv.drawCentredString(55*mm, y - 10*mm, nombre_cajero)
    cv.drawCentredString((120*mm + W - 20*mm) / 2, y - 5*mm, "Firma del supervisor")
    cv.setFont("Helvetica", 7)
    cv.drawCentredString(W/2, 12*mm, f"Generado el {dt.datetime.now().strftime('%d/%m/%Y %I:%M %p')}  ·  SICA-VS  ·  Residencial Villas del Sol")

    cv.showPage(); cv.save(); buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"constancia-caja-{str(s.uuid_publico)[:8]}.pdf")


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
        nuevo = dinero.a_decimal(data.get("saldo_inicial"))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Saldo inicial inválido"}}), 400

    dev = _validar_clave_dev(clave)
    if not dev:
        return jsonify({"error": {"code": "clave_invalida",
                                  "message": "Clave de desarrollador incorrecta"}}), 403

    cfg = ConfigCaja.get()
    anterior = dinero.a_decimal(cfg.saldo_inicial)
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
        saldo_real = dinero.a_decimal(data.get("saldo_real"))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "monto_invalido", "message": "Saldo real inválido"}}), 400

    dev = _validar_clave_dev(clave)
    if not dev:
        return jsonify({"error": {"code": "clave_invalida",
                                  "message": "Clave de desarrollador incorrecta"}}), 403

    # Calcular el saldo actual que el sistema tiene registrado
    # (fórmula centralizada en models/caja.py -> calcular_saldo_global)
    from app.models.caja import calcular_saldo_global
    saldo_sistema = calcular_saldo_global()["saldo_actual"]

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
        monto = abs(dinero.a_decimal(data.get("monto")))
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
        monto = dinero.a_decimal(data.get("monto"))
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
                                  "message": "Indicá el concepto (ej. Efectivo traído del banco)"}}), 400
    try:
        monto = dinero.a_decimal(data.get("monto"))
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
