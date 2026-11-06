"""
(base tomada de prueba_dia74.py) Dia 74: el ciclo de vida de una casa — padron, sistema de cuotas y mudanza.

  1. ARREGLO CON PROPOSITO Y DESCUENTO — se pregunta siempre para que se
     firma (ponerse al dia o volver al padron). El descuento, sin tope, lo
     autoriza un SEGUNDO administrador con su contrasena.

  2. VOLVER AL PADRON — sin deuda, directo; con deuda, solo con un arreglo
     "para volver al padron". Se nivela la cuota del mes, la app queda
     suspendida y los abonos siguen pendientes.

  3. INCUMPLIR ESTANDO EN EL PADRON — el arreglo queda incumplido, la deuda
     pendiente, y la casa NO se bloquea. (De paso: el bug que hacia que
     ningun arreglo llegara nunca a incumplido.)

  4. VOLVER A SUMARSE — solo al dia con el arreglo; la gente recupera la app.

  5. MUDANZA — baja con deuda confirmada; la deuda sigue al titular y le
     impide darse de alta en otra casa. La casa queda libre para otra familia.

    python3 prueba_dia74.py
"""
import os, sys, logging, datetime as dt
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


import app as paquete_app                                    # noqa: E402
from app import create_app                                    # noqa: E402
from app.extensions import db, limiter                        # noqa: E402
from app.models.usuario import Usuario                        # noqa: E402
from app.models.cuenta import (                               # noqa: E402
    Unidad, Cuenta, Residente, Tarifa, Cuota, ArregloPago, AbonoArreglo,
)
from app.models.visita import Visita                          # noqa: E402
import uuid as _uuid                                          # noqa: E402

import app.tasks.correo_task as _ct                           # noqa: E402
_ct.enviar_correo_activacion_task.delay = lambda *a, **k: None

fallos = []


def ok(desc, cond):
    print(f"  [{'OK  ' if cond else 'FALLA'}] {desc}")
    if not cond:
        fallos.append(desc)


def codigo(r):
    return ((r.get_json() or {}).get("error") or {}).get("code")


def _parchear_uuid():
    q = Usuario.query.__class__
    orig = q.filter_by

    def fb(self, **kw):
        if isinstance(kw.get("uuid_publico"), str):
            try:
                kw["uuid_publico"] = _uuid.UUID(kw["uuid_publico"])
            except (ValueError, AttributeError):
                pass
        return orig(self, **kw)

    q.filter_by = fb


app = create_app()
limiter.enabled = False
# Las tareas de Celery arman su propia app; en la prueba tienen que usar
# ESTA, que es la que tiene la base en memoria.
paquete_app.create_app = lambda *a, **k: app

HOY = dt.date.today()


def mes_atras(n):
    y, m = HOY.year, HOY.month - n
    while m <= 0:
        m += 12; y -= 1
    return dt.date(y, m, 1)


N = {"id": 100}


def nid():
    N["id"] += 1
    return N["id"]


def casa_completa(nombre, vencidas=0, dni=None):
    """Una casa que paga cuota, con su titular con app y N cuotas vencidas."""
    u = Unidad(id=nid(), tipo="casa", identificador=f"Casa {nombre}", activa=True)
    db.session.add(u); db.session.flush()
    c = Cuenta(id=nid(), unidad_id=u.id, modo_participacion="completa", activa=True,
               tarifa_id=1, dia_pago=5, fecha_conversion=mes_atras(6))
    p = Usuario(id=nid(), nombre=nombre, apellido="Prueba", email=f"{nombre.lower()}@x.com",
                rol="residente", activo=True, dni=dni)
    p.set_password("Clave#2026")
    db.session.add_all([c, p]); db.session.flush()
    db.session.add(Residente(id=nid(), cuenta_id=c.id, usuario_id=p.id, rol_cuenta="titular"))
    for i in range(vencidas):
        per = mes_atras(3 + i)
        db.session.add(Cuota(id=nid(), cuenta_id=c.id, periodo=per, monto=600,
                             fecha_vencimiento=per.replace(day=5), estado="vencida"))
    db.session.commit()
    return str(c.uuid_publico), c.id, p.id, u.id


with app.app_context():
    db.drop_all()
    db.create_all()
    a1 = Usuario(id=1, nombre="Ad", apellido="Uno", email="admin@x.com", rol="admin", activo=True)
    a2 = Usuario(id=2, nombre="Ad", apellido="Dos", email="admin2@x.com", rol="admin", activo=True)
    caj = Usuario(id=3, nombre="Ca", apellido="Jero", email="caja@x.com", rol="cajero", activo=True)
    for x in (a1, a2, caj):
        x.set_password("Clave#2026")
    db.session.add_all([a1, a2, caj, Tarifa(id=1, nombre="Cuota mensual", monto=600, activa=True)])
    db.session.commit()

    SIN_DEUDA = casa_completa("Sofia")
    CON_DEUDA = casa_completa("Diego", vencidas=1)
    ARREGLO = casa_completa("Zoe", vencidas=2)
    INCUMPLE = casa_completa("Walter", vencidas=1, dni="0801-1980-00001")
    SE_MUDA = casa_completa("Marta", vencidas=1, dni="0801-1980-00002")
    COMPLETA = casa_completa("Carla", vencidas=2)
    # Un QR de visita activo de Sofia: al volver al padron tiene que caerse.
    with db.session.no_autoflush:
        db.session.add(Visita(id=nid(), cuenta_id=SIN_DEUDA[1],
                              generada_por=Residente.query.filter_by(cuenta_id=SIN_DEUDA[1]).first().id,
                              tipo="unica", nombre_visitante="Pedro", estado="activa",
                              ))
    try:
        db.session.commit()
    except Exception as e:  # el modelo puede pedir otros campos
        db.session.rollback()
        print("  (sin visita de prueba:", type(e).__name__, ")")
    _parchear_uuid()

cli = app.test_client()


def login(correo):
    return {"Authorization": "Bearer " + cli.post(
        "/api/v1/auth/login", json={"email": correo, "password": "Clave#2026"}
    ).get_json()["data"]["token"]}


H, H2, HC = login("admin@x.com"), login("admin2@x.com"), login("caja@x.com")


def cuotas_de(cuenta_uuid):
    return [c["id"] for c in cli.get(
        f"/api/v1/arreglos/cuenta/{cuenta_uuid}/cuotas-pendientes", headers=H).get_json()["data"]]


def arreglo(cuenta_uuid, **extra):
    body = {"cuenta_id": cuenta_uuid, "cuotas": cuotas_de(cuenta_uuid), "num_abonos": 3}
    body.update(extra)
    return cli.post("/api/v1/arreglos", json=body, headers=H)



from app.services.ciclo_casa import nivelar_cuotas, inicio_de_cobro   # noqa: E402
from app.utils.cuotas import calcular_cuota_prorrateada               # noqa: E402

print("\n1. El prorrateo del alta guarda desde que dia cobra")
d = calcular_cuota_prorrateada(600, 5, hoy=dt.date(2026, 11, 2))
ok("alta el 2 de noviembre -> 28 dias, L 560, cobra desde el 3",
   d["dias_restantes"] == 28 and d["monto"] == 560 and d["cobra_desde_dia"] == 3)

NOV = dt.date(2026, 11, 1)


def cuota_suelta(cuenta_id, monto, periodo=NOV, desde=None, venc=dt.date(2026, 12, 5)):
    c = Cuota(id=nid(), cuenta_id=cuenta_id, periodo=periodo, monto=monto,
              fecha_vencimiento=venc, estado="pendiente", cobra_desde_dia=desde)
    db.session.add(c); db.session.flush()
    return c


print("\n2. Nivelar al dia en que se va (el caso de la casa 60)")
with app.app_context():
    cid = Cuenta.query.get(SIN_DEUDA[1]).id
    c = cuota_suelta(cid, 560, desde=3)
    aj = nivelar_cuotas([c], dt.date(2026, 11, 6))
    ok("alta el 2, se va el 6 -> 4 dias (3 al 6) = L 80", float(c.monto) == 80
       and aj[0]["dias_ocupados"] == 4)
    db.session.rollback()

    c = cuota_suelta(cid, 560, desde=None)      # creada antes del Dia 75
    ok("cuota vieja sin el dato: se deduce del monto y la tarifa (desde el 3)",
       inicio_de_cobro(c) == 3)
    nivelar_cuotas([c], dt.date(2026, 11, 6))
    ok("...y nivela igual: L 80", float(c.monto) == 80)
    db.session.rollback()

    c = cuota_suelta(cid, 600)
    nivelar_cuotas([c], dt.date(2026, 11, 15))
    ok("mes completo, se va el 15 -> 15 dias = L 300", float(c.monto) == 300)
    db.session.rollback()

    c = cuota_suelta(cid, 560, desde=3)
    nivelar_cuotas([c], dt.date(2026, 11, 2))
    ok("se va el mismo dia del alta -> la cuota se anula", c.estado == "anulada")
    db.session.rollback()

    c = cuota_suelta(cid, 600, periodo=dt.date(2026, 10, 1), venc=dt.date(2026, 11, 5))
    nivelar_cuotas([c], dt.date(2026, 11, 6))
    ok("la cuota de un mes ya vivido entero no se toca", float(c.monto) == 600
       and not c.nivelada)
    db.session.rollback()

    c = cuota_suelta(cid, 600, periodo=dt.date(2026, 12, 1), venc=dt.date(2027, 1, 5))
    nivelar_cuotas([c], dt.date(2026, 11, 6))
    ok("la de un mes posterior se anula", c.estado == "anulada")
    db.session.rollback()

    c = cuota_suelta(cid, 560, desde=3)
    nivelar_cuotas([c], dt.date(2026, 11, 6))
    nivelar_cuotas([c], dt.date(2026, 11, 6))
    ok("nivelar dos veces no la sigue achicando", float(c.monto) == 80)
    db.session.rollback()


print("\n3. Volver al padron con la cuota del mes sin vencer")
with app.app_context():
    nueva = casa_completa("Sesenta")
    # La cuota del alta, como la crea el sistema: cobra desde el dia
    # siguiente al alta y vence el mes que viene. Alta "el 2" del mes en curso.
    per = dt.date(HOY.year, HOY.month, 1)
    venc = (per + dt.timedelta(days=40)).replace(day=5)
    db.session.add(Cuota(id=nid(), cuenta_id=nueva[1], periodo=per, monto=560,
                         fecha_vencimiento=venc, estado="pendiente", cobra_desde_dia=3))
    db.session.commit()
S60 = nueva[0]
esperado = round(560 / 28 * (min(HOY.day, 30) - 2), 2) if HOY.day >= 3 else 0

r = cli.post(f"/api/v1/unidades/cuentas/{S60}/volver-al-padron", json={"simular": True}, headers=H)
dd = r.get_json().get("data") or {}
ok("ya NO exige arreglo por una cuota que no ha vencido -> 200", r.status_code == 200)
ok(f"la simulacion cobra solo los dias que estuvo (L {esperado})",
   dd.get("queda_debiendo_fuera_de_arreglo") == esperado)
ok("y nada de eso esta vencido", dd.get("queda_vencido_fuera_de_arreglo") == 0)

r = arreglo(S60, proposito="volver_al_padron")
ok("un arreglo 'para volver al padron' con esa cuota -> 400 cuota_no_vencida",
   codigo(r) == "cuota_no_vencida")
ok("...y el mensaje lo explica", "todavía no vence" in r.get_json()["error"]["message"])

r = cli.post(f"/api/v1/unidades/cuentas/{S60}/volver-al-padron", json={}, headers=H)
ok("vuelve al padron -> 200", r.status_code == 200)
with app.app_context():
    q = Cuota.query.filter_by(cuenta_id=nueva[1]).first()
    ok("la cuota queda pendiente por los dias que estuvo", float(q.monto) == esperado
       and q.estado in ("pendiente", "pagada", "anulada"))
if esperado > 0:
    r = cli.post(f"/api/v1/censo/casas/{S60}/convertir", json={"tarifa_id": 1, "dia_pago": 5}, headers=H)
    ok("no puede volver a sumarse sin pagar esos dias -> 400 deuda_pendiente",
       codigo(r) == "deuda_pendiente")


print("\n4. Cancelar un arreglo sin nada vencido no bloquea la casa")
with app.app_context():
    otra = casa_completa("Paola")
    db.session.add(Cuota(id=nid(), cuenta_id=otra[1], periodo=per, monto=600,
                         fecha_vencimiento=venc, estado="pendiente"))
    db.session.commit()
r = arreglo(otra[0], proposito="ponerse_al_dia")
ok("para ponerse al dia si se puede incluir la cuota del mes -> 201", r.status_code == 201)
r = cli.post(f"/api/v1/arreglos/{r.get_json()['data']['id']}/cancelar",
             json={"motivo": "prueba"}, headers=H)
ok("se cancela -> 200", r.status_code == 200)
with app.app_context():
    c = Cuenta.query.get(otra[1])
    q = Cuota.query.filter_by(cuenta_id=otra[1]).first()
    ok("la cuota vuelve a pendiente (no a vencida)", q.estado == "pendiente")
    ok("y la casa NO queda bloqueada", not c.bloqueada)


print("\n5. Una cuota anulada por la nivelacion no es deuda")
with app.app_context():
    an = casa_completa("Anulada")
    viejo = dt.date(HOY.year - 1, 1, 1)
    db.session.add(Cuota(id=nid(), cuenta_id=an[1], periodo=viejo, monto=0,
                         monto_original=600, nivelada=True,
                         fecha_vencimiento=viejo.replace(month=2, day=5), estado="anulada"))
    c = Cuenta.query.get(an[1]); c.bloqueada = True; c.estado = "en_mora"
    db.session.commit()
    ok("con solo una anulada vencida, la casa no tiene cuotas vencidas",
       not Cuenta.query.get(an[1]).tiene_deuda_vencida())
    cc = Cuenta.query.get(an[1]); cc.intentar_desbloquear(); db.session.commit()
    ok("...y se puede desbloquear", not Cuenta.query.get(an[1]).bloqueada)
r = cli.get("/api/v1/arreglos/cuenta/" + an[0] + "/cuotas-pendientes", headers=H)
ok("no aparece entre las cuotas para un arreglo", r.get_json()["data"] == [])
r = cli.get("/api/v1/caja/buscar-cuenta?q=Casa%20Anulada", headers=HC)
res = (r.get_json() or {}).get("data") or []
ok("caja no la ofrece para cobrar", r.status_code == 200 and res and res[0]["cuotas_pendientes"] == [])

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo bien.")
