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
from app.models.dispositivo import Dispositivo, generar_token, hash_token
from app.models.residencial import Residencial
from app.models.plan import Plan
from app.models.suscripcion_pago import SuscripcionPago
from app.models.usuario import Usuario
from app.auth.security import roles_required
from app.utils.passwords import generar_password_temporal

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
    # Día 48: filtro por residencial, a pedido del usuario. Se resuelve por
    # uuid_publico (nunca se expone el id interno) y se aplica uniendo con
    # Usuario -> residencial_id, ya que LogAuditoria no guarda una columna
    # propia (ver comentario en el modelo, to_dict()).
    residencial_uuid = (request.args.get("residencial_id") or "").strip()
    pagina   = max(1, int(request.args.get("pagina", 1)))
    por_pagina = 50

    q = LogAuditoria.query
    if email_q:
        q = q.filter(LogAuditoria.email.ilike(f"%{email_q}%"))
    if endpoint_q:
        q = q.filter(LogAuditoria.endpoint.ilike(f"%{endpoint_q}%"))
    if solo_errores:
        q = q.filter(LogAuditoria.status_code >= 400)
    if residencial_uuid:
        from app.models.residencial import Residencial
        from app.models.usuario import Usuario
        r = Residencial.query.filter_by(uuid_publico=residencial_uuid).first()
        if not r:
            return jsonify({"error": {"code": "residencial_no_encontrada",
                                      "message": "No se encontró esa residencial"}}), 404
        q = q.join(Usuario, LogAuditoria.usuario_id == Usuario.id) \
             .filter(Usuario.residencial_id == r.id)

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

    # Bases multi-residencial (Día 37): asignar/reasignar/desasignar esta
    # tranca a una residencial. residencial_id: null o "" desasigna.
    if "residencial_id" in body:
        residencial_uuid = body.get("residencial_id")
        if not residencial_uuid:
            acceso.residencial_id = None
        else:
            r = Residencial.query.filter_by(uuid_publico=residencial_uuid).first()
            if not r:
                return jsonify({"error": {"code": "residencial_no_encontrada",
                                          "message": "La residencial indicada no existe"}}), 404
            acceso.residencial_id = r.id

    # Día 49 — modo_control: 'gpio' (económico, Wiegand+relay directo a la
    # Pi) o 'modbus' (premium, Cidron por OSDP + relay externo). Se valida
    # ANTES que los campos de cada modo, para poder dar un mensaje de error
    # más útil si alguien manda campos de un modo con otro modo activo.
    if "modo_control" in body:
        modo = (body["modo_control"] or "").strip().lower()
        if modo not in ("gpio", "modbus"):
            return jsonify({"error": {"code": "modo_control_invalido",
                                      "message": "El modo debe ser 'gpio' o 'modbus'"}}), 400
        acceso.modo_control = modo

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

    # Modo 'gpio' — pines de datos del lector Wiegand (D0/D1). Mismo rango
    # y mismo criterio de validación que relay_pin, ya que es el mismo tipo
    # de recurso físico (un pin GPIO de la Pi).
    for campo in ("wiegand_d0_pin", "wiegand_d1_pin"):
        if campo in body:
            valor = body[campo]
            if valor is None or valor == "":
                setattr(acceso, campo, None)
            else:
                try:
                    valor = int(valor)
                except (TypeError, ValueError):
                    return jsonify({"error": {"code": "pin_invalido",
                                              "message": f"{campo} debe ser un número entero"}}), 400
                if valor < 0 or valor > 40:
                    return jsonify({"error": {"code": "pin_fuera_rango",
                                              "message": f"{campo} debe estar entre 0 y 40"}}), 400
                setattr(acceso, campo, valor)

    # Modo 'modbus' — canal del relay externo (1 a 4, la placa Waveshare del
    # Día 48 trae exactamente 4 canales).
    if "relay_canal" in body:
        canal = body["relay_canal"]
        if canal is None or canal == "":
            acceso.relay_canal = None
        else:
            try:
                canal = int(canal)
            except (TypeError, ValueError):
                return jsonify({"error": {"code": "canal_invalido",
                                          "message": "El canal debe ser un número entero"}}), 400
            if canal < 1 or canal > 4:
                return jsonify({"error": {"code": "canal_fuera_rango",
                                          "message": "El canal del relay debe estar entre 1 y 4"}}), 400
            acceso.relay_canal = canal

    # Modo 'modbus' — dirección OSDP del lector Cidron asignado a esta
    # tranca. El protocolo OSDP permite direcciones de 0 a 126; no se acota
    # a 1-3 (lo típico en un punto de 3 trancas) porque un punto futuro
    # podría tener más lectores en su bus.
    if "lector_direccion_osdp" in body:
        direccion_osdp = body["lector_direccion_osdp"]
        if direccion_osdp is None or direccion_osdp == "":
            acceso.lector_direccion_osdp = None
        else:
            try:
                direccion_osdp = int(direccion_osdp)
            except (TypeError, ValueError):
                return jsonify({"error": {"code": "direccion_osdp_invalida",
                                          "message": "La dirección OSDP debe ser un número entero"}}), 400
            if direccion_osdp < 0 or direccion_osdp > 126:
                return jsonify({"error": {"code": "direccion_osdp_fuera_rango",
                                          "message": "La dirección OSDP debe estar entre 0 y 126"}}), 400
            acceso.lector_direccion_osdp = direccion_osdp

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

    # Bases multi-residencial (Día 37): opcionalmente asignada al crear.
    residencial_id = None
    residencial_uuid = body.get("residencial_id")
    if residencial_uuid:
        r = Residencial.query.filter_by(uuid_publico=residencial_uuid).first()
        if not r:
            return jsonify({"error": {"code": "residencial_no_encontrada",
                                      "message": "La residencial indicada no existe"}}), 404
        residencial_id = r.id

    acceso = AccesoFisico(nombre=nombre, tipo=tipo, activo=True, pulso_ms=800,
                          punto_acceso=(body.get("punto_acceso") or "").strip() or None,
                          residencial_id=residencial_id)
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
    # Día 46: 'lector_ct9' se suma como tercer tipo de controlador de acceso,
    # junto a la Raspberry Pi ('acceso'). Registrar el hardware (nombre, punto,
    # token, residencial) ya funciona igual para los tres tipos — lo que aún
    # NO existe es el adaptador que traduce el protocolo HTTP propio del CT9;
    # eso llega con el SDK de Civintec. Por ahora el CT9 se puede dar de alta
    # mostrando ese estado, sin prometer que ya sincroniza.
    if tipo not in ("acceso", "camara", "lector_ct9"):
        tipo = "acceso"
    if not nombre:
        return jsonify({"error": {"code": "nombre_requerido",
                                  "message": "El nombre es obligatorio"}}), 400

    # Bases multi-residencial (Día 37): el desarrollador puede asignar la
    # Pi a una residencial ya al crearla (opcional — puede quedar sin
    # asignar y asociarse después desde 'actualizar_dispositivo').
    residencial_id = None
    residencial_uuid = body.get("residencial_id")
    if residencial_uuid:
        r = Residencial.query.filter_by(uuid_publico=residencial_uuid).first()
        if not r:
            return jsonify({"error": {"code": "residencial_no_encontrada",
                                      "message": "La residencial indicada no existe"}}), 404
        residencial_id = r.id

    # DEVICE-06: el token en claro solo existe en esta variable local, para
    # devolverlo una vez al admin. En la base solo se guarda el hash.
    token_plano = generar_token()
    disp = Dispositivo(nombre=nombre, tipo=tipo, punto_acceso=punto,
                        token_hash=hash_token(token_plano), activo=True,
                        residencial_id=residencial_id)
    db.session.add(disp)
    db.session.commit()
    # Al crear, se devuelve el token UNA vez (anótalo, no se vuelve a mostrar)
    return jsonify({"data": disp.to_dict(token_plano=token_plano)}), 201


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
    # Bases multi-residencial (Día 37): asignar/reasignar/desasignar esta
    # Pi a una residencial. residencial_id: null o "" desasigna (la Pi deja
    # de descargar información hasta que se le asigne una de nuevo).
    if "residencial_id" in body:
        residencial_uuid = body.get("residencial_id")
        if not residencial_uuid:
            disp.residencial_id = None
        else:
            r = Residencial.query.filter_by(uuid_publico=residencial_uuid).first()
            if not r:
                return jsonify({"error": {"code": "residencial_no_encontrada",
                                          "message": "La residencial indicada no existe"}}), 404
            disp.residencial_id = r.id
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
    token_plano = generar_token()
    disp.token_hash = hash_token(token_plano)
    db.session.commit()
    return jsonify({"data": disp.to_dict(token_plano=token_plano)})


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


# =====================================================================
# RESIDENCIALES (bases multi-residencial, Día 37)
#
# El desarrollador ve cuántos admins tiene creados (uno por Residencial)
# y qué usuarios hay bajo cada uno. Hoy, en Villas del Sol, esto muestra
# una sola fila — es la vista que se vuelve realmente útil el día que
# exista un segundo cliente.
# =====================================================================
@dev_bp.get("/residenciales")
@roles_required("desarrollador")
def listar_residenciales(usuario_actual):
    residenciales = Residencial.query.order_by(Residencial.created_at).all()
    return jsonify({"data": [r.to_dict(incluir_stats=True) for r in residenciales]})


@dev_bp.put("/residenciales/<uuid:res_uuid>")
@roles_required("desarrollador")
def editar_residencial(usuario_actual, res_uuid):
    """
    Día 50 (corrección del usuario): edición consolidada de TODOS los
    campos que el desarrollador configura al dar de alta una residencial
    — nombre, dirección, teléfono, plan y días de gracia — desde un
    único botón "Editar residencial" en el panel, en vez de tener el
    plan/días de gracia siempre editables sueltos en la tarjeta (como
    quedó en la Etapa 5, antes de esta corrección).

    Ruta renombrada de /suscripcion a esta, más genérica, ya que ahora
    cubre más que solo la suscripción.

    fecha_proximo_pago NO se edita acá a propósito: nunca se digita a
    mano — se calcula sola al crear la residencial (fecha de alta + 30
    días) y se recalcula sola cuando se registra un pago.
    """
    residencial = Residencial.query.filter_by(uuid_publico=res_uuid).first()
    if not residencial:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Residencial no encontrada"}}), 404

    body = request.get_json(silent=True) or {}

    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if not nombre:
            return jsonify({"error": {"code": "nombre_requerido",
                                      "message": "El nombre no puede quedar vacío"}}), 400
        otra = Residencial.query.filter(Residencial.nombre == nombre,
                                        Residencial.id != residencial.id).first()
        if otra:
            return jsonify({"error": {"code": "nombre_duplicado",
                                      "message": "Ya existe otra residencial con ese nombre"}}), 400
        residencial.nombre = nombre

    if "direccion" in body:
        residencial.direccion = (body["direccion"] or "").strip() or None

    if "telefono" in body:
        residencial.telefono = (body["telefono"] or "").strip() or None

    if "plan_id" in body:
        plan_id_pedido = body["plan_id"]
        if plan_id_pedido in (None, ""):
            residencial.plan_id = None
        else:
            plan = Plan.query.filter_by(uuid_publico=plan_id_pedido).first()
            if not plan:
                return jsonify({"error": {"code": "plan_no_encontrado",
                                          "message": "No se encontró ese plan"}}), 404
            residencial.plan_id = plan.id
            # Al asignar un plan nuevo se da por atendida cualquier
            # solicitud de upgrade pendiente — es justo lo que el admin
            # estaba pidiendo.
            residencial.upgrade_solicitado = False

    if "dias_gracia" in body:
        try:
            dias = int(body["dias_gracia"])
            if dias < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": {"code": "dias_gracia_invalido",
                                      "message": "Los días de gracia deben ser un número entero mayor o igual a 0"}}), 400
        residencial.dias_gracia = dias

    db.session.commit()
    return jsonify({"data": residencial.to_dict(incluir_stats=True)})


def _extender_servicio_30_dias(residencial):
    """
    Día 50 — un pago (por cualquier vía: botón directo del desarrollador,
    o aprobar un comprobante) siempre extiende el servicio 30 días desde
    HOY, no desde la fecha_proximo_pago vieja — así, si una residencial
    estuvo suspendida por atraso, el servicio se reactiva contando 30
    días completos desde este momento, no desde una fecha vencida hace
    tiempo. Un solo lugar para esta regla, para que no se desincronice
    entre los distintos puntos donde se aplica.
    """
    residencial.fecha_proximo_pago = dt.date.today() + dt.timedelta(days=30)


@dev_bp.post("/residenciales/<uuid:res_uuid>/registrar-pago")
@roles_required("desarrollador")
def registrar_pago_residencial(usuario_actual, res_uuid):
    """Botón directo del desarrollador (pago recibido por fuera del
    sistema — efectivo, etc.) — ver _extender_servicio_30_dias()."""
    residencial = Residencial.query.filter_by(uuid_publico=res_uuid).first()
    if not residencial:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Residencial no encontrada"}}), 404
    _extender_servicio_30_dias(residencial)
    db.session.commit()
    return jsonify({"data": residencial.to_dict(incluir_stats=True)})


# ── Revisión de pagos de suscripción (Etapa 8) ──────────────────────────────
@dev_bp.get("/suscripcion-pagos")
@roles_required("desarrollador")
def listar_pagos_suscripcion(usuario_actual):
    """
    Todos los pagos de suscripción de todas las residenciales — filtrable
    por estado (?estado=en_revision). Sin filtro, trae todos (para poder
    ver el historial completo, no solo lo pendiente).
    """
    q = SuscripcionPago.query
    estado_filtro = request.args.get("estado")
    if estado_filtro:
        q = q.filter_by(estado=estado_filtro)
    pagos = q.order_by(SuscripcionPago.created_at.desc()).all()
    return jsonify({"data": [p.to_dict() for p in pagos]})


@dev_bp.post("/suscripcion-pagos/<uuid:pago_uuid>/revisar")
@roles_required("desarrollador")
def revisar_pago_suscripcion(usuario_actual, pago_uuid):
    """
    Aprobar o rechazar un comprobante de pago de suscripción. Al
    aprobar, extiende el servicio 30 días (misma regla que el botón
    directo) — al rechazar, NO se toca la fecha, solo queda registrado
    el motivo para que el admin lo vea en su historial.
    """
    pago = SuscripcionPago.query.filter_by(uuid_publico=pago_uuid).first()
    if not pago:
        return jsonify({"error": {"code": "no_encontrado", "message": "Pago no encontrado"}}), 404
    if pago.estado != "en_revision":
        return jsonify({"error": {"code": "ya_revisado",
                                  "message": f"Este pago ya fue {pago.estado}"}}), 400

    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    if decision not in ("aprobar", "rechazar"):
        return jsonify({"error": {"code": "decision_invalida",
                                  "message": "decision debe ser 'aprobar' o 'rechazar'"}}), 400

    if decision == "aprobar":
        pago.estado = "aprobado"
        if pago.residencial:
            _extender_servicio_30_dias(pago.residencial)
    else:
        pago.estado = "rechazado"
        notas = (body.get("notas_rechazo") or "").strip()
        pago.notas_rechazo = notas or None

    pago.revisado_por = usuario_actual.id
    pago.revisado_en = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": pago.to_dict()})


@dev_bp.get("/residenciales/<uuid:res_uuid>/usuarios")
@roles_required("desarrollador")
def usuarios_de_residencial(usuario_actual, res_uuid):
    """
    Lista los usuarios de staff (admin, supervisor, guardia, cajero) de una
    residencial completos, y solo la CANTIDAD de residentes — una
    residencial real puede tener cientos, no tiene sentido traerlos todos
    acá para una vista de diagnóstico del desarrollador.
    """
    r = Residencial.query.filter_by(uuid_publico=res_uuid).first()
    if not r:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Residencial no encontrada"}}), 404

    staff = (Usuario.query
             .filter(Usuario.residencial_id == r.id,
                     Usuario.rol.in_(("admin", "supervisor", "guardia", "cajero")))
             .order_by(Usuario.rol, Usuario.nombre).all())

    return jsonify({"data": {
        "residencial": r.to_dict(),
        "staff": [u.to_dict() for u in staff],
        "residentes_count": Usuario.query.filter_by(
            residencial_id=r.id, rol="residente").count(),
    }})


@dev_bp.post("/residenciales")
@roles_required("desarrollador")
def crear_residencial(usuario_actual):
    """
    Crea un cliente nuevo del futuro SaaS: un admin dueño + su Residencial,
    todo junto en una sola operación. Exclusivo del desarrollador — dar de
    alta un cliente nuevo es una operación de plataforma, no algo que un
    admin/supervisor haga sobre sí mismo.

    El admin nuevo recibe una contraseña aleatoria (mismo patrón SEC-01 que
    guardia/cajero/supervisor) mostrada una sola vez en la respuesta, con
    cambio obligatorio en su primer login. Esto es temporal: se reemplazará
    por un correo de activación cuando esté conectado el envío real de
    emails — por ahora, el desarrollador se la entrega en persona o por
    el canal que tenga con ese cliente.
    """
    body = request.get_json(silent=True) or {}

    # Datos de la residencial (todos obligatorios, según lo acordado)
    nombre_res = (body.get("nombre_residencial") or "").strip()
    direccion = (body.get("direccion") or "").strip()
    telefono_res = (body.get("telefono_residencial") or "").strip()

    # Datos del admin dueño
    nombre_admin = (body.get("nombre_admin") or "").strip()
    apellido_admin = (body.get("apellido_admin") or "").strip()
    email_admin = (body.get("email_admin") or "").strip().lower()
    telefono_admin = (body.get("telefono_admin") or "").strip()

    # Día 50 — sistema de suscripciones: de acá en adelante, toda
    # residencial nueva nace CON plan (Villas del Sol, creada antes de
    # que este sistema existiera, queda como la única excepción
    # histórica sin plan asignado).
    plan_id_pedido = (body.get("plan_id") or "").strip()

    faltantes = []
    if not nombre_res: faltantes.append("nombre de la residencial")
    if not direccion: faltantes.append("dirección")
    if not telefono_res: faltantes.append("teléfono de la residencial")
    if not nombre_admin: faltantes.append("nombre del admin")
    if not apellido_admin: faltantes.append("apellido del admin")
    if not email_admin: faltantes.append("correo del admin")
    if not plan_id_pedido: faltantes.append("plan")
    if faltantes:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Faltan campos obligatorios: " + ", ".join(faltantes)}}), 400

    plan = Plan.query.filter_by(uuid_publico=plan_id_pedido).first()
    if not plan:
        return jsonify({"error": {"code": "plan_no_encontrado",
                                  "message": "No se encontró ese plan"}}), 404

    try:
        dias_gracia = int(body.get("dias_gracia", 5))
        if dias_gracia < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "dias_gracia_invalido",
                                  "message": "Los días de gracia deben ser un número entero mayor o igual a 0"}}), 400

    if Usuario.query.filter_by(email=email_admin).first():
        return jsonify({"error": {"code": "email_duplicado",
                                  "message": "Ya existe un usuario con ese correo"}}), 400
    if Residencial.query.filter_by(nombre=nombre_res).first():
        return jsonify({"error": {"code": "nombre_duplicado",
                                  "message": "Ya existe una residencial con ese nombre"}}), 400

    # 1. Crear el admin dueño (SEC-01: contraseña aleatoria, cambio obligatorio)
    password_temporal = generar_password_temporal()
    admin = Usuario(
        nombre=nombre_admin, apellido=apellido_admin, email=email_admin,
        telefono=telefono_admin or None,
        rol="admin", activo=True, debe_cambiar_password=True,
    )
    admin.set_password(password_temporal)
    db.session.add(admin)
    db.session.flush()  # necesito admin.id antes de crear la Residencial

    # 2. Crear la Residencial, dueña = el admin recién creado
    # Día 50: fecha_proximo_pago se CALCULA (hoy + 30 días, "un mes de
    # servicio"), nunca se digita a mano — ni acá ni cuando se registre
    # un pago más adelante (ver registrar_pago_residencial()).
    residencial = Residencial(
        admin_id=admin.id, nombre=nombre_res,
        direccion=direccion, telefono=telefono_res,
        plan_id=plan.id, dias_gracia=dias_gracia,
        fecha_proximo_pago=dt.date.today() + dt.timedelta(days=30),
    )
    db.session.add(residencial)
    db.session.flush()  # necesito residencial.id

    # 3. Atar al admin a su propia Residencial
    admin.residencial_id = residencial.id

    db.session.commit()

    return jsonify({"data": {
        "residencial": residencial.to_dict(),
        "admin": {
            "email": admin.email,
            "nombre": f"{admin.nombre} {admin.apellido}",
            "password_generica": password_temporal,
        },
    }}), 201


# ── Planes de suscripción (Día 50) ──────────────────────────────────────────
@dev_bp.get("/planes")
@roles_required("desarrollador")
def listar_planes(usuario_actual):
    """Todos los planes, activos e inactivos — el desarrollador necesita
    ver los retirados también, para saber qué residenciales siguen en uno."""
    planes = Plan.query.order_by(Plan.orden.asc(), Plan.id.asc()).all()
    return jsonify({"data": [p.to_dict(incluir_stats=True) for p in planes]})


@dev_bp.post("/planes")
@roles_required("desarrollador")
def crear_plan(usuario_actual):
    body = request.get_json(silent=True) or {}
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": {"code": "nombre_requerido", "message": "El nombre es obligatorio"}}), 400

    def entero_positivo(campo, minimo=1):
        v = body.get(campo)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None, f"{campo} debe ser un número entero"
        if v < minimo:
            return None, f"{campo} debe ser al menos {minimo}"
        return v, None

    max_casas, err = entero_positivo("max_casas")
    if err:
        return jsonify({"error": {"code": "dato_invalido", "message": err}}), 400
    max_usuarios, err = entero_positivo("max_usuarios")
    if err:
        return jsonify({"error": {"code": "dato_invalido", "message": err}}), 400
    almacenamiento_gb, err = entero_positivo("almacenamiento_gb")
    if err:
        return jsonify({"error": {"code": "dato_invalido", "message": err}}), 400

    try:
        precio = float(body.get("precio_mensual", 0))
        if precio < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": {"code": "precio_invalido", "message": "El precio debe ser un número mayor o igual a 0"}}), 400

    plan = Plan(
        nombre=nombre, max_casas=max_casas, max_usuarios=max_usuarios,
        almacenamiento_gb=almacenamiento_gb, precio_mensual=precio,
        orden=int(body.get("orden", 0)),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify({"data": plan.to_dict()}), 201


@dev_bp.put("/planes/<int:plan_id>")
@roles_required("desarrollador")
def editar_plan(usuario_actual, plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"error": {"code": "no_encontrado", "message": "Plan no encontrado"}}), 404

    body = request.get_json(silent=True) or {}
    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if not nombre:
            return jsonify({"error": {"code": "nombre_requerido", "message": "El nombre no puede quedar vacío"}}), 400
        plan.nombre = nombre

    for campo in ("max_casas", "max_usuarios", "almacenamiento_gb"):
        if campo in body:
            try:
                v = int(body[campo])
                if v < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return jsonify({"error": {"code": "dato_invalido",
                                          "message": f"{campo} debe ser un número entero mayor a 0"}}), 400
            setattr(plan, campo, v)

    if "precio_mensual" in body:
        try:
            precio = float(body["precio_mensual"])
            if precio < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": {"code": "precio_invalido",
                                      "message": "El precio debe ser un número mayor o igual a 0"}}), 400
        plan.precio_mensual = precio

    if "activo" in body:
        plan.activo = bool(body["activo"])
    if "orden" in body:
        try:
            plan.orden = int(body["orden"])
        except (TypeError, ValueError):
            pass  # el orden es solo cosmético, no vale la pena bloquear el guardado por esto

    db.session.commit()
    return jsonify({"data": plan.to_dict()})
