"""
Módulo de Reportería — /api/v1/reportes/

Reportes financieros para el patronato: cobranza, morosos, recaudación.
"""
import datetime as dt
import calendar
from collections import defaultdict

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.cuenta import Cuenta, Cuota, Pago, Unidad
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
    anio = int(request.args.get("anio", hoy.year))
    mes = int(request.args.get("mes", hoy.month))
    periodo = dt.date(anio, mes, 1)

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
        "mes_label": periodo.strftime("%B %Y"),
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
