"""
Pagos de suscripción — Día 50, sistema de suscripciones.

Lo que el admin de una residencial le paga al DESARROLLADOR por el
servicio (distinto de Pago en models/cuenta.py, que es lo que los
RESIDENTES le pagan a SU administrador — dos negocios completamente
separados, aunque el patrón de "subir comprobante -> revisar ->
aprobar/rechazar" sea deliberadamente el mismo, para que el desarrollador
reconozca la pantalla de un vistazo).
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class SuscripcionPago(db.Model):
    __tablename__ = "suscripcion_pagos"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"), nullable=False)

    # El plan que se está pagando. Puede ser el plan ACTUAL de la
    # residencial (pago normal, renovación) o uno DISTINTO (el admin
    # está pidiendo upgrade al mismo tiempo que paga). No se asume cuál
    # es — se resuelve comparando contra residencial.plan_id al momento
    # de crear el registro (ver es_upgrade).
    plan_id = db.Column(db.BigInteger, db.ForeignKey("planes.id"), nullable=False)
    # Snapshot del precio en el momento del pago — NO se lee el precio
    # actual del plan para mostrar el historial. Si el precio de un plan
    # cambia más adelante, los pagos viejos tienen que seguir mostrando
    # lo que realmente se cobró ese mes.
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    es_upgrade = db.Column(db.Boolean, nullable=False, default=False)

    metodo = db.Column(db.String(20), nullable=False, default="comprobante")  # 'comprobante' | 'pasarela'
    comprobante_archivo = db.Column(db.String(255))  # clave del storage, si metodo='comprobante'
    referencia_pasarela = db.Column(db.String(120))  # id de transacción, si metodo='pasarela' (Etapa 9)

    estado = db.Column(db.String(20), nullable=False, default="en_revision")  # en_revision | aprobado | rechazado
    notas_rechazo = db.Column(db.String(500))

    subido_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    revisado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    revisado_en = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, index=True)

    residencial = db.relationship("Residencial", foreign_keys=[residencial_id])
    plan = db.relationship("Plan", foreign_keys=[plan_id])
    subido_por_usuario = db.relationship("Usuario", foreign_keys=[subido_por])
    revisado_por_usuario = db.relationship("Usuario", foreign_keys=[revisado_por])

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "residencial": {"id": str(self.residencial.uuid_publico), "nombre": self.residencial.nombre}
                if self.residencial else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "monto": float(self.monto),
            "es_upgrade": self.es_upgrade,
            "metodo": self.metodo,
            "comprobante_archivo": self.comprobante_archivo,
            "referencia_pasarela": self.referencia_pasarela,
            "estado": self.estado,
            "notas_rechazo": self.notas_rechazo,
            "subido_por": f"{self.subido_por_usuario.nombre} {self.subido_por_usuario.apellido}"
                if self.subido_por_usuario else None,
            "revisado_por": f"{self.revisado_por_usuario.nombre} {self.revisado_por_usuario.apellido}"
                if self.revisado_por_usuario else None,
            "revisado_en": self.revisado_en.isoformat() if self.revisado_en else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
