"""
Día 73 — ¿de quién es la cuenta de Resend?

EL PROBLEMA: el sistema manda correos con una RESEND_API_KEY que está en
el .env del servidor y funciona perfecto, pero nadie se acuerda con qué
correo se registró esa cuenta, así que no hay forma de entrar al panel —
y sin panel no se puede crear el webhook de rebotes.

LA IDEA: la llave no dice de quién es la cuenta, pero sí deja consultar
todo lo que la cuenta hizo. Y entre lo que hizo está el primer correo de
prueba que se mandó el día que se configuró esto (Día 61, 17 de agosto),
que casi con seguridad fue a una dirección propia.

Este script consulta:

  1. Los dominios      -> cuándo se creó la cuenta, qué dominio verificó.
  2. Las llaves de API -> qué nombres se les puso y cuándo.
  3. Los webhooks      -> por si ya había uno configurado.
  4. Los correos enviados, del más viejo al más nuevo, marcando cuáles
     NO corresponden a ningún usuario del sistema. Esos son los
     candidatos: direcciones personales usadas para probar.

NO imprime la llave ni ningún secreto. Las direcciones de los residentes
se cuentan pero no se listan: no hacen falta para esto.

USO (en el servidor, desde /opt/sicavs):

    docker compose -f docker-compose.prod.yml exec backend \\
        python3 herramientas/pistas_cuenta_resend.py
"""
import os
import sys
import datetime as dt

# Python pone en sys.path la carpeta DEL SCRIPT (herramientas/), no la del
# proyecto, así que sin esto el "from app import create_app" de más abajo
# falla con "No module named 'app'" y se pierde el descarte de residentes,
# que es justo lo que hace útil la lista.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("Falta la librería requests. Corré esto DENTRO del contenedor backend.")
    sys.exit(1)

API = "https://api.resend.com"
CLAVE = os.environ.get("RESEND_API_KEY", "").strip()


def _cabeceras():
    return {"Authorization": f"Bearer {CLAVE}"}


def _get(ruta, **params):
    """Devuelve (json, error). No levanta excepciones: queremos seguir."""
    try:
        r = requests.get(f"{API}{ruta}", headers=_cabeceras(), params=params, timeout=20)
    except Exception as e:
        return None, f"no se pudo conectar: {e}"
    if r.status_code == 401:
        return None, "401 — la llave no es válida (¿la cuenta fue borrada?)"
    if r.status_code == 403:
        return None, "403 — la llave no tiene permiso para esto (es de solo envío)"
    if r.status_code == 404:
        return None, "404 — este endpoint no existe en el plan de la cuenta"
    if not r.ok:
        return None, f"{r.status_code} — {r.text[:200]}"
    try:
        return r.json(), None
    except Exception:
        return None, "la respuesta no era JSON"


def _fecha(valor):
    if not valor:
        return "—"
    try:
        return dt.datetime.fromisoformat(valor.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(valor)[:16]


def _titulo(texto):
    print(f"\n{texto}")
    print("─" * len(texto))


def correos_del_sistema():
    """Direcciones que SÍ son de usuarios nuestros: no son pistas."""
    try:
        from app import create_app
        from app.models.usuario import Usuario
        app = create_app()
        with app.app_context():
            return {(u.email or "").lower() for u in Usuario.query.all() if u.email}
    except Exception as e:
        print(f"  (no se pudo leer la base para descartar residentes: {e})")
        return set()


def main():
    if not CLAVE:
        print("RESEND_API_KEY está vacía en el entorno del contenedor.\n"
              "Revisá /opt/sicavs/.env y que el contenedor se haya recreado después.")
        return 1

    print(f"Consultando Resend con la llave que termina en …{CLAVE[-4:]}")

    # ── 1. Dominios ──────────────────────────────────────────────────────
    _titulo("1. Dominios de la cuenta")
    datos, err = _get("/domains")
    if err:
        print(f"  {err}")
    else:
        dominios = datos.get("data") or []
        if not dominios:
            print("  La cuenta no tiene ningún dominio.")
        for d in dominios:
            print(f"  · {d.get('name')}  [{d.get('status')}]  "
                  f"región {d.get('region')}  creado {_fecha(d.get('created_at'))}")
        print("\n  La fecha de creación dice qué día se armó la cuenta:")
        print("  buscá en tu correo de ESE día un mensaje de Resend.")

    # ── 2. Llaves de API ─────────────────────────────────────────────────
    _titulo("2. Llaves de API")
    datos, err = _get("/api-keys")
    if err:
        print(f"  {err}")
        print("  (si dice 403, la llave es de solo envío: no puede crear el webhook)")
    else:
        for k in (datos.get("data") or []):
            print(f"  · «{k.get('name')}»  creada {_fecha(k.get('created_at'))}")

    # ── 3. Webhooks ──────────────────────────────────────────────────────
    _titulo("3. Webhooks configurados")
    datos, err = _get("/webhooks")
    if err:
        print(f"  {err}")
    else:
        hooks = datos.get("data") or []
        if not hooks:
            print("  Ninguno. Por eso no llegan los avisos de rebote.")
        for h in hooks:
            print(f"  · {h.get('endpoint')}  [{h.get('status')}]  "
                  f"creado {_fecha(h.get('created_at'))}")

    # ── 4. Correos enviados, del más viejo al más nuevo ──────────────────
    _titulo("4. A quién le mandó correos esta cuenta")
    nuestros = correos_del_sistema()
    print(f"  ({len(nuestros)} direcciones de usuarios del sistema se van a descartar)")

    todos = []
    cursor = None
    for _ in range(50):          # tope de seguridad: 50 páginas x 100 = 5000
        params = {"limit": 100}
        if cursor:
            params["after"] = cursor
        datos, err = _get("/emails", **params)
        if err:
            print(f"  {err}")
            break
        lote = datos.get("data") or []
        todos.extend(lote)
        if not datos.get("has_more") or not lote:
            break
        cursor = lote[-1].get("id")

    if not todos:
        print("  No se pudo listar ningún correo.")
    else:
        print(f"  {len(todos)} correos enviados en total.\n")

        # Primera vez que aparece cada destinatario.
        primera_vez = {}
        for e in todos:
            destinos = e.get("to") or []
            if isinstance(destinos, str):
                destinos = [destinos]
            for d in destinos:
                d = (d or "").strip().lower()
                if not d:
                    continue
                cuando = e.get("created_at") or ""
                if d not in primera_vez or cuando < primera_vez[d][0]:
                    primera_vez[d] = (cuando, e.get("subject") or "")

        candidatos = [(c, v) for c, v in primera_vez.items() if c not in nuestros]
        candidatos.sort(key=lambda x: x[1][0])

        if not candidatos:
            print("  Todas las direcciones son de usuarios del sistema.")
            print("  No hay pistas de una dirección personal por acá.")
        else:
            print("  CANDIDATOS — direcciones que NO son de ningún usuario del")
            print("  sistema, ordenadas de la más vieja a la más nueva. Las de")
            print("  arriba son las pruebas del día que se configuró esto:\n")
            for correo, (cuando, asunto) in candidatos[:40]:
                print(f"    {_fecha(cuando)}   {correo}")
                if asunto:
                    print(f"                       «{asunto[:60]}»")

    print("\n" + "─" * 60)
    print("Si ninguno te suena, la última carta es escribirle a Resend")
    print("(support@resend.com) desde cualquier correo tuyo, diciendo que")
    print("perdiste el acceso, con el dominio verificado y los últimos")
    print("cuatro caracteres de la llave. Ellos sí pueden decirte de quién")
    print("es la cuenta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
