"""
Registro de fotos de accesos por residencial — Día 50, sistema de
suscripciones.

Por qué existe esta tabla, y no basta con las fotos que ya se guardan en
Visita/EventoAcceso: para poder aplicar la cuota de almacenamiento del
plan de cada residencial (borrar la foto MÁS VIEJA cuando se excede el
límite), hace falta saber, de forma centralizada y ordenable por fecha:
qué archivo es, cuánto pesa, y a qué residencial pertenece. Esa
información hoy está dispersa (foto_identidad y foto_placa son campos
sueltos en Visita), así que se registra acá aparte en el momento de
guardarse, sin duplicar el archivo en sí — solo la referencia.

Alcance: fotos de EVENTOS DE ACCESO (identidad, placa) — no
comprobantes de pago, logos, ni otros archivos, que tienen sus propias
reglas de retención (o ninguna).
"""
import datetime as dt

from app.extensions import db


class FotoAcceso(db.Model):
    __tablename__ = "fotos_acceso"

    id = db.Column(db.BigInteger, primary_key=True)
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"), nullable=False)
    # La clave que ya devuelve services/storage.py — sirve tanto en modo
    # local como en modo Spaces, sin cambios.
    clave = db.Column(db.String(255), nullable=False)
    tamano_bytes = db.Column(db.BigInteger, nullable=False)
    # A qué evento de acceso pertenece (para trazabilidad) — no se usa
    # para el borrado (que se hace directo por fecha), solo referencia.
    evento_acceso_id = db.Column(db.BigInteger, db.ForeignKey("eventos_acceso.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, index=True)

    residencial = db.relationship("Residencial", foreign_keys=[residencial_id])

    def to_dict(self):
        return {
            "id": self.id,
            "clave": self.clave,
            "tamano_bytes": self.tamano_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
