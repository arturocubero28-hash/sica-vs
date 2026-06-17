"""
Modelo CredencialWebAuthn — credenciales biométricas (Passkeys).

Cada credencial representa un dispositivo (celular) que el usuario registró
para entrar con huella/Face ID. Guardamos solo la LLAVE PÚBLICA y un contador
anti-clonación; la biometría nunca sale del dispositivo del usuario.
"""
import datetime as dt
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


class CredencialWebAuthn(db.Model):
    __tablename__ = "credenciales_webauthn"

    id = db.Column(db.BigInteger, primary_key=True)
    usuario_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    # credential_id que devuelve el autenticador (identifica la credencial), en base64url
    credential_id = db.Column(db.String(400), unique=True, nullable=False, index=True)
    # llave pública en formato COSE, base64url
    public_key = db.Column(db.Text, nullable=False)
    # contador de firmas, para detectar clonación
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)
    # nombre amigable del dispositivo (ej. "Samsung de Arturo")
    nombre_dispositivo = db.Column(db.String(120))
    transports = db.Column(db.String(120))  # ej. "internal,hybrid"
    creada_en = db.Column(db.DateTime(timezone=True), default=_now)
    ultimo_uso = db.Column(db.DateTime(timezone=True))

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def to_dict(self):
        return {
            "id": self.id,
            "nombre_dispositivo": self.nombre_dispositivo or "Dispositivo",
            "creada_en": self.creada_en.isoformat() if self.creada_en else None,
            "ultimo_uso": self.ultimo_uso.isoformat() if self.ultimo_uso else None,
        }
