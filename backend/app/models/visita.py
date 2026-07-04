"""
Módulo 3 — Visitas, Códigos QR y Eventos de Acceso.

Tres modalidades de QR:
  - unica:      una sola entrada
  - recurrente: vigencia por periodo (libre o una_por_dia)
  - repartidor: delivery, empresa de envío
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


def _uuid():
    return db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)


class AccesoFisico(db.Model):
    __tablename__ = "accesos_fisicos"
    id = db.Column(db.BigInteger, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Hardware: relay/GPIO que acciona la tranca de este acceso y duración del pulso.
    # relay_pin = número de pin GPIO de la Raspberry Pi que cierra el contacto seco.
    # pulso_ms  = milisegundos que dura el pulso (configurable; a confirmar con el ingeniero).
    relay_pin = db.Column(db.Integer)
    pulso_ms = db.Column(db.Integer, nullable=False, default=800)
    # Punto de acceso (identifica la Raspberry Pi que controla este dispositivo).
    # Los accesos del mismo punto los maneja la misma Pi. Ej: "Acceso Principal".
    punto_acceso = db.Column(db.String(80))
    # Dirección fija de la tranca: "entrada" o "salida". Cada punto tiene una
    # tranca de entrada y una de salida; la dirección del evento la define por
    # qué tranca pasó la tarjeta (no se adivina). Default "entrada".
    direccion = db.Column(db.String(10), nullable=False, default="entrada")

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "activo": self.activo,
            "relay_pin": self.relay_pin,
            "pulso_ms": self.pulso_ms,
            "punto_acceso": self.punto_acceso,
            "direccion": self.direccion,
        }


class Visita(db.Model):
    __tablename__ = "visitas"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid()
    cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False, index=True)
    generada_por = db.Column(db.BigInteger, db.ForeignKey("residentes.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # unica | recurrente | repartidor

    nombre_visitante = db.Column(db.String(160), nullable=False)
    documento_id = db.Column(db.String(40))
    telefono = db.Column(db.String(30))
    empresa = db.Column(db.String(120))
    placa_vehiculo = db.Column(db.String(20))
    en_vehiculo = db.Column(db.Boolean, nullable=False, default=False)

    valido_desde = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    valido_hasta = db.Column(db.DateTime(timezone=True))
    modo_recurrencia = db.Column(db.String(20))  # libre | una_por_dia

    estado = db.Column(db.String(20), nullable=False, default="activa", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    qr = db.relationship("CodigoQR", backref="visita", uselist=False, lazy="joined")
    eventos = db.relationship("EventoAcceso", backref="visita", lazy="select")
    residente = db.relationship("Residente", foreign_keys=[generada_por], lazy="joined")

    def estado_efectivo(self):
        """Estado real considerando los eventos de acceso y el vencimiento.
        Distingue 'adentro' (último evento fue entrada) y 'salio' (último fue salida),
        que el campo 'estado' por sí solo no refleja."""
        ultimo = None
        if self.eventos:
            def _key(e):
                t = e.ocurrido_en
                if t is None:
                    return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=dt.timezone.utc)
                return t
            ultimo = max(self.eventos, key=_key)
        if ultimo:
            return "adentro" if ultimo.direccion == "entrada" else "salio"

        # Sin eventos: revisar si venció por fecha (visita creada y nunca usada).
        # Aplica a las visitas únicas/temporales con valido_hasta en el pasado.
        if self.estado == "activa" and self.valido_hasta:
            ahora = dt.datetime.now(dt.timezone.utc)
            vence = self.valido_hasta
            if vence.tzinfo is None:
                vence = vence.replace(tzinfo=dt.timezone.utc)
            if vence < ahora:
                return "expirada"

        return self.estado  # activa, expirada, revocada (aún sin eventos)

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "tipo": self.tipo,
            "nombre_visitante": self.nombre_visitante,
            "documento_id": self.documento_id,
            "telefono": self.telefono,
            "empresa": self.empresa,
            "placa_vehiculo": self.placa_vehiculo,
            "en_vehiculo": self.en_vehiculo,
            "valido_desde": self.valido_desde.isoformat() if self.valido_desde else None,
            "valido_hasta": self.valido_hasta.isoformat() if self.valido_hasta else None,
            "modo_recurrencia": self.modo_recurrencia,
            "estado": self.estado,
            "estado_real": self.estado_efectivo(),
            "qr_token": str(self.qr.token) if self.qr else None,
            "codigo_numerico": self.qr.codigo_numerico if self.qr else None,
            "generada_por": (
                f"{self.residente.usuario.nombre} {self.residente.usuario.apellido}"
                if self.residente and self.residente.usuario else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "hora_entrada": self._hora_evento("entrada"),
            "hora_salida": self._hora_evento("salida"),
        }

    def _hora_evento(self, direccion):
        """Devuelve la hora del primer evento de entrada / último de salida."""
        eventos = [e for e in self.eventos if e.direccion == direccion]
        if not eventos:
            return None
        # Entrada: la primera; Salida: la última
        elegido = (min if direccion == "entrada" else max)(
            eventos,
            key=lambda e: e.ocurrido_en or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        )
        return elegido.ocurrido_en.isoformat() if elegido.ocurrido_en else None


class CodigoQR(db.Model):
    __tablename__ = "codigos_qr"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid()
    visita_id = db.Column(db.BigInteger, db.ForeignKey("visitas.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    codigo_numerico = db.Column(db.String(8), unique=True)  # para delivery: código corto dictable
    usos = db.Column(db.Integer, nullable=False, default=0)
    revocado = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)


class EventoAcceso(db.Model):
    __tablename__ = "eventos_acceso"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid()
    origen = db.Column(db.String(20), nullable=False)  # residente | visita
    direccion = db.Column(db.String(10), nullable=False)  # entrada | salida
    acceso_id = db.Column(db.BigInteger, db.ForeignKey("accesos_fisicos.id"), nullable=False)

    tarjeta_id = db.Column(db.BigInteger, db.ForeignKey("tarjetas_proximidad.id"))
    residente_id = db.Column(db.BigInteger, db.ForeignKey("residentes.id"))

    visita_id = db.Column(db.BigInteger, db.ForeignKey("visitas.id"), index=True)
    guardia_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    foto_identidad = db.Column(db.String(255))
    foto_placa = db.Column(db.String(255))
    foto_numero_asignado = db.Column(db.String(255))  # foto extra: número asignado a la visita

    en_vehiculo = db.Column(db.Boolean, nullable=False, default=False)
    placa_vehiculo = db.Column(db.String(20))
    ocurrido_en = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    sincronizado = db.Column(db.Boolean, nullable=False, default=True)
    # Identificador único que genera la Raspberry Pi para cada evento. Permite
    # ignorar duplicados si la Pi reenvía eventos tras estar sin conexión
    # (idempotencia). NULL para eventos creados directo en el servidor.
    id_externo = db.Column(db.String(80), unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    guardia = db.relationship("Usuario", foreign_keys=[guardia_id], lazy="joined")

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "origen": self.origen,
            "direccion": self.direccion,
            "en_vehiculo": self.en_vehiculo,
            "placa_vehiculo": self.placa_vehiculo,
            "guardia": (
                f"{self.guardia.nombre} {self.guardia.apellido}" if self.guardia else None
            ),
            "foto_identidad": self.foto_identidad,
            "foto_placa": self.foto_placa,
            "foto_numero_asignado": self.foto_numero_asignado,
            "ocurrido_en": self.ocurrido_en.isoformat() if self.ocurrido_en else None,
        }
