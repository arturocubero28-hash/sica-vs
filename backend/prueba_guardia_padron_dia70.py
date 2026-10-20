"""
Prueba de punta a punta del acceso de residentes sin telefono (Dia 70),
contra SQLite en memoria y el cliente de pruebas de Flask.

Cubre los dos modos de /guardias/residente/buscar --con codigo (residente
con app) y sin codigo (persona del padron)-- y el registro con los tres
botones (entrada vehicular, salida vehicular, entrada peatonal).

Requiere un Redis local (lo usa la verificacion de tokens revocados):
    REDIS_URL=redis://localhost:6379/9 python3 prueba_guardia_padron_dia70.py
"""
import os, sys, io, logging
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.WARNING)
# SQLite solo autonumera INTEGER PRIMARY KEY, no BIGINT (en Postgres es
# BIGSERIAL). Para esta prueba, BIGINT se compila como INTEGER.
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger
@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"
from app import create_app
from app.extensions import db
from app.models.usuario import Usuario
from app.models.residencial import Residencial
from app.models.cuenta import Unidad, Cuenta, Residente
from app.models.visita import AccesoFisico, EventoAcceso
from app.auth.security import generar_token
import uuid as _uuid, app.auth.security as _sec

# SQLite no convierte texto a UUID como Postgres: solo en esta prueba se
# envuelve la carga del usuario para pasarle un UUID real. El endpoint
# bajo prueba no se toca.
_orig_filter_by = None
def _parchear_uuid():
    from app.models.usuario import Usuario
    q = Usuario.query.__class__
    orig = q.filter_by
    def fb(self, **kw):
        if isinstance(kw.get("uuid_publico"), str):
            kw["uuid_publico"] = _uuid.UUID(kw["uuid_publico"])
        return orig(self, **kw)
    q.filter_by = fb

fallos = []
def ok(desc, cond):
    print(f"  [{'OK  ' if cond else 'FALLA'}] {desc}")
    if not cond: fallos.append(desc)

app = create_app()
app.config["RATELIMIT_ENABLED"] = False
with app.app_context():
    db.drop_all(); db.create_all()
    admin = Usuario(id=1, nombre="Ad", apellido="Min", email="a@x.com", rol="admin")
    admin.set_password("x"); db.session.add(admin); db.session.flush()
    res = Residencial(id=1, admin_id=admin.id, nombre="Villas")
    db.session.add(res); db.session.flush()
    admin.residencial_id = 1
    g = Usuario(id=2, nombre="Gu", apellido="Ardia", email="g@x.com", rol="guardia",
                residencial_id=1, punto_acceso_actual="Porton")
    g.set_password("x"); db.session.add(g)

    # trancas del punto
    for i,(tipo,dir_) in enumerate([("vehicular","entrada"),("vehicular","salida"),("peatonal","entrada")], start=1):
        db.session.add(AccesoFisico(id=i, nombre=f"T{i}", tipo=tipo, direccion=dir_,
                                    punto_acceso="Porton", residencial_id=1, activo=True))

    # Casa 10 del padron: dos personas sin app
    u10 = Unidad(id=10, tipo="casa", identificador="Casa 10", activa=True, residencial_id=1)
    c10 = Cuenta(id=10, unidad_id=10, modo_participacion="censo")
    p1 = Usuario(id=10, nombre="Rosa", apellido="Lopez", dni="0501-1990-00001", es_censo=True, rol="residente", residencial_id=1)
    p2 = Usuario(id=11, nombre="Juan", apellido="Lopez", dni="0501-1992-00002", es_censo=True, rol="residente", residencial_id=1)
    # Casa 20 completa: residente con app y codigo
    u20 = Unidad(id=20, tipo="casa", identificador="Casa 20", activa=True, residencial_id=1)
    c20 = Cuenta(id=20, unidad_id=20, modo_participacion="completa")
    p3 = Usuario(id=12, nombre="Ana", apellido="Paz", email="ana@x.com", rol="residente", residencial_id=1)
    p3.set_password("x"); p3.set_codigo_emergencia("482913")
    # Edificio con dos aptos del padron
    ue = Unidad(id=30, tipo="edificio", identificador="Edificio Sol", activa=True, residencial_id=1)
    cont = Cuenta(id=30, unidad_id=30, apartamento=None, modo_participacion="censo")
    a1 = Cuenta(id=31, unidad_id=30, apartamento="1A", modo_participacion="censo")
    a2 = Cuenta(id=32, unidad_id=30, apartamento="2B", modo_participacion="censo")
    p4 = Usuario(id=13, nombre="Luis", apellido="Mejia", dni="0501-1980-00004", es_censo=True, rol="residente", residencial_id=1)
    p5 = Usuario(id=14, nombre="Eva", apellido="Cruz", dni="0501-1985-00005", es_censo=True, rol="residente", residencial_id=1)
    db.session.add_all([u10,c10,p1,p2,u20,c20,p3,ue,cont,a1,a2,p4,p5]); db.session.flush()
    db.session.add_all([
        Residente(id=1, usuario_id=10, cuenta_id=10, rol_cuenta="titular"),
        Residente(id=2, usuario_id=11, cuenta_id=10, rol_cuenta="miembro"),
        Residente(id=3, usuario_id=12, cuenta_id=20, rol_cuenta="titular"),
        Residente(id=4, usuario_id=13, cuenta_id=31, rol_cuenta="titular"),
        Residente(id=5, usuario_id=14, cuenta_id=32, rol_cuenta="titular"),
    ])
    db.session.commit()
    _parchear_uuid()
    token = generar_token(g)
    H = {"Authorization": f"Bearer {token}"}
    cli = app.test_client()
    url = "/api/v1/guardias/residente/buscar"

    print("\nBusqueda sin codigo (padron)")
    r = cli.post(url, json={"casa": "casa 10"}, headers=H); d = r.get_json()
    ok("casa del padron sin codigo devuelve 200", r.status_code == 200)
    ok("modo = padron", d and d["data"]["modo"] == "padron")
    nombres = sorted(p["nombre"] for p in d["data"]["personas"]) if r.status_code==200 else []
    ok("lista a las dos personas de la casa", len(nombres) == 2)
    ok("cada persona trae su identidad", all(p.get("dni") for p in d["data"]["personas"]) if r.status_code==200 else False)

    r = cli.post(url, json={"casa": "Casa 20"}, headers=H)
    ok("casa con app y SIN codigo NO lista a nadie (404)", r.status_code == 404)

    r = cli.post(url, json={"casa": "Edificio Sol"}, headers=H)
    ok("edificio sin apartamento pide el apartamento (400)",
       r.status_code == 400 and r.get_json()["error"]["code"] == "apartamento_requerido")
    r = cli.post(url, json={"casa": "Edificio Sol", "apartamento": "2b"}, headers=H); d = r.get_json()
    ok("edificio + apto lista SOLO a ese apartamento",
       r.status_code == 200 and [p["nombre"] for p in d["data"]["personas"]] == ["Eva Cruz"])

    r = cli.post(url, json={"casa": "Casa 99"}, headers=H)
    ok("casa inexistente da 404", r.status_code == 404)

    print("\nBusqueda con codigo (sigue igual)")
    r = cli.post(url, json={"casa": "Casa 20", "codigo": "482913"}, headers=H); d = r.get_json()
    ok("codigo correcto encuentra al residente", r.status_code == 200 and d["data"]["modo"] == "codigo")
    r = cli.post(url, json={"casa": "Casa 20", "codigo": "000000"}, headers=H)
    ok("codigo incorrecto da 404", r.status_code == 404)

    print("\nRegistro con los tres botones")
    rid_rosa = None
    with app.app_context():
        rid_rosa = str(db.session.get(Residente, 1).uuid_publico)
    reg = "/api/v1/guardias/residente/registrar"
    foto = lambda: (io.BytesIO(b"\xff\xd8\xff\xe0" + b"0"*200), "id.jpg")

    r = cli.post(reg, data={"residente_id": rid_rosa, "direccion": "entrada",
                            "tipo_acceso": "peatonal", "foto_identidad": foto()},
                 headers=H, content_type="multipart/form-data")
    j = r.get_json()
    ok(f"entrada peatonal registra (status {r.status_code})", r.status_code == 201)
    ev = EventoAcceso.query.order_by(EventoAcceso.id.desc()).first()
    ok("usa la tranca peatonal de entrada", ev is not None and ev.acceso_id == 3)
    ok("metodo = padron_identidad", ev is not None and ev.metodo == "padron_identidad")

    r = cli.post(reg, data={"residente_id": rid_rosa, "direccion": "salida",
                            "tipo_acceso": "vehicular"},
                 headers=H, content_type="multipart/form-data")
    ev = EventoAcceso.query.order_by(EventoAcceso.id.desc()).first()
    ok("salida vehicular usa la tranca 2", r.status_code == 201 and ev.acceso_id == 2)

    r = cli.post(reg, data={"residente_id": rid_rosa, "direccion": "salida",
                            "tipo_acceso": "peatonal"},
                 headers=H, content_type="multipart/form-data")
    ok("tranca que no existe en el punto da 400 claro",
       r.status_code == 400 and r.get_json()["error"]["code"] == "sin_tranca")

    r = cli.post(reg, data={"residente_id": rid_rosa, "direccion": "entrada",
                            "tipo_acceso": "vehicular"},
                 headers=H, content_type="multipart/form-data")
    ok("entrada sin foto sigue rechazandose", r.status_code == 400)

print("\n" + ("TODO OK" if not fallos else f"{len(fallos)} FALLAS: {fallos}"))
sys.exit(1 if fallos else 0)
