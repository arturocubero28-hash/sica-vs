"""
Modelo de ejemplo: Usuario.
Sirve como PATRÓN para que el equipo cree sus propios modelos.

Convenciones:
  * Cada modelo en su propio archivo dentro de app/models/
  * Siempre id, created_at, updated_at
  * uuid_publico para exponer en la API (nunca el id interno)
  * Método to_dict() para serializar de forma controlada
"""
import uuid
import datetime as dt
import bcrypt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False,
                             default=uuid.uuid4)
    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    telefono = db.Column(db.String(30))
    # Información extendida del residente (titular y dependientes)
    dni = db.Column(db.String(20))                        # número de identidad
    rtn = db.Column(db.String(20))                        # para recibos SAR (futuro)
    direccion_exacta = db.Column(db.String(255))          # dirección domiciliar completa
    profesion = db.Column(db.String(120))
    contacto_emergencia_nombre = db.Column(db.String(120))
    contacto_emergencia_telefono = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    # rol global: super_admin | admin | guardia | residente
    rol = db.Column(db.String(20), nullable=False, default="residente")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=False)
    biometria_activa = db.Column(db.Boolean, nullable=False, default=False)
    ultimo_acceso = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow,
                           onupdate=dt.datetime.utcnow)

    # ---- Manejo seguro de contraseñas (bcrypt) ----
    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    # ---- Serialización para la API (nunca expone el hash ni el id interno) ----
    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "apellido": self.apellido,
            "email": self.email,
            "telefono": self.telefono,
            "dni": self.dni,
            "rtn": self.rtn,
            "direccion_exacta": self.direccion_exacta,
            "profesion": self.profesion,
            "contacto_emergencia_nombre": self.contacto_emergencia_nombre,
            "contacto_emergencia_telefono": self.contacto_emergencia_telefono,
            "rol": self.rol,
            "activo": self.activo,
            "debe_cambiar_password": self.debe_cambiar_password,
            "biometria_activa": self.biometria_activa,
        }
