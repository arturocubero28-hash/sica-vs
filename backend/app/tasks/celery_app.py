"""
Configuración de Celery para tareas en segundo plano de SICA-VS.

Tareas programadas:
  * generar_cuotas_mensuales — 1ro de cada mes 00:05 (hora Honduras)
  * revisar_mora — todas las noches 01:00 (hora Honduras)

Arranque (docker-compose):
  celery -A app.tasks.celery_app.celery worker --beat --loglevel=info
"""
import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery = Celery(
    "sicavs",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.mora", "app.tasks.notificaciones_task", "app.tasks.correo_task",
             "app.tasks.latido"],   # <-- registra las tareas
)

# Día 76 — si Redis no responde, encolar falla RÁPIDO (y quien encola cae a
# su respaldo: ver encolar_correo_* en correo_task.py), en vez de dejar la
# petición colgada varios segundos reintentando la conexión.
celery.conf.broker_connection_timeout = 2
celery.conf.broker_transport_options = {"socket_connect_timeout": 2}
celery.conf.redis_socket_connect_timeout = 2
celery.conf.task_publish_retry_policy = {
    "max_retries": 1, "interval_start": 0, "interval_step": 0.5, "interval_max": 0.5,
}

celery.conf.timezone = "America/Tegucigalpa"
celery.conf.enable_utc = False   # respetar el timezone configurado

# Programación centralizada (única fuente de verdad)
celery.conf.beat_schedule = {
    # Día 73 — "estoy vivo", cada minuto. Ver app/tasks/latido.py: si esto
    # deja de correr, el panel y el vigilante del servidor avisan.
    "latido-worker": {
        "task": "tasks.latido_worker",
        "schedule": 60.0,
    },
    "generar-cuotas-1ro-de-mes": {
        "task": "tasks.generar_cuotas_mensuales",
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
    "revisar-mora-diaria": {
        "task": "tasks.revisar_mora",
        "schedule": crontab(hour=1, minute=0),
    },
    "revisar-arreglos-diaria": {
        "task": "tasks.revisar_arreglos",
        "schedule": crontab(hour=1, minute=30),
    },
    "limpiar-tokens-diaria": {
        "task": "tasks.limpiar_tokens_revocados",
        "schedule": crontab(hour=2, minute=0),
    },
    "avisar-cuotas-por-vencer": {
        "task": "tasks.avisar_cuotas_por_vencer",
        "schedule": crontab(hour=8, minute=0),
    },
    # Rotación de tarjetas virtuales (QR permanentes) a medianoche
    # El código anterior queda válido 10 min para evitar que nadie quede
    # afuera mientras la Pi descarga la nueva lista en su próximo sync.
    "rotar-tarjetas-virtuales": {
        "task": "tasks.rotar_tarjetas_virtuales",
        "schedule": crontab(hour=0, minute=0),
    },
    # Marca como 'expirada' las visitas activas cuyo valido_hasta ya pasó y
    # nadie las usó — antes era perezoso (solo se marcaba al intentar
    # validar el QR), así que una visita vencida sin uso seguía apareciendo
    # como 'activa' para siempre. Corre cada hora, no una vez al día, para
    # que la transición a 'vencida' sea razonablemente oportuna.
    "expirar-visitas-vencidas": {
        "task": "tasks.expirar_visitas_vencidas",
        "schedule": crontab(minute=5),  # a los 5 minutos de cada hora
    },
}
