"""
Modelo de Cámara ONVIF/RTSP para el módulo de Monitoreo.
"""
import uuid
import datetime as dt
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Camara(db.Model):
    __tablename__ = "camaras"

    id           = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    nombre       = db.Column(db.String(100), nullable=False)
    ip           = db.Column(db.String(45), nullable=False)
    puerto_rtsp  = db.Column(db.Integer, nullable=False, default=554)
    puerto_onvif = db.Column(db.Integer, nullable=False, default=80)
    usuario      = db.Column(db.String(60))
    password     = db.Column(db.String(120))
    ruta_stream  = db.Column(db.String(200), default="/Streaming/Channels/101")
    acceso_id    = db.Column(db.BigInteger, db.ForeignKey("accesos_fisicos.id"))
    activa       = db.Column(db.Boolean, nullable=False, default=True)
    orden        = db.Column(db.Integer, nullable=False, default=0)
    created_at   = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at   = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    def url_rtsp(self):
        """Construye la URL RTSP completa con credenciales."""
        cred = ""
        if self.usuario:
            cred = f"{self.usuario}:{self.password or ''}@"
        return f"rtsp://{cred}{self.ip}:{self.puerto_rtsp}{self.ruta_stream or ''}"

    def to_dict(self, incluir_credenciales=False):
        d = {
            "id":           str(self.uuid_publico),
            "nombre":       self.nombre,
            "ip":           self.ip,
            "puerto_rtsp":  self.puerto_rtsp,
            "puerto_onvif": self.puerto_onvif,
            "usuario":      self.usuario,
            "ruta_stream":  self.ruta_stream,
            "acceso_id":    self.acceso_id,
            "activa":       self.activa,
            "orden":        self.orden,
        }
        if incluir_credenciales:
            d["password"] = self.password
        return d
