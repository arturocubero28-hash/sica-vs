"""
Dia 72: correo editable, regeneracion al correo nuevo y aviso de rebote.

    REDIS_URL=redis://localhost:6379/9 python3 prueba_dia72_correo.py
"""
import os, sys, json, base64, hmac, hashlib, logging, datetime as dt
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(b"secreto-de-prueba-1234").decode()
sys.path.insert(0, ".")
logging.disable(logging.WARNING)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger
@compiles(BigInteger, "sqlite")
def _b(t, c, **k): return "INTEGER"
from app import create_app
from app.extensions import db, limiter
from app.models.usuario import Usuario
from app.models.residencial import Residencial
from app.models.cuenta import Unidad, Cuenta, Residente
from app.auth.security import generar_token
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
def ok(d, c):
    print(f"  [{'OK  ' if c else 'FALLA'}] {d}")
    if not c: fallos.append(d)

app = create_app()
limiter.enabled = False
with app.app_context():
    db.drop_all(); db.create_all()
    admin = Usuario(id=1, nombre="Ad", apellido="Min", email="a@x.com", rol="admin")
    admin.set_password("x"); db.session.add(admin); db.session.flush()
    db.session.add(Residencial(id=1, admin_id=admin.id, nombre="Villas")); db.session.flush()
    admin.residencial_id = 1
    db.session.add(Unidad(id=10, tipo="casa", identificador="Casa 10", activa=True, residencial_id=1))
    db.session.add(Cuenta(id=10, unidad_id=10, modo_participacion="completa"))
    # Residente con el correo MAL escrito, como pasa en el alta real
    rosa = Usuario(id=10, nombre="Rosa", apellido="Lopez", email="rosa@gmial.com",
                   rol="residente", residencial_id=1, activo=False)
    otra = Usuario(id=11, nombre="Otra", apellido="Persona", email="ocupado@x.com",
                   rol="residente", residencial_id=1)
    db.session.add_all([rosa, otra]); db.session.flush()
    db.session.add(Residente(id=1, usuario_id=10, cuenta_id=10, rol_cuenta="titular"))
    db.session.commit()
    _parchear_uuid()
    uid_rosa = str(db.session.get(Usuario, 10).uuid_publico)
    cta = str(db.session.get(Cuenta, 10).uuid_publico)
    res_uuid = str(db.session.get(Residente, 1).uuid_publico)
    H = {"Authorization": f"Bearer {generar_token(admin)}"}

cli = app.test_client()

def firmar(cuerpo: bytes, cuando=None, secreto=None):
    sec = secreto or os.environ["RESEND_WEBHOOK_SECRET"]
    clave = base64.b64decode(sec.split("_", 1)[1])
    ts = str(int((cuando or dt.datetime.now(dt.timezone.utc)).timestamp()))
    svix_id = "msg_prueba"
    firma = base64.b64encode(
        hmac.new(clave, svix_id.encode() + b"." + ts.encode() + b"." + cuerpo, hashlib.sha256).digest()
    ).decode()
    return {"svix-id": svix_id, "svix-timestamp": ts, "svix-signature": f"v1,{firma}",
            "Content-Type": "application/json"}

def webhook(evento, **kw):
    cuerpo = json.dumps(evento).encode()
    return cli.post("/api/v1/webhooks/resend", data=cuerpo, headers=firmar(cuerpo, **kw))

print("\nEl correo se puede corregir")
r = cli.put(f"/api/v1/usuarios/{uid_rosa}", json={"email": "rosa@gmail.com"}, headers=H)
ok("el admin corrige el correo mal escrito", r.status_code == 200)
with app.app_context():
    ok("queda guardado en minusculas", db.session.get(Usuario, 10).email == "rosa@gmail.com")

r = cli.put(f"/api/v1/usuarios/{uid_rosa}", json={"email": "no-es-correo"}, headers=H)
ok("rechaza un correo con formato invalido", r.status_code == 400)
r = cli.put(f"/api/v1/usuarios/{uid_rosa}", json={"email": "ocupado@x.com"}, headers=H)
ok("rechaza un correo que ya usa otro usuario",
   r.status_code == 400 and r.get_json()["error"]["code"] == "email_duplicado")
r = cli.put(f"/api/v1/usuarios/{uid_rosa}", json={"email": "   "}, headers=H)
ok("rechaza dejarlo vacio", r.status_code == 400)
with app.app_context():
    ok("tras los rechazos el correo sigue siendo el bueno",
       db.session.get(Usuario, 10).email == "rosa@gmail.com")

print("\nEl rebote de Resend marca a la persona")
with app.app_context():
    u = db.session.get(Usuario, 10)
    u.correo_estado = "enviado"; u.correo_resend_id = "env-1"; db.session.commit()
r = webhook({"type": "email.bounced", "data": {
    "email_id": "env-1", "to": ["rosa@gmail.com"],
    "bounce": {"type": "Permanent", "subType": "General",
               "message": "The recipient's email address does not exist."}}})
ok("el webhook responde 200", r.status_code == 200)
with app.app_context():
    u = db.session.get(Usuario, 10)
    ok("el usuario queda marcado como rebotado", u.correo_estado == "rebotado")
    ok("se guarda el motivo que dio Resend", "does not exist" in (u.correo_detalle or ""))

r = webhook({"type": "email.delivered", "data": {"email_id": "env-1", "to": ["rosa@gmail.com"]}})
with app.app_context():
    ok("un 'entregado' que llega tarde no borra el rebote",
       db.session.get(Usuario, 10).correo_estado == "rebotado")

print("\nSolo se aceptan avisos firmados")
cuerpo = json.dumps({"type": "email.bounced", "data": {"email_id": "env-1"}}).encode()
r = cli.post("/api/v1/webhooks/resend", data=cuerpo, headers={"Content-Type": "application/json"})
ok("sin firma -> 401", r.status_code == 401)
h = firmar(cuerpo); h["svix-signature"] = "v1,firmaFalsaFalsaFalsa="
r = cli.post("/api/v1/webhooks/resend", data=cuerpo, headers=h)
ok("con firma incorrecta -> 401", r.status_code == 401)
r = webhook({"type": "email.bounced", "data": {"email_id": "env-1"}},
            cuando=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30))
ok("firmado hace 30 minutos -> 401 (no se puede reenviar una copia)", r.status_code == 401)
r = webhook({"type": "email.opened", "data": {"email_id": "env-1"}})
ok("un evento que no nos interesa se ignora con 200", r.status_code == 200)

print("\nRegenerar el enlace limpia la advertencia y usa el correo nuevo")
with app.app_context():
    ok("antes de regenerar sigue marcado", db.session.get(Usuario, 10).correo_estado == "rebotado")
enviados = []
import app.tasks.correo_task as ct
ct.enviar_correo_activacion_task.delay = lambda *a, **k: enviados.append(a)
r = cli.post(f"/api/v1/unidades/cuentas/{cta}/residentes/{res_uuid}/regenerar-enlace", headers=H)
ok("regenerar responde 200", r.status_code == 200)
ok("el correo sale al destino corregido", bool(enviados) and enviados[-1][0] == "rosa@gmail.com")
ok("el nombre de la residencial reemplaza al viejo SICA-VS",
   bool(enviados) and "SICA" not in enviados[-1][3])
with app.app_context():
    ok("se limpia la advertencia de rebote", db.session.get(Usuario, 10).correo_estado is None)

print("\nEl panel ve el estado junto al residente")
with app.app_context():
    u = db.session.get(Usuario, 10)
    u.correo_estado = "rebotado"; u.correo_detalle = "no existe"; db.session.commit()
    d = db.session.get(Residente, 1).to_dict()
    ok("el residente expone correo_estado", d.get("correo_estado") == "rebotado")
    ok("el residente expone el motivo", d.get("correo_detalle") == "no existe")

print(f"\n{'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
sys.exit(1 if fallos else 0)
