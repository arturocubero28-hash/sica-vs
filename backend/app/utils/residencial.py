"""
Helper compartido para la herencia de residencial_id (Día 37, bases
multi-residencial).

Cuando un admin o supervisor crea algo (un guardia, un cajero, una unidad,
un dispositivo), ese algo debe quedar bajo la misma Residencial que su
creador — así es como, el día que exista un segundo cliente, cada uno ve
solo lo suyo sin que nadie tenga que acordarse de pasar el dato a mano en
cada endpoint.

Hoy, con un solo admin en Villas del Sol, esta función siempre devuelve el
mismo valor (o None, si nunca se corrió el bootstrap) — no cambia ningún
comportamiento existente.
"""


def residencial_id_heredado(usuario_actual):
    """
    Determina qué residencial_id debe heredar algo creado por usuario_actual.

    - admin / supervisor: su propio residencial_id (el admin lo tiene
      seteado a su propia Residencial desde que esta se crea; el
      supervisor hereda el mismo valor al ser creado por ese admin).
    - super_admin / desarrollador: None — son roles de plataforma, no
      pertenecen a ninguna Residencial de cliente. Si alguno de estos
      roles crea algo directamente (posible hoy porque varios endpoints
      también aceptan "super_admin"), ese registro queda sin residencial
      asignada — coherente con que son operaciones de administración
      general, no de un cliente específico.
    - cualquier otro rol: None (no debería llegar a crear nada de esto,
      pero por seguridad se devuelve None en vez de fallar).
    """
    if usuario_actual.rol in ("admin", "supervisor"):
        return usuario_actual.residencial_id
    return None
