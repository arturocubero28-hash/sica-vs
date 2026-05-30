"""
Configuración de Celery para tareas en segundo plano.

Tareas que vivirán aquí (Integrante 4 principalmente):
  * Generación mensual de cuotas
  * Alertas de vencimiento y mora (escalonadas)
  * Envío de notificaciones por correo (Resend)

Arranque (ya configurado en docker-compose):
  celery -A app.tasks.celery_app.celery worker --beat --loglevel=info
"""
import os
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery = Celery(
    "sicavs",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Tareas programadas (cron). Ejemplo: revisar mora todos los días a las 7am.
celery.conf.beat_schedule = {
    "revisar-mora-diario": {
        "task": "app.tasks.mora.revisar_mora",
        "schedule": 60.0 * 60.0 * 24.0,  # cada 24 h (ajustar a hora fija con crontab)
    },
}
celery.conf.timezone = "America/Tegucigalpa"
