"""
Tarea de ejemplo: revisión de mora (Integrante 4).

Esto es un ESQUELETO con la lógica que acordamos, comentada paso a paso.
El Integrante 4 lo completa cuando existan los modelos de cuenta y cuota.

Lógica de mora acordada:
  -1 día:   "Tu fecha de pago está por vencer mañana"
   0 día:   "Hoy vence tu cuota"
  +1, +2:   "Tienes X días de atraso" (acceso aún activo)
  +3 o más: BLOQUEO -> tarjetas inactivas + no puede generar QR
"""
from app.tasks.celery_app import celery


@celery.task
def revisar_mora():
    """Se ejecuta a diario. Revisa todas las cuentas y aplica la lógica de mora."""
    # Pseudocódigo / pasos a implementar:
    #
    # 1. hoy = date.today()
    # 2. Para cada cuota pendiente:
    #      dias = (hoy - cuota.fecha_vencimiento).days
    #      if dias == -1:  notificar("pago_por_vencer")
    #      elif dias == 0: notificar("pago_vence_hoy")
    #      elif 1 <= dias <= 2: notificar("pago_atrasado", dias)
    #      elif dias >= 3:
    #           bloquear_cuenta(cuota.cuenta_id)   # tarjetas a 'bloqueada', bloquea QR
    #           notificar("acceso_bloqueado", dias)
    #
    # 3. El desbloqueo NO ocurre aquí: se dispara cuando el admin aprueba un pago.
    return {"status": "pendiente_de_implementar"}
