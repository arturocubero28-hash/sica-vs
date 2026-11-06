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


def nivelar_cuotas(cuotas, fecha_des):
    """
    Deja cada cuota impaga en lo que corresponde a los días que la casa
    estuvo, si deja de pagar en fecha_des (se muda o vuelve al padrón).

    MODELO DE COBRO (Día 62, el que usan el alta y el cron mensual): la
    cuota de un mes cobra los días de ESE mes, en mes comercial de 30 días,
    y vence el día de pago del mes SIGUIENTE. La primera cuota de una casa
    nueva arranca el día siguiente al alta.

    Por eso, para la cuota del mes en que deja de pagar se cobran los días
    desde que empezó a cobrar esa cuota hasta fecha_des, inclusive:

        alta el 2 de noviembre → la cuota cobra del 3 al 30 (28 días)
        deja de pagar el 6     → se cobran del 3 al 6 (4 días)

    Las de meses anteriores se consumieron completas y no se tocan; las de
    meses posteriores se anulan.

    Día 75 — corregido. Antes contaba los días desde el día de pago DEL
    MISMO mes (el modelo de cobro anterior al Día 62) y tomaba el monto ya
    prorrateado como si fuera un mes completo: a una casa dada de alta el 2
    que se iba el 6 le cobraba mal, y si se iba antes del día de pago, nada.

    No hace commit.
    """
    ajustes = []
    for cuota in cuotas:
        periodo = cuota.periodo  # primer día del mes del período
        # Fijar el monto original SOLO la primera vez — evita que nivelaciones
        # repetidas sigan achicando el monto sobre un valor ya reducido.
        if cuota.monto_original is None:
            cuota.monto_original = cuota.monto
        baseline = float(cuota.monto_original)
        inicio = inicio_de_cobro(cuota)
        dias_cubiertos = 31 - inicio
        pagado = monto_pagado_cuota(cuota)

        mes_cuota = (periodo.year, periodo.month)
        mes_salida = (fecha_des.year, fecha_des.month)
        if mes_salida > mes_cuota:
            continue  # ese mes lo vivió entero: la cuota queda como estaba
        dia_salida = min(fecha_des.day, 30)
        if mes_salida < mes_cuota or dia_salida < inicio:
            # Se fue antes de que esta cuota empezara a cobrar → anularla
            cuota.monto = pagado  # dejarla en lo ya pagado
            cuota.estado = "pagada" if pagado > 0 else "anulada"
            cuota.nivelada = True
            ajustes.append({
                "periodo": periodo.isoformat(),
                "accion": "anulada",
                "monto_original": baseline,
                "monto_final": float(cuota.monto),
            })
            continue

        dias_ocupados = dia_salida - inicio + 1
        monto_diario = baseline / dias_cubiertos
        monto_nivelado = round(monto_diario * dias_ocupados, 2)
        cuota.monto = max(monto_nivelado, pagado)  # nunca menos de lo ya pagado
        cuota.nivelada = True
        if pagado >= float(cuota.monto):
            cuota.estado = "pagada"
        ajustes.append({
            "periodo": periodo.isoformat(),
            "accion": "prorrateada",
            "dias_ocupados": dias_ocupados,
            "monto_original": baseline,
            "monto_final": float(cuota.monto),
        })
    return ajustes


def cuotas_fuera_de_arreglo(cuenta):
    """Cuotas impagas que NO están congeladas en un arreglo activo."""
    from app.models.cuenta import Cuota
    return (Cuota.query
            .filter(Cuota.cuenta_id == cuenta.id, Cuota.estado.in_(IMPAGAS))
            .order_by(Cuota.periodo.asc()).all())


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
    return d


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
    Regla 1. Valida y aplica, SIN commit. Devuelve (resumen, None) o
    (None, (code, mensaje, status)). Si devuelve error, quien llama tiene que
    hacer rollback: la nivelación ya se aplicó en la sesión para poder medir
    cuánto queda debiendo.
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
    if total_vencido > 0 and arr is None:
        return None, ("deuda_sin_arreglo",
                      f"La casa tiene L {total_vencido:,.2f} en cuotas vencidas. Para volver al "
                      "padrón tiene que pagarlas en caja, o firmar un arreglo de pago "
                      "«para volver al padrón».", 409)

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

    suspendidos = suspender_accesos(cuenta)
    return {
        "ajustes": ajustes,
        "queda_debiendo_fuera_de_arreglo": total_fuera,
        "queda_vencido_fuera_de_arreglo": total_vencido,
        "arreglo": estado_deuda(cuenta)["arreglo"],
        "suspendidos": suspendidos,
    }, None


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
