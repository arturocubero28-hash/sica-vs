"""
Tareas Celery para el envío de notificaciones push en segundo plano.

En vez de llamar a Firebase de forma síncrona dentro del request (lo que
retrasaba la respuesta al guardia/admin hasta ~1 minuto), estas tareas
encolan el envío para que ocurra en paralelo. El request responde al
instante y la notificación sale por su cuenta.
"""
from app.tasks.celery_app import celery


@celery.task(name="tasks.enviar_push_usuario")
def enviar_push_usuario(usuario_id, titulo, cuerpo, datos=None):
    """Envía una notificación a todos los dispositivos de un usuario."""
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services import notificaciones as _notif
        return _notif.notificar_usuario(usuario_id, titulo, cuerpo, datos)


@celery.task(name="tasks.enviar_push_cuenta")
def enviar_push_cuenta(cuenta_id, titulo, cuerpo, datos=None):
    """Envía una notificación a todos los residentes de una cuenta."""
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services import notificaciones as _notif
        from app.models.cuenta import Cuenta
        cuenta = Cuenta.query.get(cuenta_id)
        if cuenta:
            return _notif.notificar_cuenta(cuenta, titulo, cuerpo, datos)
        return 0
