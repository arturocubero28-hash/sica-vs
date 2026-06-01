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
    include=["app.tasks.mora"],   # <-- IMPORTANTE: registra las tareas de mora.py
)

celery.conf.timezone = "America/Tegucigalpa"
celery.conf.enable_utc = False   # respetar el timezone configurado

# Programación centralizada (única fuente de verdad)
celery.conf.beat_schedule = {
    "generar-cuotas-1ro-de-mes": {
        "task": "tasks.generar_cuotas_mensuales",
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
    "revisar-mora-diaria": {
        "task": "tasks.revisar_mora",
        "schedule": crontab(hour=1, minute=0),
    },
}
