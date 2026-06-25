"""
Modelo de Dispositivo — las Raspberry Pi que controlan los accesos físicos.

Cada Pi se autentica con su propio token (no uno compartido). El token
identifica a qué punto de acceso pertenece, de modo que al sincronizar solo
recibe las tarjetas y trancas de su punto, y al reportar eventos solo puede
reportar lo de su punto.

Pensado para multi-tenancy futuro: el campo residencial_id queda preparado
(hoy NULL = la única residencial) para que, al pasar a SaaS, cada token quede
ligado también a su residencial sin migrar el modelo.
"""
import uuid
import datetime as dt
import secrets

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


def generar_token():
    """Token aleatorio robusto para autenticar la Pi (URL-safe, ~43 chars)."""
    return secrets.token_urlsafe(32)


class Dispositivo(db.Model):
    __tablename__ = "dispositivos_pi"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    nombre = db.Column(db.String(80), nullable=False)            # "Pi Acceso Principal"
    punto_acceso = db.Column(db.String(80))                      # debe coincidir con el de las trancas
    token = db.Column(db.String(64), unique=True, nullable=False, default=generar_token)
    activo = db.Column(db.Boolean, nullable=False, default=True) # revocar = activo False
    # Preparado para SaaS (hoy NULL). No se usa todavía en la lógica.
    residencial_id = db.Column(db.BigInteger)
    ultima_sync = db.Column(db.DateTime(timezone=True))          # cuándo descargó su copia por última vez
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    def to_dict(self, incluir_token=False):
        d = {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "punto_acceso": self.punto_acceso,
            "activo": self.activo,
            "ultima_sync": self.ultima_sync.isoformat() if self.ultima_sync else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        # El token solo se muestra cuando se pide explícitamente (al crear o
        # al regenerar), nunca en listados generales.
        if incluir_token:
            d["token"] = self.token
        return d
