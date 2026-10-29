"""
Dia 72: sesion persistente de la app (estilo WhatsApp).

    REDIS_URL=redis://localhost:6379/9 python3 prueba_dia72.py
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
from app import create_app
from app.extensions import db, limiter
from app.models.usuario import Usuario
from app.models.sesion_activa import SesionActiva
import uuid as _uuid

def _parchear_uuid():
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
limiter.enabled = False
with app.app_context():
    db.drop_all(); db.create_all()
    u = Usuario(id=1, nombre="Pe", apellido="Dro", email="p@x.com", rol="residente", activo=True)
    u.set_password("Clave#2026"); db.session.add(u); db.session.commit()
    _parchear_uuid()
cli = app.test_client()
B = lambda t: {"Authorization": f"Bearer {t}"}

def login(recordar):
    body = {"email": "p@x.com", "password": "Clave#2026"}
    if recordar is not None: body["recordar"] = recordar
    return cli.post("/api/v1/auth/login", json=body).get_json()["data"]

print("\nLogin")
web = login(None)
ok("panel web (sin recordar) NO recibe token de renovacion", "refresh_token" not in web)
d = login(True)
ok("app (recordar) recibe token de renovacion", bool(d.get("refresh_token")))
with app.app_context():
    s = SesionActiva.query.filter_by(persistente=True).one()
    dias = (s.expira_en.replace(tzinfo=None) - dt.datetime.utcnow()).days
    ok("del token solo se guarda el hash", s.refresh_hash != d["refresh_token"] and len(s.refresh_hash) == 64)
    ok("la sesion de la app dura ~180 dias", 178 <= dias <= 180)

print("\nRenovar")
r = cli.post("/api/v1/auth/renovar", json={"refresh_token": d["refresh_token"]})
n = r.get_json().get("data", {})
ok("renueva sin contrasena", r.status_code == 200 and n.get("token") and n.get("refresh_token"))
ok("el token de renovacion rota", n.get("refresh_token") != d["refresh_token"])
ok("el JWT nuevo funciona", cli.get("/api/v1/auth/me", headers=B(n["token"])).status_code == 200)
ok("el JWT anterior queda revocado", cli.get("/api/v1/auth/me", headers=B(d["token"])).status_code == 401)
with app.app_context():
    ok("sigue siendo UNA sola sesion (no se duplica al renovar)",
       SesionActiva.query.filter_by(persistente=True).count() == 1)

r = cli.post("/api/v1/auth/renovar", json={"refresh_token": d["refresh_token"]})
n2 = r.get_json().get("data", {})
ok("reintento con el token recien rotado (respuesta perdida) se acepta", r.status_code == 200)

with app.app_context():
    s = SesionActiva.query.filter_by(persistente=True).one()
    s.refresh_rotado_en = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
    db.session.commit()
r = cli.post("/api/v1/auth/renovar", json={"refresh_token": n["refresh_token"]})
ok("token viejo fuera del margen -> 401 sesion_revocada",
   r.status_code == 401 and r.get_json()["error"]["code"] == "sesion_revocada")
r = cli.post("/api/v1/auth/renovar", json={"refresh_token": n2["refresh_token"]})
ok("...y la sesion entera queda cerrada (el token vigente tampoco sirve)", r.status_code == 401)
ok("...y su JWT tambien", cli.get("/api/v1/auth/me", headers=B(n2["token"])).status_code == 401)

r = cli.post("/api/v1/auth/renovar", json={"refresh_token": "inventado"})
ok("token inventado -> 401", r.status_code == 401)
r = cli.post("/api/v1/auth/renovar", json={"refresh_token": web["token"]})
ok("un JWT no sirve como token de renovacion", r.status_code == 401)

print("\nCerrar sesion")
d = login(True)
r = cli.post("/api/v1/auth/logout", json={"refresh_token": d["refresh_token"]})
ok("logout solo con el token de renovacion (JWT vencido) responde 200", r.status_code == 200)
ok("despues del logout ya no renueva",
   cli.post("/api/v1/auth/renovar", json={"refresh_token": d["refresh_token"]}).status_code == 401)
ok("y el JWT de esa sesion queda revocado", cli.get("/api/v1/auth/me", headers=B(d["token"])).status_code == 401)
d = login(True)
r = cli.post("/api/v1/auth/logout", json={}, headers=B(d["token"]))
ok("logout con JWT (como el panel web) tambien mata la renovacion",
   cli.post("/api/v1/auth/renovar", json={"refresh_token": d["refresh_token"]}).status_code == 401)
ok("logout sin nada responde 200 (idempotente)", cli.post("/api/v1/auth/logout", json={}).status_code == 200)

print("\nCerrar desde otro dispositivo")
tel = login(True); pc = login(None)
with app.app_context():
    sid = SesionActiva.query.filter_by(persistente=True).one().id
r = cli.post(f"/api/v1/auth/sesiones/{sid}/cerrar", headers=B(pc["token"]))
ok("cerrar el telefono desde 'dispositivos conectados' mata su renovacion",
   r.status_code == 200 and
   cli.post("/api/v1/auth/renovar", json={"refresh_token": tel["refresh_token"]}).status_code == 401)

print("\nCambio de contrasena")
tel = login(True); pc = login(None)
r = cli.post("/api/v1/auth/cambiar-password", headers=B(pc["token"]),
             json={"password_actual": "Clave#2026", "password_nueva": "Nueva#2026"})
ok("cambiar la contrasena responde 200", r.status_code == 200)
ok("cierra la sesion del otro dispositivo",
   cli.post("/api/v1/auth/renovar", json={"refresh_token": tel["refresh_token"]}).status_code == 401)
ok("pero no la del dispositivo donde se cambio", cli.get("/api/v1/auth/me", headers=B(pc["token"])).status_code == 200)

print("\nGuardia (telefono compartido de la caseta)")
with app.app_context():
    gu = Usuario(id=2, nombre="Gu", apellido="Ar", email="g@x.com", rol="guardia", activo=True)
    gu.set_password("Clave#2026"); db.session.add(gu); db.session.commit()
r = cli.post("/api/v1/auth/login", json={"email": "g@x.com", "password": "Clave#2026", "recordar": True}).get_json()["data"]
ok("el guardia NO recibe sesion permanente (vence con el turno)", "refresh_token" not in r and bool(r.get("token")))

print("\nUsuario desactivado / sesion vencida")
tel = cli.post("/api/v1/auth/login", json={"email": "p@x.com", "password": "Nueva#2026", "recordar": True}).get_json()["data"]
with app.app_context():
    db.session.get(Usuario, 1).activo = False; db.session.commit()
ok("usuario desactivado no puede renovar",
   cli.post("/api/v1/auth/renovar", json={"refresh_token": tel["refresh_token"]}).status_code == 401)
with app.app_context():
    db.session.get(Usuario, 1).activo = True; db.session.commit()
tel = cli.post("/api/v1/auth/login", json={"email": "p@x.com", "password": "Nueva#2026", "recordar": True}).get_json()["data"]
with app.app_context():
    s = SesionActiva.query.filter_by(persistente=True).one()
    s.expira_en = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1); db.session.commit()
r = cli.post("/api/v1/auth/renovar", json={"refresh_token": tel["refresh_token"]})
ok("sesion sin usar por mas de 180 dias -> sesion_vencida",
   r.status_code == 401 and r.get_json()["error"]["code"] == "sesion_vencida")

print(f"\n{'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
sys.exit(1 if fallos else 0)
