"""
Modelo CuentaBancaria (Día 76) — cuentas autorizadas para pagar las cuotas.

El administrador configura en el panel las cuentas del patronato a las que
los residentes pueden transferir o depositar: el banco y el número (más,
opcional, a nombre de quién está y el tipo). Los residentes las ven en la
app y en el portal web, junto a sus cuotas, con un botón para copiar el
número. Antes esa información circulaba por WhatsApp y cada quien tenía
una versión distinta.

Es solo información para mostrar: no interviene en ningún cálculo ni en la
aprobación de pagos. Por eso se borra de verdad (no hay historial que
cuidar) y no se valida el número contra ningún formato de banco: cada banco
de Honduras usa el suyo.
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db

TIPOS_CUENTA = ("ahorro", "cheques")
MAX_CUENTAS = 10


class CuentaBancaria(db.Model):
    __tablename__ = "cuentas_bancarias"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"), index=True)
    banco = db.Column(db.String(80), nullable=False)
    numero = db.Column(db.String(40), nullable=False)
    titular = db.Column(db.String(120))     # a nombre de quién está (opcional)
    tipo = db.Column(db.String(20))         # "ahorro" | "cheques" (opcional)
    orden = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "banco": self.banco,
            "numero": self.numero,
            "titular": self.titular,
            "tipo": self.tipo,
        }
