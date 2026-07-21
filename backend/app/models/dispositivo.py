"""
Modelo de Dispositivo — las Raspberry Pi que controlan los accesos físicos.

Cada Pi se autentica con su propio token (no uno compartido). El token
identifica a qué punto de acceso pertenece, de modo que al sincronizar solo
recibe las tarjetas y trancas de su punto, y al reportar eventos solo puede
reportar lo de su punto.

DEVICE-06 (Auditoría Día 35): el token se guarda como HASH (SHA-256), no en
texto plano. Se usa SHA-256 simple (no bcrypt/argon2 con salt) a propósito:
el token ya es aleatorio de alta entropía (32 bytes de secrets.token_urlsafe),
a diferencia de una contraseña de usuario que puede ser débil — no necesita
salt para resistir fuerza bruta, y un hash simple permite comparar con un
WHERE directo en la consulta en vez de traer todos los dispositivos y
comparar uno por uno en Python.

El token en texto plano solo existe en el momento de crear/regenerar el
dispositivo (se muestra una vez al admin para copiarlo a la Pi) — nunca se
vuelve a poder leer desde la base de datos.

Pensado para multi-tenancy futuro: el campo residencial_id queda preparado
(hoy NULL = la única residencial) para que, al pasar a SaaS, cada token quede
ligado también a su residencial sin migrar el modelo.
"""
import uuid
import datetime as dt
import secrets
import hashlib

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


def generar_token():
    """Token aleatorio robusto para autenticar la Pi (URL-safe, ~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 del token, en hexadecimal. Determinístico — permite buscar
    por igualdad directa en la base sin tener que comparar uno por uno."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Dispositivo(db.Model):
    __tablename__ = "dispositivos_pi"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    nombre = db.Column(db.String(80), nullable=False)            # "Pi Acceso Principal"
    # "acceso" (trancas/GPIO) o "camara" (agente de video NVR). Mismo modelo,
    # mismo token/revocación; el AGENTE (programa Python) que corre en la Pi
    # es distinto para cada tipo, por simplicidad de mantenimiento en sitio.
    tipo = db.Column(db.String(20), nullable=False, default="acceso")
    punto_acceso = db.Column(db.String(80))                      # debe coincidir con el de las trancas
    # DEVICE-06: se guarda el HASH del token, nunca el token en claro.
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True) # revocar = activo False
    # Bases para multi-residencial (Día 37): a qué Residencial pertenece esta
    # Pi. El desarrollador la asigna al crear el dispositivo o después, desde
    # el panel — es lo que le dice a /sincronizar y /validar-tarjeta qué
    # tarjetas y trancas debe descargar (solo las de SU residencial). Antes
    # era un BigInteger suelto sin FK, preparado pero sin usar; ahora es una
    # referencia real. Sigue siendo NULL-able: una Pi sin asignar no
    # descarga nada hasta que el desarrollador la asocie a una residencial.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    ultima_sync = db.Column(db.DateTime(timezone=True))          # cuándo descargó su copia por última vez
    # Solo aplica a tipo='camara': latido periódico para saber si el agente
    # de video sigue conectado (distinto de ultima_sync, que es de accesos).
    ultimo_heartbeat = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    def to_dict(self, token_plano=None):
        residencial = None
        if self.residencial_id:
            from app.models.residencial import Residencial
            r = Residencial.query.get(self.residencial_id)
            if r:
                residencial = {"id": str(r.uuid_publico), "nombre": r.nombre}
        d = {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "tipo": self.tipo,
            "punto_acceso": self.punto_acceso,
            "activo": self.activo,
            "residencial": residencial,
            "ultima_sync": self.ultima_sync.isoformat() if self.ultima_sync else None,
            "ultimo_heartbeat": self.ultimo_heartbeat.isoformat() if self.ultimo_heartbeat else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        # DEVICE-06: el token en claro NUNCA se guarda ni se puede recuperar
        # de la base — solo existe en el instante de crear/regenerar, cuando
        # se lo pasa explícitamente a to_dict() para mostrárselo al admin
        # una única vez.
        if token_plano:
            d["token"] = token_plano
        return d
