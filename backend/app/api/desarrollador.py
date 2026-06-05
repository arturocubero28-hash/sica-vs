"""
Panel del Desarrollador — /api/v1/dev/

Métricas de salud del sistema e información forense.
Acceso exclusivo al rol 'desarrollador'.
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.auditoria import LogAuditoria
from app.auth.security import roles_required

dev_bp = Blueprint("desarrollador", __name__)


@dev_bp.get("/metricas")
@roles_required("desarrollador")
def metricas(usuario_actual):
    """Salud del sistema: disco, RAM, CPU, estado BD y servicios."""
    ahora = dt.datetime.now(dt.timezone.utc)

    # Recursos del sistema con psutil
    sistema = {}
    try:
        import psutil

        disco = psutil.disk_usage("/")
        ram   = psutil.virtual_memory()
        cpu   = psutil.cpu_percent(interval=0.5)

        sistema = {
            "disco": {
                "total_gb":  round(disco.total / 1e9, 1),
                "usado_gb":  round(disco.used  / 1e9, 1),
                "libre_gb":  round(disco.free  / 1e9, 1),
                "porcentaje": disco.percent,
            },
            "ram": {
                "total_gb":  round(ram.total     / 1e9, 1),
                "usado_gb":  round(ram.used       / 1e9, 1),
                "libre_gb":  round(ram.available  / 1e9, 1),
                "porcentaje": ram.percent,
            },
            "cpu_porcentaje": cpu,
        }
    except ImportError:
        sistema = {"error": "psutil no instalado — corré docker compose up --build"}
    except Exception as e:
        sistema = {"error": str(e)}

    # Estado de la base de datos
    db_ok = True
    db_latencia_ms = None
    db_error = None
    try:
        from sqlalchemy import text
        import time
        t0 = time.monotonic()
        db.session.execute(text("SELECT 1"))
        db_latencia_ms = round((time.monotonic() - t0) * 1000, 2)
    except Exception as e:
        db_ok = False
        db_error = str(e)

    # Estado de Redis
    redis_ok = True
    redis_error = None
    try:
        import redis as redis_lib
        import os
        r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
        r.ping()
    except Exception as e:
        redis_ok = False
        redis_error = str(e)

    # Errores recientes (status 5xx en el log de auditoría)
    errores_recientes = LogAuditoria.query.filter(
        LogAuditoria.status_code >= 500
    ).order_by(LogAuditoria.created_at.desc()).limit(5).all()

    return jsonify({"data": {
        "timestamp": ahora.isoformat(),
        "estado_general": "operativo" if db_ok else "degradado",
        "db_conectada": db_ok,
        "db_latencia_ms": db_latencia_ms,
        "db_error": db_error,
        "redis": {
            "conectado": redis_ok,
            "error": redis_error,
        },
        "sistema": sistema,
        "errores_recientes": [e.to_dict() for e in errores_recientes],
    }})


@dev_bp.get("/logs")
@roles_required("desarrollador")
def logs(usuario_actual):
    """
    Logs de auditoría forense: quién se conectó, a qué hora, desde qué IP,
    qué endpoint llamó y con qué resultado. Útil para forensia e investigación.
    """
    # Filtros opcionales
    email_q   = (request.args.get("email") or "").strip().lower()
    endpoint_q = (request.args.get("endpoint") or "").strip().lower()
    solo_errores = request.args.get("errores") == "1"
    pagina   = max(1, int(request.args.get("pagina", 1)))
    por_pagina = 50

    q = LogAuditoria.query
    if email_q:
        q = q.filter(LogAuditoria.email.ilike(f"%{email_q}%"))
    if endpoint_q:
        q = q.filter(LogAuditoria.endpoint.ilike(f"%{endpoint_q}%"))
    if solo_errores:
        q = q.filter(LogAuditoria.status_code >= 400)

    total = q.count()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    items = q.order_by(LogAuditoria.created_at.desc()) \
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return jsonify({"data": {
        "logs": [l.to_dict() for l in items],
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total": total,
    }})
