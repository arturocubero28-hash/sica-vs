"""
Prueba de punta a punta: edificios en el padrón (Día 70).

El padrón tiene que dejar EXACTAMENTE la misma estructura que el alta
normal, porque convertir es un cambio de modo y no una migración:
  - dueño que solo administra -> cuenta contenedora, sin cuota nunca;
  - dueño que vive ahí        -> su apartamento es la administración,
                                 sin contenedora;
  - inquilinos                -> apartamentos de un edificio YA registrado.

Uso:  REDIS_URL=redis://localhost:6379/9 python3 prueba_padron_edificios_dia70.py
"""
import os, sys, logging, uuid as _uuid
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.WARNING)

# SQLite solo autonumera INTEGER PRIMARY KEY, no BIGINT.
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger
@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"

from app import create_app
from app.extensions import db, limiter
from app.models.usuario import Usuario
from app.models.residencial import Residencial
from app.models.cuenta import Unidad, Cuenta, Residente, Tarifa
from app.auth.security import generar_token
import app.utils.residencial as _ur

fallos = []
def ok(desc, cond):
    print(f"  [{'OK  ' if cond else 'FALLA'}] {desc}")
    if not cond: fallos.append(desc)

app = create_app()
limiter.enabled = False
_ur.plan_permite = lambda *a, **k: True   # la residencial de prueba no tiene plan

with app.app_context():
    db.drop_all(); db.create_all()
    # SQLite no convierte texto a UUID como Postgres (solo en esta prueba).
    q = Usuario.query.__class__; _orig = q.filter_by
    def _fb(self, **kw):
        for k in ("uuid_publico",):
            if isinstance(kw.get(k), str):
                try: kw[k] = _uuid.UUID(kw[k])
                except ValueError: pass
        return _orig(self, **kw)
    q.filter_by = _fb

    admin = Usuario(nombre="Ad", apellido="Min", email="a@x.com", rol="admin")
    admin.set_password("x"); db.session.add(admin); db.session.flush()
    db.session.add(Residencial(id=1, admin_id=admin.id, nombre="Villas")); db.session.flush()
    admin.residencial_id = 1
    tarifa = Tarifa(nombre="Normal", monto=500, residencial_id=1)
    db.session.add(tarifa); db.session.commit()

    cli = app.test_client()
    H = {"Authorization": f"Bearer {generar_token(admin)}"}
    alta = lambda body: cli.post("/api/v1/censo/casas", json=body, headers=H)
    tit = lambda n: {"nombre": n, "apellido": "Prueba", "dni": "0501199000001"}

    def cuenta_de(r):
        cid = r.get_json()["data"]["casa"]["id"]
        return Cuenta.query.filter_by(uuid_publico=_uuid.UUID(cid)).first()

    print("\n1. Edificio cuyo dueño SOLO ADMINISTRA")
    r = alta({"tipo": "edificio", "identificador": "Edificio Sol", "dueno_vive": False,
              "max_apartamentos": 2, "titular": tit("Dueño")})
    ok(f"se registra (status {r.status_code})", r.status_code == 201)
    c = cuenta_de(r) if r.status_code == 201 else None
    ok("queda como cuenta contenedora", c is not None and c.tipo_cuenta() == "edificio_contenedor")
    ok("sin apartamento y sin tarifa", c is not None and c.apartamento is None and c.tarifa_id is None)
    ok("el dueño queda como titular de la contenedora",
       c is not None and c.titular() is not None and c.titular().usuario.nombre == "Dueño")
    ok("el dueño queda como propietario del edificio",
       c is not None and c.unidad.propietario_id == c.titular().usuario.id)

    print("\n2. Apartamentos de ese edificio")
    r = alta({"tipo": "apartamento", "identificador": "Edificio Sol", "apartamento": "1A",
              "titular": tit("Inquilina")})
    a1 = cuenta_de(r) if r.status_code == 201 else None
    ok(f"un inquilino se registra (status {r.status_code})", a1 is not None)
    ok("queda como apartamento", a1 is not None and a1.tipo_cuenta() == "apartamento")
    r = alta({"tipo": "apartamento", "identificador": "Edificio Sol", "apartamento": "1a",
              "titular": tit("Otro")})
    ok("el mismo apartamento no se repite", r.status_code == 409)
    alta({"tipo": "apartamento", "identificador": "Edificio Sol", "apartamento": "2A",
          "titular": tit("Otro")})
    r = alta({"tipo": "apartamento", "identificador": "Edificio Sol", "apartamento": "3A",
              "titular": tit("Otro")})
    ok("respeta el máximo de apartamentos del edificio",
       r.status_code == 400 and r.get_json()["error"]["code"] == "limite_apartamentos")
    r = alta({"tipo": "apartamento", "identificador": "Edificio Fantasma", "apartamento": "1",
              "titular": tit("X")})
    ok("un apartamento de un edificio NO registrado se rechaza",
       r.status_code == 400 and r.get_json()["error"]["code"] == "edificio_no_registrado")

    print("\n3. Edificio donde el dueño VIVE")
    r = alta({"tipo": "edificio", "identificador": "Torre Luna", "dueno_vive": True,
              "apartamento": "PH", "titular": tit("Dueña")})
    d = cuenta_de(r) if r.status_code == 201 else None
    ok(f"se registra (status {r.status_code})", d is not None)
    ok("su apartamento es la administración del edificio",
       d is not None and d.tipo_cuenta() == "edificio_admin")
    ok("NO se crea contenedora (igual que el alta normal)",
       d is not None and Cuenta.query.filter_by(unidad_id=d.unidad_id, apartamento=None,
                                                activa=True).first() is None)
    r = alta({"tipo": "edificio", "identificador": "Torre Luna", "dueno_vive": True,
              "apartamento": "PH", "titular": tit("Z")})
    ok("el mismo edificio no se registra dos veces", r.status_code == 409)
    r = alta({"tipo": "edificio", "identificador": "Torre X", "dueno_vive": True,
              "titular": tit("Z")})
    ok("si el dueño vive, exige el apartamento", r.status_code == 400)

    print("\n4. Edificio sin dueño que dejó el padrón anterior (se adopta)")
    viejo = Unidad(tipo="edificio", identificador="Edificio Viejo", activa=True, residencial_id=1)
    db.session.add(viejo); db.session.flush()
    vacia = Cuenta(unidad_id=viejo.id, apartamento=None, modo_participacion="censo")
    db.session.add(vacia); db.session.commit()
    r = alta({"tipo": "edificio", "identificador": "Edificio Viejo", "dueno_vive": True,
              "apartamento": "1", "titular": tit("Dueño viejo")})
    ok(f"se adopta en vez de rechazarse (status {r.status_code})", r.status_code == 201)
    db.session.refresh(vacia)
    ok("la contenedora vacía se da de baja (el dueño vive ahí)", vacia.activa is False)

    print("\n5. Conversión a cuenta completa")
    conv = lambda c, body: cli.post(f"/api/v1/censo/casas/{c.uuid_publico}/convertir",
                                    json=body, headers=H)
    r = conv(c, {})
    db.session.refresh(c)
    ok(f"la contenedora se convierte SIN tarifa (status {r.status_code})", r.status_code == 200)
    ok("sigue siendo contenedora", c.tipo_cuenta() == "edificio_contenedor")
    ok("y no cobra cuota", c.cobra_cuotas() is False)
    r = conv(a1, {})
    ok("un apartamento SÍ exige tarifa", r.status_code == 400)
    r = conv(a1, {"tarifa_id": tarifa.id, "dia_pago": 5})
    db.session.refresh(a1)
    ok("con tarifa, el apartamento cobra cuota", r.status_code == 200 and a1.cobra_cuotas() is True)
    r = conv(d, {"tarifa_id": tarifa.id, "dia_pago": 5})
    db.session.refresh(d)
    ok("el dueño que vive paga como apartamento y sigue siendo administración",
       r.status_code == 200 and d.cobra_cuotas() is True and d.tipo_cuenta() == "edificio_admin")

    print("\n6. Casas")
    r = alta({"tipo": "casa", "identificador": "Casa 5", "titular": tit("C")})
    ok("una casa se registra", r.status_code == 201)
    r = alta({"tipo": "casa", "identificador": "casa 5", "titular": tit("C")})
    ok("una casa repetida se rechaza", r.status_code == 409)

print("\n" + ("TODO OK" if not fallos else f"{len(fallos)} FALLAS: {fallos}"))
sys.exit(1 if fallos else 0)
