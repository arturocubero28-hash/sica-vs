"""
Log de auditoría forense — registra accesos al sistema para diagnóstico.
Cada entrada guarda: usuario, acción (endpoint), método HTTP, IP, timestamp
y el status code de la respuesta.
"""
import uuid
import datetime as dt
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


class LogAuditoria(db.Model):
    __tablename__ = "log_auditoria"

    id          = db.Column(db.BigInteger, primary_key=True)
    usuario_id  = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=True)
    email       = db.Column(db.String(120))           # por si el usuario no existe aún
    rol         = db.Column(db.String(30))
    metodo      = db.Column(db.String(10))            # GET, POST, etc.
    endpoint    = db.Column(db.String(200))           # /api/v1/auth/login
    status_code = db.Column(db.Integer)               # 200, 401, 500...
    ip          = db.Column(db.String(45))            # IPv4 o IPv6
    user_agent  = db.Column(db.String(300))
    created_at  = db.Column(db.DateTime(timezone=True), default=_now)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def to_dict(self):
        return {
            "id":           self.id,
            "email":        self.email or "—",
            "rol":          self.rol or "—",
            "metodo":       self.metodo,
            "endpoint":     self.endpoint,
            "status_code":  self.status_code,
            "ip":           self.ip,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }
