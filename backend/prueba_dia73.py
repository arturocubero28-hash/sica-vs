"""
Dia 73: del padron a cuenta que paga, y la regla de no crear nada sin un
correo confirmado.

  1. CONVERTIR A MEDIAS YA NO SE PUEDE — convertir solo la casa con el
     titular todavia en el padron dejaba una casa cobrando cuota a alguien
     sin correo. Se rechaza; para eso esta /sumar.

  2. SUMAR ES TODO O NADA — convierte la casa, le genera la cuota
     prorrateada y le da acceso al titular con la ficha completa, en una
     sola transaccion.

  3. FICHA COMPLETA — dar acceso exige la misma ficha que el alta normal.

  4. NO SE CREA NADA SIN CORREO CONFIRMADO — con la regla encendida (como
     en produccion), ni el alta, ni el paso desde el padron, ni dar acceso
     crean algo hasta que Resend confirme que el correo LLEGO. Si rebota,
     no queda ningun resto y se puede reintentar con la direccion corregida.
     El aviso de rebote entra por un webhook firmado, igual que en
     produccion.

    python3 prueba_dia73.py
"""
import os, sys, logging, json, time, hmac, hashlib, base64, datetime as dt
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)

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
from app.models.verificacion_correo import VerificacionCorreo  # noqa: E402
from app.utils.cuotas import calcular_cuota_prorrateada        # noqa: E402
import uuid as _uuid                                          # noqa: E402

# El envio del correo de activacion va por Celery; en la prueba no hay
# Redis y cada intento esperaria el timeout de conexion. Se reemplaza por
# un registro en memoria: lo que importa aca es si se PIDIO el envio.
import app.tasks.correo_task as _ct                           # noqa: E402
ENVIADOS = []
_ct.enviar_correo_activacion_task.delay = lambda *a, **k: ENVIADOS.append(a[0])

fallos = []


def ok(desc, cond):
    print(f"  [{'OK  ' if cond else 'FALLA'}] {desc}")
    if not cond:
        fallos.append(desc)


def codigo(r):
    return ((r.get_json() or {}).get("error") or {}).get("code")


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


SECRETO = "whsec_" + base64.b64encode(b"clave-de-prueba-del-webhook-0001").decode()

app = create_app()
app.config["RESEND_WEBHOOK_SECRET"] = SECRETO
limiter.enabled = False

N = {"casa": 0, "usuario": 10, "residente": 0}


def casa_de_padron(nombre):
    """Una casa en el padron con su titular sin correo."""
    N["casa"] += 1; N["usuario"] += 1; N["residente"] += 1
    u = Unidad(id=N["casa"], tipo="casa", identificador=f"Casa {N['casa']}", activa=True)
    db.session.add(u); db.session.flush()
    c = Cuenta(id=N["casa"], unidad_id=u.id, modo_participacion="censo", activa=True)
    p = Usuario(id=N["usuario"], nombre=nombre, apellido="", email=None,
                rol="residente", es_censo=True, activo=False)
    db.session.add_all([c, p]); db.session.flush()
    r = Residente(id=N["residente"], cuenta_id=c.id, usuario_id=p.id, rol_cuenta="titular")
    db.session.add(r); db.session.commit()
    return str(c.uuid_publico), str(r.uuid_publico), c.id, p.id


with app.app_context():
    db.drop_all()
    db.create_all()
    admin = Usuario(id=1, nombre="Ad", apellido="Min", email="admin@x.com",
                    rol="admin", activo=True)
    admin.set_password("Clave#2026")
    db.session.add_all([admin, Tarifa(id=1, nombre="Cuota mensual", monto=600, activa=True)])
    db.session.commit()

    CASA_A = casa_de_padron("Ana")
    CASA_B = casa_de_padron("Berta")
    CASA_C = casa_de_padron("Carla")
    PERS_D = casa_de_padron("Diana")
    _parchear_uuid()

cli = app.test_client()
B = lambda t: {"Authorization": f"Bearer {t}"}                # noqa: E731
H = B(cli.post("/api/v1/auth/login",
               json={"email": "admin@x.com", "password": "Clave#2026"}
               ).get_json()["data"]["token"])


def ficha(correo, **extra):
    base = {"tarifa_id": 1, "dia_pago": 5, "email": correo, "apellido": "Lopez",
            "telefono": "9999-0000", "dni": "0501-1990-00123",
            "direccion_exacta": "Casa, bloque C", "profesion": "Contadora",
            "contacto_emergencia_nombre": "Luis Lopez",
            "contacto_emergencia_telefono": "8888-1111"}
    base.update(extra)
    return base


def webhook(tipo, email_id, **datos):
    """Un aviso de Resend firmado exactamente como lo firma Svix."""
    cuerpo = json.dumps({"type": tipo, "created_at": "2026-11-05T00:00:00Z",
                         "data": {"email_id": email_id, **datos}}).encode()
    wid, ts = f"msg_{time.time_ns()}", str(int(time.time()))
    clave = base64.b64decode(SECRETO.split("_", 1)[1])
    firma = base64.b64encode(hmac.new(clave, f"{wid}.{ts}.".encode() + cuerpo,
                                      hashlib.sha256).digest()).decode()
    return cli.post("/api/v1/webhooks/resend", data=cuerpo,
                    content_type="application/json",
                    headers={"svix-id": wid, "svix-timestamp": ts,
                             "svix-signature": f"v1,{firma}"})


# ─────────────────────────────────────────────────────────────────────────
print("\n1. Convertir a medias ya no se puede")
casa_uuid, _, casa_id, _ = CASA_A
r = cli.post(f"/api/v1/censo/casas/{casa_uuid}/convertir",
             json={"tarifa_id": 1, "dia_pago": 5}, headers=H)
ok("convertir con el titular en el padron -> 400 titular_sin_acceso",
   r.status_code == 400 and codigo(r) == "titular_sin_acceso")
with app.app_context():
    ok("...la casa sigue en el padron", Cuenta.query.get(casa_id).es_censo)
    ok("...y no se le genero cuota", Cuota.query.filter_by(cuenta_id=casa_id).count() == 0)

# ─────────────────────────────────────────────────────────────────────────
print("\n2. Sumar es todo o nada")
r = cli.post(f"/api/v1/censo/casas/{casa_uuid}/sumar",
             json=ficha("ana@x.com", dni="123"), headers=H)
ok("con la identidad mal -> 400", r.status_code == 400)
with app.app_context():
    ok("...y no se toco NADA: la casa sigue en el padron",
       Cuenta.query.get(casa_id).es_censo)
    ok("...ni se le genero cuota", Cuota.query.filter_by(cuenta_id=casa_id).count() == 0)

r = cli.post(f"/api/v1/censo/casas/{casa_uuid}/sumar", json=ficha("ana@x.com"), headers=H)
ok("con todo bien -> 200", r.status_code == 200)
with app.app_context():
    c = Cuenta.query.get(casa_id)
    cuotas = Cuota.query.filter_by(cuenta_id=casa_id).all()
    cfg = ConfigResidencial.get(None)
    esperado = calcular_cuota_prorrateada(600, cfg.dia_pago)
    ok("la casa salio del padron", not c.es_censo)
    if esperado is None:
        ok("fin de mes comercial: sin cuota este mes", len(cuotas) == 0)
    else:
        ok("tiene UNA cuota, prorrateada",
           len(cuotas) == 1 and float(cuotas[0].monto) == esperado["monto"]
           and float(cuotas[0].monto) < 600)
        ok("que vence el mes siguiente (no nace en mora)",
           cuotas[0].fecha_vencimiento > dt.date.today())
    tit = Usuario.query.get(CASA_A[3])
    ok("el titular ya tiene correo y ficha",
       tit.email == "ana@x.com" and not tit.es_censo and tit.profesion == "Contadora")
ok("se pidio el correo de activacion", "ana@x.com" in ENVIADOS)

# ─────────────────────────────────────────────────────────────────────────
print("\n3. Dar acceso exige la ficha completa")
pers_uuid = PERS_D[1]
r = cli.post(f"/api/v1/censo/personas/{pers_uuid}/dar-acceso",
             json={"email": "diana@x.com"}, headers=H)
ok("solo con el correo -> 400 datos_incompletos",
   r.status_code == 400 and codigo(r) == "datos_incompletos")
r = cli.post(f"/api/v1/censo/personas/{pers_uuid}/dar-acceso",
             json=ficha("diana@x.com"), headers=H)
ok("con la ficha completa -> 200", r.status_code == 200)
with app.app_context():
    d = Usuario.query.get(PERS_D[3])
    ok("queda con correo, ficha, y pendiente de activar",
       d.email == "diana@x.com" and d.dni == "0501-1990-00123" and d.activo is False)

# ─────────────────────────────────────────────────────────────────────────
print("\n4. Con la regla de produccion: nada sin correo confirmado")
app.config["EXIGIR_VERIFICACION_CORREO"] = True
casa_b, _, casa_b_id, pers_b_id = CASA_B

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar", json=ficha("berta@x.com"), headers=H)
ok("sumar sin verificar el correo -> 400 correo_no_verificado",
   r.status_code == 400 and codigo(r) == "correo_no_verificado")
with app.app_context():
    ok("...y la casa sigue en el padron", Cuenta.query.get(casa_b_id).es_censo)

# Un correo que REBOTA: se simula el envio y llega el aviso por webhook.
with app.app_context():
    v = VerificacionCorreo(email="bertha@gmial.com", resend_id="re_rebota",
                           estado="enviado", creado_por_id=1)
    db.session.add(v); db.session.commit()
    v_rebota = str(v.uuid_publico)
r = webhook("email.bounced", "re_rebota",
            bounce={"message": "The email account does not exist"})
ok("el webhook firmado del rebote se acepta", r.status_code == 200)
r = cli.get(f"/api/v1/correo/verificaciones/{v_rebota}", headers=H)
ok("la verificacion queda rebotada, con el motivo",
   r.get_json()["data"]["estado"] == "rebotado"
   and "does not exist" in (r.get_json()["data"]["detalle"] or ""))

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("bertha@gmial.com", verificacion_id=v_rebota), headers=H)
ok("sumar con un correo que rebotó -> 400", r.status_code == 400)
with app.app_context():
    ok("...NO SE CREO NADA: la casa sigue en el padron", Cuenta.query.get(casa_b_id).es_censo)
    ok("...ni cuota", Cuota.query.filter_by(cuenta_id=casa_b_id).count() == 0)
    ok("...y la persona sigue sin acceso (asi se puede reintentar)",
       Usuario.query.get(pers_b_id).es_censo)

# Se corrige el correo y se verifica de nuevo.
r = cli.post("/api/v1/correo/verificaciones",
             json={"email": "berta@x.com", "nombre": "Berta"}, headers=H)
ok("pedir verificar el correo corregido -> 201", r.status_code == 201)
v_bien = r.get_json()["data"]["id"]
# Sin RESEND_API_KEY fuera de produccion la entrega se simula.
ok("(desarrollo sin Resend: la entrega se simula)", r.get_json()["data"]["estado"] == "entregado")

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("otra@x.com", verificacion_id=v_bien), headers=H)
ok("usar la verificacion con OTRO correo -> 400", r.status_code == 400)

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("con el correo corregido y confirmado -> 200 (el reintento funciona)",
   r.status_code == 200)
with app.app_context():
    ok("ahora si: la casa salio del padron", not Cuenta.query.get(casa_b_id).es_censo)

casa_c, _, casa_c_id, _ = CASA_C
r = cli.post(f"/api/v1/censo/casas/{casa_c}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("una verificacion no sirve dos veces", r.status_code in (400, 409))
# Lo de arriba puede dar 409 solo porque el correo ya quedo ocupado. Lo que
# de verdad impide reusarla es que quedo marcada como usada:
with app.app_context():
    vb = VerificacionCorreo.query.filter_by(uuid_publico=_uuid.UUID(v_bien)).first()
    ok("...porque quedo marcada como usada al crear la cuenta", vb.usada is True)
    vb_dup = VerificacionCorreo(email="nadie@x.com", estado="entregado",
                                creado_por_id=1, usada=True)
    db.session.add(vb_dup); db.session.commit()
    v_usada = str(vb_dup.uuid_publico)
r = cli.post(f"/api/v1/censo/casas/{casa_c}/sumar",
             json=ficha("nadie@x.com", verificacion_id=v_usada), headers=H)
ok("una verificacion usada se rechaza aunque el correo este libre",
   r.status_code == 400 and codigo(r) == "correo_no_verificado")

# Verificacion de un correo que todavia no confirmo entrega.
with app.app_context():
    v = VerificacionCorreo(email="carla@x.com", resend_id="re_lento",
                           estado="enviado", creado_por_id=1)
    db.session.add(v); db.session.commit()
    v_lento = str(v.uuid_publico)
r = cli.post(f"/api/v1/censo/casas/{casa_c}/sumar",
             json=ficha("carla@x.com", verificacion_id=v_lento), headers=H)
ok("enviado pero sin confirmar entrega -> 400", r.status_code == 400)
r = webhook("email.delivered", "re_lento")
ok("llega el aviso de entregado", r.status_code == 200)
r = cli.post(f"/api/v1/censo/casas/{casa_c}/sumar",
             json=ficha("carla@x.com", verificacion_id=v_lento), headers=H)
ok("ya confirmado -> 200", r.status_code == 200)

# El alta normal sigue la misma regla.
r = cli.post("/api/v1/unidades/cuentas", headers=H, json={
    "unidad_nueva": {"tipo": "casa", "identificador": "Casa Nueva"},
    "tarifa_id": 1, "dia_pago": 5,
    "titular": {"nombre": "Eva", "apellido": "Ruiz", "email": "eva@x.com",
                "telefono": "9999-1111", "dni": "0501-1985-00999"}})
ok("alta normal sin verificar -> 400 correo_no_verificado",
   r.status_code == 400 and codigo(r) == "correo_no_verificado")
with app.app_context():
    ok("...y no se creo el usuario", Usuario.query.filter_by(email="eva@x.com").first() is None)

app.config["EXIGIR_VERIFICACION_CORREO"] = False

# ─────────────────────────────────────────────────────────────────────────
print("\n5. El listado del padron sigue respondiendo")
rl = cli.get("/api/v1/censo", headers=H)
cuerpo = (rl.get_json() or {}).get("data", {})
ok("GET /censo responde 200", rl.status_code == 200 and "casas" in cuerpo)
ok("sin casas duplicadas por el joinedload",
   len(cuerpo.get("casas", [])) == len({c["id"] for c in cuerpo.get("casas", [])}))

print()
if fallos:
    print(f"FALLAN {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo OK")
