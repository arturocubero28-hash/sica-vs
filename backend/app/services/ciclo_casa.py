"""
Día 74 — ciclo de vida de una casa: padrón ⇄ sistema de cuotas ⇄ mudanza.

Antes del Día 74 una casa podía entrar al sistema desde el padrón, pero no
había un camino de vuelta. Si una familia ya no quería o no podía pagar la
mensualidad, la única salida era la baja, que exige saldo en cero y saca a
la casa de todos lados -- incluido el padrón, donde la familia sigue
viviendo y el guardia la tiene que poder identificar.

LAS REGLAS (definidas con el patronato):

  1. Volver al padrón (sigue viviendo ahí, deja de pagar mensualidad):
       - sin deuda                → directo.
       - con deuda                → solo con un arreglo de pago firmado
                                    "para volver al padrón".
     La cuota del mes se nivela a la fecha y no se generan más. Los abonos
     del arreglo siguen pendientes y se pagan en caja. La app queda
     suspendida: la familia vuelve a ser gente de padrón para el guardia.

  2. Volver a sumarse desde el padrón:
       - solo si va al día con el arreglo (ningún abono vencido) y no debe
         nada fuera de él. Paga la cuota nueva prorrateada MÁS los abonos
         que le falten.

  3. Si incumple el arreglo estando en el padrón: el arreglo queda
     incumplido, la deuda sigue pendiente a su nombre, NO se le bloquea el
     portón (no tiene servicio que cortar) y no puede volver a sumarse
     hasta pagarla.

  4. Mudanza: se puede dar de baja con deuda. La deuda queda a nombre del
     titular, y la regla anti-mora por DNI le impide darse de alta en otra
     casa hasta pagarla. La cuenta no se borra: queda el historial.
"""
import datetime as dt

from app.extensions import db
from app.utils.fechas import mes_es


IMPAGAS = ("pendiente", "parcial", "vencida")


def monto_pagado_cuota(cuota):
    """Suma los pagos APROBADOS de una cuota."""
    from app.models.cuenta import Pago
    total = (Pago.query.filter_by(cuota_id=cuota.id, estado="aprobado")
             .with_entities(db.func.coalesce(db.func.sum(Pago.monto), 0)).scalar())
    return float(total or 0)


def saldo_cuota(cuota):
    return round(max(float(cuota.monto) - monto_pagado_cuota(cuota), 0.0), 2)


def inicio_de_cobro(cuota):
    """
    Día comercial (1-30) desde el que cobra la cuota.

    Día 75 — la primera cuota de una casa nueva NO cubre el mes entero: va
    del día siguiente al alta hasta el 30 (utils/cuotas.py). Desde el Día 75
    eso queda guardado en cobra_desde_dia. Para las cuotas creadas antes se
    deduce del monto: si es menor que la tarifa de la casa, cubre
    monto / (tarifa / 30) días contados hacia atrás desde el 30.
    """
    if cuota.cobra_desde_dia:
        return max(1, min(int(cuota.cobra_desde_dia), 30))
    from app.models.cuenta import Cuenta
    cuenta = Cuenta.query.get(cuota.cuenta_id)
    tarifa = getattr(getattr(cuenta, "tarifa", None), "monto", None)
    base = float(cuota.monto_original if cuota.monto_original is not None else cuota.monto)
    if tarifa and float(tarifa) > 0 and base < float(tarifa) - 0.01:
        dias = round(base / (float(tarifa) / 30))
        if 1 <= dias < 30:
            return 31 - dias
    return 1


def tramo_nivelado(cuota, fecha_des):
    """
    Cálculo PURO (no modifica nada) de cómo quedaría una cuota si la casa deja
    de pagar en fecha_des. Lo usan nivelar_cuotas (que lo aplica) y el panel
    del arreglo (que lo muestra antes de firmar). Devuelve un dict con
    accion = "igual" | "anulada" | "prorrateada".

    MODELO DE COBRO (Día 62, el que usan el alta y el cron mensual): la
    cuota de un mes cobra los días de ESE mes, en mes comercial de 30 días,
    y vence el día de pago del mes SIGUIENTE. La primera cuota de una casa
    nueva arranca el día siguiente al alta. Para la cuota del mes en que
    deja de pagar se cobran los días desde que empezó a cobrar esa cuota
    hasta fecha_des, inclusive:

        alta el 2 de noviembre → la cuota cobra del 3 al 30 (28 días)
        deja de pagar el 6     → se cobran del 3 al 6 (4 días)

    Las de meses anteriores se consumieron completas; las de meses
    posteriores se anulan.
    """
    periodo = cuota.periodo
    baseline = float(cuota.monto_original if cuota.monto_original is not None else cuota.monto)
    inicio = inicio_de_cobro(cuota)
    dias_cubiertos = 31 - inicio
    base = {"periodo": periodo.isoformat(), "monto_original": baseline}
    mes_cuota = (periodo.year, periodo.month)
    mes_salida = (fecha_des.year, fecha_des.month)
    if mes_salida > mes_cuota:
        return {**base, "accion": "igual", "monto_final": float(cuota.monto)}
    dia_salida = min(fecha_des.day, 30)
    if mes_salida < mes_cuota or dia_salida < inicio:
        return {**base, "accion": "anulada", "monto_final": 0.0}
    dias = dia_salida - inicio + 1
    diario = baseline / dias_cubiertos
    return {**base, "accion": "prorrateada", "dias_ocupados": dias,
            "desde_dia": inicio, "hasta_dia": dia_salida,
            "monto_diario": round(diario, 2), "monto_final": round(diario * dias, 2)}


def nivelar_cuotas(cuotas, fecha_des):
    """
    Deja cada cuota impaga en lo que corresponde a los días que la casa
    estuvo, si deja de pagar en fecha_des (se muda o vuelve al padrón). El
    cálculo está en tramo_nivelado.

    Día 75 — corregido. Antes contaba los días desde el día de pago DEL
    MISMO mes (el modelo de cobro anterior al Día 62) y tomaba el monto ya
    prorrateado como si fuera un mes completo.

    No hace commit.
    """
    ajustes = []
    for cuota in cuotas:
        t = tramo_nivelado(cuota, fecha_des)
        if t["accion"] == "igual":
            continue  # ese mes lo vivió entero: la cuota queda como estaba
        # Fijar el monto original SOLO la primera vez — evita que nivelaciones
        # repetidas sigan achicando el monto sobre un valor ya reducido.
        if cuota.monto_original is None:
            cuota.monto_original = cuota.monto
        pagado = monto_pagado_cuota(cuota)
        if t["accion"] == "anulada":
            cuota.monto = pagado  # dejarla en lo ya pagado
            cuota.estado = "pagada" if pagado > 0 else "anulada"
            cuota.nivelada = True
            ajustes.append({**t, "monto_final": float(cuota.monto)})
            continue
        cuota.monto = max(t["monto_final"], pagado)  # nunca menos de lo ya pagado
        cuota.nivelada = True
        if pagado >= float(cuota.monto):
            cuota.estado = "pagada"
        ajustes.append({**t, "monto_final": float(cuota.monto)})
    return ajustes


def restaurar_nivelacion(cuota):
    """
    Día 75 — deshace la nivelación de una cuota: vuelve a su monto completo.
    Para cuando la nivelación estaba condicionada a que la casa saliera (un
    arreglo «para volver al padrón» que se cancela o se incumple con la casa
    todavía en el sistema). No hace commit.
    """
    if cuota.nivelada and cuota.monto_original is not None:
        cuota.monto = cuota.monto_original
        cuota.nivelada = False


def cuotas_fuera_de_arreglo(cuenta):
    """Cuotas impagas que NO están congeladas en un arreglo activo."""
    from app.models.cuenta import Cuota
    return (Cuota.query
            .filter(Cuota.cuenta_id == cuenta.id, Cuota.estado.in_(IMPAGAS))
            .order_by(Cuota.periodo.asc()).all())


def pagos_en_revision(cuenta):
    """
    Día 76 — comprobantes que el residente subió y la administración todavía
    no revisó (de cuotas o de abonos de un arreglo).

    Mientras un comprobante está en revisión, la cuota queda en estado
    'en_revision' y deja de contarse como impaga. Pero no es dinero todavía:
    el admin lo puede rechazar. Antes, con un comprobante sin revisar, la
    casa aparecía como que «no debe nada» y se podía dar de baja o pasar al
    padrón; si después el comprobante se rechazaba, la deuda quedaba a
    nombre de alguien que ya no está en el sistema.
    """
    from app.models.cuenta import Pago
    return (Pago.query.filter(Pago.cuenta_id == cuenta.id, Pago.estado == "en_revision")
            .order_by(Pago.id.asc()).all())


def resumen_en_revision(cuenta):
    """{cantidad, monto} de los comprobantes sin revisar, o None si no hay."""
    pagos = pagos_en_revision(cuenta)
    if not pagos:
        return None
    return {"cantidad": len(pagos), "monto": round(sum(float(p.monto) for p in pagos), 2)}


def impedimento_en_revision(cuenta, que="sacar la casa del sistema"):
    """(code, mensaje, 409) si hay comprobantes sin revisar; si no, None."""
    r = resumen_en_revision(cuenta)
    if r is None:
        return None
    cuantos = "un comprobante" if r["cantidad"] == 1 else f"{r['cantidad']} comprobantes"
    return ("comprobante_en_revision",
            f"La casa tiene {cuantos} de pago sin revisar (L {r['monto']:,.2f}). Antes de "
            f"{que}, revisalo en Pagos: si lo aprobás, queda pagado; si lo rechazás, se "
            "cobra en caja.", 409)


def arreglo_activo(cuenta):
    from app.models.cuenta import ArregloPago
    return ArregloPago.query.filter_by(cuenta_id=cuenta.id, estado="activo").first()


def estado_deuda(cuenta):
    """
    Resumen de lo que debe una casa, para mostrarlo en el padrón y para
    decidir si puede volver a sumarse. Distingue lo que está en un arreglo
    (se paga en abonos) de lo que no.
    """
    fuera = cuotas_fuera_de_arreglo(cuenta)
    total_fuera = round(sum(saldo_cuota(c) for c in fuera), 2)
    arr = arreglo_activo(cuenta)
    d = {
        "fuera_de_arreglo": total_fuera,
        "cuotas_fuera_de_arreglo": len([c for c in fuera if saldo_cuota(c) > 0]),
        "arreglo": None,
    }
    if arr is not None:
        prox = arr.proximo_abono()
        d["arreglo"] = {
            "id": str(arr.uuid_publico),
            "proposito": arr.proposito,
            "saldo_pendiente": arr.saldo_pendiente(),
            "abonos_pagados": arr.abonos_pagados(),
            "abonos_total": len(arr.abonos),
            "atrasado": arr.atrasado(),
            "proximo_abono": prox.to_dict() if prox else None,
        }
    d["total"] = round(total_fuera + (d["arreglo"]["saldo_pendiente"] if d["arreglo"] else 0), 2)
    d["al_dia"] = total_fuera == 0 and not (d["arreglo"] and d["arreglo"]["atrasado"])
    # Día 76 — lo que está pagado «a medias»: comprobantes sin revisar.
    d["en_revision"] = resumen_en_revision(cuenta)
    return d


def _dinero(x):
    from decimal import Decimal, ROUND_HALF_UP
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quitar_cuotas_de_arreglo(arr, salen, parte, motivo, quien):
    """
    Día 76 — saca del arreglo `salen` (cuotas cuya parte financiada era
    `parte`) y reparte lo que falta en los abonos que quedan.

    Lo ya pagado no se toca. Si al sacarlas lo abonado ya cubre la deuda que
    queda, se devuelve un error: no hay forma honesta de devolver ese
    sobrante desde acá. No hace commit.
    """
    from decimal import Decimal
    parte = _dinero(parte)
    original = _dinero(arr.deuda_original if arr.deuda_original is not None else arr.deuda_total)
    nuevo_original = original - parte
    pct = _dinero(arr.descuento_pct or 0)
    nuevo_desc = _dinero(nuevo_original * pct / 100) if pct > 0 else Decimal("0.00")
    nuevo_total = nuevo_original - nuevo_desc
    pagado = sum((_dinero(a.monto) for a in arr.abonos if a.estado == "pagado"), Decimal("0.00"))
    falta = nuevo_total - pagado
    pendientes = sorted((a for a in arr.abonos if a.estado in ("pendiente", "vencido")),
                        key=lambda a: a.numero)
    if falta < 0 or (falta > 0 and not pendientes):
        return ("arreglo_sobrepagado",
                f"Lo abonado al arreglo (L {pagado:,.2f}) ya cubre la deuda que queda sin esas cuotas "
                f"(L {nuevo_total:,.2f}). Revisá el caso a mano antes de seguir.", 409)

    for c in salen:
        c.arreglo_id = None
        c.estado = "pendiente"
    arr.deuda_original = nuevo_original
    arr.descuento_monto = nuevo_desc if pct > 0 else arr.descuento_monto
    arr.deuda_total = nuevo_total
    arr.saldo_financiado = nuevo_total - _dinero(arr.abono_inicial or 0)
    hoy = dt.date.today()
    if falta == 0:
        for a in pendientes:
            db.session.delete(a)
        arr.num_abonos = max(len(arr.abonos) - len(pendientes) - (1 if _prima(arr) else 0), 0)
        arr.estado = "completado"
        arr.completado_en = dt.datetime.now(dt.timezone.utc)
        arr.motivo_cierre = "Lo abonado cubrió la deuda que quedó"
        for c in arr.cuotas:
            if c not in salen:
                c.estado = "pagada"
    else:
        arr.monto_por_abono = repartir_en_abonos(arr, falta, pendientes)
    arr.nota = (f"{arr.nota or ''}\n[{hoy.strftime('%d/%m/%Y')}] {quien}: {motivo}").strip()[:500]
    return None


def _prima(arr):
    """El abono 1 cuando el arreglo se firmó con prima (abono_inicial)."""
    if not arr.abono_inicial or _dinero(arr.abono_inicial) <= 0:
        return None
    return next((a for a in arr.abonos if a.numero == 1), None)


def repartir_en_abonos(arr, falta, pendientes):
    """
    Reparte `falta` en los abonos `pendientes` (ordenados por número).
    Día 76 — la PRIMA pactada no se toca si todavía no se pagó: es el monto
    que la familia acordó dar al firmar. Lo que falta se reparte parejo en
    los abonos normales (el último absorbe el redondeo). Solo si los abonos
    normales no alcanzan a absorber el cambio se ajusta también la prima.
    Devuelve el monto base por abono. No hace commit.
    """
    prima = _prima(arr)
    prima = prima if prima in pendientes else None
    normales = [a for a in pendientes if a is not prima]
    if prima is not None:
        monto_prima = _dinero(arr.abono_inicial)
        resto = falta - monto_prima
        if normales and resto > 0:
            prima.monto = monto_prima
            pendientes, falta = normales, resto
    base = _dinero(falta / len(pendientes))
    for i, a in enumerate(pendientes):
        a.monto = base if i < len(pendientes) - 1 else falta - base * (len(pendientes) - 1)
    return base


def preparar_regreso_con_arreglo(cuenta, quien, aplicar=False):
    """
    Día 76 — una casa del padrón que vuelve a sumarse con un arreglo activo.

    Caso real (casa 2): firmó un arreglo «para volver al padrón» que incluía
    la cuota del mes en curso nivelada hasta el día de la firma, pasó al
    padrón, pagó un abono y volvió a sumarse ESE MISMO MES. Al volver, a esa
    cuota (que seguía dentro del arreglo) se le sumaron los días que faltan
    y quedó «pendiente»: los días antes de salir se cobraban dos veces, en
    el arreglo y en la cuota.

    Regla: esa cuota entró al arreglo SOLO porque la casa se iba. Si vuelve
    el mismo mes, sale del arreglo y se paga normal (con los días que faltan
    sumados); el arreglo queda con la deuda vieja y los abonos que faltan se
    recalculan. Además el arreglo pasa a ser «para ponerse al día», porque
    la casa ya no se va. Si vuelve en otro mes, la cuota nivelada es deuda
    vieja de verdad y se queda en el arreglo.

    Devuelve (texto_para_el_admin | None, error | None). Con aplicar=False
    solo valida (no cambia nada).
    """
    arr = arreglo_activo(cuenta)
    if arr is None:
        return None, None
    hoy = dt.date.today()
    salen = [c for c in arr.cuotas
             if c.nivelada and (c.periodo.year, c.periodo.month) == (hoy.year, hoy.month)]
    if not aplicar:
        if not salen:
            return None, None
        from decimal import Decimal
        parte = sum((_dinero(c.monto) for c in salen), Decimal("0.00"))
        original = _dinero(arr.deuda_original if arr.deuda_original is not None else arr.deuda_total)
        pct = _dinero(arr.descuento_pct or 0)
        resto = original - parte
        resto = resto - (_dinero(resto * pct / 100) if pct > 0 else 0)
        pagado = sum((_dinero(a.monto) for a in arr.abonos if a.estado == "pagado"), Decimal("0.00"))
        if pagado > resto:
            return None, ("arreglo_sobrepagado",
                          f"Lo abonado al arreglo (L {pagado:,.2f}) ya supera la deuda vieja "
                          f"(L {resto:,.2f}). Revisá el caso a mano antes de sumarla.", 409)
        return None, None

    textos = []
    if salen:
        from decimal import Decimal
        parte = sum((_dinero(c.monto) for c in salen), Decimal("0.00"))
        mes = mes_es(salen[0].periodo)
        err = quitar_cuotas_de_arreglo(
            arr, salen, parte,
            f"la casa volvió a sumarse el mismo mes; la cuota de {mes} salió del arreglo "
            "(se paga normal) y se recalcularon los abonos que faltan.", quien)
        if err:
            return None, err
        textos.append(f"La cuota de {mes} salió del arreglo de pago y se paga normal; "
                      "los abonos que faltan se recalcularon.")
    if arr.estado == "activo" and arr.proposito == "volver_al_padron":
        arr.proposito = "ponerse_al_dia"
        arr.nota = (f"{arr.nota or ''}\n[{hoy.strftime('%d/%m/%Y')}] {quien}: la casa volvió a "
                    "sumarse; el arreglo sigue «para ponerse al día».").strip()[:500]
        textos.append("El arreglo sigue activo, ahora «para ponerse al día».")
    return (" ".join(textos) or None), None


def puede_volver_a_sumarse(cuenta):
    """
    Regla 2. Devuelve (None) si puede, o (code, mensaje) si no.
    Solo aplica a casas que ya estuvieron en el sistema y volvieron (o que
    arrastran deuda): una casa del padrón sin historia no debe nada.
    """
    arr = arreglo_activo(cuenta)
    if arr is not None and arr.atrasado():
        ab = next(a for a in sorted(arr.abonos, key=lambda x: x.fecha_pactada)
                  if a.estado in ("pendiente", "vencido") and a.fecha_pactada < dt.date.today())
        return ("arreglo_atrasado",
                f"Esta casa debe el abono {ab.numero} de su arreglo de pago, que venció el "
                f"{ab.fecha_pactada.strftime('%d/%m/%Y')} (L {float(ab.monto):,.2f}). "
                "Tiene que ponerse al día con el arreglo antes de volver a sumarse.")
    fuera = cuotas_fuera_de_arreglo(cuenta)
    total = round(sum(saldo_cuota(c) for c in fuera), 2)
    if total > 0:
        return ("deuda_pendiente",
                f"Esta casa debe L {total:,.2f} de cuando estaba en el sistema "
                "(o de un arreglo que no cumplió). Tiene que pagarlo en caja antes de volver a sumarse.")
    return None


def suspender_accesos(cuenta):
    """
    Apaga la app y las credenciales de la casa. A los usuarios se les deja
    la marca suspendido_por_padron para poder prenderlos de nuevo si la
    casa se vuelve a sumar, SIN tocar a alguien que la administración ya
    había desactivado por otra razón. No hace commit.
    """
    from app.models.cuenta import Tarjeta, TarjetaVirtual, CredencialBLE
    from app.models.visita import Visita
    resumen = {"usuarios": 0, "tarjetas": 0, "credenciales": 0, "visitas": 0}
    for r in cuenta.residentes:
        u = r.usuario
        if r.activo and u is not None and u.activo and not u.es_censo:
            u.activo = False
            u.suspendido_por_padron = True
            resumen["usuarios"] += 1
    for t in Tarjeta.query.filter_by(cuenta_id=cuenta.id, estado="activa").all():
        t.estado = "desactivada"
        t.fecha_baja = dt.date.today()
        resumen["tarjetas"] += 1
    for modelo in (TarjetaVirtual, CredencialBLE):
        for c in modelo.query.filter_by(cuenta_id=cuenta.id, estado="activa").all():
            c.estado = "suspendida"
            resumen["credenciales"] += 1
    # Los QR de visita que la familia ya había compartido dejan de servir:
    # una visita entra con un QR de la casa, y la casa ya no lo puede emitir.
    for v in Visita.query.filter_by(cuenta_id=cuenta.id, estado="activa").all():
        v.estado = "revocada"
        resumen["visitas"] += 1
    return resumen


def contar_accesos(cuenta):
    """Lo que se apagaría al sacar la casa del sistema, sin tocar nada.
    Para que el panel lo muestre ANTES de confirmar."""
    from app.models.cuenta import Tarjeta, TarjetaVirtual, CredencialBLE
    from app.models.visita import Visita
    return {
        "usuarios": sum(1 for r in cuenta.residentes
                        if r.activo and r.usuario is not None and r.usuario.activo
                        and not r.usuario.es_censo),
        "tarjetas": Tarjeta.query.filter_by(cuenta_id=cuenta.id, estado="activa").count(),
        "credenciales": sum(m.query.filter_by(cuenta_id=cuenta.id, estado="activa").count()
                            for m in (TarjetaVirtual, CredencialBLE)),
        "visitas": Visita.query.filter_by(cuenta_id=cuenta.id, estado="activa").count(),
    }


def reactivar_suspendidos(cuenta):
    """Al volver a sumarse: prende solo a quienes se apagó por el padrón."""
    n = 0
    for r in cuenta.residentes:
        u = r.usuario
        if r.activo and u is not None and u.suspendido_por_padron:
            u.activo = True
            u.suspendido_por_padron = False
            n += 1
    return n


def volver_al_padron(cuenta, fecha, usuario_actual):
    """
    Regla 1. Valida y aplica, SIN commit. Devuelve:
      (resumen, None)  → se aplicó;
      (resumen, err)   → no se puede todavía, pero hay números que mostrar
                         (cuánto debe, los días del mes): el panel los usa
                         para explicar qué falta;
      (None, err)      → no se puede y no hay nada que mostrar.
    err = (code, mensaje, status). Si hay error, quien llama hace rollback:
    la nivelación ya se aplicó en la sesión para poder medir lo que queda.
    """
    from app.models.cuenta import Cuenta

    if not cuenta.activa:
        return None, ("cuenta_inactiva", "Esta casa está dada de baja.", 400)
    if cuenta.es_censo:
        return None, ("ya_en_padron", "Esta casa ya está en el padrón.", 400)
    if cuenta.es_contenedor_edificio():
        return None, ("es_contenedora",
                      "La administración de un edificio no paga cuota: vuelven al padrón "
                      "los apartamentos, uno por uno.", 400)
    hoy = dt.date.today()
    if fecha > hoy:
        return None, ("fecha_invalida", "La fecha no puede ser futura.", 400)

    arr = arreglo_activo(cuenta)
    if arr is not None and arr.proposito != "volver_al_padron":
        return None, ("arreglo_para_seguir",
                      "Esta casa tiene un arreglo de pago firmado para ponerse al día y "
                      "SEGUIR pagando. Si ahora quiere volver al padrón, cambiá el propósito "
                      "del arreglo (en Arreglos de pago) y volvé a intentarlo.", 409)

    # ¿La cuota del mes ya estaba nivelada? (el admin niveló, fue a caja y
    # volvió): el panel salta ese paso.
    ya_nivelada = any(c.nivelada for c in cuotas_fuera_de_arreglo(cuenta)
                      if (c.periodo.year, c.periodo.month) == (fecha.year, fecha.month))
    # Si ya se cobró, ya no está entre las impagas: también cuenta como hecho.
    from app.models.cuenta import Cuota as _Cuota
    ya_nivelada = ya_nivelada or _Cuota.query.filter(
        _Cuota.cuenta_id == cuenta.id, _Cuota.nivelada.is_(True),
        _Cuota.periodo == dt.date(fecha.year, fecha.month, 1)).first() is not None

    # La cuota del mes se nivela a los días que estuvo; las de meses
    # posteriores se anulan. Mismo cálculo que "Nivelar saldo" en una mudanza.
    ajustes = nivelar_cuotas(cuotas_fuera_de_arreglo(cuenta), fecha)
    db.session.flush()

    # Día 75 — el arreglo es para la deuda ATRASADA, no para la cuota del mes
    # en curso. Antes se exigía arreglo por cualquier saldo, y a una casa
    # dada de alta el 2 que volvía al padrón el 6 se le pedía firmar un
    # arreglo por una cuota que ni siquiera había vencido. Ahora lo que
    # todavía no vence (ya nivelado) queda pendiente y se paga en caja; solo
    # lo vencido necesita arreglo.
    fuera = cuotas_fuera_de_arreglo(cuenta)
    vencidas = [c for c in fuera if c.fecha_vencimiento < hoy]
    total_vencido = round(sum(saldo_cuota(c) for c in vencidas), 2)
    total_fuera = round(sum(saldo_cuota(c) for c in fuera), 2)
    resumen = {
        "ajustes": ajustes,
        "queda_debiendo_fuera_de_arreglo": total_fuera,
        "queda_vencido_fuera_de_arreglo": total_vencido,
        "a_cobrar_antes_de_salir": round(total_fuera - total_vencido, 2) if arr is None else total_fuera,
        "ya_nivelada": ya_nivelada,
        "arreglo": estado_deuda(cuenta)["arreglo"],
        "afectados": contar_accesos(cuenta),
        "en_revision": resumen_en_revision(cuenta),
    }
    # Día 76 — un comprobante sin revisar no es un pago todavía.
    imp = impedimento_en_revision(cuenta, "pasarla al padrón")
    if imp is not None:
        return resumen, imp
    if total_vencido > 0 and arr is None:
        return resumen, ("deuda_sin_arreglo",
                      f"La casa tiene L {total_vencido:,.2f} en cuotas vencidas. Para volver al "
                      "padrón tiene que pagarlas en caja, o firmar un arreglo de pago "
                      "«para volver al padrón».", 409)
    # Día 75 — decisión del usuario: lo que queda por pagar FUERA de un
    # arreglo (los días que estuvo este mes) se paga ANTES de salir, como
    # quien cierra la cuenta al irse. Así no queda nada que perseguir
    # después. Para que caja cobre el monto nivelado y no la cuota entera,
    # primero hay que nivelarla a la fecha (endpoint nivelar-saldo); el
    # panel lo ofrece con un botón.
    if total_fuera > 0:
        dias = [a for a in ajustes if a["accion"] == "prorrateada"]
        detalle = ""
        if len(dias) == 1:
            detalle = f" por los {dias[0]['dias_ocupados']} días que estuvo en el mes"
        return resumen, ("pagar_antes_de_salir",
                      f"Antes de pasar al padrón, la casa tiene que pagar en caja L {total_fuera:,.2f}"
                      f"{detalle}. Nivelá la cuota a la fecha {fecha.strftime('%d/%m/%Y')} para "
                      "que caja cobre solo eso, y después volvé a pasarla al padrón.", 409)

    cuenta.modo_participacion = "censo"
    cuenta.tarifa_id = None
    cuenta.dia_pago = None
    cuenta.fecha_regreso_padron = fecha
    cuenta.estado = "al_dia"
    cuenta.bloqueada = False
    cuenta.acceso_pausado = False

    # Si era el último apartamento participando, el edificio vuelve con él
    # (lo inverso de _aplicar_conversion en api/censo.py).
    if cuenta.apartamento and cuenta.unidad and cuenta.unidad.tipo == "edificio":
        otros = (Cuenta.query.filter(Cuenta.unidad_id == cuenta.unidad_id,
                                     Cuenta.activa.is_(True),
                                     Cuenta.apartamento.isnot(None),
                                     Cuenta.id != cuenta.id,
                                     Cuenta.modo_participacion == "completa").count())
        if otros == 0:
            cont = Cuenta.query.filter_by(unidad_id=cuenta.unidad_id,
                                          apartamento=None, activa=True).first()
            if cont is not None and not cont.es_censo:
                cont.modo_participacion = "censo"

    resumen["suspendidos"] = suspender_accesos(cuenta)
    return resumen, None


def dar_de_baja(cuenta, motivo, fecha=None):
    """
    Regla 4. Mudanza: la cuenta queda inactiva como historial. No hace
    commit ni mira la deuda (eso lo decide quien llama).
    """
    from app.models.cuenta import Tarjeta
    cuenta.activa = False
    cuenta.estado = "baja"
    cuenta.bloqueada = False
    cuenta.fecha_baja = fecha or dt.date.today()
    cuenta.motivo_baja = (motivo or "Mudanza")[:255]
    for r in cuenta.residentes:
        if r.usuario and not r.usuario.es_censo:
            r.usuario.activo = False
    desactivadas = 0
    for t in Tarjeta.query.filter_by(cuenta_id=cuenta.id).all():
        if t.estado == "activa":
            t.estado = "desactivada"
            t.fecha_baja = dt.date.today()
            desactivadas += 1
    from app.models.cuenta import TarjetaVirtual, CredencialBLE
    from app.models.visita import Visita
    for modelo in (TarjetaVirtual, CredencialBLE):
        for c in modelo.query.filter_by(cuenta_id=cuenta.id, estado="activa").all():
            c.estado = "suspendida"
    for v in Visita.query.filter_by(cuenta_id=cuenta.id, estado="activa").all():
        v.estado = "revocada"
    return desactivadas
