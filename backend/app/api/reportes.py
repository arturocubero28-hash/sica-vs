"""
Módulo de Reportería — /api/v1/reportes/

Reportes financieros para el patronato: cobranza, morosos, recaudación.
"""
import datetime as dt
from collections import defaultdict

from flask import Blueprint, jsonify, request

from app.models.cuenta import Cuota, Pago, Cuenta
from app.auth.security import roles_required

reportes_bp = Blueprint("reportes", __name__)


@reportes_bp.get("/financiero")
@roles_required("admin", "super_admin")
def reporte_financiero(usuario_actual):
    """
    Reporte financiero del mes en curso (o el indicado por ?anio=&mes=).
    Devuelve: totales, cobranza, lista de al día y morosos, tendencia.
    """
    hoy = dt.date.today()
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    # ── MODO RANGO ──────────────────────────────────────────────────────────
    # Si vienen desde y hasta, el reporte se basa en la FECHA EN QUE SE PAGÓ
    # (cuánto dinero entró en ese período), no en el período de la cuota.
    # Esto responde "¿cuánto recaudamos entre estas fechas?".
    modo_rango = bool(desde_str and hasta_str)
    if modo_rango:
        try:
            desde = dt.date.fromisoformat(desde_str)
            hasta = dt.date.fromisoformat(hasta_str)
        except ValueError:
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido (use YYYY-MM-DD)"}}), 400
        if desde > hasta:
            desde, hasta = hasta, desde
        # Rango de datetime para comparar (incluye todo el día 'hasta')
        ini = dt.datetime.combine(desde, dt.time.min).replace(tzinfo=dt.timezone.utc)
        fin = dt.datetime.combine(hasta, dt.time.max).replace(tzinfo=dt.timezone.utc)
        label = (desde.strftime("%d/%m/%Y") if desde == hasta
                 else f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}")

        # Pagos aprobados cuya fecha efectiva (revisado_en, o created_at si null)
        # caiga dentro del rango. El filtro de fecha se hace en SQL con COALESCE
        # para no cargar todo el histórico de pagos en memoria.
        from sqlalchemy import func
        fecha_sql = func.coalesce(Pago.revisado_en, Pago.created_at)
        pagos_rango = (Pago.query
                       .filter(Pago.estado == "aprobado",
                               fecha_sql >= ini, fecha_sql <= fin)
                       .all())

        def fecha_efectiva(p):
            f = p.revisado_en or p.created_at
            if f and f.tzinfo is None:
                f = f.replace(tzinfo=dt.timezone.utc)
            return f

        total_recaudado = sum(float(p.monto) for p in pagos_rango)
        por_metodo = {"efectivo": 0.0, "tarjeta_pos": 0.0, "transferencia": 0.0, "linea": 0.0}
        detalle_pagos = []
        for p in pagos_rango:
            m = p.metodo or "transferencia"
            if m == "pasarela":
                m = "linea"
            if m not in por_metodo:
                por_metodo[m] = 0.0
            por_metodo[m] += float(p.monto)
            cuenta = p.cuenta
            unidad = cuenta.unidad.identificador if cuenta and cuenta.unidad else "—"
            titular = "—"
            if cuenta:
                tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None)
                if tit and tit.usuario:
                    titular = f"{tit.usuario.nombre} {tit.usuario.apellido}"
            fe = fecha_efectiva(p)
            detalle_pagos.append({
                "unidad": unidad, "titular": titular, "monto": float(p.monto),
                "metodo": m, "fecha": fe.isoformat() if fe else None,
            })
        detalle_pagos.sort(key=lambda x: x["fecha"] or "", reverse=True)

        return jsonify({"data": {
            "modo": "rango",
            "periodo": desde.isoformat(),
            "mes_label": label,
            "total_esperado": 0.0,
            "total_recaudado": round(total_recaudado, 2),
            "total_pendiente": 0.0,
            "pct_cobranza": 0.0,
            "recaudado_por_metodo": {
                "efectivo": round(por_metodo.get("efectivo", 0.0), 2),
                "tarjeta_pos": round(por_metodo.get("tarjeta_pos", 0.0), 2),
                "transferencia": round(por_metodo.get("transferencia", 0.0), 2),
                "linea": round(por_metodo.get("linea", 0.0), 2),
            },
            "al_dia": [],
            "morosos": [],
            "tendencia": [],
            "detalle_pagos": detalle_pagos,
            "total_pagos": len(pagos_rango),
        }})

    # ── MODO MES (un solo período de cuota) ─────────────────────────────────
    anio = int(request.args.get("anio", hoy.year))
    mes = int(request.args.get("mes", hoy.month))
    periodo = dt.date(anio, mes, 1)
    label = periodo.strftime("%B %Y")
    cuotas = Cuota.query.filter_by(periodo=periodo).all()

    total_esperado = 0.0
    total_recaudado = 0.0
    al_dia = []
    morosos = []

    for c in cuotas:
        monto = float(c.monto)
        total_esperado += monto
        cuenta = c.cuenta
        unidad = cuenta.unidad.identificador if cuenta and cuenta.unidad else "—"
        titular = "—"
        if cuenta:
            tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None)
            if tit and tit.usuario:
                titular = f"{tit.usuario.nombre} {tit.usuario.apellido}"

        if c.estado == "pagada":
            total_recaudado += monto
            al_dia.append({"unidad": unidad, "titular": titular, "monto": monto})
        else:
            dias_atraso = (hoy - c.fecha_vencimiento).days
            morosos.append({
                "unidad": unidad, "titular": titular, "monto": monto,
                "estado": c.estado,
                "vencimiento": c.fecha_vencimiento.isoformat(),
                "dias_atraso": dias_atraso if dias_atraso > 0 else 0,
            })

    total_pendiente = total_esperado - total_recaudado
    pct_cobranza = (total_recaudado / total_esperado * 100) if total_esperado > 0 else 0

    # Ordenar morosos por días de atraso (más atrasados primero)
    morosos.sort(key=lambda m: m["dias_atraso"], reverse=True)

    # ── Desglose de lo recaudado por método de pago ──────────────────────────
    # Tomamos los pagos APROBADOS de las cuotas de este período y los agrupamos.
    cuota_ids = [c.id for c in cuotas]
    por_metodo = {"efectivo": 0.0, "tarjeta_pos": 0.0, "transferencia": 0.0, "linea": 0.0, "pasarela": 0.0}
    if cuota_ids:
        pagos = Pago.query.filter(
            Pago.cuota_id.in_(cuota_ids), Pago.estado == "aprobado"
        ).all()
        for p in pagos:
            m = p.metodo or "transferencia"
            if m not in por_metodo:
                por_metodo[m] = 0.0
            por_metodo[m] += float(p.monto)
    # Unificar pasarela dentro de linea (pago en línea de la plataforma)
    por_metodo["linea"] += por_metodo.pop("pasarela", 0.0)

    # Tendencia: recaudación de los últimos 6 meses
    tendencia = []
    for i in range(5, -1, -1):
        m = mes - i
        a = anio
        while m <= 0:
            m += 12
            a -= 1
        p = dt.date(a, m, 1)
        qs = Cuota.query.filter_by(periodo=p).all()
        esperado = sum(float(x.monto) for x in qs)
        recaudado = sum(float(x.monto) for x in qs if x.estado == "pagada")
        tendencia.append({
            "mes_label": p.strftime("%b %Y"),
            "esperado": esperado,
            "recaudado": recaudado,
        })

    return jsonify({"data": {
        "periodo": periodo.isoformat(),
        "mes_label": label,
        "modo": "mes",
        "total_esperado": total_esperado,
        "total_recaudado": total_recaudado,
        "total_pendiente": total_pendiente,
        "pct_cobranza": round(pct_cobranza, 1),
        "recaudado_por_metodo": {
            "efectivo": round(por_metodo.get("efectivo", 0.0), 2),
            "tarjeta_pos": round(por_metodo.get("tarjeta_pos", 0.0), 2),
            "transferencia": round(por_metodo.get("transferencia", 0.0), 2),
            "linea": round(por_metodo.get("linea", 0.0), 2),
        },
        "cuentas_al_dia": len(al_dia),
        "cuentas_morosas": len(morosos),
        "al_dia": al_dia,
        "morosos": morosos,
        "tendencia": tendencia,
    }})


@reportes_bp.get("/mora-por-casa")
@roles_required("admin", "super_admin")
def mora_por_casa(usuario_actual):
    """
    Reporte de mora detallado por casa: lista cada cuenta con cuotas pendientes
    y QUÉ MESES específicos debe, con el total adeudado.
    Útil para gestión de cobro de la administración.
    """
    hoy = dt.date.today()

    # Todas las cuotas no pagadas (pendiente, vencida, en_arreglo, etc.)
    cuotas = Cuota.query.filter(Cuota.estado != "pagada").order_by(Cuota.periodo.asc()).all()

    # Agrupar por cuenta
    por_cuenta = defaultdict(list)
    for c in cuotas:
        por_cuenta[c.cuenta_id].append(c)

    casas = []
    total_general = 0.0
    for cuenta_id, lista in por_cuenta.items():
        cuenta = lista[0].cuenta
        if not cuenta:
            continue
        unidad = cuenta.unidad.identificador if cuenta.unidad else "—"
        titular = "—"
        telefono = None
        if cuenta:
            tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None)
            if tit and tit.usuario:
                titular = f"{tit.usuario.nombre} {tit.usuario.apellido}"
                telefono = tit.usuario.telefono

        meses = []
        total_casa = 0.0
        for c in sorted(lista, key=lambda x: x.periodo):
            monto = float(c.monto)
            total_casa += monto
            dias = (hoy - c.fecha_vencimiento).days
            meses.append({
                "periodo": c.periodo.isoformat(),
                "mes_label": c.periodo.strftime("%B %Y"),
                "monto": monto,
                "estado": c.estado,
                "vencimiento": c.fecha_vencimiento.isoformat(),
                "dias_atraso": dias if dias > 0 else 0,
            })
        total_general += total_casa
        casas.append({
            "unidad": unidad,
            "titular": titular,
            "telefono": telefono,
            "cantidad_meses": len(meses),
            "total_adeudado": round(total_casa, 2),
            "meses": meses,
            "max_dias_atraso": max((m["dias_atraso"] for m in meses), default=0),
        })

    # Ordenar: las más atrasadas primero
    casas.sort(key=lambda c: (c["cantidad_meses"], c["max_dias_atraso"]), reverse=True)

    # Aging de cartera: clasificar cada cuota vencida por antigüedad de la deuda.
    # Es la lectura que un contador/tesorero hace para medir el riesgo de cobro.
    # El tramo 90+ es la "cartera de difícil cobro".
    aging = {"d_1_30": 0.0, "d_31_60": 0.0, "d_61_90": 0.0, "d_90_mas": 0.0, "sin_vencer": 0.0}
    for c in cuotas:
        monto = float(c.monto)
        dias = (hoy - c.fecha_vencimiento).days
        if dias <= 0:
            aging["sin_vencer"] += monto
        elif dias <= 30:
            aging["d_1_30"] += monto
        elif dias <= 60:
            aging["d_31_60"] += monto
        elif dias <= 90:
            aging["d_61_90"] += monto
        else:
            aging["d_90_mas"] += monto
    aging = {k: round(v, 2) for k, v in aging.items()}

    # % de morosidad de la comunidad (casas en mora / total de cuentas activas)
    total_cuentas = Cuenta.query.filter_by(activa=True).count()
    pct_morosidad = round((len(casas) / total_cuentas * 100), 1) if total_cuentas else 0.0

    return jsonify({"data": {
        "casas": casas,
        "total_casas_mora": len(casas),
        "total_general_adeudado": round(total_general, 2),
        "aging": aging,
        "total_cuentas_activas": total_cuentas,
        "pct_morosidad": pct_morosidad,
        "generado": hoy.isoformat(),
    }})


@reportes_bp.get("/caja")
@roles_required("admin", "super_admin")
def reporte_caja(usuario_actual):
    """
    Reporte de sesiones de caja en un período (control de arqueo).
    Filtros: ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD  ?cajero_id=<uuid>
    Responde: resumen consolidado + lista de sesiones con sus descuadres.
    Pensado para el tesorero: ¿cuánto cobró cada cajero, cuadró la caja?
    """
    from app.models.caja import SesionCaja
    from app.models.usuario import Usuario

    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    cajero_uuid = request.args.get("cajero_id")

    q = SesionCaja.query.filter(SesionCaja.estado == "cerrada")

    if desde_str and hasta_str:
        try:
            desde = dt.date.fromisoformat(desde_str)
            hasta = dt.date.fromisoformat(hasta_str)
        except ValueError:
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido (use YYYY-MM-DD)"}}), 400
        if desde > hasta:
            desde, hasta = hasta, desde
        ini = dt.datetime.combine(desde, dt.time.min).replace(tzinfo=dt.timezone.utc)
        fin = dt.datetime.combine(hasta, dt.time.max).replace(tzinfo=dt.timezone.utc)
        q = q.filter(SesionCaja.cerrada_en >= ini, SesionCaja.cerrada_en <= fin)
        label = (desde.strftime("%d/%m/%Y") if desde == hasta
                 else f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}")
    else:
        label = "Todas las sesiones cerradas"

    if cajero_uuid:
        cajero = Usuario.query.filter_by(uuid_publico=cajero_uuid).first()
        if cajero:
            q = q.filter(SesionCaja.cajero_id == cajero.id)

    sesiones = q.order_by(SesionCaja.cerrada_en.desc()).all()

    # Consolidado general y por cajero
    total_efectivo = total_pos = total_otros = 0.0
    total_dif_efectivo = total_dif_pos = 0.0
    sesiones_descuadradas = 0
    por_cajero = {}
    filas = []

    for s in sesiones:
        d = s.to_dict()
        total_efectivo += d["total_efectivo"]
        total_pos += d["total_pos"]
        total_otros += d.get("total_otros", 0.0)
        dif_ef = d.get("diferencia_efectivo", 0.0)
        dif_pos = d.get("diferencia_pos", 0.0)
        total_dif_efectivo += dif_ef
        total_dif_pos += dif_pos
        if abs(dif_ef) > 0.009 or abs(dif_pos) > 0.009:
            sesiones_descuadradas += 1

        nombre = d["cajero"]
        pc = por_cajero.setdefault(nombre, {
            "cajero": nombre, "sesiones": 0, "efectivo": 0.0, "pos": 0.0,
            "diferencia": 0.0, "cobros": 0,
        })
        pc["sesiones"] += 1
        pc["efectivo"] += d["total_efectivo"]
        pc["pos"] += d["total_pos"]
        pc["diferencia"] += dif_ef + dif_pos
        pc["cobros"] += d["cantidad_pagos"]

        filas.append({
            "id": d["id"],
            "cajero": nombre,
            "abierta_en": d["abierta_en"],
            "cerrada_en": d["cerrada_en"],
            "monto_inicial": d["monto_inicial"],
            "total_efectivo": d["total_efectivo"],
            "total_pos": d["total_pos"],
            "cantidad_pagos": d["cantidad_pagos"],
            "diferencia_efectivo": dif_ef,
            "diferencia_pos": dif_pos,
            "cuadrada": abs(dif_ef) < 0.009 and abs(dif_pos) < 0.009,
        })

    return jsonify({"data": {
        "periodo_label": label,
        "total_sesiones": len(sesiones),
        "total_efectivo": round(total_efectivo, 2),
        "total_pos": round(total_pos, 2),
        "total_otros": round(total_otros, 2),
        "total_recaudado": round(total_efectivo + total_pos + total_otros, 2),
        "total_diferencia": round(total_dif_efectivo + total_dif_pos, 2),
        "sesiones_descuadradas": sesiones_descuadradas,
        "por_cajero": list(por_cajero.values()),
        "sesiones": filas,
        "generado": dt.date.today().isoformat(),
    }})


@reportes_bp.get("/accesos")
@roles_required("admin", "super_admin")
def reporte_accesos(usuario_actual):
    """
    Reporte de accesos y seguridad en un período.
    Filtros: ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD  ?tipo=unica|recurrente|repartidor
    Responde: totales de visitas, desglose por tipo, horas pico, casas con más
    visitas. Pensado para el administrador: control de seguridad de la comunidad.
    """
    from app.models.visita import Visita, EventoAcceso
    from app.models.cuenta import Cuenta, Unidad
    from sqlalchemy import func

    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    tipo_filtro = request.args.get("tipo")

    q = Visita.query
    if desde_str and hasta_str:
        try:
            desde = dt.date.fromisoformat(desde_str)
            hasta = dt.date.fromisoformat(hasta_str)
        except ValueError:
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido (use YYYY-MM-DD)"}}), 400
        if desde > hasta:
            desde, hasta = hasta, desde
        ini = dt.datetime.combine(desde, dt.time.min).replace(tzinfo=dt.timezone.utc)
        fin = dt.datetime.combine(hasta, dt.time.max).replace(tzinfo=dt.timezone.utc)
        q = q.filter(Visita.created_at >= ini, Visita.created_at <= fin)
        label = (desde.strftime("%d/%m/%Y") if desde == hasta
                 else f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}")
    else:
        label = "Histórico completo"

    if tipo_filtro in ("unica", "recurrente", "repartidor"):
        q = q.filter(Visita.tipo == tipo_filtro)

    visitas = q.all()
    visita_ids = [v.id for v in visitas]

    # Desglose por tipo
    por_tipo = {"unica": 0, "recurrente": 0, "repartidor": 0}
    for v in visitas:
        if v.tipo in por_tipo:
            por_tipo[v.tipo] += 1

    # Eventos de entrada de esas visitas (para horas pico y conteo real de accesos)
    eventos_entrada = []
    if visita_ids:
        eventos_entrada = (EventoAcceso.query
                           .filter(EventoAcceso.visita_id.in_(visita_ids),
                                   EventoAcceso.direccion == "entrada")
                           .all())

    # Horas pico (distribución por hora del día)
    por_hora = {h: 0 for h in range(24)}
    for e in eventos_entrada:
        if e.ocurrido_en:
            por_hora[e.ocurrido_en.hour] += 1
    horas_pico = sorted(
        [{"hora": f"{h:02d}:00", "cantidad": c} for h, c in por_hora.items() if c > 0],
        key=lambda x: x["cantidad"], reverse=True)[:5]

    # Casas que más visitas generan
    cuenta_ids = [v.cuenta_id for v in visitas if v.cuenta_id]
    conteo_casa = {}
    for cid in cuenta_ids:
        conteo_casa[cid] = conteo_casa.get(cid, 0) + 1
    top_ids = sorted(conteo_casa, key=conteo_casa.get, reverse=True)[:10]
    cuentas = {c.id: c for c in Cuenta.query.filter(Cuenta.id.in_(top_ids)).all()} if top_ids else {}
    unidad_ids = {c.unidad_id for c in cuentas.values() if c.unidad_id}
    unidades = {u.id: u for u in Unidad.query.filter(Unidad.id.in_(unidad_ids)).all()} if unidad_ids else {}
    top_casas = []
    for cid in top_ids:
        c = cuentas.get(cid)
        ident = "—"
        if c:
            u = unidades.get(c.unidad_id)
            ident = u.identificador if u else "—"
            if c.apartamento:
                ident = f"{ident} - {c.apartamento}"
        top_casas.append({"casa": ident, "visitas": conteo_casa[cid]})

    return jsonify({"data": {
        "periodo_label": label,
        "total_visitas": len(visitas),
        "total_entradas": len(eventos_entrada),
        "por_tipo": por_tipo,
        "horas_pico": horas_pico,
        "top_casas": top_casas,
        "generado": dt.date.today().isoformat(),
    }})


@reportes_bp.get("/inventario")
@roles_required("admin", "super_admin")
def reporte_inventario(usuario_actual):
    """
    Reporte de inventario de tarjetas en un período.
    Filtros: ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    Responde: stock actual por tipo, vendidas y recaudado en el período,
    alertas de stock bajo. Para que la administración controle el inventario.
    """
    from app.models.cuenta import TipoTarjeta, VentaTarjeta

    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    q = VentaTarjeta.query
    if desde_str and hasta_str:
        try:
            desde = dt.date.fromisoformat(desde_str)
            hasta = dt.date.fromisoformat(hasta_str)
        except ValueError:
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido (use YYYY-MM-DD)"}}), 400
        if desde > hasta:
            desde, hasta = hasta, desde
        ini = dt.datetime.combine(desde, dt.time.min).replace(tzinfo=dt.timezone.utc)
        fin = dt.datetime.combine(hasta, dt.time.max).replace(tzinfo=dt.timezone.utc)
        q = q.filter(VentaTarjeta.created_at >= ini, VentaTarjeta.created_at <= fin)
        label = (desde.strftime("%d/%m/%Y") if desde == hasta
                 else f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}")
    else:
        label = "Histórico completo"

    ventas = q.all()

    # Stock actual por tipo (todos los tipos)
    tipos = TipoTarjeta.query.order_by(TipoTarjeta.nombre.asc()).all()
    tipos_por_id = {t.id: t for t in tipos}

    # Vendidas y recaudado por tipo en el período
    vendidas_por_tipo = {}
    total_recaudado = 0.0
    for v in ventas:
        total_recaudado += float(v.precio)
        d = vendidas_por_tipo.setdefault(v.tipo_tarjeta_id, {"cantidad": 0, "recaudado": 0.0})
        d["cantidad"] += 1
        d["recaudado"] += float(v.precio)

    filas = []
    stock_total = 0
    bajo_stock = 0
    for t in tipos:
        vt = vendidas_por_tipo.get(t.id, {"cantidad": 0, "recaudado": 0.0})
        stock_total += t.stock
        if t.activo and t.stock <= 5:
            bajo_stock += 1
        filas.append({
            "nombre": t.nombre,
            "tipo_acceso": t.tipo_acceso,
            "precio": float(t.precio),
            "stock": t.stock,
            "activo": t.activo,
            "vendidas_periodo": vt["cantidad"],
            "recaudado_periodo": round(vt["recaudado"], 2),
            "bajo_stock": t.activo and t.stock <= 5,
        })

    return jsonify({"data": {
        "periodo_label": label,
        "total_vendidas": len(ventas),
        "total_recaudado": round(total_recaudado, 2),
        "stock_total": stock_total,
        "tipos_bajo_stock": bajo_stock,
        "tipos": filas,
        "generado": dt.date.today().isoformat(),
    }})


@reportes_bp.get("/ejecutivo")
@roles_required("admin", "super_admin")
def reporte_ejecutivo(usuario_actual):
    """
    Resumen ejecutivo del mes: los KPIs clave en un solo lugar, pensado para
    imprimir y llevar a la junta de la residencial.

    Incluye: cobranza del mes, cartera vencida, morosidad, accesos del mes y
    tasa de recuperación de mora.
    """
    from sqlalchemy import func
    from app.models.visita import EventoAcceso

    hoy = dt.date.today()
    anio = int(request.args.get("anio", hoy.year))
    mes = int(request.args.get("mes", hoy.month))
    ini_mes = dt.date(anio, mes, 1)
    fin_mes = dt.date(anio + (mes // 12), (mes % 12) + 1, 1) - dt.timedelta(days=1)
    meses_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    mes_label = f"{meses_es[mes]} {anio}"

    # ── Cobranza del mes (cuotas cuyo periodo es este mes) ──
    cuotas_mes = Cuota.query.filter(Cuota.periodo == ini_mes).all()
    total_esperado = sum(float(c.monto) for c in cuotas_mes)
    total_recaudado = sum(float(c.monto) for c in cuotas_mes if c.estado == "pagada")
    pct_cobranza = round((total_recaudado / total_esperado * 100), 1) if total_esperado else 0.0

    # ── Cartera vencida total (todas las cuotas no pagadas ya vencidas) ──
    cuotas_vencidas = (Cuota.query
                       .filter(Cuota.estado != "pagada", Cuota.fecha_vencimiento < hoy)
                       .all())
    cartera_vencida = sum(float(c.monto) for c in cuotas_vencidas)
    casas_en_mora = len({c.cuenta_id for c in cuotas_vencidas})

    # ── Morosidad: % de cuentas activas con al menos una cuota vencida ──
    cuentas_activas = Cuenta.query.filter_by(activa=True).count()
    pct_morosidad = round((casas_en_mora / cuentas_activas * 100), 1) if cuentas_activas else 0.0

    # ── Accesos del mes (eventos de residentes) ──
    ini_dt = dt.datetime.combine(ini_mes, dt.time.min).replace(tzinfo=dt.timezone.utc)
    fin_dt = dt.datetime.combine(fin_mes, dt.time.max).replace(tzinfo=dt.timezone.utc)
    accesos_mes = (EventoAcceso.query
                   .filter(EventoAcceso.ocurrido_en >= ini_dt,
                           EventoAcceso.ocurrido_en <= fin_dt)
                   .count())

    # ── Tasa de recuperación de mora ──
    # De los pagos aprobados este mes, cuántos correspondían a cuotas que ya
    # estaban vencidas al momento de pagar (= recuperación de cartera vieja).
    fecha_sql = func.coalesce(Pago.revisado_en, Pago.created_at)
    pagos_mes = (Pago.query
                 .filter(Pago.estado == "aprobado",
                         fecha_sql >= ini_dt, fecha_sql <= fin_dt,
                         Pago.cuota_id.isnot(None))
                 .all())
    recuperado = 0.0
    total_pagado_mes = 0.0
    for p in pagos_mes:
        monto = float(p.monto)
        total_pagado_mes += monto
        cuota = Cuota.query.get(p.cuota_id)
        if cuota:
            f = p.revisado_en or p.created_at
            fecha_pago = f.date() if f else hoy
            if cuota.fecha_vencimiento < fecha_pago:
                recuperado += monto
    pct_recuperacion = round((recuperado / total_pagado_mes * 100), 1) if total_pagado_mes else 0.0

    return jsonify({"data": {
        "mes_label": mes_label,
        "anio": anio, "mes": mes,
        "total_esperado": round(total_esperado, 2),
        "total_recaudado": round(total_recaudado, 2),
        "total_pendiente": round(total_esperado - total_recaudado, 2),
        "pct_cobranza": pct_cobranza,
        "cartera_vencida": round(cartera_vencida, 2),
        "casas_en_mora": casas_en_mora,
        "cuentas_activas": cuentas_activas,
        "pct_morosidad": pct_morosidad,
        "accesos_mes": accesos_mes,
        "recuperado_mora": round(recuperado, 2),
        "pct_recuperacion": pct_recuperacion,
        "generado": dt.datetime.utcnow().isoformat() + "Z",
    }})
