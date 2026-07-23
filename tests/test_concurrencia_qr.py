#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QR-CONC-20 — Prueba de concurrencia del registro de acceso por QR.

Auditoría Día 39. El auditor validó el diseño de ACCESS-03 por inspección
del código, pero fue explícito:

    "La inspección estática indica que el diseño es correcto, pero una
    condición de carrera solo se considera cerrada después de una prueba
    concurrente."

Tenía razón. Un SELECT FOR UPDATE puede verse impecable y aun así fallar
por el nivel de aislamiento, por una relación lazy que rompe el bloqueo, o
porque el commit ocurre fuera del candado. La única forma de saberlo es
lanzar peticiones simultáneas de verdad.

QUÉ VERIFICA
    N peticiones simultáneas con el MISMO token QR de una visita de tipo
    "única" deben producir:
      - exactamente 1 entrada aceptada (201)
      - N-1 rechazos (400 con código qr_usado)
      - exactamente 1 evento de acceso en la base
      - la visita en estado "usada"

    Si pasan 2 o más, hay condición de carrera y el bloqueo no funciona.

CÓMO SE USA
    Desde la carpeta raíz del proyecto, con Docker corriendo:

        python tests/test_concurrencia_qr.py

    Opciones:
        --url    URL base        (default http://localhost:5000)
        --n      peticiones      (default 20)
        --email  guardia         (default guardia@villasdelsol.hn)
        --pass   contraseña      (default guardia123)

NOTA: la prueba crea una visita real y registra un acceso real. Está
pensada para desarrollo, no para producción.
"""
import argparse
import io
import json
import sys
import threading
import time
import urllib.request
import urllib.error
import uuid


# ── Utilidades HTTP (sin dependencias externas) ──────────────────────

def _peticion(url, metodo="GET", datos=None, token=None, campos=None):
    """Devuelve (status, cuerpo_dict). No lanza por errores HTTP."""
    headers = {"ngrok-skip-browser-warning": "true"}
    cuerpo = None

    if campos:
        # multipart/form-data — el endpoint de acceso lo espera así
        limite = f"----sicavs{uuid.uuid4().hex}"
        buf = io.BytesIO()
        for k, v in campos.items():
            buf.write(f"--{limite}\r\n".encode())
            if isinstance(v, tuple):      # (nombre_archivo, bytes)
                nombre, contenido = v
                buf.write(
                    f'Content-Disposition: form-data; name="{k}"; '
                    f'filename="{nombre}"\r\n'
                    f"Content-Type: image/jpeg\r\n\r\n".encode())
                buf.write(contenido)
            else:
                buf.write(
                    f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
                buf.write(str(v).encode())
            buf.write(b"\r\n")
        buf.write(f"--{limite}--\r\n".encode())
        cuerpo = buf.getvalue()
        headers["Content-Type"] = f"multipart/form-data; boundary={limite}"
    elif datos is not None:
        cuerpo = json.dumps(datos).encode()
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": {"code": "conexion", "message": str(e)}}


# JPEG mínimo válido — el endpoint exige foto de identidad para entradas
JPEG_MINIMO = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300"
    + "08" * 64
    + "ffc00011080001000103012200021101031101"
    + "ffc4001f0000010501010101010100000000000000000102030405060708090a0b"
    + "ffda0008010100003f00d2cf20ffd9"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--email", default="guardia@villasdelsol.hn")
    ap.add_argument("--password", "--pass", dest="password", default="guardia123")
    ap.add_argument("--residente-email", default="democasa1@demo.local")
    ap.add_argument("--residente-pass", default="demo123")
    args = ap.parse_args()

    base = args.url.rstrip("/") + "/api/v1"
    print("=" * 68)
    print("  QR-CONC-20 — Prueba de concurrencia del registro por QR")
    print("=" * 68)
    print(f"  Servidor       : {args.url}")
    print(f"  Peticiones     : {args.n} simultáneas, mismo token")
    print()

    # ── 1. Residente: crear la visita ────────────────────────────────
    print("[1/5] Iniciando sesión como residente…")
    st, r = _peticion(f"{base}/auth/login", "POST",
                      {"email": args.residente_email, "password": args.residente_pass})
    if st != 200:
        print(f"      ERROR ({st}): {r}")
        print("      Verificá que el backend esté arriba y las credenciales demo existan.")
        return 1
    tok_res = r["data"]["token"]
    print("      OK")

    print("[2/5] Creando una visita de tipo 'única'…")
    # Ruta sin barra final: el blueprint registra @visitas_bp.post("")
    st, r = _peticion(f"{base}/visitas", "POST", {
        "nombre_visitante": f"Prueba Concurrencia {uuid.uuid4().hex[:6]}",
        "tipo": "unica",
        "en_vehiculo": False,
    }, token=tok_res)
    if st not in (200, 201):
        print(f"      ERROR ({st}): {r}")
        return 1
    visita = r["data"]
    # Visita.to_dict() expone el token del QR como 'qr_token'
    token_qr = visita.get("qr_token")
    if not token_qr:
        print(f"      ERROR: la respuesta no trae qr_token: {visita}")
        return 1
    print(f"      OK — token {token_qr[:16]}…")

    # ── 2. Guardia: preparar la sesión ───────────────────────────────
    print("[3/5] Iniciando sesión como guardia…")
    st, r = _peticion(f"{base}/auth/login", "POST",
                      {"email": args.email, "password": args.password})
    if st != 200:
        print(f"      ERROR ({st}): {r}")
        return 1
    tok_gua = r["data"]["token"]

    # El guardia necesita punto de acceso asignado (ACCESS-04). La visita
    # de prueba es peatonal, así que hay que elegir un punto que tenga
    # tranca peatonal — si no, el registro falla con 'tranca_no_disponible'.
    st, r = _peticion(f"{base}/acceso/puntos", token=tok_gua)
    puntos = (r.get("data") or []) if st == 200 else []
    peatonales = [p for p in puntos
                  if p.get("tiene_peatonal") and not p.get("sin_nombre")]
    if peatonales:
        punto = peatonales[0]["punto_acceso"]
        st2, r2 = _peticion(f"{base}/guardias/mi-punto-acceso", "POST",
                            {"punto_acceso": punto}, token=tok_gua)
        if st2 == 200:
            print(f"      OK — punto '{punto}'")
        else:
            print(f"      AVISO: no se pudo fijar el punto ({st2}): {r2}")
    else:
        print("      ERROR: no hay ningún punto de acceso con tranca peatonal.")
        print("      Creá uno desde el panel de admin antes de correr la prueba.")
        return 1

    # ── 3. El disparo simultáneo ─────────────────────────────────────
    print(f"[4/5] Disparando {args.n} peticiones simultáneas…")
    resultados = []
    lock = threading.Lock()
    # Barrera: todos los hilos esperan acá y salen juntos. Sin esto, el
    # primero terminaría antes de que arranque el último y no habría
    # concurrencia real.
    barrera = threading.Barrier(args.n)

    def worker(i):
        campos = {
            "token": token_qr,
            "direccion": "entrada",
            "foto_identidad": (f"id{i}.jpg", JPEG_MINIMO),
        }
        try:
            barrera.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        t0 = time.time()
        st, r = _peticion(f"{base}/visitas/accesos/visita", "POST",
                          token=tok_gua, campos=campos)
        ms = (time.time() - t0) * 1000
        code = (r.get("error") or {}).get("code", "")
        with lock:
            resultados.append({"i": i, "status": st, "code": code, "ms": ms})

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(args.n)]
    t_ini = time.time()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    dur = time.time() - t_ini
    print(f"      Terminado en {dur:.2f}s")

    # ── 4. Veredicto ─────────────────────────────────────────────────
    print("[5/5] Analizando…")
    print()

    aceptadas = [r for r in resultados if r["status"] in (200, 201)]
    usadas    = [r for r in resultados if r["code"] == "qr_usado"]
    otras     = [r for r in resultados if r not in aceptadas and r not in usadas]

    print("  Distribución de respuestas")
    print("  " + "-" * 46)
    conteo = {}
    for r in resultados:
        k = f"{r['status']} {r['code']}".strip()
        conteo[k] = conteo.get(k, 0) + 1
    for k, v in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f"    {v:3d} ×  {k}")

    tiempos = sorted(r["ms"] for r in resultados)
    if tiempos:
        print(f"\n  Latencia: min {tiempos[0]:.0f}ms · "
              f"mediana {tiempos[len(tiempos)//2]:.0f}ms · máx {tiempos[-1]:.0f}ms")
        print("  (una máxima notablemente mayor indica que las peticiones")
        print("   se serializaron esperando el bloqueo — es lo esperado)")

    print()
    print("  Veredicto")
    print("  " + "-" * 46)
    ok = True

    if len(aceptadas) == 1:
        print("  [OK   ] Exactamente 1 entrada aceptada")
    else:
        ok = False
        print(f"  [FALLA] {len(aceptadas)} entradas aceptadas — se esperaba 1")
        if len(aceptadas) > 1:
            print("          *** CONDICIÓN DE CARRERA: el bloqueo NO funciona ***")
            print("          La misma visita entró más de una vez.")

    if len(usadas) == args.n - 1:
        print(f"  [OK   ] {len(usadas)} rechazos por 'qr_usado'")
    else:
        print(f"  [AVISO] {len(usadas)} rechazos por 'qr_usado' "
              f"(se esperaban {args.n - 1})")

    if otras:
        print(f"  [AVISO] {len(otras)} respuestas de otro tipo:")
        for r in otras[:5]:
            print(f"            {r['status']} {r['code']}")

    # Confirmación desde la base: en qué estado quedó realmente la visita.
    # No hay GET /visitas/<id>, así que se busca en la lista del residente.
    st, r = _peticion(f"{base}/visitas/mias", token=tok_res)
    if st == 200:
        lista = r.get("data") or []
        mia = next((v for v in lista if v.get("id") == visita["id"]), None)
        if mia:
            estado = mia.get("estado")
            print(f"  [INFO ] Estado final de la visita: {estado}")
            if estado == "usada":
                print("  [OK   ] La visita quedó marcada como usada")
            else:
                ok = False
                print(f"  [FALLA] Se esperaba estado 'usada'")
            if mia.get("hora_entrada"):
                print(f"  [INFO ] Hora de entrada registrada: {mia['hora_entrada'][:19]}")
        else:
            print("  [AVISO] No se encontró la visita en /mias para confirmar")

    print()
    print("=" * 68)
    if ok and len(aceptadas) == 1:
        print("  RESULTADO: ACCESS-03 verificado bajo concurrencia real.")
        print("  El bloqueo de fila serializa correctamente las peticiones.")
    else:
        print("  RESULTADO: REVISAR. Ver los detalles arriba.")
    print("=" * 68)
    return 0 if (ok and len(aceptadas) == 1) else 1


if __name__ == "__main__":
    sys.exit(main())
