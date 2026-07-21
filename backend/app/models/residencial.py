"""
Modelo de Residencial — la unidad de cliente/facturación para el futuro SaaS.

DISEÑO ACORDADO CON EL USUARIO (Día 37, sesión de bases multi-residencial):
  - Un admin = una Residencial = un cliente que factura. No es una tabla
    separada de "tenants" con su propia jerarquía compleja — es simplemente
    el admin dueño con un nombre y un logo configurables, y todo lo que ese
    admin (o su/s supervisor/es) crean cuelga de esa misma Residencial.
  - Hoy, en Villas del Sol, existe UNA sola fila acá — el comportamiento del
    sistema no cambia en nada porque todo sigue resolviendo al mismo valor.
  - El día que haya un segundo cliente, se crea una segunda fila con su
    propio admin, y el filtrado por residencial_id (ya presente en Usuario,
    Unidad, AccesoFisico y Dispositivo) empieza a separar los datos de
    verdad, sin haber tenido que tocar esas tablas de nuevo.

Quién pertenece a esta Residencial:
  - El admin dueño (Usuario.residencial_id apunta acá, igual que el resto)
  - Todo lo que ese admin o sus supervisores creen (guardias, cajeros,
    residentes, unidades, puntos de acceso, dispositivos Pi) hereda el
    mismo residencial_id al momento de crearse — ver cada endpoint de
    creación para el detalle de la herencia.

Quién NO pertenece a ninguna Residencial (residencial_id queda NULL):
  - super_admin y desarrollador: son roles a nivel de la plataforma SaaS,
    no de un cliente específico.
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Residencial(db.Model):
    __tablename__ = "residenciales"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    # El admin dueño — una Residencial tiene exactamente un admin raíz.
    # Los supervisores que ese admin cree tienen el mismo residencial_id,
    # pero NO son el "admin_id" de la Residencial (no pueden, por ejemplo,
    # transferir la propiedad ni crear otros supervisores — ver
    # app/utils/passwords.py puede_gestionar_rol()).
    admin_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    nombre = db.Column(db.String(160), nullable=False)
    logo_archivo = db.Column(db.String(255))  # nombre de archivo guardado (mismo patrón que comunicados/comprobantes)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow,
                           onupdate=dt.datetime.utcnow)

    admin = db.relationship("Usuario", foreign_keys=[admin_id], lazy="joined")

    def to_dict(self, incluir_stats=False):
        d = {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "logo_archivo": self.logo_archivo,
            "activa": self.activa,
            "admin": {
                "nombre": f"{self.admin.nombre} {self.admin.apellido}",
                "email": self.admin.email,
            } if self.admin else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if incluir_stats:
            from app.models.usuario import Usuario
            from app.models.dispositivo import Dispositivo
            d["stats"] = {
                "guardias": Usuario.query.filter_by(residencial_id=self.id, rol="guardia").count(),
                "cajeros": Usuario.query.filter_by(residencial_id=self.id, rol="cajero").count(),
                "supervisores": Usuario.query.filter_by(residencial_id=self.id, rol="supervisor").count(),
                "residentes": Usuario.query.filter_by(residencial_id=self.id, rol="residente").count(),
                "dispositivos": Dispositivo.query.filter_by(residencial_id=self.id).count(),
            }
        return d
