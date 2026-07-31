"""
Cuota de almacenamiento por residencial — Día 50, sistema de suscripciones.

Envuelve a services/storage.py (que ya sabe guardar en disco local o en
DigitalOcean Spaces, sin que el resto del código tenga que saber cuál)
con la lógica de negocio: cada archivo que consume espacio (fotos de
acceso, comprobantes de pago) se registra contra la residencial dueña,
y si eso hace que se pase de la cuota de su plan, se borra el archivo
MÁS VIEJO de esa residencial al instante —nunca se le deja quedar por
encima de su límite, ni siquiera un momento.

Decisión del usuario (Día 50): el borrado es EN TIEMPO REAL, en el mismo
pedido que guarda el archivo nuevo — no un proceso de limpieza aparte
que corra una vez al día.

Decisión del usuario (misma sesión): comprobantes de pago comparten el
MISMO pozo de espacio y el MISMO borrado automático que las fotos de
acceso — más simple, con el riesgo aceptado de que algún día se borre
un comprobante viejo. No hay tratamiento especial por tipo.
"""
from app.extensions import db
from app.models.archivo_residencial import ArchivoResidencial
from app.services.storage import guardar_archivo, eliminar_archivo

TIPOS_VALIDOS = ("acceso", "comprobante")


def guardar_con_cuota(stream, residencial_id, tipo, subcarpeta="",
                      content_type="application/octet-stream", extension="jpg",
                      evento_acceso_id=None, pago_id=None):
    """
    Guarda un archivo (foto de acceso o comprobante de pago) aplicando la
    cuota de almacenamiento de la residencial. Devuelve la clave del
    archivo guardado, igual que guardar_archivo() — el código que llama
    a esto no necesita saber que la cuota existe por dentro, solo qué
    función invocar.

    tipo: 'acceso' o 'comprobante' — solo para trazabilidad/reportes, NO
    afecta la lógica de qué se borra primero (eso es solo por fecha, sin
    importar el tipo — decisión del usuario).

    Sin residencial_id, no se aplica ninguna cuota — mismo criterio que
    el resto del sistema de suscripciones: sin contexto de residencial,
    no hay límite contra el cual medir.
    """
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo debe ser uno de {TIPOS_VALIDOS}, llegó '{tipo}'")

    # Leer el stream completo a memoria para conocer el tamaño exacto —
    # estos archivos son chicos (una foto o un comprobante, no video),
    # así que esto no es un problema de memoria.
    datos = stream.read()
    tamano = len(datos)

    import io
    clave = guardar_archivo(io.BytesIO(datos), subcarpeta, content_type, extension)
    registrar_archivo_existente(residencial_id, clave, tamano, tipo, evento_acceso_id, pago_id)
    return clave


def registrar_archivo_existente(residencial_id, clave, tamano_bytes, tipo,
                                evento_acceso_id=None, pago_id=None):
    """
    Registra contra la cuota un archivo que YA se guardó por otro camino
    — para comprobantes de pago, que pasan primero por
    guardar_imagen_segura() (utils/archivos.py), que ya trae su propia
    validación de contenido (magic bytes, extensión, 5MB máximo) y no
    tiene sentido duplicar acá. guardar_con_cuota() usa esta misma
    función por dentro, así la lógica de registro+cuota vive en un solo
    lugar sin importar por qué puerta entró el archivo.

    Sin residencial_id, no se aplica ninguna cuota — mismo criterio que
    el resto del sistema de suscripciones.
    """
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo debe ser uno de {TIPOS_VALIDOS}, llegó '{tipo}'")
    if not residencial_id or not clave:
        return

    from app.models.residencial import Residencial
    residencial = Residencial.query.get(residencial_id)
    if not residencial:
        return

    registro = ArchivoResidencial(
        residencial_id=residencial_id, clave=clave, tamano_bytes=tamano_bytes, tipo=tipo,
        evento_acceso_id=evento_acceso_id, pago_id=pago_id,
    )
    db.session.add(registro)
    residencial.almacenamiento_usado_bytes = (residencial.almacenamiento_usado_bytes or 0) + tamano_bytes
    db.session.commit()

    _aplicar_cuota(residencial)


def vincular_pago(clave, pago_id):
    """
    Para comprobantes: el archivo se guarda ANTES de que exista el Pago
    (hace falta validar el archivo primero), así que el registro de
    cuota se crea sin pago_id todavía. Esta función lo completa una vez
    que el Pago ya tiene su id — solo trazabilidad, no afecta la cuota
    en sí (que ya se aplicó al guardar).
    """
    registro = ArchivoResidencial.query.filter_by(clave=clave).first()
    if registro:
        registro.pago_id = pago_id
        db.session.commit()


def _aplicar_cuota(residencial):
    """
    Si la residencial se pasó de la cuota de su plan, borra los archivos
    más viejos (uno por uno, sin importar el tipo) hasta volver a estar
    dentro del límite. Sin plan asignado, no hay cuota que aplicar.
    """
    if not residencial.plan_id or not residencial.plan:
        return
    limite_bytes = residencial.plan.almacenamiento_gb * 1024 ** 3

    while (residencial.almacenamiento_usado_bytes or 0) > limite_bytes:
        mas_viejo = (
            ArchivoResidencial.query.filter_by(residencial_id=residencial.id)
            .order_by(ArchivoResidencial.created_at.asc(), ArchivoResidencial.id.asc())
            .first()
        )
        if not mas_viejo:
            # No queda nada que borrar pero el contador sigue marcando
            # que se excede — señal de que se desincronizó (no debería
            # pasar, pero no hay que quedarse en un loop infinito). Se
            # corrige al total real y se corta.
            residencial.almacenamiento_usado_bytes = (
                db.session.query(db.func.coalesce(db.func.sum(ArchivoResidencial.tamano_bytes), 0))
                .filter(ArchivoResidencial.residencial_id == residencial.id).scalar()
            )
            db.session.commit()
            break

        eliminar_archivo(mas_viejo.clave)
        residencial.almacenamiento_usado_bytes = max(
            0, (residencial.almacenamiento_usado_bytes or 0) - mas_viejo.tamano_bytes)
        db.session.delete(mas_viejo)
        db.session.commit()


def deshacer_registro(clave):
    """
    Para rollbacks: deshace un archivo ya registrado (storage + registro
    + contador) — si no se revirtiera también esto, un rollback dejaría
    "fantasmas" contando espacio que en realidad se liberó.
    """
    if not clave:
        return
    eliminar_archivo(clave)
    registro = ArchivoResidencial.query.filter_by(clave=clave).first()
    if registro:
        residencial = registro.residencial
        if residencial:
            residencial.almacenamiento_usado_bytes = max(
                0, (residencial.almacenamiento_usado_bytes or 0) - registro.tamano_bytes)
        db.session.delete(registro)
        db.session.commit()
