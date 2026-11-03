"""Dia 72: los correos ya no dicen SICA-VS y nombran a la residencial."""
import os, sys, logging
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, ".")
logging.disable(logging.WARNING)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import BigInteger
@compiles(BigInteger, "sqlite")
def _b(t, c, **k): return "INTEGER"
from app import create_app
from app.services import correo

fallos = []
def ok(d, c):
    print(f"  [{'OK  ' if c else 'FALLA'}] {d}")
    if not c: fallos.append(d)

enviados = []
correo._enviar = lambda dest, asunto, html: enviados.append((dest, asunto, html)) or True

app = create_app()
with app.app_context():
    RES = "Residencial Villas del Sol"
    correo.enviar_correo_activacion("r@x.com", "Rosa", "tok123", RES)
    correo.enviar_correo_reset("r@x.com", "tok456", RES)

    act_asunto, act_html = enviados[0][1], enviados[0][2]
    res_asunto, res_html = enviados[1][1], enviados[1][2]

    print("\nNinguno menciona el nombre interno")
    ok("el correo de activacion no dice SICA", "SICA" not in act_html and "SICA" not in act_asunto)
    ok("el correo de reset no dice SICA", "SICA" not in res_html and "SICA" not in res_asunto)

    print("\nCada uno nombra a la residencial")
    ok("el encabezado de activacion muestra la residencial", f">{RES}<" in act_html)
    ok("el encabezado de reset muestra la residencial", f">{RES}<" in res_html)
    ok("el asunto de reset nombra la residencial", res_asunto == f"Restablecer tu contraseña — {RES}")
    ok("el asunto de activacion nombra la residencial", act_asunto == f"Activá tu cuenta — {RES}")
    ok("el cuerpo del reset nombra la residencial", f"<b>{RES}</b>" in res_html)

    print("\nLo que ya funcionaba sigue igual")
    ok("activacion saluda por nombre", "Hola Rosa," in act_html)
    ok("activacion lleva el enlace con su token", "?activar=tok123" in act_html)
    ok("reset lleva el enlace con su token", "?reset=tok456" in res_html)
    ok("activacion ofrece la descarga de Android", "Descargar para Android" in act_html)
    ok("el remitente ya no dice SICA", "SICA" not in app.config["RESEND_FROM"])
    ok("el remitente nombra la residencial", app.config["RESEND_FROM"].startswith(RES))
    ok("el nombre que ve la huella en el navegador ya no dice SICA",
       "SICA" not in app.config["WEBAUTHN_RP_NAME"])

print(f"\n{'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
sys.exit(1 if fallos else 0)
