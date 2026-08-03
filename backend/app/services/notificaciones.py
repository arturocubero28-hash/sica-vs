"""
Servicio de notificaciones push vía Firebase Cloud Messaging (FCM).

Usa firebase-admin, la librería oficial de Google. Se inicializa una sola vez
con las credenciales del service account (archivo JSON que se descarga de la
consola de Firebase → Configuración → Cuentas de servicio).

La ruta al archivo de credenciales se toma de la variable de entorno
FIREBASE_CREDENTIALS (por defecto /app/firebase-credentials.json dentro del
contenedor).

Si Firebase no está configurado (falta el archivo), el servicio NO rompe la
app: simplemente registra un aviso y las notificaciones se omiten. Esto permite
que el sistema siga funcionando en entornos sin push configurado.
"""
import os
import logging

logger = logging.getLogger(__name__)

_fb_app = None
_habilitado = False


def inicializar():
    """Inicializa firebase-admin una sola vez. Se llama al arrancar la app."""
    global _fb_app, _habilitado
    if _fb_app is not None:
        return

    ruta = os.environ.get("FIREBASE_CREDENTIALS", "/app/firebase-credentials.json")
    if not os.path.exists(ruta):
        logger.warning(
            "Firebase no configurado (no existe %s). "
            "Las notificaciones push quedan deshabilitadas.", ruta
        )
        return

    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(ruta)
        _fb_app = firebase_admin.initialize_app(cred)
        _habilitado = True
        logger.info("Firebase Cloud Messaging inicializado correctamente.")
    except Exception as e:
        logger.error("No se pudo inicializar Firebase: %s", e)


def _enviar_a_tokens(tokens, titulo, cuerpo, datos=None):
    """Envía una notificación a una lista de tokens FCM. Devuelve cuántas
    se enviaron bien. Limpia los tokens inválidos de la base de datos."""
    if not _habilitado or not tokens:
        return 0

    from firebase_admin import messaging
    from app.extensions import db
    from app.models.dispositivo_movil import DispositivoMovil

    enviadas = 0
    tokens_invalidos = []

    for token in tokens:
        try:
            mensaje = messaging.Message(
                notification=messaging.Notification(title=titulo, body=cuerpo),
                data={k: str(v) for k, v in (datos or {}).items()},
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="sicavs_canal",
                        color="#F48723",
                    ),
                ),
            )
            messaging.send(mensaje)
            enviadas += 1
        except messaging.UnregisteredError:
            # El token ya no es válido (app desinstalada, etc.): lo marcamos
            tokens_invalidos.append(token)
        except Exception as e:
            logger.warning("Error enviando push: %s", e)

    # Limpiar tokens muertos
    if tokens_invalidos:
        DispositivoMovil.query.filter(
            DispositivoMovil.fcm_token.in_(tokens_invalidos)
        ).update({"activo": False}, synchronize_session=False)
        db.session.commit()

    return enviadas


def notificar_usuario(usuario_id, titulo, cuerpo, datos=None):
    """Envía una notificación a todos los dispositivos activos de un usuario."""
    if not _habilitado:
        return 0
    # Día 51 — niveles de plan (Básico/Premium): si la residencial del
    # usuario tiene un plan que no incluye notificaciones, no se manda
    # nada. Se chequea acá, el único lugar donde de verdad se dispara el
    # envío — notificar_cuenta() y las dos versiones _async llaman a
    # esta misma función por dentro, así que quedan cubiertas sin
    # repetir el chequeo en cada una.
    from app.utils.residencial import plan_permite
    from app.models.usuario import Usuario
    usuario = Usuario.query.get(usuario_id)
    if not usuario or not plan_permite(usuario.residencial_id, "notificaciones"):
        return 0
    from app.models.dispositivo_movil import DispositivoMovil
    dispositivos = DispositivoMovil.query.filter_by(
        usuario_id=usuario_id, activo=True
    ).all()
    tokens = [d.fcm_token for d in dispositivos]
    return _enviar_a_tokens(tokens, titulo, cuerpo, datos)


def notificar_cuenta(cuenta, titulo, cuerpo, datos=None):
    """Envía una notificación a todos los residentes activos de una cuenta.
    Útil para avisos que le importan a toda la familia (visita entró, etc.)."""
    if not _habilitado or not cuenta:
        return 0
    total = 0
    for residente in cuenta.residentes:
        if residente.activo and residente.usuario:
            total += notificar_usuario(
                residente.usuario.id, titulo, cuerpo, datos
            )
    return total


# ── Versiones asíncronas (encolan en Celery para no bloquear el request) ──────

def notificar_usuario_async(usuario_id, titulo, cuerpo, datos=None):
    """Encola el envío a un usuario en Celery. Devuelve de inmediato.
    Si Celery no está disponible, cae al envío síncrono como respaldo."""
    try:
        from app.tasks.notificaciones_task import enviar_push_usuario
        enviar_push_usuario.delay(usuario_id, titulo, cuerpo, datos)
    except Exception:
        # Respaldo: si no se pudo encolar, enviar síncrono
        try:
            notificar_usuario(usuario_id, titulo, cuerpo, datos)
        except Exception:
            pass


def notificar_cuenta_async(cuenta_id, titulo, cuerpo, datos=None):
    """Encola el envío a una cuenta en Celery. Devuelve de inmediato.
    Recibe cuenta_id (no el objeto) porque la tarea corre en otro proceso."""
    try:
        from app.tasks.notificaciones_task import enviar_push_cuenta
        enviar_push_cuenta.delay(cuenta_id, titulo, cuerpo, datos)
    except Exception:
        pass
