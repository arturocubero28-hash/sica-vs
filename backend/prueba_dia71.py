"""
Dia 71: el guardia identifica a TODOS los miembros de una casa que no
pueden usar el codigo (padron o sin codigo), sin exponer datos de contacto;
y el residente puede ver su codigo de emergencia.

    REDIS_URL=redis://localhost:6379/9 python3 prueba_dia71.py
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
# Los limites de tasa se guardan en Redis y sobreviven entre corridas: sin
# esto, la segunda ejecucion seguida choca con el limite de 20 busquedas
# por minuto del propio endpoint y falla sin que el codigo tenga nada mal.
from app.extensions import limiter
limiter.enabled = False
with app.app_context():
    db.drop_all(); db.create_all()
    admin = Usuario(id=1, nombre="Ad", apellido="Min", email="a@x.com", rol="admin")
    admin.set_password("x"); db.session.add(admin); db.session.flush()
    db.session.add(Residencial(id=1, admin_id=admin.id, nombre="Villas")); db.session.flush()
    admin.residencial_id = 1
    g = Usuario(id=2, nombre="Gu", apellido="Ardia", email="g@x.com", rol="guardia",
                residencial_id=1, punto_acceso_actual="Porton")
    g.set_password("x"); db.session.add(g)
    for i,(tipo,dir_) in enumerate([("vehicular","entrada"),("vehicular","salida"),("peatonal","entrada")], start=1):
        db.session.add(AccesoFisico(id=i, nombre=f"T{i}", tipo=tipo, direccion=dir_,
                                    punto_acceso="Porton", residencial_id=1, activo=True))

    # Casa 10 del padron: titular Rosa y miembro Juan (Juan va antes en orden alfabetico)
    u10 = Unidad(id=10, tipo="casa", identificador="Casa 10", activa=True, residencial_id=1)
    c10 = Cuenta(id=10, unidad_id=10, modo_participacion="censo")
    rosa = Usuario(id=10, nombre="Rosa", apellido="Lopez", dni="0501-1990-00001", es_censo=True, rol="residente", residencial_id=1)
    juan = Usuario(id=11, nombre="Juan", apellido="Lopez", dni="0501-1992-00002", es_censo=True, rol="residente", residencial_id=1)

    # Casa 40 mixta: titular con app y codigo, miembro con app SIN codigo,
    # miembro todavia del padron.
    u40 = Unidad(id=40, tipo="casa", identificador="Casa 40", activa=True, residencial_id=1)
    c40 = Cuenta(id=40, unidad_id=40, modo_participacion="completa")
    pedro = Usuario(id=20, nombre="Pedro", apellido="Rivas", email="pedro@x.com", telefono="9999-0000",
                    dni="0501-1970-00010", rol="residente", residencial_id=1)
    pedro.set_password("x"); pedro.set_codigo_emergencia("482913")
    marta = Usuario(id=21, nombre="Marta", apellido="Rivas", email="marta@x.com", telefono="8888-0000",
                    dni="0501-1975-00011", rol="residente", residencial_id=1)
    marta.set_password("x")
    nino = Usuario(id=22, nombre="Nino", apellido="Rivas", dni="0501-2005-00012", es_censo=True,
                   rol="residente", residencial_id=1)

    # Ana: tiene codigo creado ANTES del Dia 71 (solo hash, sin copia cifrada)
    u50 = Unidad(id=50, tipo="casa", identificador="Casa 50", activa=True, residencial_id=1)
    c50 = Cuenta(id=50, unidad_id=50, modo_participacion="completa")
    ana = Usuario(id=30, nombre="Ana", apellido="Paz", email="ana@x.com", rol="residente", residencial_id=1)
    ana.set_password("x"); ana.set_codigo_emergencia("771205"); ana.codigo_emergencia_cifrado = None

    db.session.add_all([u10, c10, rosa, juan, u40, c40, pedro, marta, nino, u50, c50, ana]); db.session.flush()
    db.session.add_all([
        Residente(id=1, usuario_id=10, cuenta_id=10, rol_cuenta="titular"),
        Residente(id=2, usuario_id=11, cuenta_id=10, rol_cuenta="miembro", relacion="hijo"),
        Residente(id=3, usuario_id=20, cuenta_id=40, rol_cuenta="titular"),
        Residente(id=4, usuario_id=21, cuenta_id=40, rol_cuenta="miembro", relacion="esposa"),
        Residente(id=5, usuario_id=22, cuenta_id=40, rol_cuenta="miembro", relacion="hijo"),
        Residente(id=6, usuario_id=30, cuenta_id=50, rol_cuenta="titular"),
    ])
    db.session.commit()
    _parchear_uuid()
    H = {"Authorization": f"Bearer {generar_token(g)}"}
    cli = app.test_client()
    url = "/api/v1/guardias/residente/buscar"

    print("\nGuardia: identificar a los miembros de una casa sin codigo")
    r = cli.post(url, json={"casa": "Casa 10"}, headers=H); d = r.get_json()
    pers = d["data"]["personas"] if r.status_code == 200 else []
    ok("casa del padron lista a sus dos personas", len(pers) == 2)
    ok("el titular sale primero aunque otro vaya antes alfabeticamente",
       [p["nombre"] for p in pers] == ["Rosa Lopez", "Juan Lopez"])
    ok("cada persona dice si es titular o miembro y su relacion",
       pers and pers[0]["rol_cuenta"] == "titular" and pers[1]["relacion"] == "hijo")

    r = cli.post(url, json={"casa": "casa 40"}, headers=H); d = r.get_json()
    pers = d["data"]["personas"] if r.status_code == 200 else []
    nombres = [p["nombre"] for p in pers]
    ok("casa mixta: aparece el miembro con app pero SIN codigo", "Marta Rivas" in nombres)
    ok("casa mixta: aparece el miembro del padron", "Nino Rivas" in nombres)
    ok("casa mixta: NO aparece quien tiene codigo", "Pedro Rivas" not in nombres)
    ok("origen distingue padron de sin_codigo",
       {p["nombre"]: p["origen"] for p in pers} == {"Marta Rivas": "sin_codigo", "Nino Rivas": "padron"})
    ok("trae nombre, identidad y foto", all("dni" in p and "foto_url" in p for p in pers))
    ok("NO expone correo, telefono ni datos de contacto",
       all(not ({"email", "telefono", "rtn", "direccion_exacta",
                 "contacto_emergencia_telefono"} & set(p)) for p in pers))

    r = cli.post(url, json={"casa": "Casa 40", "codigo": "482913"}, headers=H)
    ok("Pedro se sigue encontrando con su codigo", r.status_code == 200 and r.get_json()["data"]["modo"] == "codigo")

    print("\nRegistro: el historial dice como se identifico")
    reg = "/api/v1/guardias/residente/registrar"
    foto = lambda: (io.BytesIO(b"\xff\xd8\xff\xe0" + b"0"*200), "id.jpg")
    with app.app_context():
        uid = {i: str(db.session.get(Residente, i).uuid_publico) for i in (3, 4, 5)}
    def registrar(rid):
        r = cli.post(reg, data={"residente_id": rid, "direccion": "entrada", "tipo_acceso": "peatonal",
                                "foto_identidad": foto()}, headers=H, content_type="multipart/form-data")
        return r.get_json()["data"]["evento"]["metodo"] if r.status_code == 201 else f"error {r.status_code}"
    ok("miembro con app sin codigo -> identidad_sin_codigo", registrar(uid[4]) == "identidad_sin_codigo")
    ok("miembro del padron -> padron_identidad", registrar(uid[5]) == "padron_identidad")
    ok("residente con codigo -> codigo_emergencia", registrar(uid[3]) == "codigo_emergencia")

    print("\nResidente: ver su codigo de emergencia")
    with app.app_context():
        HP = {"Authorization": f"Bearer {generar_token(db.session.get(Usuario, 20))}"}
        HA = {"Authorization": f"Bearer {generar_token(db.session.get(Usuario, 30))}"}
        HM = {"Authorization": f"Bearer {generar_token(db.session.get(Usuario, 21))}"}
    ce = "/api/v1/auth/codigo-emergencia"
    d = cli.get(ce, headers=HP).get_json()["data"]
    ok("devuelve el codigo a su dueno", d["configurado"] and d["codigo"] == "482913")
    with app.app_context():
        guardado = db.session.get(Usuario, 20).codigo_emergencia_cifrado or ""
    ok("en la base el codigo NO esta en claro", guardado and "482913" not in guardado)
    d = cli.get(ce, headers=HM).get_json()["data"]
    ok("quien no tiene codigo: configurado=false y codigo null", d["configurado"] is False and d["codigo"] is None)
    d = cli.get(ce, headers=HA).get_json()["data"]
    ok("codigo anterior al Dia 71: configurado=true pero codigo null", d["configurado"] and d["codigo"] is None)
    r = cli.put(ce, json={"codigo": "580341"}, headers=HA)
    d = cli.get(ce, headers=HA).get_json()["data"]
    ok("al cambiarlo, ya se puede ver", r.status_code == 200 and d["codigo"] == "580341")
    r = cli.post(url, json={"casa": "Casa 50", "codigo": "580341"}, headers=H)
    ok("el codigo nuevo sirve en el porton", r.status_code == 200)
    r = cli.post(url, json={"casa": "Casa 50", "codigo": "771205"}, headers=H)
    ok("el codigo viejo ya no sirve", r.status_code == 404)

print("\nTODO OK" if not fallos else f"\n{len(fallos)} FALLA(S): {fallos}")
sys.exit(1 if fallos else 0)
