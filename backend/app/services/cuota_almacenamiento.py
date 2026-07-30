"""
Cuota de almacenamiento por residencial — Día 50, sistema de suscripciones.

Envuelve a services/storage.py (que ya sabe guardar en disco local o en
DigitalOcean Spaces, sin que el resto del código tenga que saber cuál)
con la lógica de negocio: cada foto de acceso que se guarda se registra
contra la residencial dueña, y si eso hace que se pase de la cuota de su
plan, se borra la foto MÁS VIEJA de esa residencial al instante —nunca
se le deja quedar por encima de su límite, ni siquiera un momento.

Decisión del usuario (Día 50): el borrado es EN TIEMPO REAL, en el mismo
pedido que guarda la foto nueva — no un proceso de limpieza aparte que
corra una vez al día.
"""
from app.extensions import db
from app.models.foto_acceso import FotoAcceso
from app.services.storage import guardar_archivo, eliminar_archivo


def guardar_foto_con_cuota(stream, residencial_id, subcarpeta,
                           content_type="application/octet-stream",
                           extension="jpg", evento_acceso_id=None):
    """
    Guarda una foto de acceso (identidad, placa) aplicando la cuota de
    almacenamiento de la residencial. Devuelve la clave del archivo
    guardado, igual que guardar_archivo() — el resto del código que ya
    llama a guardar fotos no necesita saber que esto existe por dentro,
    solo cambiar qué función llama.

    Sin residencial_id (no debería pasar en la práctica, pero por las
    dudas) simplemente no aplica ninguna cuota — mismo criterio que el
    resto del sistema de suscripciones: sin contexto de residencial, no
    hay límite contra el cual medir.
    """
    # Leer el stream completo a memoria para conocer el tamaño exacto —
    # las fotos de este sistema son chicas (una foto de identidad o de
    # placa, no video), así que esto no es un problema de memoria.
    datos = stream.read()
    tamano = len(datos)

    import io
    clave = guardar_archivo(io.BytesIO(datos), subcarpeta, content_type, extension)

    if not residencial_id:
        return clave

    from app.models.residencial import Residencial
    residencial = Residencial.query.get(residencial_id)
    if not residencial:
        return clave

    registro = FotoAcceso(
        residencial_id=residencial_id, clave=clave, tamano_bytes=tamano,
        evento_acceso_id=evento_acceso_id,
    )
    db.session.add(registro)
    residencial.almacenamiento_usado_bytes = (residencial.almacenamiento_usado_bytes or 0) + tamano
    db.session.commit()

    _aplicar_cuota(residencial)
    return clave


def _aplicar_cuota(residencial):
    """
    Si la residencial se pasó de la cuota de su plan, borra las fotos
    más viejas (una por una) hasta volver a estar dentro del límite.
    Sin plan asignado, no hay cuota que aplicar — se sale de inmediato.
    """
    if not residencial.plan_id or not residencial.plan:
        return
    limite_bytes = residencial.plan.almacenamiento_gb * 1024 ** 3

    while (residencial.almacenamiento_usado_bytes or 0) > limite_bytes:
        mas_vieja = (
            FotoAcceso.query.filter_by(residencial_id=residencial.id)
            .order_by(FotoAcceso.created_at.asc(), FotoAcceso.id.asc())
            .first()
        )
        if not mas_vieja:
            # No queda nada que borrar pero el contador sigue marcando
            # que se excede — señal de que el contador se desincronizó
            # (no debería pasar, pero no hay que quedarse en un loop
            # infinito). Se corrige el contador al total real y se corta.
            residencial.almacenamiento_usado_bytes = (
                db.session.query(db.func.coalesce(db.func.sum(FotoAcceso.tamano_bytes), 0))
                .filter(FotoAcceso.residencial_id == residencial.id).scalar()
            )
            db.session.commit()
            break

        eliminar_archivo(mas_vieja.clave)
        residencial.almacenamiento_usado_bytes = max(
            0, (residencial.almacenamiento_usado_bytes or 0) - mas_vieja.tamano_bytes)
        db.session.delete(mas_vieja)
        db.session.commit()
