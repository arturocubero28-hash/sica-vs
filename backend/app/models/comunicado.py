"""
Modelo de Comunicado — anuncios que el admin publica y los residentes ven en su Home.
"""
import uuid
import datetime as dt
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Comunicado(db.Model):
    __tablename__ = "comunicados"

    id           = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    titulo       = db.Column(db.String(160), nullable=False)
    cuerpo       = db.Column(db.Text, nullable=False)
    imagen       = db.Column(db.String(255))            # nombre de archivo opcional
    creado_por   = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    created_at   = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at   = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    autor = db.relationship("Usuario", foreign_keys=[creado_por], lazy="joined")

    def to_dict(self):
        return {
            "id":         str(self.uuid_publico),
            "titulo":     self.titulo,
            "cuerpo":     self.cuerpo,
            "imagen":     self.imagen,
            "autor": (
                f"{self.autor.nombre} {self.autor.apellido}" if self.autor else "Administración"
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
