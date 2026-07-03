"""
Modelo de DispositivoMovil — los teléfonos de los residentes y guardias que
reciben notificaciones push vía Firebase Cloud Messaging (FCM).

Cada vez que un usuario inicia sesión en la app móvil, se guarda (o actualiza)
el token FCM de su teléfono asociado a su usuario. Un mismo usuario puede tener
varios dispositivos (celular + tablet), y un mismo teléfono puede ser usado por
distintos usuarios en distintos momentos (por eso el token es único, pero se
reasigna al último que inició sesión).

Distinto del modelo Dispositivo (esas son las Raspberry Pi de accesos físicos).
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class DispositivoMovil(db.Model):
    __tablename__ = "dispositivos_moviles"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    # El token FCM identifica al teléfono ante Firebase. Es único: si el mismo
    # teléfono lo reutiliza otro usuario, se reasigna (last-write-wins).
    fcm_token = db.Column(db.Text, unique=True, nullable=False)
    usuario_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    plataforma = db.Column(db.String(20), default="android")   # android / ios
    activo = db.Column(db.Boolean, nullable=False, default=True)
    ultima_actividad = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    usuario = db.relationship("Usuario", backref="dispositivos_moviles")

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "plataforma": self.plataforma,
            "activo": self.activo,
            "ultima_actividad": self.ultima_actividad.isoformat() if self.ultima_actividad else None,
        }
