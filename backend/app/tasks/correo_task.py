"""
Tareas Celery para el envío de correos en segundo plano (Día 61).

Mismo criterio que notificaciones_task.py: el envío de correo (llamada
HTTP a Resend) no debe bloquear la respuesta al admin que está creando
una cuenta o pidiendo un reset -- se encola y corre en paralelo.
"""
from app.tasks.celery_app import celery


@celery.task(name="tasks.enviar_correo_activacion")
def enviar_correo_activacion_task(email, nombre, token, nombre_residencial, es_reenvio=False):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services import correo
        return correo.enviar_correo_activacion(email, nombre, token, nombre_residencial, es_reenvio)


@celery.task(name="tasks.enviar_correo_reset")
def enviar_correo_reset_task(email, token, nombre_residencial):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services import correo
        return correo.enviar_correo_reset(email, token, nombre_residencial)


# ── Día 76 — encolar, o mandar en el momento si Redis no responde ─────────
#
# Antes cada lugar hacía tarea.delay(...) dentro de un try. Con Redis caído
# el .delay fallaba y el correo se perdía en silencio (el de recuperar
# contraseña, con un "pass"). Celery y el limitador dependen de Redis; el
# correo no: lo manda Resend por HTTP. Si no se puede encolar, se manda ahí
# mismo, en el proceso de la petición (tarda un segundo más, pero llega).

from app.tasks.encolar import encolar as _encolar  # noqa: E402


def encolar_correo_activacion(email, nombre, token, nombre_residencial, es_reenvio=False):
    from app.services import correo
    _encolar(enviar_correo_activacion_task, correo.enviar_correo_activacion,
             email, nombre, token, nombre_residencial, es_reenvio)


def encolar_correo_reset(email, token, nombre_residencial):
    from app.services import correo
    _encolar(enviar_correo_reset_task, correo.enviar_correo_reset, email, token, nombre_residencial)
