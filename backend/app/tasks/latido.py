"""
Latido del worker (Día 73).

EL PROBLEMA: el 5 de noviembre el worker quedó en un bucle de reinicios
(una dependencia se actualizó sola en un build) y NADA lo delataba: el
backend respondía, el health daba 200, el panel funcionaba. Pero el
worker es el que genera las cuotas el 1ro de cada mes, revisa la mora,
manda las notificaciones push, los correos de recuperar contraseña y
"Regenerar enlace", rota las tarjetas virtuales y vence las visitas.
Con el worker caído, el 1ro de diciembre no se habría generado ninguna
cuota, y nadie se habría enterado hasta que alguien preguntara.

LA SOLUCIÓN: el worker deja una marca en Redis cada minuto diciendo
"estoy vivo". Si la marca envejece, el worker está caído. Lo importante
es QUIÉN mira esa marca: no puede ser el worker (si está caído no mira
nada), así que la mira el backend (GET /api/v1/health/worker, que usa el
panel para mostrar el aviso) y un vigilante en el propio servidor, fuera
de Docker (deploy/vigilar.sh), que manda un correo de alerta.

La marca la escribe una tarea que el worker EJECUTA, no el programador
que la agenda: así un worker que arranca pero no puede procesar tareas
-que es justo lo que pasó, se caía al conectarse a Redis- tampoco deja
marca, y se detecta igual.
"""
import time

from app.tasks.celery_app import celery, REDIS_URL

CLAVE = "sicavs:worker:latido"
# Si la clave no se renueva, Redis la borra sola: un worker que murió hace
# rato no deja una marca vieja que confunda.
DURA_SEGUNDOS = 900


@celery.task(name="tasks.latido_worker", ignore_result=True)
def latido_worker():
    import redis
    redis.from_url(REDIS_URL).set(CLAVE, str(int(time.time())), ex=DURA_SEGUNDOS)


# El latido programado corre recién al minuto de arrancar: sin esto, cada
# despliegue o reinicio mostraría al worker "caído" durante ese minuto.
# worker_ready se dispara cuando el worker ya se conectó a Redis y puede
# recibir tareas, así que un worker que no logra conectarse (lo que pasó
# el 5 de noviembre) tampoco late por acá.
from celery.signals import worker_ready  # noqa: E402


@worker_ready.connect
def _latir_al_arrancar(**_):
    try:
        latido_worker()
    except Exception:
        pass   # el programado lo reintenta al minuto
