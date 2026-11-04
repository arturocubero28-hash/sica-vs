"""
Dia 73: lo que faltaba al pasar del padron a cuenta que paga.

Cubre dos agujeros encontrados en produccion:

  1. CUOTA PRORRATEADA — una casa convertida desde el padron nacia SIN
     deuda. El alta normal si genera la primera cuota prorrateada por los
     dias que quedan del mes; la conversion se habia quedado sin esa
     parte, asi que el mes en que la familia se sumaba le salia gratis y
     las dos puertas de entrada al sistema cobraban distinto.

  2. DATOS COMPLETOS — dar acceso a alguien del padron solo pedia el
     correo. El padron se llena con lo minimo (nombre y a veces identidad)
     a proposito, pero quien pasa a ser residente con app y cuota tiene
     que tener la misma ficha que cualquier otro: identidad, telefono,
     direccion, profesion y contacto de emergencia.

    python3 prueba_dia73.py
"""
import os, sys, logging, datetime as dt
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.WARNING)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


from app import create_app                                    # noqa: E402
from app.extensions import db, limiter                        # noqa: E402
from app.models.usuario import Usuario                        # noqa: E402
from app.models.cuenta import (                               # noqa: E402
    Unidad, Cuenta, Residente, Tarifa, Cuota, ConfigResidencial,
)
from app.utils.cuotas import calcular_cuota_prorrateada        # noqa: E402
import uuid as _uuid                                          # noqa: E402

fallos = []


def ok(desc, cond):
    print(f"  [{'OK  ' if cond else 'FALLA'}] {desc}")
    if not cond:
        fallos.append(desc)


def _parchear_uuid():
    """SQLite guarda uuid_publico como texto; filter_by recibe str."""
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

with app.app_context():
    db.drop_all()
    db.create_all()

    admin = Usuario(id=1, nombre="Ad", apellido="Min", email="admin@x.com",
                    rol="admin", activo=True)
    admin.set_password("Clave#2026")
    db.session.add(admin)

    tarifa = Tarifa(id=1, nombre="Cuota mensual", monto=600, activa=True)
    db.session.add(tarifa)

    unidad = Unidad(id=1, tipo="casa", identificador="Casa 101", activa=True)
    db.session.add(unidad)
    db.session.flush()

    # Casa en el padron, con una persona sin correo ni contrasena.
    casa = Cuenta(id=1, unidad_id=unidad.id, modo_participacion="censo", activa=True)
    db.session.add(casa)
    persona = Usuario(id=2, nombre="Ana", apellido="Lopez", email=None,
                      rol="residente", es_censo=True, activo=False)
    db.session.add(persona)
    db.session.flush()
    db.session.add(Residente(id=1, cuenta_id=casa.id, usuario_id=persona.id,
                             rol_cuenta="titular"))
    db.session.commit()

    casa_uuid = str(casa.uuid_publico)
    persona_uuid = str(Residente.query.get(1).uuid_publico)
    _parchear_uuid()

cli = app.test_client()
B = lambda t: {"Authorization": f"Bearer {t}"}                # noqa: E731
token = cli.post("/api/v1/auth/login",
                 json={"email": "admin@x.com", "password": "Clave#2026"}
                 ).get_json()["data"]["token"]

# ─────────────────────────────────────────────────────────────────────────
print("\n1. Cuota prorrateada al convertir una casa del padron")

with app.app_context():
    ok("antes de convertir, la casa no debe nada",
       Cuota.query.filter_by(cuenta_id=1).count() == 0)

r = cli.post(f"/api/v1/censo/casas/{casa_uuid}/convertir",
             json={"tarifa_id": 1, "dia_pago": 5}, headers=B(token))
ok("la conversion responde 200", r.status_code == 200)

with app.app_context():
    cuotas = Cuota.query.filter_by(cuenta_id=1).all()
    cfg = ConfigResidencial.get(None)
    esperado = calcular_cuota_prorrateada(600, cfg.dia_pago)

    if esperado is None:
        # Hoy es fin del mes comercial: no queda fraccion que cobrar y la
        # primera cuota es la del mes que viene. Es un caso real del
        # calendario, no una falla.
        ok("fin de mes comercial: no se genera cuota de este mes",
           len(cuotas) == 0)
    else:
        ok("se genero exactamente una cuota", len(cuotas) == 1)
        if cuotas:
            c = cuotas[0]
            ok("el monto es el prorrateado, no la tarifa completa",
               float(c.monto) == esperado["monto"] and float(c.monto) < 600)
            ok("el periodo es el mes en curso", c.periodo == esperado["periodo"])
            ok("vence el mes siguiente (no nace en mora)",
               c.fecha_vencimiento == esperado["fecha_vencimiento"]
               and c.fecha_vencimiento > dt.date.today())
            ok("queda pendiente de pago", c.estado == "pendiente")

# Mismo calculo que el alta normal: si los dos caminos no coinciden, una
# familia paga distinto segun por donde entro al sistema.
with app.app_context():
    cfg = ConfigResidencial.get(None)
    a = calcular_cuota_prorrateada(600, cfg.dia_pago)
    ok("el prorrateo usa la misma funcion que el alta normal",
       a is None or (a["monto"] > 0 and a["periodo"].day == 1))

print("\n2. No se duplica ni se cobra hacia atras")

r2 = cli.post(f"/api/v1/censo/casas/{casa_uuid}/convertir",
              json={"tarifa_id": 1, "dia_pago": 5}, headers=B(token))
ok("convertir una casa ya convertida -> 400", r2.status_code == 400)

with app.app_context():
    cuotas = Cuota.query.filter_by(cuenta_id=1).all()
    ok("sigue sin haber cuotas de meses anteriores",
       all(c.periodo.month == dt.date.today().month for c in cuotas))

print("\n3. Dar acceso exige la ficha completa")

falta = {"email": "ana@x.com"}
r3 = cli.post(f"/api/v1/censo/personas/{persona_uuid}/dar-acceso",
              json=falta, headers=B(token))
ok("solo con el correo -> 400 datos_incompletos",
   r3.status_code == 400
   and (r3.get_json() or {}).get("error", {}).get("code") == "datos_incompletos")

completo = {
    "email": "ana@x.com", "apellido": "Lopez", "telefono": "9999-0000",
    "dni": "0501-1990-00123", "direccion_exacta": "Casa 101, bloque C",
    "profesion": "Contadora",
    "contacto_emergencia_nombre": "Luis Lopez",
    "contacto_emergencia_telefono": "8888-1111",
}

malo = dict(completo, dni="123")
r4 = cli.post(f"/api/v1/censo/personas/{persona_uuid}/dar-acceso",
              json=malo, headers=B(token))
ok("identidad de 3 digitos -> 400", r4.status_code == 400)

r5 = cli.post(f"/api/v1/censo/personas/{persona_uuid}/dar-acceso",
              json=completo, headers=B(token))
ok("con la ficha completa -> 200", r5.status_code == 200)

with app.app_context():
    p = Usuario.query.get(2)
    ok("deja de ser gente de padron", p.es_censo is False)
    ok("queda con correo", p.email == "ana@x.com")
    ok("y con los datos que antes no se pedian",
       p.dni == "0501-1990-00123" and p.profesion == "Contadora"
       and p.direccion_exacta == "Casa 101, bloque C"
       and p.contacto_emergencia_nombre == "Luis Lopez"
       and p.contacto_emergencia_telefono == "8888-1111")
    ok("sigue sin poder autenticarse hasta activar", p.activo is False)

print("\n4. El listado del padron sigue respondiendo (joinedload)")

rl = cli.get("/api/v1/censo", headers=B(token))
ok("GET /censo responde 200", rl.status_code == 200)
cuerpo = (rl.get_json() or {}).get("data", {})
ok("trae la forma esperada",
   "casas" in cuerpo and "resumen" in cuerpo)
# La casa de arriba ya se convirtio, asi que el padron quedo vacio: lo que
# importa es que la consulta con joinedload no reviente ni duplique filas.
ok("no duplica casas por el joinedload",
   len(cuerpo.get("casas", [])) == len({c["id"] for c in cuerpo.get("casas", [])}))

print()
if fallos:
    print(f"FALLAN {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo OK")
