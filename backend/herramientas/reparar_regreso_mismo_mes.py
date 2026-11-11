"""
Día 76 — repara las casas que volvieron a sumarse el mismo mes con un
arreglo «para volver al padrón» activo (caso real: casa 2, 11/11/2026).

QUÉ PASÓ: el arreglo incluía la cuota del mes en curso nivelada hasta el
día de la firma (Oct L 800 + Nov L 293.33 = L 1 093.33). La casa pasó al
padrón, pagó el abono 1 y volvió a sumarse ese mismo día. Al volver, a la
cuota de noviembre —que seguía DENTRO del arreglo— se le sumaron los días
que faltaban (queda en L 800) y se marcó «pendiente». Resultado: los
L 293.33 de noviembre se cobraban dos veces, en el arreglo y en la cuota.

LO QUE HACE (la misma regla que ya aplica el sistema desde el Día 76):
  - la cuota del mes sale del arreglo y se paga normal (L 800);
  - el arreglo queda con la deuda vieja (octubre) y los abonos que faltan
    se recalculan con lo que falta;
  - el arreglo pasa a ser «para ponerse al día»;
  - queda anotado en la nota del arreglo.

Busca SOLO cuotas en ese estado imposible: dentro de un arreglo activo
pero marcadas «pendiente» (las cuotas de un arreglo están «en_arreglo»), de
una casa que está participando. Lo ya pagado no se toca.

USO (en el servidor, desde /opt/sicavs). Primero mirar, después aplicar:

    docker compose -f docker-compose.prod.yml exec backend \\
        python3 herramientas/reparar_regreso_mismo_mes.py

    docker compose -f docker-compose.prod.yml exec backend \\
        python3 herramientas/reparar_regreso_mismo_mes.py --aplicar
"""
import sys
from decimal import Decimal

sys.path.insert(0, ".")

from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models.cuenta import Cuota, ArregloPago             # noqa: E402
from app.services.ciclo_casa import (quitar_cuotas_de_arreglo, repartir_en_abonos,  # noqa: E402
                                     _dinero, _prima)
from app.utils.fechas import mes_es                          # noqa: E402

APLICAR = "--aplicar" in sys.argv


def corregir_primas():
    """
    La primera versión de esta reparación repartió lo que faltaba también en
    la PRIMA pendiente (casa 4: la prima de L 300 pasó a L 657.78). La prima
    es lo que la familia acordó dar al firmar: se le devuelve su monto y el
    resto se reparte en los abonos normales.
    """
    tocados = ArregloPago.query.filter(ArregloPago.estado == "activo",
                                       ArregloPago.nota.ilike("%reparación Día 76%")).all()
    for arr in tocados:
        prima = _prima(arr)
        if prima is None or prima.estado == "pagado" or _dinero(prima.monto) == _dinero(arr.abono_inicial):
            continue
        casa = arr.cuenta.unidad.identificador if arr.cuenta and arr.cuenta.unidad else f"arreglo {arr.id}"
        pagado = sum((_dinero(a.monto) for a in arr.abonos if a.estado == "pagado"), Decimal("0.00"))
        falta = _dinero(arr.deuda_total) - pagado
        pendientes = sorted((a for a in arr.abonos if a.estado in ("pendiente", "vencido")),
                            key=lambda a: a.numero)
        antes = {a.numero: a.monto for a in pendientes}
        arr.monto_por_abono = repartir_en_abonos(arr, falta, pendientes)
        print(f"\n── Casa {casa} · prima del arreglo {arr.id}: vuelve a L {arr.abono_inicial}")
        for a in pendientes:
            print(f"      abono {a.numero}: {a.estado} L {antes[a.numero]}  ->  L {a.monto}")
        print(f"   suma de lo pendiente: L {sum(_dinero(a.monto) for a in pendientes)} (falta L {falta})")


def main():
    app = create_app()
    with app.app_context():
        malas = (Cuota.query.join(ArregloPago, ArregloPago.id == Cuota.arreglo_id)
                 .filter(ArregloPago.estado == "activo", Cuota.estado == "pendiente")
                 .order_by(Cuota.id).all())
        malas = [c for c in malas if c.cuenta and c.cuenta.activa and not c.cuenta.es_censo]
        corregir_primas()
        if not malas:
            print("No hay casas con la cuota del mes cobrada dos veces.")

        for c in malas:
            arr = c.arreglo if hasattr(c, "arreglo") and c.arreglo else ArregloPago.query.get(c.arreglo_id)
            casa = c.cuenta.unidad.identificador if c.cuenta.unidad else f"cuenta {c.cuenta_id}"
            otras = sum((_dinero(x.monto) for x in arr.cuotas if x.id != c.id), Decimal("0.00"))
            original = _dinero(arr.deuda_original if arr.deuda_original is not None else arr.deuda_total)
            parte = original - otras        # lo que de esta cuota estaba financiado
            pagado = sum((_dinero(a.monto) for a in arr.abonos if a.estado == "pagado"), Decimal("0.00"))
            print(f"\n── Casa {casa} · cuota de {mes_es(c.periodo)} (id {c.id})")
            print(f"   cuota: L {c.monto} pendiente, pero dentro del arreglo {arr.id}")
            print(f"   arreglo: deuda L {arr.deuda_total} (de esta cuota: L {parte}), abonado L {pagado}")
            if parte <= 0:
                print("   ! no se puede calcular qué parte estaba en el arreglo: revisar a mano")
                continue
            antes = {a.numero: (a.estado, a.monto) for a in arr.abonos}
            err = quitar_cuotas_de_arreglo(
                arr, [c], parte,
                f"reparación Día 76: la cuota de {mes_es(c.periodo)} salió del arreglo porque la casa "
                "volvió a sumarse el mismo mes (se cobraba dos veces).", "Sistema")
            if err:
                print(f"   ! {err[1]}")
                db.session.rollback()
                continue
            if arr.estado == "activo" and arr.proposito == "volver_al_padron":
                arr.proposito = "ponerse_al_dia"
            print(f"   => cuota L {c.monto} fuera del arreglo · arreglo L {arr.deuda_total} · "
                  f"propósito {arr.proposito} · estado {arr.estado}")
            for a in sorted(arr.abonos, key=lambda x: x.numero):
                est, monto = antes.get(a.numero, ("—", "—"))
                print(f"      abono {a.numero}: {est} L {monto}  ->  {a.estado} L {a.monto}")
            falta = _dinero(arr.deuda_total) - pagado
            print(f"   total que debe: arreglo L {falta} + cuota L {c.monto} = L {falta + _dinero(c.monto)}")

        if APLICAR:
            db.session.commit()
            print("\nAPLICADO.")
        else:
            db.session.rollback()
            print("\nSolo se mostró (no se cambió nada). Para aplicar: agregá --aplicar")


if __name__ == "__main__":
    main()
