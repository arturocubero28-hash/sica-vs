"""
Dia 76: lo que pide la nueva version de la app y los pendientes del Dia 75.

  1. CUENTAS BANCARIAS — el admin configura a que cuentas se puede pagar;
     cualquier usuario de su residencial las ve; nadie de otra residencial.
  2. CONTACTO DE AYUDA — telefono y correo para dudas, quejas y sugerencias.
  3. SALDO DE LA CUOTA — lo que falta, no el monto entero.
  4. CAJA — encuentra a quien se mudo debiendo; no busca en otra residencial.
  5. DESCUENTOS EN EL REPORTE — esperado = recaudado + perdonado + pendiente.
  6. REDIS CAIDO — los correos salen igual y la API responde 503, no 500.

    python3 prueba_dia76.py
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
from app.models.residencial import Residencial                # noqa: E402
from app.models.cuenta_bancaria import CuentaBancaria         # noqa: E402
from app.models.cuenta import (                               # noqa: E402
    Unidad, Cuenta, Residente, Tarifa, Cuota, ArregloPago, Pago,
)
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
paquete_app.create_app = lambda *a, **k: app

# Una ruta que falla como fallaria con Redis caido (se registra antes de la
# primera peticion, como pide Flask).
import redis as _redis_lib                                    # noqa: E402


@app.get("/api/v1/_prueba_redis")
def _prueba_redis():
    raise _redis_lib.exceptions.ConnectionError("Error 111 connecting to redis:6379")


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


def usuario(i, nombre, correo, rol, rid=None):
    u = Usuario(id=i, nombre=nombre, apellido="Prueba", email=correo, rol=rol, activo=True,
                residencial_id=rid)
    u.set_password("Clave#2026")
    db.session.add(u)
    return u


def casa(nombre, rid, vencidas=0, activa=True):
    u = Unidad(id=nid(), tipo="casa", identificador=f"Casa {nombre}", activa=True, residencial_id=rid)
    db.session.add(u); db.session.flush()
    c = Cuenta(id=nid(), unidad_id=u.id, modo_participacion="completa", activa=activa,
               tarifa_id=1, dia_pago=5, fecha_conversion=mes_atras(6))
    p = Usuario(id=nid(), nombre=nombre, apellido="Prueba", email=f"{nombre.lower()}@x.com",
                rol="residente", activo=True, residencial_id=rid)
    p.set_password("Clave#2026")
    db.session.add_all([c, p]); db.session.flush()
    db.session.add(Residente(id=nid(), cuenta_id=c.id, usuario_id=p.id, rol_cuenta="titular"))
    for i in range(vencidas):
        per = mes_atras(3 + i)
        db.session.add(Cuota(id=nid(), cuenta_id=c.id, periodo=per, monto=600,
                             fecha_vencimiento=per.replace(day=5), estado="vencida"))
    db.session.commit()
    return str(c.uuid_publico), c.id, p.id


with app.app_context():
    db.drop_all()
    db.create_all()
    # Dos residenciales: la de la prueba (R1) y otra (R2) que no debe ver nada de R1.
    usuario(1, "Ad", "admin@x.com", "admin")
    usuario(2, "Ad", "admin2@x.com", "admin")
    usuario(3, "Ca", "caja@x.com", "cajero")
    usuario(4, "Otro", "otro@x.com", "admin")
    usuario(5, "Caja", "caja2@x.com", "cajero")
    db.session.add(Tarifa(id=1, nombre="Cuota mensual", monto=600, activa=True))
    db.session.flush()
    db.session.add_all([Residencial(id=1, admin_id=1, nombre="Villas del Sol"),
                        Residencial(id=2, admin_id=4, nombre="Otra Residencial")])
    db.session.flush()
    for uid, rid in ((1, 1), (2, 1), (3, 1), (4, 2), (5, 2)):
        Usuario.query.get(uid).residencial_id = rid
    db.session.commit()

    VECINO = casa("Rosa", 1)
    SE_FUE = casa("Mudado", 1, vencidas=1, activa=False)       # se mudo debiendo
    SALDADA = casa("Saldada", 1, activa=False)                 # se mudo sin deber
    AJENA = casa("Ajena", 2, vencidas=1)                       # de la otra residencial
    DESC = casa("Descuento", 1, vencidas=2)
    _parchear_uuid()

cli = app.test_client()


def login(correo):
    r = cli.post("/api/v1/auth/login", json={"email": correo, "password": "Clave#2026"})
    return {"Authorization": "Bearer " + r.get_json()["data"]["token"]}


H, H2, HC = login("admin@x.com"), login("admin2@x.com"), login("caja@x.com")
HOTRO, HC2, HR = login("otro@x.com"), login("caja2@x.com"), login("rosa@x.com")
CB = "/api/v1/unidades/mi-residencial/cuentas-bancarias"

print("\n1. Cuentas bancarias autorizadas")
ok("al principio no hay ninguna", cli.get(CB, headers=HR).get_json()["data"] == [])
r = cli.post(CB, json={"banco": "Banco Atlántida", "numero": "1234-5678-90",
                       "titular": "Patronato Villas del Sol", "tipo": "ahorro"}, headers=H)
ok("el admin agrega una -> 201", r.status_code == 201)
c1 = r.get_json()["data"]
ok("...con banco, numero, titular y tipo; el id es el uuid publico",
   c1["banco"] == "Banco Atlántida" and c1["numero"] == "1234-5678-90"
   and c1["titular"] == "Patronato Villas del Sol" and c1["tipo"] == "ahorro" and len(c1["id"]) == 36)
r = cli.post(CB, json={"banco": "BAC Credomatic", "numero": "  7300 1122 "}, headers=H)
ok("otra sin titular ni tipo -> 201, numero sin espacios de sobra",
   r.status_code == 201 and r.get_json()["data"]["numero"] == "7300 1122")
c2 = r.get_json()["data"]
ok("la misma cuenta escrita con otros guiones -> 409 cuenta_repetida",
   codigo(cli.post(CB, json={"banco": "banco atlántida", "numero": "1234567890"}, headers=H)) == "cuenta_repetida")
ok("sin banco -> 400", codigo(cli.post(CB, json={"numero": "123456"}, headers=H)) == "banco_invalido")
ok("numero con letras -> 400", codigo(cli.post(CB, json={"banco": "BAC", "numero": "12AB34"}, headers=H)) == "numero_invalido")
ok("tipo inventado -> 400", codigo(cli.post(CB, json={"banco": "BAC", "numero": "998877", "tipo": "plazo"}, headers=H)) == "tipo_invalido")
ok("un residente no puede agregar -> 403", cli.post(CB, json={"banco": "X", "numero": "112233"}, headers=HR).status_code == 403)
ok("un cajero tampoco -> 403", cli.post(CB, json={"banco": "X", "numero": "112233"}, headers=HC).status_code == 403)
lista = cli.get(CB, headers=HR).get_json()["data"]
ok("el residente las ve, en el orden en que se agregaron",
   [c["banco"] for c in lista] == ["Banco Atlántida", "BAC Credomatic"])
ok("la otra residencial no ve ninguna", cli.get(CB, headers=HOTRO).get_json()["data"] == [])
ok("...ni puede editarlas (404)", cli.put(f"{CB}/{c1['id']}", json={"banco": "Hack"}, headers=HOTRO).status_code == 404)
ok("...ni borrarlas (404)", cli.delete(f"{CB}/{c1['id']}", headers=HOTRO).status_code == 404)
r = cli.put(f"{CB}/{c2['id']}", json={"tipo": "cheques", "titular": "Junta Directiva"}, headers=H)
ok("editar solo el tipo y el titular deja banco y numero",
   r.status_code == 200 and r.get_json()["data"]["tipo"] == "cheques"
   and r.get_json()["data"]["numero"] == "7300 1122")
r = cli.put(f"{CB}/{c2['id']}", json={"tipo": ""}, headers=H)
ok("tipo vacio lo quita", r.get_json()["data"]["tipo"] is None)
ok("un identificador que no es uuid -> 404", cli.delete(f"{CB}/abc", headers=H).status_code == 404)
ok("borrar -> 200", cli.delete(f"{CB}/{c2['id']}", headers=H).status_code == 200)
ok("...y ya no aparece", [c["id"] for c in cli.get(CB, headers=HR).get_json()["data"]] == [c1["id"]])
for i in range(9):
    cli.post(CB, json={"banco": f"Banco {i}", "numero": f"1000{i}00"}, headers=H)
ok("hasta 10 cuentas: la 11 -> 400 demasiadas_cuentas",
   codigo(cli.post(CB, json={"banco": "Banco Once", "numero": "11111111"}, headers=H)) == "demasiadas_cuentas")

print("\n2. Contacto de ayuda")
MR = "/api/v1/unidades/mi-residencial"
r = cli.put(MR, json={"telefono_ayuda": "+504 2550-1234", "email_ayuda": " Ayuda@VillasDelSol.hn "}, headers=H)
ok("el admin guarda telefono y correo", r.status_code == 200)
d = cli.get(MR, headers=HR).get_json()["data"]
ok("el residente los ve (correo en minusculas)",
   d["telefono_ayuda"] == "+504 2550-1234" and d["email_ayuda"] == "ayuda@villasdelsol.hn")
ok("telefono con letras -> 400", codigo(cli.put(MR, json={"telefono_ayuda": "llamar a Juan"}, headers=H)) == "telefono_invalido")
ok("telefono muy corto -> 400", codigo(cli.put(MR, json={"telefono_ayuda": "12-34"}, headers=H)) == "telefono_invalido")
ok("correo sin arroba -> 400", codigo(cli.put(MR, json={"email_ayuda": "ayuda.villas"}, headers=H)) == "email_invalido")
ok("un residente no puede cambiarlos -> 403", cli.put(MR, json={"telefono_ayuda": "99999999"}, headers=HR).status_code == 403)
cli.put(MR, json={"nombre": "Villas del Sol"}, headers=H)
ok("guardar otro campo no los borra", cli.get(MR, headers=HR).get_json()["data"]["telefono_ayuda"] == "+504 2550-1234")
cli.put(MR, json={"email_ayuda": ""}, headers=H)
d = cli.get(MR, headers=HR).get_json()["data"]
ok("vacio borra solo ese", d["email_ayuda"] is None and d["telefono_ayuda"] == "+504 2550-1234")
ok("la otra residencial no los tiene", cli.get(MR, headers=HOTRO).get_json()["data"]["telefono_ayuda"] is None)

print("\n3. Saldo de la cuota")
with app.app_context():
    cu = Cuota.query.filter_by(cuenta_id=DESC[1]).order_by(Cuota.periodo).first()
    ok("sin pagos: saldo = monto", cu.to_dict()["saldo"] == 600 and cu.to_dict()["pagado"] == 0)
    db.session.add(Pago(id=nid(), cuota_id=cu.id, cuenta_id=DESC[1], subido_por=1, metodo="efectivo",
                        monto=200, estado="aprobado"))
    db.session.add(Pago(id=nid(), cuota_id=cu.id, cuenta_id=DESC[1], subido_por=1, metodo="transferencia",
                        monto=100, estado="en_revision"))
    db.session.flush()
    d = cu.to_dict()
    ok("con L 200 aprobados (y L 100 sin revisar): pagado 200, saldo 400",
       d["pagado"] == 200 and d["saldo"] == 400)
    cu.estado = "pagada"
    ok("pagada -> saldo 0", cu.to_dict()["saldo"] == 0)
    db.session.rollback()

print("\n4. Caja: quien se mudo debiendo")
res = cli.get("/api/v1/caja/buscar-cuenta?q=Mudado", headers=HC).get_json()["data"]
ok("la encuentra, marcada como dada de baja", len(res) == 1 and res[0].get("dada_de_baja") is True)
ok("...con su cuota pendiente para cobrar", len(res) == 1 and len(res[0].get("cuotas_pendientes") or res[0].get("cuotas") or []) == 1)
ok("una dada de baja sin deuda no aparece",
   cli.get("/api/v1/caja/buscar-cuenta?q=Saldada", headers=HC).get_json()["data"] == [])
res = cli.get("/api/v1/caja/buscar-cuenta?q=Rosa", headers=HC).get_json()["data"]
ok("una activa sigue apareciendo, sin la marca", len(res) == 1 and res[0].get("dada_de_baja") is False)
ok("el cajero no encuentra casas de otra residencial",
   cli.get("/api/v1/caja/buscar-cuenta?q=Ajena", headers=HC).get_json()["data"] == [])
ok("...ni el de la otra las de esta",
   cli.get("/api/v1/caja/buscar-cuenta?q=Rosa", headers=HC2).get_json()["data"] == [])
ok("...pero si las suyas",
   len(cli.get("/api/v1/caja/buscar-cuenta?q=Ajena", headers=HC2).get_json()["data"]) == 1)

print("\n5. Descuentos en el reporte financiero")
cuotas_desc = [c["id"] for c in cli.get(f"/api/v1/arreglos/cuenta/{DESC[0]}/cuotas-pendientes",
                                        headers=H).get_json()["data"]]
r = cli.post("/api/v1/arreglos", json={
    "cuenta_id": DESC[0], "cuotas": cuotas_desc, "num_abonos": 3, "proposito": "ponerse_al_dia",
    "descuento_pct": 25, "autorizacion": {"email": "admin2@x.com", "password": "Clave#2026"}}, headers=H)
ok("arreglo de 2 cuotas (L 1 200) con 25 % -> 201", r.status_code == 201)
P = mes_atras(3)
rep = cli.get(f"/api/v1/reportes/financiero?anio={P.year}&mes={P.month}", headers=H).get_json()["data"]
ok("el mes de una de esas cuotas muestra L 150 perdonados", rep.get("total_descontado") == 150)
ok("esperado = recaudado + perdonado + pendiente",
   abs(rep["total_esperado"] - rep["total_recaudado"] - rep["total_descontado"] - rep["total_pendiente"]) < 0.01)
det = rep.get("detalle_descuentos") or []
ok("el detalle dice que casa, cuanto y quien lo autorizo",
   len(det) == 1 and det[0]["unidad"] == "Casa Descuento" and det[0]["monto"] == 150
   and det[0]["descuento_pct"] == 25 and "Ad" in (det[0].get("autorizado_por") or ""))
with app.app_context():
    arr = ArregloPago.query.filter_by(cuenta_id=DESC[1]).first()
    arr.estado = "completado"
    for c in arr.cuotas:
        c.estado = "pagada"
    db.session.commit()
rep2 = cli.get(f"/api/v1/reportes/financiero?anio={P.year}&mes={P.month}", headers=H).get_json()["data"]
ok("completado: lo recaudado de esa cuota es 450, no 600",
   abs((rep2["total_recaudado"] - rep["total_recaudado"]) - 450) < 0.01)
ok("...y sigue cuadrando",
   abs(rep2["total_esperado"] - rep2["total_recaudado"] - rep2["total_descontado"] - rep2["total_pendiente"]) < 0.01)
tend = rep2.get("tendencia") or []
ok("la tendencia tambien descuenta lo perdonado",
   any(abs(t["recaudado"] - rep2["total_recaudado"]) < 0.01 for t in tend))
ok("los meses de la tendencia en espanol",
   all(t["mes_label"].split()[0].lower() in ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago",
                                              "sep", "oct", "nov", "dic") for t in tend))
with app.app_context():
    arr = ArregloPago.query.filter_by(cuenta_id=DESC[1]).first()
    arr.estado = "cancelado"
    db.session.commit()
rep3 = cli.get(f"/api/v1/reportes/financiero?anio={P.year}&mes={P.month}", headers=H).get_json()["data"]
ok("un arreglo cancelado ya no cuenta como descuento", rep3.get("total_descontado") == 0)
ok("la otra residencial no ve los descuentos de esta",
   (cli.get(f"/api/v1/reportes/financiero?anio={P.year}&mes={P.month}", headers=HOTRO)
    .get_json()["data"].get("total_descontado")) == 0)

print("\n6. Redis caido")
r = cli.get("/api/v1/_prueba_redis")
ok("un error de conexion con Redis -> 503 servicio_no_disponible, no 500",
   r.status_code == 503 and codigo(r) == "servicio_no_disponible")

from app.tasks import encolar as _enc                         # noqa: E402


class _Tarea:
    name = "prueba"

    def __init__(self, falla=False):
        self.encoladas, self.falla = [], falla

    def delay(self, *a, **k):          # metodo ligado: tiene __self__, como Celery
        if self.falla:
            raise ConnectionError("sin broker")
        self.encoladas.append(a)


enviados = []
t = _Tarea()
_enc._REDIS_OK.update(ok=False, hasta=float("inf"))
_enc.encolar(t, lambda *a: enviados.append(a), "correo@x.com")
ok("Redis no responde: se envia en el momento, sin encolar",
   enviados == [("correo@x.com",)] and t.encoladas == [])
_enc._REDIS_OK.update(ok=True, hasta=float("inf"))
enviados.clear()
_enc.encolar(t, lambda *a: enviados.append(a), "correo@x.com")
ok("Redis responde: se encola y no se envia dos veces", t.encoladas == [("correo@x.com",)] and enviados == [])
t2 = _Tarea(falla=True)
_enc.encolar(t2, lambda *a: enviados.append(a), "otro@x.com")
ok("Redis responde pero encolar falla: se envia en el momento", enviados == [("otro@x.com",)])


def _revienta(*a):
    raise RuntimeError("SMTP caido")


_enc._REDIS_OK.update(ok=False, hasta=float("inf"))
try:
    _enc.encolar(t, _revienta, "x@x.com")
    ok("si tampoco se puede enviar, no tumba la peticion", True)
except Exception:
    ok("si tampoco se puede enviar, no tumba la peticion", False)
_enc._REDIS_OK.update(ok=True, hasta=0.0)

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo bien.")
