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

# Resend "configurado", pero el envio real se reemplaza: en la prueba no
# hay red. Se registra cada correo de activacion que se manda ANTES de
# crear, con el id que Resend le daria. Es el unico correo que debe salir.
import app.services.correo as _correo
app.config["RESEND_API_KEY"] = "re_prueba"
PREVIOS = []
def _envio_falso(email, nombre, token, residencial):
    rid = f"re_{len(PREVIOS)+1:03d}"
    PREVIOS.append((email, rid, token))
    return True, rid
_correo.enviar_activacion_antes_de_crear = _envio_falso
ENVIADOS.clear()

casa_b, _, casa_b_id, pers_b_id = CASA_B

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar", json=ficha("berta@x.com"), headers=H)
ok("sumar sin verificar el correo -> 400 correo_no_verificado",
   r.status_code == 400 and codigo(r) == "correo_no_verificado")
with app.app_context():
    ok("...y la casa sigue en el padron", Cuenta.query.get(casa_b_id).es_censo)

# ── Un correo que REBOTA
r = cli.post("/api/v1/correo/verificaciones",
             json={"email": "bertha@gmial.com", "nombre": "Berta"}, headers=H)
ok("pedir la verificacion manda el correo de activacion -> 201",
   r.status_code == 201 and r.get_json()["data"]["estado"] == "enviado")
v_rebota = r.get_json()["data"]["id"]
ok("...y ese correo YA lleva el enlace de activacion (un solo correo)",
   len(PREVIOS) == 1 and PREVIOS[0][0] == "bertha@gmial.com" and PREVIOS[0][2])

r = webhook("email.bounced", PREVIOS[0][1],
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

r = cli.post("/api/v1/correo/verificaciones", json={"email": "bertha@gmial.com"}, headers=H)
ok("reintentar el MISMO correo que reboto no manda otro: devuelve el rebote",
   r.status_code == 200 and r.get_json()["data"]["estado"] == "rebotado" and len(PREVIOS) == 1)

# ── Se corrige y LLEGA
r = cli.post("/api/v1/correo/verificaciones", json={"email": "berta@x.com", "nombre": "Berta"},
             headers=H)
v_bien = r.get_json()["data"]["id"]
ok("el correo corregido se verifica (sale un correo nuevo)", len(PREVIOS) == 2)
r = cli.post("/api/v1/correo/verificaciones", json={"email": "berta@x.com"}, headers=H)
ok("doble clic: la segunda vez devuelve la MISMA verificacion, sin otro correo",
   r.get_json()["data"]["id"] == v_bien and len(PREVIOS) == 2)

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("enviado pero sin confirmar entrega -> 400, nada creado", r.status_code == 400)
r = webhook("email.delivered", PREVIOS[1][1])
ok("llega el aviso de entregado", r.status_code == 200)

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("otra@x.com", verificacion_id=v_bien), headers=H)
ok("usar la verificacion con OTRO correo -> 400", r.status_code == 400)

r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("confirmado -> 200 (el reintento despues del rebote funciona)", r.status_code == 200)
with app.app_context():
    ok("ahora si: la casa salio del padron", not Cuenta.query.get(casa_b_id).es_censo)
    b = Usuario.query.get(pers_b_id)
    ok("la persona queda con 'Correo entregado' desde el primer momento",
       b.correo_estado == "entregado" and b.correo_resend_id == PREVIOS[1][1])
ok("NO se mando un segundo correo de activacion", "berta@x.com" not in ENVIADOS)

# ── Idempotencia: el mismo pedido otra vez (doble clic, respuesta perdida)
r = cli.post(f"/api/v1/censo/casas/{casa_b}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("repetir el pedido -> 200 'repetido', no 'ya tiene acceso'",
   r.status_code == 200 and r.get_json()["data"].get("repetido") is True)
with app.app_context():
    ok("...y la cuota NO se duplico", Cuota.query.filter_by(cuenta_id=casa_b_id).count() == 1)

casa_c, _, casa_c_id, _ = CASA_C
r = cli.post(f"/api/v1/censo/casas/{casa_c}/sumar",
             json=ficha("berta@x.com", verificacion_id=v_bien), headers=H)
ok("la misma verificacion no sirve para OTRA casa", r.status_code in (400, 409))
with app.app_context():
    ok("...y esa otra casa sigue en el padron", Cuenta.query.get(casa_c_id).es_censo)

# ── Correo ya usado en otra casa
r = cli.post("/api/v1/correo/verificaciones", json={"email": "berta@x.com"}, headers=H)
cuerpo = (r.get_json() or {}).get("error", {})
ok("verificar un correo que ya es de otra persona -> 409", r.status_code == 409)
ok("...y dice de quien es y en que casa",
   "Berta" in cuerpo.get("message", "") and cuerpo.get("donde") == "Casa 2")
ok("...sin mandarle nada", len(PREVIOS) == 2)

# ── Alta normal: misma regla, atomica e idempotente
alta = {"unidad_nueva": {"tipo": "casa", "identificador": "Casa Nueva"},
        "tarifa_id": 1, "dia_pago": 5,
        "titular": {"nombre": "Eva", "apellido": "Ruiz", "email": "eva@x.com",
                    "telefono": "9999-1111", "dni": "0501-1985-00999"}}
r = cli.post("/api/v1/unidades/cuentas", headers=H, json=alta)
ok("alta normal sin verificar -> 400 correo_no_verificado",
   r.status_code == 400 and codigo(r) == "correo_no_verificado")
with app.app_context():
    ok("...y no se creo ni el usuario ni la casa",
       Usuario.query.filter_by(email="eva@x.com").first() is None
       and Unidad.query.filter_by(identificador="Casa Nueva").first() is None)

r = cli.post("/api/v1/correo/verificaciones", json={"email": "eva@x.com", "nombre": "Eva"}, headers=H)
v_eva = r.get_json()["data"]["id"]
webhook("email.delivered", PREVIOS[-1][1])
r1 = cli.post("/api/v1/unidades/cuentas", headers=H, json={**alta, "verificacion_id": v_eva})
r2 = cli.post("/api/v1/unidades/cuentas", headers=H, json={**alta, "verificacion_id": v_eva})
ok("alta verificada -> 201", r1.status_code == 201)
ok("el mismo alta otra vez -> 200 'repetido'",
   r2.status_code == 200 and r2.get_json()["data"].get("repetido") is True)
with app.app_context():
    eva = Usuario.query.filter_by(email="eva@x.com").all()
    casas = Unidad.query.filter_by(identificador="Casa Nueva").all()
    ok("...una sola persona y una sola casa", len(eva) == 1 and len(casas) == 1)
    cta = Cuenta.query.filter_by(unidad_id=casas[0].id).first()
    n = Cuota.query.filter_by(cuenta_id=cta.id).count()
    esperado = calcular_cuota_prorrateada(600, ConfigResidencial.get(None).dia_pago)
    ok("...con su cuota prorrateada en la misma transaccion, una sola",
       n == (0 if esperado is None else 1))
ok("...y un solo correo de activacion (el de la verificacion)",
   [e for e, _, _ in PREVIOS].count("eva@x.com") == 1 and "eva@x.com" not in ENVIADOS)

# ── Agregar miembro repetido, con la casa justo en el limite
with app.app_context():
    u = Unidad.query.get(Cuenta.query.get(casa_b_id).unidad_id)
    u.max_residentes_extra = 1
    db.session.commit()
r = cli.post("/api/v1/correo/verificaciones", json={"email": "hijo@x.com", "nombre": "Hijo"}, headers=H)
v_hijo = r.get_json()["data"]["id"]
webhook("email.delivered", PREVIOS[-1][1])
miembro = {"nombre": "Hijo", "apellido": "Lopez", "email": "hijo@x.com",
           "telefono": "9999-2222", "dni": "0501-2005-00321", "verificacion_id": v_hijo}
r1 = cli.post(f"/api/v1/unidades/cuentas/{casa_b}/residentes", json=miembro, headers=H)
r2 = cli.post(f"/api/v1/unidades/cuentas/{casa_b}/residentes", json=miembro, headers=H)
ok("agregar miembro verificado -> 201", r1.status_code == 201)
ok("repetirlo con la casa ya en el limite -> 200 'repetido', no 'ya tiene el maximo'",
   r2.status_code == 200 and r2.get_json()["data"].get("repetido") is True)
with app.app_context():
    ok("...un solo miembro creado", Usuario.query.filter_by(email="hijo@x.com").count() == 1)

# ── Dar acceso repetido
_, carla_res, _, carla_id = CASA_C
r = cli.post("/api/v1/correo/verificaciones", json={"email": "carla@x.com", "nombre": "Carla"}, headers=H)
v_carla = r.get_json()["data"]["id"]
webhook("email.delivered", PREVIOS[-1][1])
r1 = cli.post(f"/api/v1/censo/personas/{carla_res}/dar-acceso",
              json=ficha("carla@x.com", verificacion_id=v_carla), headers=H)
r2 = cli.post(f"/api/v1/censo/personas/{carla_res}/dar-acceso",
              json=ficha("carla@x.com", verificacion_id=v_carla), headers=H)
ok("dar acceso verificado -> 200", r1.status_code == 200)
ok("repetirlo -> 200 'repetido', no 'ya tiene acceso al sistema'",
   r2.status_code == 200 and r2.get_json()["data"].get("repetido") is True)

# ── El enlace antes de que exista la cuenta
r = cli.post("/api/v1/correo/verificaciones", json={"email": "nueva@x.com"}, headers=H)
token_sin_cuenta = PREVIOS[-1][2]
r = cli.post("/api/v1/auth/activar", json={"token": token_sin_cuenta, "password": "Clave#2026x"})
ok("abrir el enlace antes de que exista la cuenta -> mensaje claro, no 'no se encontro'",
   codigo(r) == "cuenta_no_lista")

app.config["EXIGIR_VERIFICACION_CORREO"] = False
app.config["RESEND_API_KEY"] = ""

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
