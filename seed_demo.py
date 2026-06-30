"""
Script de datos de prueba para SICA-VS.

Genera datos genéricos para poder ver la reportería con vida: casas,
residentes, cuentas, cuotas (pagadas, vencidas, pendientes) y pagos. También
algunos eventos de acceso, para que el resumen ejecutivo y los gráficos
muestren números reales.

CÓMO USARLO (desde la carpeta del proyecto, con Docker corriendo):

    docker compose cp seed_demo.py backend:/app/seed_demo.py
    docker compose exec backend python seed_demo.py

Para borrar los datos de prueba y volver a generarlos, se puede correr otra
vez: limpia lo que creó antes (identificado por el prefijo DEMO) y lo recrea.

NOTA: es solo para desarrollo/demostración. No usar en producción.
"""
import random
import datetime as dt

from app import create_app
from app.extensions import db
from app.models.usuario import Usuario
from app.models.cuenta import Unidad, Cuenta, Tarifa, Residente, Cuota, Pago

app = create_app()

# Cantidades
N_CASAS = 40            # casas/unidades a crear
MESES_HISTORIA = 6      # meses de cuotas hacia atrás

NOMBRES = ["Carlos", "María", "José", "Ana", "Luis", "Carmen", "Jorge", "Rosa",
           "Pedro", "Laura", "Miguel", "Sofía", "Juan", "Elena", "Roberto",
           "Patricia", "Fernando", "Gabriela", "Ricardo", "Daniela"]
APELLIDOS = ["García", "Martínez", "López", "Rodríguez", "Hernández", "Flores",
             "Cruz", "Reyes", "Mejía", "Castro", "Núñez", "Ramírez", "Aguilar",
             "Cárdenas", "Fuentes", "Lagos", "Pineda", "Zelaya", "Madrid", "Bonilla"]

PREFIJO = "DEMO"   # marca para identificar y poder limpiar


def limpiar_demo():
    """Borra los datos de prueba creados antes (por el email DEMO)."""
    usuarios_demo = Usuario.query.filter(Usuario.email.like(f"{PREFIJO.lower()}%")).all()
    ids = [u.id for u in usuarios_demo]
    if not ids:
        return 0
    # Borrar en orden por las llaves foráneas
    residentes = Residente.query.filter(Residente.usuario_id.in_(ids)).all()
    cuentas_ids = list({r.cuenta_id for r in residentes})
    for r in residentes:
        db.session.delete(r)
    db.session.flush()
    cuotas = Cuota.query.filter(Cuota.cuenta_id.in_(cuentas_ids)).all() if cuentas_ids else []
    cuota_ids = [c.id for c in cuotas]
    if cuota_ids:
        for p in Pago.query.filter(Pago.cuota_id.in_(cuota_ids)).all():
            db.session.delete(p)
    for c in cuotas:
        db.session.delete(c)
    db.session.flush()
    unidades_ids = []
    for cid in cuentas_ids:
        cu = Cuenta.query.get(cid)
        if cu:
            unidades_ids.append(cu.unidad_id)
            db.session.delete(cu)
    db.session.flush()
    for uid in set(unidades_ids):
        un = Unidad.query.get(uid)
        if un and un.identificador.startswith(PREFIJO):
            db.session.delete(un)
    for u in usuarios_demo:
        db.session.delete(u)
    db.session.commit()
    return len(ids)


def primer_dia(anio, mes):
    return dt.date(anio, mes, 1)


def generar():
    with app.app_context():
        print("Limpiando datos DEMO anteriores (si los hay)…")
        borrados = limpiar_demo()
        if borrados:
            print(f"  Se limpiaron {borrados} usuarios DEMO y sus datos.")

        # Tarifa (usa una existente o crea una)
        tarifa = Tarifa.query.filter_by(activa=True).first()
        if not tarifa:
            tarifa = Tarifa(nombre="DEMO Estándar", monto=800, activa=True)
            db.session.add(tarifa); db.session.flush()

        hoy = dt.date.today()
        creadas = 0

        for i in range(1, N_CASAS + 1):
            # Usuario (titular)
            nombre = random.choice(NOMBRES)
            apellido = f"{random.choice(APELLIDOS)} {random.choice(APELLIDOS)}"
            u = Usuario(
                nombre=nombre, apellido=apellido,
                email=f"{PREFIJO.lower()}casa{i}@demo.local",
                telefono=f"504{random.randint(30000000, 99999999)}",
                rol="residente", activo=True,
            )
            u.set_password("demo123")
            db.session.add(u); db.session.flush()

            # Unidad
            un = Unidad(tipo="casa", identificador=f"{PREFIJO} Casa {i}", activa=True,
                        propietario_id=u.id)
            db.session.add(un); db.session.flush()

            # Cuenta
            cuenta = Cuenta(unidad_id=un.id, tarifa_id=tarifa.id,
                            dia_pago=random.choice([1, 5, 10, 15]),
                            fecha_alta=hoy - dt.timedelta(days=300),
                            estado="al_dia", activa=True)
            db.session.add(cuenta); db.session.flush()

            # Residente (titular)
            r = Residente(usuario_id=u.id, cuenta_id=cuenta.id,
                          rol_cuenta="titular", relacion="propietario", activo=True)
            db.session.add(r)

            # Perfil de pago de esta casa: define qué tan al día está
            # 60% buenos pagadores, 25% atrasados, 15% morosos fuertes
            perfil = random.choices(["bueno", "atrasado", "moroso"], weights=[60, 25, 15])[0]
            monto = float(tarifa.monto)

            for m in range(MESES_HISTORIA, -1, -1):
                # mes de la cuota (hacia atrás desde el actual)
                y = hoy.year
                mm = hoy.month - m
                while mm <= 0:
                    mm += 12; y -= 1
                periodo = primer_dia(y, mm)
                venc = periodo + dt.timedelta(days=14)

                # ¿está pagada esta cuota según el perfil?
                if perfil == "bueno":
                    pagada = m >= 1 or random.random() < 0.7   # casi todo pagado
                elif perfil == "atrasado":
                    pagada = m >= 3                              # debe los últimos 2-3 meses
                else:
                    pagada = m >= 5                              # moroso fuerte: debe varios

                estado = "pagada" if pagada else "pendiente"
                cuota = Cuota(cuenta_id=cuenta.id, periodo=periodo, monto=monto,
                              fecha_vencimiento=venc, estado=estado)
                db.session.add(cuota); db.session.flush()

                if pagada:
                    # Pago aprobado. Para algunos, la fecha de pago es posterior
                    # al vencimiento (recuperación de mora).
                    dias_offset = random.randint(-3, 20)  # puede pagar antes o después
                    fecha_pago = venc + dt.timedelta(days=dias_offset)
                    if fecha_pago > hoy:
                        fecha_pago = hoy
                    pago = Pago(
                        cuota_id=cuota.id, cuenta_id=cuenta.id, subido_por=u.id,
                        metodo=random.choice(["efectivo", "transferencia", "tarjeta_pos"]),
                        monto=monto, estado="aprobado",
                        revisado_en=dt.datetime.combine(fecha_pago, dt.time(12, 0)),
                    )
                    db.session.add(pago)

            # Marcar la cuenta como morosa/bloqueada si corresponde
            if perfil == "moroso":
                cuenta.estado = "moroso"
            creadas += 1

        db.session.commit()
        print(f"✅ Listo: {creadas} casas con residentes, cuentas, cuotas y pagos.")
        print(f"   Historia de {MESES_HISTORIA} meses. Mezcla de buenos pagadores,")
        print(f"   atrasados y morosos para que los reportes muestren variedad.")
        print()
        print("   Ahora andá a Reportería y vas a ver el Resumen ejecutivo,")
        print("   la mora, el top deudores y los gráficos con datos reales.")
        print()
        print("   Para borrar estos datos: volvé a correr el script (se limpian solos)")
        print("   o pedímelo y te paso un comando de limpieza.")


if __name__ == "__main__":
    generar()
