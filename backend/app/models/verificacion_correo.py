"""
Modelo VerificacionCorreo (Día 73) — confirmar que un correo llega ANTES
de crear nada con él.

LA REGLA: no se crea ninguna cuenta (alta normal, miembro nuevo, paso del
padrón a residente) hasta que Resend confirme que un correo a esa
dirección fue ENTREGADO. Si rebota, no se creó nada y se corrige la
dirección sin dejar restos.

POR QUÉ HACE FALTA UNA TABLA: crear la cuenta primero y después mirar si
el correo llegó deja, cuando rebota, una cuenta pendiente que nunca se va
a activar — y peor, en el padrón dejaba a la persona marcada como "con
acceso", así que al corregir el correo el segundo intento fallaba con
"esta persona ya tiene acceso al sistema". El único orden que no deja
basura es verificar primero y crear después.

Pero la confirmación de entrega es asíncrona: llega por webhook segundos
después del envío. Esta tabla es lo que conecta las dos mitades: guarda
el id que Resend le asignó al envío, el webhook la actualiza al llegar el
aviso, y el endpoint que crea la cuenta solo acepta una verificación en
estado "entregado" y para el mismo correo.

El correo de verificación es corto y honesto: avisa que la administración
está registrando la cuenta y que en minutos llega otro correo con el
enlace para la contraseña. No lleva token ni nada utilizable.
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


# Una verificación sirve por un rato: si alguien deja el formulario
# abierto una tarde entera, al volver se le pide verificar otra vez.
# Una dirección que existía a las 9 sigue existiendo a las 10, pero el
# punto es que la confirmación sea de ESTE intento, no de cualquiera.
VIGENCIA = dt.timedelta(hours=2)


class VerificacionCorreo(db.Model):
    __tablename__ = "verificaciones_correo"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False,
                             default=uuid.uuid4)
    email = db.Column(db.String(255), nullable=False, index=True)
    # El id que Resend le dio al envío: es lo que trae el webhook.
    resend_id = db.Column(db.String(64), index=True)
    # enviando -> enviado -> entregado | rebotado | queja | demorado | error
    estado = db.Column(db.String(20), nullable=False, default="enviando")
    detalle = db.Column(db.Text)
    residencial_id = db.Column(db.BigInteger, index=True)
    creado_por_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    # Una vez usada para crear una cuenta no sirve para otra: evita que
    # una sola verificación habilite varias altas con el mismo correo.
    usada = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    actualizado = db.Column(db.DateTime(timezone=True), default=_now)

    def vigente(self):
        creada = self.created_at
        if creada is not None and creada.tzinfo is None:
            creada = creada.replace(tzinfo=dt.timezone.utc)
        return creada is not None and (_now() - creada) <= VIGENCIA

    def sirve_para(self, email):
        """¿Esta verificación habilita crear una cuenta con este correo?"""
        return (self.estado == "entregado" and not self.usada and self.vigente()
                and (self.email or "").lower() == (email or "").strip().lower())

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "email": self.email,
            "estado": self.estado,
            "detalle": self.detalle,
            "usada": bool(self.usada),
            "actualizado": self.actualizado.isoformat() if self.actualizado else None,
        }
