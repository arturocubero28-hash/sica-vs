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


@dev_bp.get("/metricas-codigo")
@roles_required("desarrollador")
def metricas_codigo(usuario_actual):
    """
    Métricas de software del proyecto, calculadas en vivo:
    - Líneas de código (backend, frontend, CSS)
    - Complejidad ciclomática (McCabe) promedio y distribución
    - Índice de mantenibilidad por módulo
    Usa radon para el análisis del backend Python.
    """
    import os
    import subprocess

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    proyecto = os.path.dirname(base)  # raíz del repo
    backend_app = os.path.join(base, "app")

    resultado = {
        "loc": {},
        "complejidad": {},
        "mantenibilidad": [],
        "resumen": {},
    }

    # ── Líneas de código (conteo simple por extensión) ──
    def contar_lineas(carpeta, exts):
        total, archivos = 0, 0
        for root, _, files in os.walk(carpeta):
            if "node_modules" in root or "__pycache__" in root or ".git" in root:
                continue
            for f in files:
                if any(f.endswith(e) for e in exts):
                    try:
                        with open(os.path.join(root, f), encoding="utf-8", errors="ignore") as fh:
                            total += sum(1 for _ in fh)
                        archivos += 1
                    except Exception:
                        pass
        return total, archivos

    be_loc, be_files = contar_lineas(backend_app, [".py"])
    fe_dir = "/frontend/src"
    if not os.path.isdir(fe_dir):
        # fallback para desarrollo local fuera de Docker
        fe_dir = os.path.join(proyecto, "frontend", "src")
    fe_loc, fe_files = contar_lineas(fe_dir, [".ts", ".tsx"])
    css_loc, _ = contar_lineas(fe_dir, [".css"])
    resultado["loc"] = {
        "backend_python": be_loc, "backend_archivos": be_files,
        "frontend_ts": fe_loc, "frontend_archivos": fe_files,
        "css": css_loc, "total": be_loc + fe_loc + css_loc,
    }

    # ── Complejidad ciclomática + mantenibilidad con radon ──
    radon_disponible = True
    try:
        import json as _json
        # Complejidad ciclomática (JSON)
        cc = subprocess.run(
            ["radon", "cc", backend_app, "-j", "-s"],
            capture_output=True, text=True, timeout=30
        )
        cc_data = _json.loads(cc.stdout) if cc.stdout else {}

        total_bloques, suma_cc = 0, 0
        dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
        mas_complejos = []
        for archivo, bloques in cc_data.items():
            rel = archivo.replace(base + "/", "")
            for b in bloques:
                total_bloques += 1
                suma_cc += b.get("complexity", 0)
                rank = b.get("rank", "A")
                dist[rank] = dist.get(rank, 0) + 1
                mas_complejos.append({
                    "nombre": b.get("name"), "archivo": rel,
                    "complejidad": b.get("complexity"), "rank": rank,
                })
        mas_complejos.sort(key=lambda x: x["complejidad"], reverse=True)
        prom = round(suma_cc / total_bloques, 2) if total_bloques else 0
        resultado["complejidad"] = {
            "promedio": prom,
            "rank_promedio": _rank_cc(prom),
            "total_bloques": total_bloques,
            "distribucion": dist,
            "mas_complejos": mas_complejos[:8],
        }

        # Índice de mantenibilidad (JSON)
        mi = subprocess.run(
            ["radon", "mi", backend_app, "-j"],
            capture_output=True, text=True, timeout=30
        )
        mi_data = _json.loads(mi.stdout) if mi.stdout else {}
        mant = []
        suma_mi = 0
        for archivo, info in mi_data.items():
            rel = archivo.replace(base + "/", "")
            val = info.get("mi", 0) if isinstance(info, dict) else 0
            suma_mi += val
            mant.append({"archivo": rel, "mi": round(val, 1),
                         "rank": info.get("rank", "A") if isinstance(info, dict) else "A"})
        mant.sort(key=lambda x: x["mi"])
        resultado["mantenibilidad"] = mant
        resultado["resumen"]["mi_promedio"] = round(suma_mi / len(mant), 1) if mant else 0
    except (FileNotFoundError, Exception):
        radon_disponible = False

    resultado["radon_disponible"] = radon_disponible
    return jsonify({"data": resultado})


def _rank_cc(valor):
    """Rango de complejidad ciclomática según escala de radon."""
    if valor <= 5:
        return "A"
    elif valor <= 10:
        return "B"
    elif valor <= 20:
        return "C"
    elif valor <= 30:
        return "D"
    elif valor <= 40:
        return "E"
    return "F"


@dev_bp.get("/seguridad")
@roles_required("desarrollador")
def metricas_seguridad(usuario_actual):
    """
    Métricas de intentos de ataque, analizando el log de auditoría:
    - Logins fallidos (401 en /auth/login)
    - Bloqueos por rate limit (429) = intentos de saturación frenados
    - Errores de autorización (401/403 en otras rutas)
    - Top de IPs sospechosas
    - Intentos contra cuentas privilegiadas (admin/desarrollador)
    """
    from sqlalchemy import func
    from app.models.usuario import Usuario

    ahora = dt.datetime.now(dt.timezone.utc)
    hace_24h = ahora - dt.timedelta(hours=24)
    hace_7d = ahora - dt.timedelta(days=7)

    L = LogAuditoria

    def contar(query):
        return query.scalar() or 0

    # ── Logins fallidos ──
    base_login_fail = L.query.filter(L.endpoint.like("%/auth/login"), L.status_code == 401)
    login_fail_24h = contar(db.session.query(func.count(L.id)).filter(
        L.endpoint.like("%/auth/login"), L.status_code == 401, L.created_at >= hace_24h))
    login_fail_7d = contar(db.session.query(func.count(L.id)).filter(
        L.endpoint.like("%/auth/login"), L.status_code == 401, L.created_at >= hace_7d))

    # ── Bloqueos por rate limit (saturación) ──
    rate_429_24h = contar(db.session.query(func.count(L.id)).filter(
        L.status_code == 429, L.created_at >= hace_24h))
    rate_429_7d = contar(db.session.query(func.count(L.id)).filter(
        L.status_code == 429, L.created_at >= hace_7d))

    # ── Errores de autorización (401/403 fuera del login) ──
    # Solo cuenta los que tienen usuario_id o email registrado — es decir, los que
    # llegaron con un token (inválido, revocado o sin permiso). Excluye los 401
    # por ausencia de token (operación normal del frontend al cargar).
    authz_24h = contar(db.session.query(func.count(L.id)).filter(
        L.status_code.in_([401, 403]),
        ~L.endpoint.like("%/auth/login"),
        ~L.endpoint.like("%/auth/me"),       # /me devuelve 401 normal al cargar
        L.created_at >= hace_24h))

    # ── Top IPs con más logins fallidos (7 días) ──
    top_ips = (db.session.query(L.ip, func.count(L.id).label("intentos"))
               .filter(L.endpoint.like("%/auth/login"), L.status_code == 401,
                       L.created_at >= hace_7d, L.ip.isnot(None))
               .group_by(L.ip).order_by(func.count(L.id).desc()).limit(8).all())

    # ── Cuentas privilegiadas con intentos de login fallidos ──
    # emails de admins/desarrolladores
    privilegiados = {u.email for u in Usuario.query.filter(
        Usuario.rol.in_(["admin", "super_admin", "desarrollador"])).all() if u.email}
    intentos_priv = (db.session.query(L.email, func.count(L.id).label("intentos"))
                     .filter(L.endpoint.like("%/auth/login"), L.status_code == 401,
                             L.created_at >= hace_7d, L.email.isnot(None))
                     .group_by(L.email).order_by(func.count(L.id).desc()).limit(20).all())
    ataques_priv = [{"email": e, "intentos": n} for e, n in intentos_priv if e in privilegiados]

    # ── Línea de tiempo: logins fallidos por día (7 días) ──
    timeline = []
    for i in range(6, -1, -1):
        dia = (ahora - dt.timedelta(days=i)).date()
        ini = dt.datetime.combine(dia, dt.time.min).replace(tzinfo=dt.timezone.utc)
        fin = dt.datetime.combine(dia, dt.time.max).replace(tzinfo=dt.timezone.utc)
        n = contar(db.session.query(func.count(L.id)).filter(
            L.endpoint.like("%/auth/login"), L.status_code == 401,
            L.created_at >= ini, L.created_at <= fin))
        timeline.append({"dia": dia.strftime("%d/%m"), "fallidos": n})

    # ── Nivel de alerta general ──
    if login_fail_24h > 50 or rate_429_24h > 20 or len(ataques_priv) > 0:
        nivel = "alto"
    elif login_fail_24h > 15 or rate_429_24h > 5:
        nivel = "medio"
    else:
        nivel = "bajo"

    return jsonify({"data": {
        "nivel_alerta": nivel,
        "login_fallidos_24h": login_fail_24h,
        "login_fallidos_7d": login_fail_7d,
        "bloqueos_saturacion_24h": rate_429_24h,
        "bloqueos_saturacion_7d": rate_429_7d,
        "errores_autorizacion_24h": authz_24h,
        "top_ips": [{"ip": ip, "intentos": n} for ip, n in top_ips],
        "ataques_privilegiados": ataques_priv,
        "timeline_7d": timeline,
    }})
