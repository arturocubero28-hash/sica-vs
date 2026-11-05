"""
Dia 74: el ciclo de vida de una casa — padron, sistema de cuotas y mudanza.

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


# ─────────────────────────────────────────────────────────────────────────
print("\n1. Arreglo con proposito y descuento autorizado por otro admin")
U = ARREGLO[0]
r = arreglo(U)
ok("sin proposito -> 400 proposito_requerido", codigo(r) == "proposito_requerido")
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=25)
ok("descuento sin autorizacion -> 400", codigo(r) == "autorizacion_requerida")
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=25,
            autorizacion={"email": "admin@x.com", "password": "Clave#2026"})
ok("lo autoriza el mismo que lo arma -> 403 autorizacion_propia",
   r.status_code == 403 and codigo(r) == "autorizacion_propia")
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=25,
            autorizacion={"email": "admin2@x.com", "password": "mala"})
ok("contrasena mala -> 403 autorizacion_invalida", codigo(r) == "autorizacion_invalida")
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=25,
            autorizacion={"email": "caja@x.com", "password": "Clave#2026"})
ok("lo autoriza un cajero -> 403 autorizacion_sin_permiso", codigo(r) == "autorizacion_sin_permiso")
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=100,
            autorizacion={"email": "admin2@x.com", "password": "Clave#2026"})
ok("descuento de 100 % -> 400 (eso no es un arreglo)", codigo(r) == "descuento_invalido")
with app.app_context():
    ok("...ninguno de esos intentos creo un arreglo",
       ArregloPago.query.filter_by(cuenta_id=ARREGLO[1]).count() == 0)
r = arreglo(U, proposito="ponerse_al_dia", descuento_pct=25,
            autorizacion={"email": "admin2@x.com", "password": "Clave#2026"})
d = r.get_json().get("data") or {}
ok("con un segundo admin -> 201", r.status_code == 201)
ok("deuda original 1200, descuento 300, deuda 900",
   d.get("deuda_original") == 1200 and d.get("descuento_monto") == 300 and d.get("deuda_total") == 900)
ok("3 abonos de 300", [a["monto"] for a in d.get("abonos", [])] == [300, 300, 300])
ok("queda quien autorizo", d.get("descuento_autorizado_por") == "Ad Dos"
   and d.get("descuento_autorizado_en"))
ok("proposito guardado", d.get("proposito") == "ponerse_al_dia")
ARR_Z = d.get("id")

# ─────────────────────────────────────────────────────────────────────────
print("\n2. Volver al padron")
r = cli.post(f"/api/v1/unidades/cuentas/{SIN_DEUDA[0]}/volver-al-padron", json={"simular": True}, headers=H)
ok("simular -> 200 simulado", r.status_code == 200 and r.get_json()["data"]["simulado"])
with app.app_context():
    ok("...y simular no cambio nada", not Cuenta.query.get(SIN_DEUDA[1]).es_censo)
r = cli.post(f"/api/v1/unidades/cuentas/{SIN_DEUDA[0]}/volver-al-padron", json={}, headers=H)
ok("sin deuda -> 200 directo", r.status_code == 200)
with app.app_context():
    c = Cuenta.query.get(SIN_DEUDA[1]); u = Usuario.query.get(SIN_DEUDA[2])
    ok("la casa esta en el padron, sin tarifa", c.es_censo and c.tarifa_id is None
       and c.fecha_regreso_padron == HOY)
    ok("ya no cobra cuotas", not c.cobra_cuotas())
    ok("la app del titular quedo suspendida (marcada por el padron)",
       not u.activo and u.suspendido_por_padron and not u.es_censo)
    v = Visita.query.filter_by(cuenta_id=SIN_DEUDA[1]).first()
    if v is not None:
        ok("el QR de visita que tenia activo quedo revocado", v.estado == "revocada")
ok("el titular ya no puede iniciar sesion",
   cli.post("/api/v1/auth/login", json={"email": "sofia@x.com", "password": "Clave#2026"}
            ).status_code != 200)

r = cli.post(f"/api/v1/unidades/cuentas/{CON_DEUDA[0]}/volver-al-padron", json={}, headers=H)
ok("con deuda y sin arreglo -> 409 deuda_sin_arreglo", r.status_code == 409
   and codigo(r) == "deuda_sin_arreglo")
ok("...el mensaje dice cuanto debe", "600" in (r.get_json()["error"]["message"]))
with app.app_context():
    c = Cuenta.query.get(CON_DEUDA[1])
    ok("...y no se toco nada (ni la nivelacion)", not c.es_censo
       and all(not q.nivelada for q in Cuota.query.filter_by(cuenta_id=c.id)))

r = cli.post(f"/api/v1/unidades/cuentas/{U}/volver-al-padron", json={}, headers=H)
ok("con un arreglo para SEGUIR pagando -> 409 arreglo_para_seguir",
   codigo(r) == "arreglo_para_seguir")
r = cli.post(f"/api/v1/arreglos/{ARR_Z}/proposito", json={"proposito": "volver_al_padron"}, headers=H)
ok("se cambia el proposito del arreglo -> 200", r.status_code == 200
   and r.get_json()["data"]["proposito"] == "volver_al_padron")
r = cli.post(f"/api/v1/unidades/cuentas/{U}/volver-al-padron", json={}, headers=H)
ok("ahora si vuelve al padron -> 200", r.status_code == 200)
with app.app_context():
    a = ArregloPago.query.filter_by(cuenta_id=ARREGLO[1]).first()
    ok("el arreglo sigue activo, con sus 3 abonos pendientes",
       a.estado == "activo" and sum(1 for x in a.abonos if x.estado == "pendiente") == 3)
    ok("las cuotas siguen congeladas en el arreglo",
       all(q.estado == "en_arreglo" for q in Cuota.query.filter_by(cuenta_id=ARREGLO[1])))

r = cli.get("/api/v1/censo", headers=H)
casas = {c["id"]: c for c in r.get_json()["data"]["casas"]}
z = casas.get(U, {})
ok("el padron muestra la casa con el estado de su arreglo",
   (z.get("deuda") or {}).get("arreglo", {}).get("saldo_pendiente") == 900)
ok("una casa del padron sin deuda figura al dia",
   (casas.get(SIN_DEUDA[0], {}).get("deuda") or {}).get("al_dia") is True)

# ─────────────────────────────────────────────────────────────────────────
print("\n3. Incumplir el arreglo estando en el padron")
W = INCUMPLE[0]
r = arreglo(W, proposito="volver_al_padron", num_abonos=2)
ARR_W = r.get_json()["data"]["id"]
ok("arreglo para volver al padron -> 201", r.status_code == 201)
ok("y vuelve al padron -> 200",
   cli.post(f"/api/v1/unidades/cuentas/{W}/volver-al-padron", json={}, headers=H).status_code == 200)
with app.app_context():
    a = ArregloPago.query.filter_by(uuid_publico=_uuid.UUID(ARR_W)).first()
    primero = min(a.abonos, key=lambda x: x.numero)
    # Ya estaba marcado "vencido" desde hace dias: con el bug viejo, el loop
    # lo saltaba y el arreglo nunca llegaba a incumplido.
    primero.fecha_pactada = HOY - dt.timedelta(days=40)
    primero.estado = "vencido"
    db.session.commit()
    from app.tasks.mora import revisar_arreglos
    revisar_arreglos()
    a = ArregloPago.query.filter_by(uuid_publico=_uuid.UUID(ARR_W)).first()
    c = Cuenta.query.get(INCUMPLE[1])
    ok("un abono ya marcado vencido y pasado de gracia -> arreglo incumplido",
       a.estado == "incumplido")
    ok("la casa del padron NO se bloquea", not c.bloqueada and c.es_censo)
    ok("la deuda vuelve a quedar pendiente a su nombre",
       all(q.estado in ("vencida", "pendiente") for q in Cuota.query.filter_by(cuenta_id=c.id)))
r = cli.post(f"/api/v1/censo/casas/{W}/convertir", json={"tarifa_id": 1, "dia_pago": 5}, headers=H)
ok("no puede volver a sumarse -> 400 deuda_pendiente", codigo(r) == "deuda_pendiente")

# ─────────────────────────────────────────────────────────────────────────
print("\n4. Volver a sumarse desde el padron")
with app.app_context():
    a = ArregloPago.query.filter_by(uuid_publico=_uuid.UUID(ARR_Z)).first()
    primero = min(a.abonos, key=lambda x: x.numero)
    primero.fecha_pactada = HOY - dt.timedelta(days=3)
    db.session.commit()
    ab1 = str(primero.uuid_publico)
r = cli.post(f"/api/v1/censo/casas/{U}/convertir", json={"tarifa_id": 1, "dia_pago": 5}, headers=H)
ok("con un abono vencido -> 400 arreglo_atrasado", codigo(r) == "arreglo_atrasado")
r = cli.post(f"/api/v1/arreglos/{ARR_Z}/abonos/{ab1}/cobrar", json={"metodo": "efectivo"}, headers=HC)
ok("el cajero cobra el abono -> 200", r.status_code == 200)
ok("...y el arreglo NO se da por completado (faltan 2)",
   r.get_json()["data"]["estado"] == "activo")
r = cli.post(f"/api/v1/censo/casas/{U}/convertir", json={"tarifa_id": 1, "dia_pago": 5}, headers=H)
ok("al dia con el arreglo -> se vuelve a sumar (200)", r.status_code == 200)
with app.app_context():
    c = Cuenta.query.get(ARREGLO[1]); u = Usuario.query.get(ARREGLO[2])
    ok("la casa vuelve a pagar cuota", not c.es_censo and c.tarifa_id == 1)
    ok("su gente recupera la app", u.activo and not u.suspendido_por_padron)
    a = ArregloPago.query.filter_by(uuid_publico=_uuid.UUID(ARR_Z)).first()
    ok("y sigue debiendo los abonos del arreglo",
       a.estado == "activo" and a.saldo_pendiente() == 600)
ok("el titular vuelve a iniciar sesion",
   cli.post("/api/v1/auth/login", json={"email": "zoe@x.com", "password": "Clave#2026"}
            ).status_code == 200)

# ─────────────────────────────────────────────────────────────────────────
print("\n5. Mudanza")
M = SE_MUDA[0]
r = cli.post(f"/api/v1/unidades/cuentas/{M}/baja", json={}, headers=H)
ok("baja con deuda sin confirmar -> 400 saldo_pendiente", codigo(r) == "saldo_pendiente")
r = cli.post(f"/api/v1/unidades/cuentas/{M}/baja", json={"confirmar_deuda": True, "motivo": "Se fue a SPS"},
             headers=H)
ok("confirmando -> 200", r.status_code == 200 and r.get_json()["data"]["deuda_pendiente"] == 600)
with app.app_context():
    c = Cuenta.query.get(SE_MUDA[1])
    ok("la cuenta queda inactiva como historial, con motivo y fecha",
       not c.activa and c.motivo_baja == "Se fue a SPS" and c.fecha_baja == HOY)
    ok("la deuda sigue ahi", Cuota.query.filter_by(cuenta_id=c.id, estado="vencida").count() == 1)

alta = lambda ident, correo, dni: cli.post("/api/v1/unidades/cuentas", headers=H, json={  # noqa: E731
    "unidad_nueva": {"tipo": "casa", "identificador": ident}, "tarifa_id": 1, "dia_pago": 5,
    "titular": {"nombre": "Nueva", "apellido": "Familia", "email": correo, "dni": dni,
                "telefono": "9999-0000", "direccion_exacta": "x", "profesion": "x",
                "contacto_emergencia_nombre": "x", "contacto_emergencia_telefono": "8888-0000"}})
r = alta("Casa Nueva 1", "marta2@x.com", "0801-1980-00002")
ok("la que se mudo debiendo no puede darse de alta en otra casa -> 409 titular_moroso",
   codigo(r) == "titular_moroso")
r = alta("Casa Marta", "otra@x.com", "0801-1990-00099")
ok("la casa que dejo queda libre para otra familia -> 201", r.status_code == 201,)
if r.status_code != 201:
    print("     ", r.get_json())
with app.app_context():
    ok("...y es la MISMA casa, con una cuenta nueva",
       Cuenta.query.filter_by(unidad_id=SE_MUDA[3]).count() == 2
       and Cuenta.query.filter_by(unidad_id=SE_MUDA[3], activa=True).count() == 1)

r = cli.post(f"/api/v1/censo/casas/{W}/mudanza", json={}, headers=H)
ok("se muda una casa del padron con deuda, sin confirmar -> 400", codigo(r) == "saldo_pendiente")
r = cli.post(f"/api/v1/censo/casas/{W}/mudanza", json={"confirmar_deuda": True}, headers=H)
ok("confirmando -> 200", r.status_code == 200)
casas = {c["id"] for c in cli.get("/api/v1/censo", headers=H).get_json()["data"]["casas"]}
ok("sale del listado del padron", W not in casas)
r = cli.post("/api/v1/censo/casas", headers=H, json={
    "tipo": "casa", "identificador": "Casa Walter",
    "titular": {"nombre": "Llega", "apellido": "Otra", "dni": "0801-2000-00077"}})
ok("en esa casa se puede registrar a la familia nueva -> 201", r.status_code == 201)
if r.status_code != 201:
    print("     ", r.get_json())

r = cli.post(f"/api/v1/unidades/cuentas/{COMPLETA[0]}/volver-al-padron", json={}, headers=H)
ok("(control) una casa con deuda sigue sin poder volver sin arreglo",
   codigo(r) == "deuda_sin_arreglo")

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo bien.")
