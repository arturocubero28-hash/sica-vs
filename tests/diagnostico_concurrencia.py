#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico de QR-CONC-20 — ver qué está pasando REALMENTE.

La prueba de concurrencia sigue dando 2 aceptadas después de cambiar
Query.get() por filter_by().first(). Eso significa que el diagnóstico
del identity map era incorrecto o incompleto.

Este script consulta la base directamente para responder preguntas
concretas en vez de seguir teorizando:

  1. ¿Cuántos eventos de entrada quedaron para la última visita?
  2. ¿Cuántos workers de Flask hay? (si son procesos separados, cada
     uno tiene su propio pool de conexiones — el candado igual debería
     funcionar, pero conviene saberlo)
  3. ¿Cuál es el nivel de aislamiento de las transacciones?
  4. ¿La tabla tiene algún índice único que debería haber impedido esto?

Uso:
    docker compose cp tests/diagnostico_concurrencia.py backend:/tmp/diag.py
    docker compose exec backend python /tmp/diag.py
"""
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("FLASK_ENV", "development")

from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("=" * 68)
    print("  DIAGNÓSTICO — QR-CONC-20")
    print("=" * 68)

    # ── 1. Nivel de aislamiento ──────────────────────────────────────
    print("\n[1] Nivel de aislamiento de PostgreSQL")
    r = db.session.execute(text("SHOW transaction_isolation")).scalar()
    print(f"    transaction_isolation = {r}")
    print("    (READ COMMITTED es el default y es suficiente para")
    print("     SELECT FOR UPDATE — no es la causa)")

    # ── 2. Las visitas con más de una entrada ────────────────────────
    print("\n[2] Visitas de tipo 'unica' con MÁS DE UNA entrada")
    print("    (si el bloqueo funcionara, esto debería estar vacío)")
    filas = db.session.execute(text("""
        SELECT v.id,
               v.nombre_visitante,
               v.estado,
               COUNT(e.id) AS entradas,
               MIN(e.ocurrido_en) AS primera,
               MAX(e.ocurrido_en) AS ultima,
               EXTRACT(EPOCH FROM (MAX(e.ocurrido_en) - MIN(e.ocurrido_en)))*1000 AS delta_ms
        FROM visitas v
        JOIN eventos_acceso e ON e.visita_id = v.id AND e.direccion = 'entrada'
        WHERE v.tipo = 'unica'
        GROUP BY v.id, v.nombre_visitante, v.estado
        HAVING COUNT(e.id) > 1
        ORDER BY v.id DESC
        LIMIT 10
    """)).fetchall()
    if not filas:
        print("    Ninguna — el bloqueo está funcionando")
    else:
        for f in filas:
            print(f"    visita {f[0]:5d} · {f[3]} entradas · "
                  f"separadas {f[6]:.0f} ms · estado={f[2]}")
            print(f"                 {f[1][:45]}")

    # ── 3. Contador de usos del QR ───────────────────────────────────
    print("\n[3] Códigos QR con usos > 1 en visitas únicas")
    filas = db.session.execute(text("""
        SELECT q.id, q.usos, v.estado, v.nombre_visitante
        FROM codigos_qr q
        JOIN visitas v ON v.id = q.visita_id
        WHERE v.tipo = 'unica' AND q.usos > 1
        ORDER BY q.id DESC LIMIT 10
    """)).fetchall()
    if not filas:
        print("    Ninguno")
    else:
        for f in filas:
            print(f"    qr {f[0]:5d} · usos={f[1]} · estado={f[2]} · {f[3][:35]}")

    # ── 4. Restricciones de la tabla de eventos ──────────────────────
    print("\n[4] Índices y restricciones sobre eventos_acceso")
    filas = db.session.execute(text("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'eventos_acceso'
    """)).fetchall()
    for f in filas:
        tipo = "UNIQUE" if "UNIQUE" in f[1].upper() else "índice"
        print(f"    [{tipo}] {f[0]}")
    print("    (una restricción única sobre (visita_id, direccion) haría")
    print("     imposible el doble registro incluso si el candado fallara)")

    # ── 5. Conexiones activas ────────────────────────────────────────
    print("\n[5] Conexiones a la base")
    r = db.session.execute(text("""
        SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()
    """)).scalar()
    print(f"    Conexiones activas: {r}")

    # ── 6. Prueba directa del candado ────────────────────────────────
    print("\n[6] ¿El SELECT ... FOR UPDATE se emite realmente?")
    print("    Ejecutando el mismo patrón del endpoint con eco de SQL…")
    print()

    import logging
    logging.basicConfig()
    log = logging.getLogger("sqlalchemy.engine")
    log.setLevel(logging.INFO)

    from app.models.visita import Visita, CodigoQR

    qr = CodigoQR.query.order_by(CodigoQR.id.desc()).first()
    if qr:
        db.session.rollback()   # empezar limpio
        print("    --- consulta del QR con FOR UPDATE ---")
        qr2 = (CodigoQR.query.filter_by(token=qr.token)
               .with_for_update(of=CodigoQR).first())
        print("\n    --- consulta de la Visita con FOR UPDATE ---")
        v = (Visita.query.filter_by(id=qr2.visita_id)
             .with_for_update(of=Visita).first())
        print(f"\n    Visita cargada: id={v.id} estado={v.estado}")
        db.session.rollback()
    else:
        print("    (no hay códigos QR en la base)")

    print("\n" + "=" * 68)
