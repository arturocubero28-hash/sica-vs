"""
Modelo de Plan de suscripción — Día 50.

Cada Plan define los límites de un nivel de servicio que el desarrollador
vende a sus clientes (residenciales): cuántas casas, cuántos usuarios, y
cuánto almacenamiento de fotos de acceso incluye. El desarrollador
gestiona los planes desde su propia pestaña del panel dev; al crear una
residencial nueva (o más adelante), le asigna uno.

Los precios de venta (precio_mensual) son una decisión de negocio del
usuario, no algo que este sistema calcule — el modelo solo los guarda.
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Plan(db.Model):
    __tablename__ = "planes"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    nombre = db.Column(db.String(80), nullable=False)
    max_casas = db.Column(db.Integer, nullable=False)
    max_usuarios = db.Column(db.Integer, nullable=False)
    almacenamiento_gb = db.Column(db.Integer, nullable=False)
    precio_mensual = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    # Un plan retirado no se borra (residenciales viejas pueden seguir en
    # él) — se desactiva, y deja de ofrecerse para asignar a residenciales
    # nuevas.
    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Orden de presentación en el panel — no el id, así se pueden reordenar
    # los planes en la lista sin que dependa de cuándo se creó cada uno.
    orden = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow,
                           onupdate=dt.datetime.utcnow)

    def to_dict(self, incluir_stats=False):
        d = {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "max_casas": self.max_casas,
            "max_usuarios": self.max_usuarios,
            "almacenamiento_gb": self.almacenamiento_gb,
            "precio_mensual": float(self.precio_mensual),
            "activo": self.activo,
            "orden": self.orden,
        }
        if incluir_stats:
            from app.models.residencial import Residencial
            d["stats"] = {
                "residenciales": Residencial.query.filter_by(plan_id=self.id).count(),
            }
        return d
