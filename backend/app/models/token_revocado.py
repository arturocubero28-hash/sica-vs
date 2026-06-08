"""
Modelo TokenRevocado — blacklist de JWT.

Cuando un usuario cierra sesión, el jti (identificador único) de su token
se guarda aquí. En cada request se verifica que el jti no esté en esta tabla.
Así un token deja de ser válido inmediatamente al hacer logout, aunque no
haya expirado todavía.

Una tarea Celery limpia los registros ya expirados cada noche.
"""
import datetime as dt
from app.extensions import db


class TokenRevocado(db.Model):
    __tablename__ = "tokens_revocados"

    id          = db.Column(db.BigInteger, primary_key=True)
    jti         = db.Column(db.String(64), unique=True, nullable=False, index=True)
    usuario_id  = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    # Cuándo expira el token original (para poder limpiarlo después)
    expira_en   = db.Column(db.DateTime(timezone=True), nullable=False)
    revocado_en = db.Column(db.DateTime(timezone=True),
                            default=lambda: dt.datetime.now(dt.timezone.utc))

    @classmethod
    def esta_revocado(cls, jti):
        if not jti:
            return False
        return db.session.query(
            cls.query.filter_by(jti=jti).exists()
        ).scalar()
