"""
Panel del Desarrollador — /api/v1/dev/

Métricas de salud del sistema e información forense.
Acceso exclusivo al rol 'desarrollador'.
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.auditoria import LogAuditoria
from app.models.visita import AccesoFisico, EventoAcceso
from app.models.dispositivo import Dispositivo, generar_token
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
    login_fail_24h = contar(db.session.query(func.count(L.id)).filter(
        L.endpoint.like("%/auth/login"), L.status_code == 401, L.created_at >= hace_24h))
    login_fail_7d = contar(db.session.query(func.count(L.id)).filter(
        L.endpoint.like("%/auth/login"), L.status_code == 401, L.created_at >= hace_7d))

    # ── Bloqueos por rate limit (saturación) ──
    rate_429_24h = contar(db.session.query(func.count(L.id)).filter(
        L.status_code == 429, L.created_at >= hace_24h))
    rate_429_7d = contar(db.session.query(func.count(L.id)).filter(
        L.status_code == 429, L.created_at >= hace_7d))

    # ── Errores de autorización reales (401/403 fuera del login) ──
    # Excluye endpoints que el frontend llama automáticamente (polling, carga inicial)
    # cuyos 401 son por sesión expirada, no ataques.
    ENDPOINTS_POLLING = ["%/auth/me", "%/cuotas/pendientes/count",
                         "%/auth/logout", "%/auth/logout%"]
    filtro_polling = [~L.endpoint.like(ep) for ep in ENDPOINTS_POLLING]
    authz_24h = contar(db.session.query(func.count(L.id)).filter(
        L.status_code.in_([401, 403]),
        ~L.endpoint.like("%/auth/login"),
        *filtro_polling,
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


# ───────────────────────────────────────────────────────────────────
# Configuración de hardware de las trancas (relay/GPIO)
# Sensible: solo el rol 'desarrollador' puede ver y cambiar esto, ya que
# un valor mal puesto puede dejar una tranca sin abrir o accionando de más.
# ───────────────────────────────────────────────────────────────────

@dev_bp.get("/accesos-fisicos")
@roles_required("desarrollador")
def listar_accesos_fisicos(usuario_actual):
    """Lista los accesos físicos con su configuración de relay y pulso."""
    accesos = AccesoFisico.query.order_by(AccesoFisico.id).all()
    return jsonify({"data": [a.to_dict() for a in accesos]})


@dev_bp.put("/accesos-fisicos/<int:acceso_id>")
@roles_required("desarrollador")
def configurar_acceso_fisico(usuario_actual, acceso_id):
    """Actualiza el relay_pin y/o pulso_ms de un acceso físico."""
    acceso = AccesoFisico.query.get(acceso_id)
    if not acceso:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Acceso físico no encontrado"}}), 404

    body = request.get_json(silent=True) or {}

    # Datos del acceso (nombre, tipo, activo)
    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if not nombre:
            return jsonify({"error": {"code": "nombre_requerido",
                                      "message": "El nombre no puede estar vacío"}}), 400
        if len(nombre) > 80:
            return jsonify({"error": {"code": "nombre_largo",
                                      "message": "El nombre no puede superar 80 caracteres"}}), 400
        acceso.nombre = nombre

    if "tipo" in body:
        tipo = (body["tipo"] or "").strip().lower()
        if tipo not in ("vehicular", "peatonal"):
            return jsonify({"error": {"code": "tipo_invalido",
                                      "message": "El tipo debe ser 'vehicular' o 'peatonal'"}}), 400
        acceso.tipo = tipo

    if "activo" in body:
        acceso.activo = bool(body["activo"])

    if "punto_acceso" in body:
        punto = (body["punto_acceso"] or "").strip()
        acceso.punto_acceso = punto or None

    if "direccion" in body:
        direccion = (body["direccion"] or "").strip().lower()
        if direccion not in ("entrada", "salida"):
            return jsonify({"error": {"code": "direccion_invalida",
                                      "message": "La dirección debe ser 'entrada' o 'salida'"}}), 400
        acceso.direccion = direccion

    # relay_pin: entero en rango de GPIO de Raspberry Pi (0–40), o null para desconfigurar.
    if "relay_pin" in body:
        pin = body["relay_pin"]
        if pin is None or pin == "":
            acceso.relay_pin = None
        else:
            try:
                pin = int(pin)
            except (TypeError, ValueError):
                return jsonify({"error": {"code": "pin_invalido",
                                          "message": "El pin debe ser un número entero"}}), 400
            if pin < 0 or pin > 40:
                return jsonify({"error": {"code": "pin_fuera_rango",
                                          "message": "El pin GPIO debe estar entre 0 y 40"}}), 400
            acceso.relay_pin = pin

    # pulso_ms: entero positivo en rango sensato (100–5000 ms).
    if "pulso_ms" in body:
        try:
            pulso = int(body["pulso_ms"])
        except (TypeError, ValueError):
            return jsonify({"error": {"code": "pulso_invalido",
                                      "message": "El pulso debe ser un número entero"}}), 400
        if pulso < 100 or pulso > 5000:
            return jsonify({"error": {"code": "pulso_fuera_rango",
                                      "message": "El pulso debe estar entre 100 y 5000 ms"}}), 400
        acceso.pulso_ms = pulso

    db.session.commit()
    return jsonify({"data": acceso.to_dict()})


@dev_bp.post("/accesos-fisicos")
@roles_required("desarrollador")
def crear_acceso_fisico(usuario_actual):
    """Crea un nuevo acceso físico (tranca o torniquete)."""
    body = request.get_json(silent=True) or {}
    nombre = (body.get("nombre") or "").strip()
    tipo = (body.get("tipo") or "").strip().lower()

    if not nombre:
        return jsonify({"error": {"code": "nombre_requerido",
                                  "message": "El nombre es obligatorio"}}), 400
    if len(nombre) > 80:
        return jsonify({"error": {"code": "nombre_largo",
                                  "message": "El nombre no puede superar 80 caracteres"}}), 400
    if tipo not in ("vehicular", "peatonal"):
        return jsonify({"error": {"code": "tipo_invalido",
                                  "message": "El tipo debe ser 'vehicular' o 'peatonal'"}}), 400

    acceso = AccesoFisico(nombre=nombre, tipo=tipo, activo=True, pulso_ms=800,
                          punto_acceso=(body.get("punto_acceso") or "").strip() or None)
    db.session.add(acceso)
    db.session.commit()
    return jsonify({"data": acceso.to_dict()}), 201


@dev_bp.get("/accesos-fisicos/<int:acceso_id>/historial-count")
@roles_required("desarrollador")
def historial_count_acceso(usuario_actual, acceso_id):
    """Devuelve cuántos eventos de acceso tiene un acceso (para avisar antes de borrar)."""
    acceso = AccesoFisico.query.get(acceso_id)
    if not acceso:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Acceso físico no encontrado"}}), 404
    n = EventoAcceso.query.filter_by(acceso_id=acceso_id).count()
    return jsonify({"data": {"eventos": n}})


@dev_bp.delete("/accesos-fisicos/<int:acceso_id>")
@roles_required("desarrollador")
def eliminar_acceso_fisico(usuario_actual, acceso_id):
    """Elimina un acceso físico. Si tiene historial, también borra sus eventos
    (el cliente ya advirtió cuántos son antes de confirmar)."""
    acceso = AccesoFisico.query.get(acceso_id)
    if not acceso:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Acceso físico no encontrado"}}), 404

    eventos = EventoAcceso.query.filter_by(acceso_id=acceso_id).count()
    if eventos:
        EventoAcceso.query.filter_by(acceso_id=acceso_id).delete()
    db.session.delete(acceso)
    db.session.commit()
    return jsonify({"data": {"eliminado": True, "eventos_borrados": eventos}})


# ───────────────────────────────────────────────────────────────────
# Gestión de dispositivos (Raspberry Pi)
# Cada Pi tiene su token individual. El token solo se muestra al crear o al
# regenerar (no en los listados), porque es secreto.
# ───────────────────────────────────────────────────────────────────

@dev_bp.get("/dispositivos")
@roles_required("desarrollador")
def listar_dispositivos(usuario_actual):
    disps = Dispositivo.query.order_by(Dispositivo.id).all()
    return jsonify({"data": [d.to_dict() for d in disps]})


@dev_bp.post("/dispositivos")
@roles_required("desarrollador")
def crear_dispositivo(usuario_actual):
    body = request.get_json(silent=True) or {}
    nombre = (body.get("nombre") or "").strip()
    punto = (body.get("punto_acceso") or "").strip() or None
    tipo = (body.get("tipo") or "acceso").strip()
    if tipo not in ("acceso", "camara"):
        tipo = "acceso"
    if not nombre:
        return jsonify({"error": {"code": "nombre_requerido",
                                  "message": "El nombre es obligatorio"}}), 400
    disp = Dispositivo(nombre=nombre, tipo=tipo, punto_acceso=punto,
                        token=generar_token(), activo=True)
    db.session.add(disp)
    db.session.commit()
    # Al crear, se devuelve el token UNA vez (anótalo, no se vuelve a mostrar)
    return jsonify({"data": disp.to_dict(incluir_token=True)}), 201


@dev_bp.put("/dispositivos/<uuid:disp_uuid>")
@roles_required("desarrollador")
def actualizar_dispositivo(usuario_actual, disp_uuid):
    disp = Dispositivo.query.filter_by(uuid_publico=disp_uuid).first()
    if not disp:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Dispositivo no encontrado"}}), 404
    body = request.get_json(silent=True) or {}
    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if not nombre:
            return jsonify({"error": {"code": "nombre_requerido",
                                      "message": "El nombre no puede estar vacío"}}), 400
        disp.nombre = nombre
    if "punto_acceso" in body:
        disp.punto_acceso = (body["punto_acceso"] or "").strip() or None
    if "activo" in body:
        disp.activo = bool(body["activo"])
    db.session.commit()
    return jsonify({"data": disp.to_dict()})


@dev_bp.post("/dispositivos/<uuid:disp_uuid>/regenerar-token")
@roles_required("desarrollador")
def regenerar_token_dispositivo(usuario_actual, disp_uuid):
    """Genera un token nuevo (el anterior deja de servir). Se muestra una vez."""
    disp = Dispositivo.query.filter_by(uuid_publico=disp_uuid).first()
    if not disp:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Dispositivo no encontrado"}}), 404
    disp.token = generar_token()
    db.session.commit()
    return jsonify({"data": disp.to_dict(incluir_token=True)})


@dev_bp.delete("/dispositivos/<uuid:disp_uuid>")
@roles_required("desarrollador")
def eliminar_dispositivo(usuario_actual, disp_uuid):
    disp = Dispositivo.query.filter_by(uuid_publico=disp_uuid).first()
    if not disp:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Dispositivo no encontrado"}}), 404
    db.session.delete(disp)
    db.session.commit()
    return jsonify({"data": {"eliminado": True}})
