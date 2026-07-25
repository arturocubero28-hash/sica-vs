#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O3.1 — Prueba de concurrencia del cobro de cuota en caja.

Auditoría Día 42. El hallazgo: registrar_pago (caja.py) leía el estado de
la cuota y creaba el Pago SIN bloqueo de fila. Dos peticiones simultáneas
(doble-clic del cajero, o dos cajeros) podían cobrar DOS VECES la misma
cuota. Es el mismo patrón que QR-CONC-20, pero con dinero.

El fix (Día 44) agregó with_for_update() sobre la cuota. Esta prueba lo
verifica de la única forma confiable: lanzando cobros SIMULTÁNEOS reales y
contando en la base cuántos Pago se crearon.

QUÉ VERIFICA
    N peticiones simultáneas cobrando la MISMA cuota deben producir:
      - exactamente 1 pago aprobado (201)
      - N-1 rechazos (400 'ya_pagada')
      - exactamente 1 fila Pago para esa cuota en la base
      - la cuota en estado 'pagada'

    Si se crean 2+ pagos, el candado no funciona y se cobró de más.

CÓMO SE USA (con Docker corriendo):
    docker compose cp tests/test_concurrencia_cobro.py backend:/tmp/tc.py
    docker compose exec backend python /tmp/tc.py --url http://localhost:5000

La prueba necesita una cuenta con al menos una cuota pendiente. La busca
sola entre las cuentas demo; si no encuentra, lo avisa.
"""
import argparse
import json
import sys
import threading
import time
import urllib.request
import urllib.error


def _peticion(url, metodo="GET", datos=None, token=None):
    headers = {"ngrok-skip-browser-warning": "true"}
    cuerpo = None
    if datos is not None:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--email", default="", help="cajero/admin; si se omite prueba admin")
    ap.add_argument("--password", "--pass", dest="password", default="")
    ap.add_argument("--cuota-id", default="",
                    help="uuid de una cuota pendiente concreta (evita la búsqueda)")
    args = ap.parse_args()

    base = args.url.rstrip("/") + "/api/v1"
    print("=" * 68)
    print("  O3.1 — Prueba de concurrencia del cobro de cuota")
    print("=" * 68)
    print(f"  Servidor    : {args.url}")
    print(f"  Peticiones  : {args.n} cobros simultáneos, misma cuota")
    print()

    # ── 1. Login como cajero/admin ───────────────────────────────────
    print("[1/4] Iniciando sesión (cajero/admin)…")
    if args.email:
        intentos = [(args.email, args.password)]
    else:
        intentos = [
            ("admin@villasdelsol.hn", "admin123"),
            ("cajero@villasdelsol.hn", "cajero123"),
            ("caja@villasdelsol.hn", "caja123"),
        ]
    tok = None
    for correo, clave in intentos:
        st, r = _peticion(f"{base}/auth/login", "POST",
                          {"email": correo, "password": clave})
        if st == 200:
            tok = r["data"]["token"]
            print(f"      OK — {correo}")
            break
    if not tok:
        print("      ERROR: no se pudo iniciar sesión. Pasá --email y --pass.")
        return 1

    # ── 2. Abrir caja (si no hay uua abierta) ────────────────────────
    print("[2/4] Verificando caja abierta…")
    st, r = _peticion(f"{base}/caja/estado", token=tok)
    tiene_caja = st == 200 and (r.get("data") or {}).get("sesion")
    if not tiene_caja:
        st, r = _peticion(f"{base}/caja/abrir", "POST", {}, token=tok)
        if st in (200, 201):
            print("      OK — caja abierta")
        else:
            # Puede haber otra caja abierta por otro usuario
            print(f"      AVISO ({st}): {r.get('error', {}).get('message', r)}")
            print("      Si hay otra caja abierta, cerrala o usá ese cajero.")
    else:
        print("      OK — ya había una caja abierta")

    # ── 3. Buscar una cuota pendiente ────────────────────────────────
    print("[3/4] Buscando una cuenta con cuota pendiente…")
    cuota_id = args.cuota_id or None
    if cuota_id:
        print(f"      Usando cuota indicada: {cuota_id[:16]}…")
    # Términos que matchean los identificadores demo reales ("DEMO Casa 5").
    for termino in ([] if cuota_id else ["DEMO Casa", "DEMO", "Casa", "demo"]):
        st, r = _peticion(f"{base}/caja/buscar-cuenta?q={termino}", token=tok)
        if st != 200:
            continue
        for cuenta in (r.get("data") or []):
            cuotas = cuenta.get("cuotas") or []
            if cuotas:
                cuota_id = cuotas[0]["cuota_id"]
                etiqueta = cuenta.get("unidad") or cuenta.get("titular") or "?"
                print(f"      OK — cuota de '{etiqueta}' · L {cuotas[0].get('monto')}")
                break
        if cuota_id:
            break

    if not cuota_id:
        print("      ERROR: no se encontró ninguna cuenta con cuota pendiente.")
        print("      Pasá una cuota directamente con --cuota-id <uuid>.")
        print("      Para obtener una desde la base:")
        print("        docker compose exec db psql -U sicavs -d sicavs -c \\")
        print("          \"SELECT uuid_publico FROM cuotas WHERE estado IN\"")
        print("          \"('pendiente','vencida') LIMIT 1;\"")
        return 1

    # ── 4. Disparar N cobros simultáneos ─────────────────────────────
    print(f"[4/4] Disparando {args.n} cobros simultáneos de la misma cuota…")
    resultados = []
    lock = threading.Lock()
    barrera = threading.Barrier(args.n)

    def worker():
        try:
            barrera.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        st, r = _peticion(f"{base}/caja/pago", "POST",
                          {"cuota_id": cuota_id, "metodo": "efectivo"}, token=tok)
        code = (r.get("error") or {}).get("code", "")
        with lock:
            resultados.append({"status": st, "code": code})

    hilos = [threading.Thread(target=worker) for _ in range(args.n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)

    # ── Veredicto ────────────────────────────────────────────────────
    print()
    print("  Distribución de respuestas")
    print("  " + "-" * 46)
    conteo = {}
    for x in resultados:
        k = f"{x['status']} {x['code']}".strip()
        conteo[k] = conteo.get(k, 0) + 1
    for k, v in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f"    {v:3d} ×  {k}")

    aprobados = [x for x in resultados if x["status"] == 201]
    yapagada  = [x for x in resultados if x["code"] == "ya_pagada"]

    print()
    print("  Veredicto (la verdad está en la base)")
    print("  " + "-" * 46)
    print(f"  Cobros aceptados (201): {len(aprobados)}")
    print(f"  Rechazos 'ya_pagada':   {len(yapagada)}")
    print()
    print("  VERIFICACIÓN DEFINITIVA — contar pagos en la base:")
    print(f"""    docker compose exec db psql -U sicavs -d sicavs -c \\
      "SELECT COUNT(*) FROM pagos p JOIN cuotas c ON c.id = p.cuota_id \\
       WHERE c.uuid_publico = '{cuota_id}';" """)
    print()
    print("    Debe devolver EXACTAMENTE 1. Si devuelve 2 o más, el candado")
    print("    falló y se cobró la cuota más de una vez.")

    print()
    print("=" * 68)
    if len(aprobados) == 1:
        print("  RESULTADO (HTTP): 1 cobro aceptado, el resto rechazado. Correcto.")
        print("  Confirmá con la consulta SQL que hay 1 solo pago en la base.")
    else:
        print(f"  RESULTADO (HTTP): {len(aprobados)} cobros aceptados. REVISAR con")
        print("  la consulta SQL — si hay 2+ pagos, el candado no funcionó.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
