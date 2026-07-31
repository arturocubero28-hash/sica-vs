"""
Registro de archivos que consumen la cuota de almacenamiento de una
residencial — Día 50, sistema de suscripciones.

Nació como "FotoAcceso" (solo fotos de entrada/salida), pero el usuario
decidió que los comprobantes de pago comparten el mismo pozo de espacio
y el mismo borrado automático — así que se generalizó el mismo día,
antes de que hubiera datos reales que migrar.

Por qué existe esta tabla, y no basta con los campos sueltos que ya
tienen Visita/ComprobantePago: para poder aplicar la cuota del plan de
cada residencial (borrar lo MÁS VIEJO cuando se excede el límite), hace
falta saber, de forma centralizada y ordenable por fecha: qué archivo
es, cuánto pesa, y a qué residencial pertenece — sin importar si es una
foto de acceso o un comprobante de pago.
"""
import datetime as dt

from app.extensions import db


class ArchivoResidencial(db.Model):
    __tablename__ = "archivos_residencial"

    id = db.Column(db.BigInteger, primary_key=True)
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"), nullable=False)
    # La clave que ya devuelve services/storage.py — sirve tanto en modo
    # local como en modo Spaces, sin cambios.
    clave = db.Column(db.String(255), nullable=False)
    tamano_bytes = db.Column(db.BigInteger, nullable=False)
    # String simple, no ENUM de Postgres — a diferencia de otras columnas
    # de este proyecto, esta tabla es NUEVA, y db.create_all() la crea
    # ANTES de que corra la lista de migraciones (donde normalmente se
    # crean los tipos ENUM con el bloque DO/EXCEPTION) — el tipo no
    # existiría todavía en el momento en que la tabla lo necesita. La
    # validación de que solo sea 'acceso' o 'comprobante' se hace en la
    # capa de servicio (cuota_almacenamiento.py), no en la base.
    tipo = db.Column(db.String(20), nullable=False)
    # Trazabilidad — de cuál registro viene este archivo. Ninguno se usa
    # para decidir QUÉ borrar (eso es solo por fecha, sin importar el
    # tipo); son solo referencia para poder rastrear un archivo hasta su
    # origen si hace falta.
    evento_acceso_id = db.Column(db.BigInteger, db.ForeignKey("eventos_acceso.id"))
    pago_id = db.Column(db.BigInteger, db.ForeignKey("pagos.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, index=True)

    residencial = db.relationship("Residencial", foreign_keys=[residencial_id])

    def to_dict(self):
        return {
            "id": self.id,
            "clave": self.clave,
            "tamano_bytes": self.tamano_bytes,
            "tipo": self.tipo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
