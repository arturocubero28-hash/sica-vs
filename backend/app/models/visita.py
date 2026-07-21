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
    # NOTA: la columna 'tipo' en la base real es un ENUM de PostgreSQL
    # (tipo_acceso: vehicular | peatonal), no un VARCHAR simple. Se usa
    # sqlalchemy.Enum con create_type=False para que SQLAlchemy no intente
    # crear el tipo (ya existe) y sí le diga a Postgres que caste el valor
    # correctamente en los INSERT — sin esto, un INSERT con VARCHAR plano
    # fallaba con 'column tipo is of type tipo_acceso but expression is of
    # type character varying' (encontrado en pruebas del Día 36).
    tipo = db.Column(
        db.Enum("vehicular", "peatonal", name="tipo_acceso", create_type=False),
        nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Hardware: relay/GPIO que acciona la tranca de este acceso y duración del pulso.
    # relay_pin = número de pin GPIO de la Raspberry Pi que cierra el contacto seco.
    # pulso_ms  = milisegundos que dura el pulso (configurable; a confirmar con el ingeniero).
    relay_pin = db.Column(db.Integer)
    pulso_ms = db.Column(db.Integer, nullable=False, default=800)
    # Punto de acceso (identifica la Raspberry Pi que controla este dispositivo).
    # Los accesos del mismo punto los maneja la misma Pi. Ej: "Acceso Principal".
    punto_acceso = db.Column(db.String(80))
    # Bases para multi-residencial (Día 37): a qué Residencial pertenece este
    # punto de acceso. Importa para que el nombre "Portón Principal" de dos
    # residenciales distintas no se mezcle el día que haya un segundo cliente.
    # Se completa al crearlo, heredado del admin/supervisor que lo crea.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    # Dirección fija de la tranca: "entrada" o "salida". Cada punto tiene una
    # tranca de entrada y una de salida; la dirección del evento la define por
    # qué tranca pasó la tarjeta (no se adivina). Default "entrada".
    # ENUM real de PostgreSQL (direccion_acceso) — fix Día 36.
    direccion = db.Column(
        db.Enum("entrada", "salida", name="direccion_acceso", create_type=False),
        nullable=False, default="entrada")

    def to_dict(self):
        residencial = None
        if self.residencial_id:
            from app.models.residencial import Residencial
            r = Residencial.query.get(self.residencial_id)
            if r:
                residencial = {"id": str(r.uuid_publico), "nombre": r.nombre}
        return {
            "id": self.id,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "activo": self.activo,
            "relay_pin": self.relay_pin,
            "pulso_ms": self.pulso_ms,
            "punto_acceso": self.punto_acceso,
            "direccion": self.direccion,
            "residencial": residencial,
        }


class Visita(db.Model):
    __tablename__ = "visitas"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid()
    cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False, index=True)
    generada_por = db.Column(db.BigInteger, db.ForeignKey("residentes.id"), nullable=False)
    # NOTA: 'tipo' y 'modo_recurrencia' son ENUMs reales de PostgreSQL
    # (tipo_visita, modo_recurrencia), no VARCHAR. create_type=False porque
    # el tipo ya existe en la base — mismo problema y mismo fix que
    # AccesoFisico.tipo, encontrado en pruebas del Día 36.
    tipo = db.Column(
        db.Enum("unica", "recurrente", "repartidor", name="tipo_visita", create_type=False),
        nullable=False)

    nombre_visitante = db.Column(db.String(160), nullable=False)
    documento_id = db.Column(db.String(40))
    telefono = db.Column(db.String(30))
    empresa = db.Column(db.String(120))
    placa_vehiculo = db.Column(db.String(20))
    en_vehiculo = db.Column(db.Boolean, nullable=False, default=False)

    valido_desde = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    valido_hasta = db.Column(db.DateTime(timezone=True))
    modo_recurrencia = db.Column(
        db.Enum("libre", "una_por_dia", name="modo_recurrencia", create_type=False))

    estado = db.Column(db.String(20), nullable=False, default="activa", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    qr = db.relationship("CodigoQR", backref="visita", uselist=False, lazy="joined")
    eventos = db.relationship("EventoAcceso", backref="visita", lazy="select")
    residente = db.relationship("Residente", foreign_keys=[generada_por], lazy="joined")
    cuenta = db.relationship("Cuenta", foreign_keys=[cuenta_id], lazy="joined")

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
    # ENUMs reales de PostgreSQL — fix Día 36.
    origen = db.Column(
        db.Enum("residente", "visita", name="origen_evento", create_type=False),
        nullable=False)
    direccion = db.Column(
        db.Enum("entrada", "salida", name="direccion_acceso", create_type=False),
        nullable=False)
    acceso_id = db.Column(db.BigInteger, db.ForeignKey("accesos_fisicos.id"), nullable=False)

    tarjeta_id = db.Column(db.BigInteger, db.ForeignKey("tarjetas_proximidad.id"))
    residente_id = db.Column(db.BigInteger, db.ForeignKey("residentes.id"))
    # DEVICE-06: qué Raspberry Pi generó este evento (origen='residente').
    # NULL para eventos de guardia (origen='visita'), que no vienen de una Pi.
    dispositivo_id = db.Column(db.BigInteger, db.ForeignKey("dispositivos_pi.id"))

    visita_id = db.Column(db.BigInteger, db.ForeignKey("visitas.id"), index=True)
    guardia_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    foto_identidad = db.Column(db.String(255))
    foto_placa = db.Column(db.String(255))
    foto_numero_asignado = db.Column(db.String(255))  # foto extra: número asignado a la visita

    en_vehiculo = db.Column(db.Boolean, nullable=False, default=False)
    placa_vehiculo = db.Column(db.String(20))
    # ACCESS-04: la placa que el residente declaró al crear la visita
    # (placa_vehiculo, arriba) y la que el guardia observa físicamente en la
    # entrada pueden no coincidir. Antes el backend ignoraba lo que digitaba
    # el guardia y siempre guardaba la declarada. Ahora se guardan ambas por
    # separado para poder detectar y auditar discrepancias.
    placa_observada = db.Column(db.String(20))
    ocurrido_en = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    sincronizado = db.Column(db.Boolean, nullable=False, default=True)
    # Identificador único que genera la Raspberry Pi para cada evento. Permite
    # ignorar duplicados si la Pi reenvía eventos tras estar sin conexión
    # (idempotencia). NULL para eventos creados directo en el servidor.
    id_externo = db.Column(db.String(80), unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    guardia = db.relationship("Usuario", foreign_keys=[guardia_id], lazy="joined")

    def to_dict(self):
        placa_declarada = self.placa_vehiculo
        placa_obs = self.placa_observada
        no_coincide = bool(
            placa_declarada and placa_obs
            and placa_declarada.strip().upper() != placa_obs.strip().upper()
        )
        return {
            "id": str(self.uuid_publico),
            "origen": self.origen,
            "direccion": self.direccion,
            "en_vehiculo": self.en_vehiculo,
            "placa_vehiculo": placa_declarada,       # la que el residente declaró al crear la visita
            "placa_observada": placa_obs,            # la que el guardia digitó viendo el vehículo
            "placa_no_coincide": no_coincide,         # aviso: declarada y observada difieren
            "guardia": (
                f"{self.guardia.nombre} {self.guardia.apellido}" if self.guardia else None
            ),
            "foto_identidad": self.foto_identidad,
            "foto_placa": self.foto_placa,
            "foto_numero_asignado": self.foto_numero_asignado,
            "ocurrido_en": self.ocurrido_en.isoformat() if self.ocurrido_en else None,
        }


class AperturaManual(db.Model):
    """
    Registro de una tranca abierta manualmente por el guardia, SIN estar
    ligada a ninguna visita (ACCESS-04, Auditoría Día 35). Ej: dejar salir
    a alguien que vio caminando, una emergencia, etc.

    Se guarda por separado de EventoAcceso (que siempre representa la
    entrada/salida de una visita o residente específico) justamente
    porque esta acción no tiene ningún visitante ni residente asociado —
    es una decisión del guardia sobre el terreno, y por eso exige
    confirmación explícita en la app y queda auditada con quién, cuándo
    y cuál tranca exacta.
    """
    __tablename__ = "aperturas_manuales"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid()
    acceso_id = db.Column(db.BigInteger, db.ForeignKey("accesos_fisicos.id"), nullable=False)
    guardia_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    motivo = db.Column(db.String(255))  # opcional: nota corta del guardia
    ocurrido_en = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)

    acceso = db.relationship("AccesoFisico", lazy="joined")
    guardia = db.relationship("Usuario", foreign_keys=[guardia_id], lazy="joined")

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "acceso": self.acceso.nombre if self.acceso else None,
            "punto_acceso": self.acceso.punto_acceso if self.acceso else None,
            "tipo": self.acceso.tipo if self.acceso else None,
            "direccion": self.acceso.direccion if self.acceso else None,
            "guardia": f"{self.guardia.nombre} {self.guardia.apellido}" if self.guardia else None,
            "motivo": self.motivo,
            "ocurrido_en": self.ocurrido_en.isoformat() if self.ocurrido_en else None,
        }
