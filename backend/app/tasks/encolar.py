"""
Día 76 — encolar una tarea en Celery sin que una caída de Redis la pierda ni
deje colgada la petición.

Celery y el limitador dependen de Redis. Cuando Redis no responde, .delay()
no falla enseguida: reintenta la conexión unos 20 segundos. Antes de encolar
se hace un ping de medio segundo (recordado 15 s por proceso); si Redis no
está, la tarea se ejecuta ahí mismo con la función "directo" que se pase.
"""
import logging

_REDIS_OK = {"hasta": 0.0, "ok": True}


def _redis_responde():
    """Ping de medio segundo, recordado 15 s por proceso. Hace falta porque
    Celery, con Redis caído, reintenta la conexión durante ~20 s antes de
    fallar, y esa espera la sufría quien pidió recuperar su contraseña."""
    import os, time
    ahora = time.monotonic()
    if ahora < _REDIS_OK["hasta"]:
        return _REDIS_OK["ok"]
    try:
        import redis
        redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                       socket_connect_timeout=0.5, socket_timeout=0.5).ping()
        ok = True
    except Exception:
        ok = False
    _REDIS_OK.update(ok=ok, hasta=ahora + 15)
    return ok


def encolar(tarea, directo, *args, **kwargs):
    import logging
    try:
        # En pruebas .delay está reemplazado por un doble y no hay Redis:
        # se lo llama igual (no tiene atributo "app" de Celery real).
        if not hasattr(tarea.delay, "__self__") or _redis_responde():
            tarea.delay(*args, **kwargs)
            return
        raise ConnectionError("Redis no responde")
    except Exception:
        logging.getLogger(__name__).warning(
            "No se pudo encolar %s (¿Redis caído?): se envía ahora mismo", tarea.name)
    try:
        directo(*args, **kwargs)
    except Exception:
        logging.getLogger(__name__).exception("Tampoco se pudo enviar %s en el momento", tarea.name)


