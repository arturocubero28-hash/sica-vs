"""
Módulo 2 — Unidades, Cuentas, Residentes y Tarjetas (Integrante 2).

Jerarquía:
    Unidad (casa | edificio)
      └── Cuenta (la que paga y genera QR; casa=1, edificio=N apartamentos)
            ├── Residente (titular | miembro)  -> vinculado a un Usuario
            └── Tarjeta de proximidad (varias por cuenta)

Sigue el patrón del modelo Usuario (uuid_publico, to_dict, timestamps).
"""
import uuid
import datetime as dt

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


def _uuid_col():
    return db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)


def _now():
    return dt.datetime.utcnow()


# ---------------------------------------------------------------------
# UNIDAD: entidad raíz (casa o edificio)
# ---------------------------------------------------------------------
class Unidad(db.Model):
    __tablename__ = "unidades"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    # ENUM real de PostgreSQL (tipo_unidad: casa | edificio) — mismo patrón
    # de fix que el resto de columnas enum encontradas el Día 36.
    tipo = db.Column(
        db.Enum("casa", "edificio", name="tipo_unidad", create_type=False),
        nullable=False)
    identificador = db.Column(db.String(60), unique=True, nullable=False)  # "Casa 24", "Edificio 1"
    direccion_ref = db.Column(db.String(160))
    # Para edificios: el usuario dueño/responsable que avala a sus inquilinos
    propietario_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    activa = db.Column(db.Boolean, nullable=False, default=True)
    # Bases para multi-residencial (Día 37): a qué Residencial pertenece esta
    # unidad. Se completa al crearla, heredado del admin/supervisor que la
    # crea. Ver Usuario.residencial_id para el detalle completo del diseño.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    # Límites por unidad (Día 29 — requisito de la administración):
    # Casa: máx 4 personas adicionales al titular (default)
    # Apto: máx 1 persona adicional al titular (default)
    # Edificio: el dueño declara cuántos aptos tiene; no se crean más
    max_residentes_extra = db.Column(db.Integer)   # null = usar default según tipo
    max_apartamentos = db.Column(db.Integer)        # solo aplica a edificios
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    cuentas = db.relationship("Cuenta", backref="unidad", lazy="select")

    def to_dict(self, incluir_cuentas=False):
        d = {
            "id": str(self.uuid_publico),
            "tipo": self.tipo,
            "identificador": self.identificador,
            "direccion_ref": self.direccion_ref,
            "activa": self.activa,
            "max_residentes_extra": self.max_residentes_extra,
            "max_apartamentos": self.max_apartamentos,
            "total_cuentas": len(self.cuentas),
        }
        if incluir_cuentas:
            d["cuentas"] = [c.to_dict() for c in self.cuentas]
        return d


# ---------------------------------------------------------------------
# CUENTA: quien paga y genera QR (casa o apartamento)
# ---------------------------------------------------------------------
class Cuenta(db.Model):
    __tablename__ = "cuentas"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    unidad_id = db.Column(db.BigInteger, db.ForeignKey("unidades.id"), nullable=False)
    apartamento = db.Column(db.String(40))                 # NULL si es casa; "1A" si es apto
    tarifa_id = db.Column(db.BigInteger, db.ForeignKey("tarifas.id"), nullable=True)
    dia_pago = db.Column(db.SmallInteger, nullable=True)   # 1..28 (null = cuenta contenedora sin cuota)
    fecha_alta = db.Column(db.Date, nullable=False, default=dt.date.today)
    estado = db.Column(db.String(20), nullable=False, default="al_dia")
    bloqueada = db.Column(db.Boolean, nullable=False, default=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)   # baja: deja de generar cuotas y accesos
    # Día 53 — Sprint 1: pausa liviana, DISTINTA de "activa" (dar de baja).
    # dar_baja_cuenta exige saldo en 0 y desactiva tarjetas/usuarios uno por
    # uno -- pensado para una mudanza real. acceso_pausado es reversible sin
    # fricción, para cortar temporalmente el acceso sin ese peso -- pensado
    # sobre todo para residenciales sin cuotas (Básico), donde "dar de baja"
    # no tiene mucho sentido conceptual.
    acceso_pausado = db.Column(db.Boolean, nullable=False, default=False)
    # Solo la administración puede habilitar la generación de QR recurrentes
    # para una cuenta. Por defecto está deshabilitado (Día 29).
    qr_recurrente_habilitado = db.Column(db.Boolean, nullable=False, default=False)
    # Tipo de acceso que el admin autoriza para las credenciales virtuales
    # (QR permanente y BLE) de esta cuenta — misma idea que el tipo_acceso
    # de las tarjetas físicas: 'peatonal' o 'vehicular'. Las cuentas con
    # tarifa reducida suelen limitarse a 'peatonal'. Este valor se copia a
    # TarjetaVirtual/CredencialBLE al activarlas, así la Pi filtra igual
    # que ya filtra las tarjetas físicas por tipo_acceso.
    tipo_acceso_virtual = db.Column(db.String(20), nullable=False, default="peatonal")
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    residentes = db.relationship("Residente", backref="cuenta", lazy="select")
    tarjetas = db.relationship("Tarjeta", backref="cuenta", lazy="select")
    tarifa = db.relationship("Tarifa", lazy="joined")
    # La relación 'unidad' ya existe automáticamente por el backref de Unidad.cuentas

    def titular(self):
        for r in self.residentes:
            if r.rol_cuenta == "titular" and r.activo:
                return r
        return None

    def tiene_deuda_vencida(self):
        """
        True si la cuenta tiene al menos una cuota vencida sin pagar.
        Las cuotas congeladas en un arreglo ('en_arreglo') NO cuentan como
        deuda vencida: el arreglo es el mecanismo activo de pago.
        """
        from app.models.cuenta import Cuota
        hoy = dt.date.today()
        vencida = (Cuota.query
                   .filter(Cuota.cuenta_id == self.id,
                           Cuota.estado.notin_(["pagada", "en_arreglo"]),
                           Cuota.fecha_vencimiento < hoy)
                   .first())
        return vencida is not None

    def intentar_desbloquear(self):
        """
        Desbloquea la cuenta SOLO si ya no le quedan cuotas vencidas sin pagar.
        Se llama después de registrar un pago. Evita el bug de desbloquear una
        cuenta que pagó una cuota pero aún debe otras. Devuelve True si quedó
        al día, False si sigue con deuda (y por tanto bloqueada).
        """
        if self.tiene_deuda_vencida():
            return False
        self.estado = "al_dia"
        self.bloqueada = False
        return True

    def es_contenedor_edificio(self):
        """True si esta cuenta es la cuenta 'raíz' de un edificio (el
        administrador que no vive ahí): unidad tipo edificio, sin apartamento
        propio y sin tarifa. Es un contenedor de otros apartamentos, no paga cuota."""
        try:
            return (self.unidad and self.unidad.tipo == "edificio"
                    and not self.apartamento and not self.tarifa_id)
        except Exception:
            return False

    def es_admin_residente(self):
        """True si esta cuenta es un apartamento cuyo titular ADEMÁS administra
        el edificio (el admin que vive ahí). Paga cuota como apartamento, pero
        tiene funciones de administración del edificio."""
        try:
            if not (self.unidad and self.unidad.tipo == "edificio" and self.apartamento):
                return False
            prop_id = self.unidad.propietario_id
            if not prop_id:
                return False
            # ¿El titular de esta cuenta es el propietario del edificio?
            t = self.titular()
            return bool(t and t.usuario_id == prop_id)
        except Exception:
            return False

    def administra_edificio(self):
        """True si esta cuenta administra el edificio, sea contenedor o
        admin-residente. Estas cuentas pueden ver los apartamentos, generar
        códigos de enrolamiento y editar el límite de apartamentos."""
        return self.es_contenedor_edificio() or self.es_admin_residente()

    def tipo_cuenta(self):
        """Discriminador único para la UI:
        'casa' | 'edificio_contenedor' | 'edificio_admin' | 'apartamento'."""
        try:
            if self.unidad and self.unidad.tipo == "edificio":
                if self.es_contenedor_edificio():
                    return "edificio_contenedor"
                if self.es_admin_residente():
                    return "edificio_admin"
                return "apartamento"
        except Exception:
            pass
        return "casa"

    def to_dict(self, detalle=False):
        t = self.titular()
        unidad = None
        try:
            unidad = self.unidad.identificador if self.unidad else None
        except Exception:
            unidad = None
        tc = self.tipo_cuenta()
        administra = tc in ("edificio_contenedor", "edificio_admin")
        d = {
            "id": str(self.uuid_publico),
            "apartamento": self.apartamento,
            "identificador": unidad,
            "tipo_cuenta": tc,
            "nombre_completo": (
                f"{unidad} · Administración" if tc == "edificio_contenedor"
                else (f"{unidad} · Apto {self.apartamento} (Admin)" if tc == "edificio_admin"
                      else (f"{unidad} · Apto {self.apartamento}"
                            if unidad and self.apartamento else (unidad or "—")))),
            "es_apartamento": bool(self.apartamento),
            "es_contenedor": tc == "edificio_contenedor",
            "administra_edificio": administra,
            "dia_pago": self.dia_pago,
            "estado": self.estado,
            "bloqueada": self.bloqueada,
            "activa": self.activa,
            "acceso_pausado": self.acceso_pausado,
            "qr_recurrente_habilitado": self.qr_recurrente_habilitado,
            "tipo_acceso_virtual": self.tipo_acceso_virtual,
            "tarifa": self.tarifa.nombre if self.tarifa else None,
            "monto": float(self.tarifa.monto) if self.tarifa else None,
            "titular": t.to_dict() if t else None,
            "total_residentes": len([r for r in self.residentes if r.activo]),
            "total_tarjetas": len([x for x in self.tarjetas if x.estado == "activa"]),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if detalle:
            d["residentes"] = [r.to_dict() for r in self.residentes if r.activo]
            d["tarjetas"] = [x.to_dict() for x in self.tarjetas]
            # Si esta cuenta administra el edificio (contenedor O admin-residente),
            # incluir la lista de apartamentos (cuentas hermanas bajo la unidad).
            if administra and self.unidad:
                aptos = [c for c in self.unidad.cuentas if c.id != self.id]
                def _nombre_titular(c):
                    tt = c.titular()
                    if tt and tt.usuario:
                        return f"{tt.usuario.nombre} {tt.usuario.apellido}"
                    return "—"
                d["apartamentos"] = [{
                    "id": str(c.uuid_publico),
                    "apartamento": c.apartamento,
                    "titular": _nombre_titular(c),
                    "estado": c.estado,
                    "bloqueada": c.bloqueada,
                    "tarifa": c.tarifa.nombre if c.tarifa else None,
                    "monto": float(c.tarifa.monto) if c.tarifa else None,
                } for c in sorted(aptos, key=lambda x: x.apartamento or "")]
            # Info de la unidad (para edificios: límite de apartamentos editable)
            if self.unidad:
                d["unidad"] = {
                    "id": str(self.unidad.uuid_publico),
                    "tipo": self.unidad.tipo,
                    "identificador": self.unidad.identificador,
                    "max_apartamentos": self.unidad.max_apartamentos,
                    "max_residentes_extra": self.unidad.max_residentes_extra,
                    "total_cuentas": len(self.unidad.cuentas),
                }
            # Resumen de cuotas (para ver el estado de pago sin abrir otra pantalla)
            from app.models.cuenta import Cuota
            cuotas = (Cuota.query.filter_by(cuenta_id=self.id)
                      .order_by(Cuota.fecha_vencimiento.desc()).limit(6).all())
            d["cuotas_recientes"] = [{
                "periodo": c.periodo.isoformat() if c.periodo else None,
                "monto": float(c.monto),
                "estado": c.estado,
                "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
            } for c in cuotas]
        return d


# ---------------------------------------------------------------------
# TARIFA (catálogo; ya existe en el schema, modelo mínimo para relación)
# ---------------------------------------------------------------------
class Tarifa(db.Model):
    __tablename__ = "tarifas"

    id = db.Column(db.BigInteger, primary_key=True)
    # Multi-residencial (Día 46): cada residencial define sus propias tarifas.
    # Nullable por compatibilidad con filas antiguas.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    nombre = db.Column(db.String(80), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    descripcion = db.Column(db.String(255))
    activa = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "monto": float(self.monto),
            "descripcion": self.descripcion,
            "activa": self.activa,
        }


# ---------------------------------------------------------------------
# RESIDENTE: vínculo Usuario <-> Cuenta
# ---------------------------------------------------------------------
class Residente(db.Model):
    __tablename__ = "residentes"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    usuario_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)
    # ENUM real de PostgreSQL (rol_en_cuenta: titular | miembro).
    rol_cuenta = db.Column(
        db.Enum("titular", "miembro", name="rol_en_cuenta", create_type=False),
        nullable=False, default="miembro")
    relacion = db.Column(db.String(60))                    # propietario, inquilino, hijo...
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_ingreso = db.Column(db.Date, nullable=False, default=dt.date.today)
    fecha_baja = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    usuario = db.relationship("Usuario", lazy="joined")

    def to_dict(self):
        u = self.usuario
        return {
            "id": str(self.uuid_publico),
            "usuario_id": str(u.uuid_publico) if u else None,
            "rol_cuenta": self.rol_cuenta,
            "relacion": self.relacion,
            "activo": self.activo,
            "nombre": f"{u.nombre} {u.apellido}" if u else None,
            "nombre_solo": u.nombre if u else None,
            "apellido": u.apellido if u else None,
            "email": u.email if u else None,
            "telefono": u.telefono if u else None,
            "dni": u.dni if u else None,
            "rtn": u.rtn if u else None,
            "direccion_exacta": u.direccion_exacta if u else None,
            "profesion": u.profesion if u else None,
            "contacto_emergencia_nombre": u.contacto_emergencia_nombre if u else None,
            "contacto_emergencia_telefono": u.contacto_emergencia_telefono if u else None,
            # estado de activación de la cuenta de acceso del residente
            "estado_acceso": "activo" if (u and u.activo and u.password_hash) else "pendiente",
        }


# ---------------------------------------------------------------------
# TARJETA de proximidad
# ---------------------------------------------------------------------
class Tarjeta(db.Model):
    __tablename__ = "tarjetas_proximidad"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    card_uid = db.Column(db.String(64), unique=True, nullable=False)
    cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)
    residente_id = db.Column(db.BigInteger, db.ForeignKey("residentes.id"))
    etiqueta = db.Column(db.String(80))                    # "Tarjeta principal", "Auto 2"
    # ENUMs reales de PostgreSQL — mismo patrón de fix del Día 36.
    tipo_acceso = db.Column(
        db.Enum("vehicular", "peatonal", name="tipo_acceso", create_type=False),
        nullable=False, default="vehicular")
    estado = db.Column(
        db.Enum("activa", "bloqueada", "extraviada", "baja", name="estado_tarjeta", create_type=False),
        nullable=False, default="activa")
    fecha_asignacion = db.Column(db.Date, nullable=False, default=dt.date.today)
    fecha_baja = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    residente = db.relationship("Residente", lazy="joined")

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "card_uid": self.card_uid,
            "etiqueta": self.etiqueta,
            "tipo_acceso": self.tipo_acceso,
            "estado": self.estado,
            "asignada_a": (
                f"{self.residente.usuario.nombre} {self.residente.usuario.apellido}"
                if self.residente and self.residente.usuario else "Sin asignar"
            ),
        }


# ---------------------------------------------------------------------
# TARJETA VIRTUAL: QR permanente que rota cada 24h para acceso sin guardia
#
# El residente lo agrega a Google/Apple Wallet. La Pi lo lee como si fuera
# una tarjeta RFID — el código del día se sincroniza igual que los card_uid.
#
# Flujo de rotación (medianoche):
#   1. Celery genera un nuevo código de 10 dígitos para cada tarjeta activa
#   2. El código_anterior se guarda para la ventana de gracia (10 min)
#   3. El sync de la Pi incluye AMBOS códigos durante esos 10 min
#   4. Google/Apple Wallet llaman al endpoint de actualización → reciben el QR nuevo
# ---------------------------------------------------------------------
class TarjetaVirtual(db.Model):
    __tablename__ = "tarjetas_virtuales"

    id            = db.Column(db.BigInteger, primary_key=True)
    uuid_publico  = _uuid_col()
    cuenta_id     = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False, unique=True)
    residente_id  = db.Column(db.BigInteger, db.ForeignKey("residentes.id"), nullable=False)

    # Código activo del día (10 dígitos, prefijado con "SV" para distinguirlo de tarjetas físicas)
    codigo_hoy      = db.Column(db.String(20), nullable=False, unique=True)
    # Código anterior — válido durante 10 min después de la rotación para
    # evitar que alguien quede afuera mientras la Pi sincroniza el nuevo
    # código.
    codigo_anterior = db.Column(db.String(20))
    # ROTATION-07 (Auditoría Día 35): antes la ventana de gracia se
    # calculaba comparando la hora ACTUAL del servidor contra un rango fijo
    # ("es medianoche y faltan menos de 10 min") usando UTC, mientras la
    # rotación real ocurre a medianoche hora de Honduras — un desfase de 6
    # horas que dejaba la ventana de gracia activa a las 6:00 AM en vez de
    # a medianoche. Ahora se guarda explícitamente HASTA CUÁNDO es válido
    # el código anterior (fijado al rotar, sin ambigüedad de zona horaria
    # ni dependencia de la hora del servidor en el momento de la consulta).
    codigo_anterior_valido_hasta = db.Column(db.DateTime(timezone=True))

    estado       = db.Column(db.String(20), nullable=False, default="activa")  # activa | suspendida
    tipo_acceso  = db.Column(db.String(20), nullable=False, default="peatonal")
    rotado_en    = db.Column(db.DateTime(timezone=True), default=_now)  # última rotación
    created_at   = db.Column(db.DateTime(timezone=True), default=_now)

    cuenta    = db.relationship("Cuenta", lazy="joined")
    residente = db.relationship("Residente", lazy="joined")

    def to_dict(self):
        from app.models.cuenta import Cuenta as C  # evitar import circular
        titular = self.residente.usuario if self.residente else None
        return {
            "id": str(self.uuid_publico),
            "estado": self.estado,
            "tipo_acceso": self.tipo_acceso,
            "codigo_hoy": self.codigo_hoy,
            "rotado_en": self.rotado_en.isoformat() if self.rotado_en else None,
            "titular": f"{titular.nombre} {titular.apellido}" if titular else None,
        }


# ---------------------------------------------------------------------
# CREDENCIAL BLE: acceso por Bluetooth de baja energía, atado al dispositivo
#
# A diferencia de la tarjeta virtual (QR), la credencial BLE está ATADA a un
# dispositivo físico específico (device_id). No basta con tener la cuenta
# abierta — el acceso solo funciona en el teléfono registrado.
#
# Defensas implementadas:
#   1. Atada al device_id — un login en otro teléfono NO hereda el acceso BLE
#   2. Clave secreta única por credencial (para el desafío-respuesta)
#   3. Rolling counter — cada uso incrementa un contador; el lector rechaza
#      un contador menor o igual al último visto (anti-repetición)
#   4. Token rotado cada 24h igual que el QR
#   5. Máximo 1 dispositivo activo por residente (registrar otro revoca el anterior)
#   6. Verificación de proximidad (RSSI) — se valida en el lector, no aquí
# ---------------------------------------------------------------------
class CredencialBLE(db.Model):
    __tablename__ = "credenciales_ble"

    id            = db.Column(db.BigInteger, primary_key=True)
    uuid_publico  = _uuid_col()
    cuenta_id     = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)
    residente_id  = db.Column(db.BigInteger, db.ForeignKey("residentes.id"), nullable=False)

    # Identificador único del dispositivo físico (generado en el teléfono al activar)
    device_id     = db.Column(db.String(128), nullable=False)
    device_nombre = db.Column(db.String(120))  # ej. "Samsung Galaxy S24" para mostrar al usuario

    # Token BLE del día (lo que el teléfono transmite al lector, rota cada 24h)
    token_hoy      = db.Column(db.String(32), nullable=False, unique=True)
    token_anterior = db.Column(db.String(32))  # ventana de gracia de 10 min
    # ROTATION-07: mismo fix que TarjetaVirtual.codigo_anterior_valido_hasta
    # — fecha explícita hasta la cual el token anterior sigue siendo válido,
    # fijada al rotar. Elimina la dependencia de comparar zonas horarias en
    # el momento de la consulta.
    token_anterior_valido_hasta = db.Column(db.DateTime(timezone=True))

    # Clave secreta para el desafío-respuesta (HMAC). Nunca sale del servidor
    # ni del teléfono en texto plano — se usa para firmar el challenge del lector.
    clave_secreta = db.Column(db.String(64), nullable=False)

    # Rolling counter anti-repetición. El lector rechaza contadores <= al último visto.
    contador      = db.Column(db.BigInteger, nullable=False, default=0)

    estado       = db.Column(db.String(20), nullable=False, default="activa")  # activa | suspendida
    tipo_acceso  = db.Column(db.String(20), nullable=False, default="peatonal")
    rotado_en    = db.Column(db.DateTime(timezone=True), default=_now)
    ultimo_uso   = db.Column(db.DateTime(timezone=True))
    created_at   = db.Column(db.DateTime(timezone=True), default=_now)

    cuenta    = db.relationship("Cuenta", lazy="joined")
    residente = db.relationship("Residente", lazy="joined")

    def to_dict(self, incluir_secretos=False):
        titular = self.residente.usuario if self.residente else None
        d = {
            "id": str(self.uuid_publico),
            "estado": self.estado,
            "tipo_acceso": self.tipo_acceso,
            "device_nombre": self.device_nombre,
            "rotado_en": self.rotado_en.isoformat() if self.rotado_en else None,
            "ultimo_uso": self.ultimo_uso.isoformat() if self.ultimo_uso else None,
            "titular": f"{titular.nombre} {titular.apellido}" if titular else None,
        }
        # La clave secreta y el token solo se envían al dispositivo dueño al activar
        if incluir_secretos:
            d["token_hoy"] = self.token_hoy
            d["clave_secreta"] = self.clave_secreta
            d["contador"] = self.contador
        return d


# ---------------------------------------------------------------------
# CUOTA: cuota mensual generada automáticamente por Celery
# ---------------------------------------------------------------------
class Cuota(db.Model):
    __tablename__ = "cuotas"

    id                = db.Column(db.BigInteger, primary_key=True)
    uuid_publico      = _uuid_col()
    cuenta_id         = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False, index=True)
    periodo           = db.Column(db.Date, nullable=False)          # primer día del mes: 2026-06-01
    monto             = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    estado            = db.Column(db.String(20), nullable=False, default="pendiente", index=True)
    arreglo_id        = db.Column(db.BigInteger, db.ForeignKey("arreglos_pago.id"))  # si está en un arreglo
    monto_original    = db.Column(db.Numeric(10, 2))  # monto pleno antes de nivelar (se fija una sola vez)
    nivelada          = db.Column(db.Boolean, nullable=False, default=False)
    created_at        = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at        = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    cuenta = db.relationship("Cuenta", backref="cuotas")
    pagos  = db.relationship("Pago", backref="cuota", lazy="dynamic")

    def to_dict(self, con_pagos=False):
        d = {
            "id":               str(self.uuid_publico),
            "periodo":          self.periodo.isoformat(),
            "mes_label":        self.periodo.strftime("%B %Y"),
            "monto":            float(self.monto),
            "fecha_vencimiento": self.fecha_vencimiento.isoformat(),
            "estado":           self.estado,
            "created_at":       self.created_at.isoformat(),
        }
        # Si el último pago fue rechazado, exponer el motivo para que el residente reintente
        ultimo = self.pagos.order_by(Pago.created_at.desc()).first()
        if ultimo and ultimo.estado == "rechazado":
            d["pago_rechazado"] = True
            d["nota_rechazo"] = ultimo.nota_admin or ""
        # Si hay un pago esperando aprobación del admin, avisar al residente
        # para que sepa que su comprobante llegó y no lo suba de nuevo.
        d["en_revision"] = bool(ultimo and ultimo.estado == "en_revision")
        if con_pagos:
            d["pagos"] = [p.to_dict() for p in self.pagos.all()]
        return d


# ---------------------------------------------------------------------
# PAGO: comprobante subido por el residente, revisado por el admin
# ---------------------------------------------------------------------
class Pago(db.Model):
    __tablename__ = "pagos"

    id                   = db.Column(db.BigInteger, primary_key=True)
    uuid_publico         = _uuid_col()
    cuota_id             = db.Column(db.BigInteger, db.ForeignKey("cuotas.id"), nullable=True)
    abono_id             = db.Column(db.BigInteger, db.ForeignKey("abonos_arreglo.id"), nullable=True)
    cuenta_id            = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False, index=True)
    # Día 54 — bug real: numero_recibo tenía un índice único GLOBAL
    # (idx_pagos_numero_recibo_unico), pero el correlativo se calcula POR
    # RESIDENCIAL (ConfigRecibo, ya corregido desde el Día 48) -- en
    # cuanto dos residenciales llegaban a su propio recibo #1, chocaban
    # contra la restricción de la base. Pago no tenía residencial_id
    # directo (solo cuenta_id, del cual se puede resolver vía unidad) --
    # se desnormaliza acá para poder armar el índice único compuesto
    # (residencial_id, numero_recibo) en vez de uno global.
    residencial_id       = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    subido_por           = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    # ENUMs reales de PostgreSQL — fix Día 36.
    metodo = db.Column(
        db.Enum("transferencia", "pasarela", "efectivo", "tarjeta_pos", "linea",
                name="metodo_pago", create_type=False),
        nullable=False, default="transferencia")
    monto                = db.Column(db.Numeric(10, 2), nullable=False)
    comprobante_archivo  = db.Column(db.String(255))
    referencia           = db.Column(db.String(120))
    estado = db.Column(
        db.Enum("en_revision", "aprobado", "rechazado", name="estado_pago", create_type=False),
        nullable=False, default="en_revision", index=True)
    revisado_por         = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    revisado_en          = db.Column(db.DateTime(timezone=True))
    nota_admin           = db.Column(db.String(255))
    numero_recibo        = db.Column(db.Integer)   # correlativo de recibo (se asigna al aprobar)
    sesion_caja_id       = db.Column(db.BigInteger, db.ForeignKey("sesiones_caja.id"))
    created_at           = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at           = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    # backref renombrado a 'pagos_de_cuenta' para no confundir con Cuota.pagos
    # y SesionCaja.pagos (tres relaciones distintas que antes se llamaban igual).
    cuenta   = db.relationship("Cuenta", foreign_keys=[cuenta_id], backref="pagos_de_cuenta")
    uploader = db.relationship("Usuario", foreign_keys=[subido_por])
    revisor  = db.relationship("Usuario", foreign_keys=[revisado_por])
    # PAY-MODEL-21 (Auditoría Día 39). MODELO: varios depósitos, UN pago.
    #
    # CASO REAL: el residente deposita desde bancos distintos — L600 en
    # Ficohsa + L600 en Atlántida para una cuota de L1,200. Son dos
    # transferencias, pero un solo Pago por el total. Hasta 5 comprobantes.
    #
    # REGLA DE APROBACIÓN: el admin aprueba solo si la suma de los
    # depósitos cubre el monto completo. Si falta, rechaza y deja una nota
    # en 'nota_admin' explicando por qué; el residente la recibe por
    # notificación push. NO existe la aprobación parcial.
    #
    # Lo que este modelo NO hace: tratar cada comprobante como un pago
    # independiente con estado propio (aprobar los L600 de Ficohsa y dejar
    # los otros pendientes). Requeriría monto, fecha y estado por
    # comprobante. Esta clase tiene un único 'monto' y ComprobantePago no
    # tiene monto propio.
    #
    # El comentario anterior decía "el residente depositó en dos partes",
    # que sugería pagos parciales. Fue el origen del hallazgo: la
    # documentación describía una función que el modelo no tiene.
    comprobantes = db.relationship("ComprobantePago", backref="pago",
                                    order_by="ComprobantePago.created_at",
                                    cascade="all, delete-orphan")

    def to_dict(self):
        # Lista de archivos: si hay comprobantes en la tabla nueva, se usan
        # esos; si el pago es viejo (de antes de esta funcionalidad) y solo
        # tiene comprobante_archivo, se devuelve como lista de un elemento
        # para que el frontend no tenga que distinguir dos formatos.
        archivos = [c.archivo for c in self.comprobantes] if self.comprobantes else (
            [self.comprobante_archivo] if self.comprobante_archivo else [])
        return {
            "id":                  str(self.uuid_publico),
            "cuota_id":            str(self.cuota.uuid_publico) if self.cuota else None,
            "monto":               float(self.monto),
            "metodo":              self.metodo,
            "referencia":          self.referencia,
            "comprobante_archivo": self.comprobante_archivo,  # compatibilidad con historial viejo
            "comprobantes":        archivos,                   # lista completa (nuevo)
            "numero_recibo":       self.numero_recibo,
            "estado":              self.estado,
            "nota_admin":          self.nota_admin,
            "revisado_en":         self.revisado_en.isoformat() if self.revisado_en else None,
            "created_at":          self.created_at.isoformat(),
        }


@event.listens_for(Pago, "before_insert")
def _pago_completar_residencial_id(mapper, connection, pago):
    """
    Día 54: completa Pago.residencial_id automáticamente antes de guardar,
    resolviéndolo desde cuenta_id -> unidad_id -> residencial_id -- sin
    depender de que cada uno de los 5 lugares donde se crea un Pago
    (cuotas.py x2, caja.py x2, arreglos.py) lo complete a mano. Cuenta no
    tiene relación ORM a Unidad (solo unidad_id, columna suelta), así que
    se resuelve con una consulta directa a la conexión de bajo nivel
    (estamos en un evento pre-flush, todavía no conviene usar la sesión
    ORM completa acá).
    """
    if pago.residencial_id is not None or not pago.cuenta_id:
        return
    fila_cuenta = connection.execute(
        db.text("SELECT unidad_id FROM cuentas WHERE id = :id"), {"id": pago.cuenta_id}
    ).first()
    if not fila_cuenta:
        return
    fila_unidad = connection.execute(
        db.text("SELECT residencial_id FROM unidades WHERE id = :id"), {"id": fila_cuenta[0]}
    ).first()
    if fila_unidad:
        pago.residencial_id = fila_unidad[0]


class ComprobantePago(db.Model):
    """
    Una imagen de comprobante asociada a un Pago. Un pago puede tener varios
    (ej. el residente depositó en dos partes y sube las dos fotos para que
    el admin las revise juntas y apruebe el pago completo de una vez).
    """
    __tablename__ = "comprobantes_pago"

    id         = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    pago_id    = db.Column(db.BigInteger, db.ForeignKey("pagos.id", ondelete="CASCADE"), nullable=False)
    archivo    = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)


class ArregloPago(db.Model):
    """
    Plan de pago negociado para una cuenta morosa.
    Congela un conjunto de cuotas vencidas y permite pagarlas en abonos.
    Sin recargo: solo difiere la deuda.
    """
    __tablename__ = "arreglos_pago"

    id                  = db.Column(db.BigInteger, primary_key=True)
    uuid_publico        = _uuid_col()
    cuenta_id           = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)

    # Montos (congelados al crear el arreglo)
    deuda_total         = db.Column(db.Numeric(10, 2), nullable=False)   # suma de cuotas incluidas
    abono_inicial       = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    saldo_financiado    = db.Column(db.Numeric(10, 2), nullable=False)   # deuda - abono_inicial
    num_abonos          = db.Column(db.Integer, nullable=False)
    monto_por_abono     = db.Column(db.Numeric(10, 2), nullable=False)

    # Política de incumplimiento
    dias_gracia         = db.Column(db.Integer, nullable=False, default=15)
    # Intervalo entre abonos, en días (configurable al crear el arreglo)
    intervalo_dias      = db.Column(db.Integer, nullable=False, default=30)

    # Estado del arreglo: activo | completado | incumplido | cancelado
    estado              = db.Column(db.String(20), nullable=False, default="activo")

    # Trazabilidad
    creado_por          = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    nota                = db.Column(db.String(500))
    motivo_cierre       = db.Column(db.String(255))
    created_at          = db.Column(db.DateTime(timezone=True), default=_now)
    completado_en       = db.Column(db.DateTime(timezone=True))

    cuenta  = db.relationship("Cuenta", backref="arreglos")
    creador = db.relationship("Usuario", foreign_keys=[creado_por])
    abonos  = db.relationship("AbonoArreglo", backref="arreglo",
                              lazy="select", cascade="all, delete-orphan")
    # Cuotas congeladas por este arreglo
    cuotas  = db.relationship("Cuota", backref="arreglo", lazy="select")

    def total_abonado(self):
        """Suma de todos los abonos pagados.

        Nota: desde el Día 24 la prima (abono_inicial) se registra como el
        primer AbonoArreglo, así que ya está incluida en la suma de abonos
        pagados. No se suma aparte para no contarla doble.
        """
        return sum(float(a.monto) for a in self.abonos if a.estado == "pagado")

    def saldo_pendiente(self):
        """Lo que falta por pagar de la deuda total."""
        return round(float(self.deuda_total) - self.total_abonado(), 2)

    def abonos_pagados(self):
        return sum(1 for a in self.abonos if a.estado == "pagado")

    def proximo_abono(self):
        """El siguiente abono pendiente (por fecha), o None si no hay."""
        pendientes = [a for a in self.abonos if a.estado == "pendiente"]
        if not pendientes:
            return None
        return min(pendientes, key=lambda a: a.fecha_pactada)

    def to_dict(self, con_detalle=False):
        d = {
            "id":               str(self.uuid_publico),
            "estado":           self.estado,
            "deuda_total":      float(self.deuda_total),
            "abono_inicial":    float(self.abono_inicial),
            "saldo_financiado": float(self.saldo_financiado),
            "num_abonos":       self.num_abonos,
            "monto_por_abono":  float(self.monto_por_abono),
            "dias_gracia":      self.dias_gracia,
            "intervalo_dias":   self.intervalo_dias,
            "total_abonado":    round(self.total_abonado(), 2),
            "saldo_pendiente":  self.saldo_pendiente(),
            "abonos_pagados":   self.abonos_pagados(),
            "nota":             self.nota,
            "motivo_cierre":    self.motivo_cierre,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "completado_en":    self.completado_en.isoformat() if self.completado_en else None,
        }
        # Datos de la cuenta para mostrar en el panel
        cuenta = self.cuenta
        if cuenta:
            d["unidad"] = cuenta.unidad.identificador if cuenta.unidad else "—"
            tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None)
            d["titular"] = (f"{tit.usuario.nombre} {tit.usuario.apellido}"
                            if tit and tit.usuario else "—")
        if con_detalle:
            d["abonos"] = [a.to_dict() for a in sorted(self.abonos, key=lambda x: x.numero)]
            d["meses_incluidos"] = [
                {"mes_label": c.periodo.strftime("%B %Y"), "monto": float(c.monto)}
                for c in sorted(self.cuotas, key=lambda x: x.periodo)
            ]
        return d


class AbonoArreglo(db.Model):
    """Cada cuota/abono del calendario de un arreglo de pago."""
    __tablename__ = "abonos_arreglo"

    id            = db.Column(db.BigInteger, primary_key=True)
    uuid_publico  = _uuid_col()
    arreglo_id    = db.Column(db.BigInteger, db.ForeignKey("arreglos_pago.id"), nullable=False)
    numero        = db.Column(db.Integer, nullable=False)              # 1, 2, 3...
    monto         = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_pactada = db.Column(db.Date, nullable=False)
    # Estado: pendiente | pagado | vencido
    estado        = db.Column(db.String(20), nullable=False, default="pendiente")
    pagado_en     = db.Column(db.DateTime(timezone=True))
    pago_id       = db.Column(db.BigInteger, db.ForeignKey("pagos.id"))  # pago que lo cubrió
    created_at    = db.Column(db.DateTime(timezone=True), default=_now)

    def to_dict(self):
        return {
            "id":            str(self.uuid_publico),
            "numero":        self.numero,
            "monto":         float(self.monto),
            "fecha_pactada": self.fecha_pactada.isoformat(),
            "estado":        self.estado,
            "pagado_en":     self.pagado_en.isoformat() if self.pagado_en else None,
        }


class ConfigRecibo(db.Model):
    """
    Configuración de recibos POR RESIDENCIAL (Día 48 — hallazgo de
    auditoría: antes era una sola fila global, id=1, igual patrón que
    tenía ConfigCaja antes del Día 47. Incluía hasta el CORRELATIVO de
    facturas compartido — si hubiera dos residenciales, sus números de
    recibo se habrían mezclado entre sí).
    FASE 1: datos del emisor + correlativo interno.
    FASE 2 (preparado): CAI, rango autorizado y fecha límite de la SAR.
    """
    __tablename__ = "config_recibo"

    id                 = db.Column(db.BigInteger, primary_key=True)
    residencial_id     = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    # Datos del emisor (Fase 1)
    # Día 54 — bug real: este default estaba hardcodeado a un nombre
    # específico. Cada vez que se creaba una fila NUEVA (ej. la primera
    # vez que Bosques de Jucutuma necesitó su config), SQLAlchemy la
    # llenaba automáticamente con este texto literal -- nunca quedaba
    # vacía, así que el fallback dinámico en recibos.py (usar el nombre
    # real de la residencial si esto no está configurado) nunca se
    # activaba: cfg.nombre_emisor NUNCA era None/vacío para chequear.
    # Default correcto: None, dejando que la aplicación decida el
    # fallback según la residencial real.
    nombre_emisor      = db.Column(db.String(160), default=None)
    rtn_emisor         = db.Column(db.String(20))
    # Mismo bug que nombre_emisor arriba, mismo arreglo.
    direccion_emisor   = db.Column(db.String(255), default=None)
    telefono_emisor    = db.Column(db.String(40))
    # Correlativo interno (Fase 1)
    ultimo_correlativo = db.Column(db.Integer, nullable=False, default=0)
    prefijo            = db.Column(db.String(20), default="REC")
    # Datos fiscales SAR (Fase 2 — preparado, aún no se usa para validez legal)
    cai                = db.Column(db.String(40))
    rango_desde        = db.Column(db.Integer)
    rango_hasta        = db.Column(db.Integer)
    fecha_limite_emision = db.Column(db.Date)
    punto_emision      = db.Column(db.String(10), default="001")
    establecimiento    = db.Column(db.String(10), default="001")
    tipo_documento     = db.Column(db.String(10), default="01")
    fase_sar_activa    = db.Column(db.Boolean, nullable=False, default=False)  # True = Fase 2 activa
    actualizado_en     = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    @classmethod
    def get(cls, residencial_id=None):
        """
        Devuelve la config de UNA residencial, creándola si no existe.
        residencial_id=None es compatibilidad legacy (fila id=1) — todo
        código nuevo debe pasar un residencial_id explícito.
        """
        if residencial_id is not None:
            cfg = cls.query.filter_by(residencial_id=residencial_id).first()
            if not cfg:
                cfg = cls(residencial_id=residencial_id)
                db.session.add(cfg)
                db.session.commit()
            return cfg
        cfg = cls.query.get(1) or cls.query.order_by(cls.id).first()
        if not cfg:
            cfg = cls(id=1)
            db.session.add(cfg)
            db.session.commit()
        return cfg

    def siguiente_correlativo(self):
        """
        Reserva y devuelve el siguiente número de recibo.

        PAY-11: antes esto era 'leer en Python, sumar 1, escribir' — dos
        aprobaciones de pago casi simultáneas podían leer el mismo valor
        antes de que la primera confirmara su escritura, generando el mismo
        número de recibo dos veces.

        Ahora el incremento ocurre como una sola sentencia UPDATE atómica en
        PostgreSQL (SET x = x + 1 ... RETURNING x), que la propia base de
        datos serializa entre transacciones concurrentes — sin necesidad de
        bloqueos manuales ni SELECT FOR UPDATE.
        """
        resultado = db.session.execute(
            db.text(
                "UPDATE config_recibo "
                "SET ultimo_correlativo = ultimo_correlativo + 1 "
                "WHERE id = :id "
                "RETURNING ultimo_correlativo"
            ),
            {"id": self.id},
        ).scalar()
        # Mantener el objeto en memoria sincronizado con lo que quedó en la BD
        self.ultimo_correlativo = resultado
        return resultado

    def numero_formateado(self, correlativo):
        """
        Formato del número de recibo.
        Fase 1: REC-000123
        Fase 2 (SAR): 001-001-01-00000123 (establecimiento-punto-tipo-correlativo)
        """
        if self.fase_sar_activa and self.cai:
            return f"{self.establecimiento}-{self.punto_emision}-{self.tipo_documento}-{correlativo:08d}"
        return f"{self.prefijo}-{correlativo:06d}"

    def to_dict(self):
        return {
            "nombre_emisor": self.nombre_emisor,
            "rtn_emisor": self.rtn_emisor,
            "direccion_emisor": self.direccion_emisor,
            "telefono_emisor": self.telefono_emisor,
            "ultimo_correlativo": self.ultimo_correlativo,
            "prefijo": self.prefijo,
            "cai": self.cai,
            "rango_desde": self.rango_desde,
            "rango_hasta": self.rango_hasta,
            "fecha_limite_emision": self.fecha_limite_emision.isoformat() if self.fecha_limite_emision else None,
            "punto_emision": self.punto_emision,
            "establecimiento": self.establecimiento,
            "tipo_documento": self.tipo_documento,
            "fase_sar_activa": self.fase_sar_activa,
        }


# ---------------------------------------------------------------------
# CÓDIGO DE ENROLAMIENTO: el dueño de un edificio genera un código
# numérico de un solo uso para que su inquilino se enrole en la oficina.
# La administración lo usa al dar de alta y asocia al inquilino al edificio.
# ---------------------------------------------------------------------
class CodigoEnrolamiento(db.Model):
    __tablename__ = "codigos_enrolamiento"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    codigo = db.Column(db.String(8), unique=True, nullable=False)   # numérico, ej. "428173"
    unidad_id = db.Column(db.BigInteger, db.ForeignKey("unidades.id"), nullable=False)  # el edificio
    generado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)  # el dueño
    apartamento_sugerido = db.Column(db.String(40))   # opcional, lo que el dueño indica
    nota = db.Column(db.String(160))                  # opcional: "Inquilino del 3B, familia López"
    estado = db.Column(db.String(10), nullable=False, default="activo")  # activo | usado
    usado_por_cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"))  # cuenta creada al enrolar
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    usado_en = db.Column(db.DateTime(timezone=True))

    unidad = db.relationship("Unidad", foreign_keys=[unidad_id])
    generador = db.relationship("Usuario", foreign_keys=[generado_por])

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "codigo": self.codigo,
            "edificio": self.unidad.identificador if self.unidad else None,
            "apartamento_sugerido": self.apartamento_sugerido,
            "nota": self.nota,
            "estado": self.estado,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "usado_en": self.usado_en.isoformat() if self.usado_en else None,
        }


class TipoTarjeta(db.Model):
    """
    Catálogo de tipos de tarjeta RFID que la administración vende.
    Define el precio y lleva el stock disponible en bodega.
    El tipo_acceso conecta con la tarjeta física (vehicular = largo alcance,
    peatonal = corto alcance).
    """
    __tablename__ = "tipos_tarjeta"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    # Multi-residencial (Día 46): cada residencial tiene su propio catálogo de
    # tipos de tarjeta (precio y stock propios). Nullable por compatibilidad
    # con filas antiguas; la migración las asigna a la residencial base.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    nombre = db.Column(db.String(80), nullable=False)          # "Tarjeta vehicular UHF"
    tipo_acceso = db.Column(db.String(20), nullable=False, default="vehicular")  # vehicular | peatonal
    precio = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)   # unidades en bodega
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "tipo_acceso": self.tipo_acceso,
            "precio": float(self.precio),
            "stock": self.stock,
            "activo": self.activo,
        }


class MovimientoStock(db.Model):
    """
    Auditoría de cambios de stock de tarjetas: entradas (compra de lotes),
    salidas (ventas en caja) y ajustes manuales. Cada movimiento deja rastro
    de quién, cuánto y por qué.
    """
    __tablename__ = "movimientos_stock"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    tipo_tarjeta_id = db.Column(db.BigInteger, db.ForeignKey("tipos_tarjeta.id"), nullable=False)
    tipo_movimiento = db.Column(db.String(20), nullable=False)  # entrada | venta | ajuste
    cantidad = db.Column(db.Integer, nullable=False)            # +entra, -sale
    stock_resultante = db.Column(db.Integer, nullable=False)
    nota = db.Column(db.String(255))
    registrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    tipo_tarjeta = db.relationship("TipoTarjeta", foreign_keys=[tipo_tarjeta_id])
    usuario = db.relationship("Usuario", foreign_keys=[registrado_por])

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "tipo_tarjeta": self.tipo_tarjeta.nombre if self.tipo_tarjeta else "—",
            "tipo_movimiento": self.tipo_movimiento,
            "cantidad": self.cantidad,
            "stock_resultante": self.stock_resultante,
            "nota": self.nota,
            "registrado_por": (f"{self.usuario.nombre} {self.usuario.apellido}"
                               if self.usuario else "—"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VentaTarjeta(db.Model):
    """
    Registro auditable de cada venta de tarjeta en caja: qué tipo, a qué casa,
    qué tarjeta física, a qué precio, qué cajero y en qué sesión de caja.
    El cobro en sí se registra como un Pago (para que sume al arqueo); esta
    tabla guarda el detalle específico de la venta.
    """
    __tablename__ = "ventas_tarjeta"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = _uuid_col()
    tipo_tarjeta_id = db.Column(db.BigInteger, db.ForeignKey("tipos_tarjeta.id"), nullable=False)
    tarjeta_id = db.Column(db.BigInteger, db.ForeignKey("tarjetas_proximidad.id"))
    cuenta_id = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)
    pago_id = db.Column(db.BigInteger, db.ForeignKey("pagos.id"))
    sesion_caja_id = db.Column(db.BigInteger, db.ForeignKey("sesiones_caja.id"))
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    metodo = db.Column(db.String(20), nullable=False)
    vendido_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    tipo_tarjeta = db.relationship("TipoTarjeta", foreign_keys=[tipo_tarjeta_id])
    cuenta = db.relationship("Cuenta", foreign_keys=[cuenta_id])
    vendedor = db.relationship("Usuario", foreign_keys=[vendido_por])

    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "tipo_tarjeta": self.tipo_tarjeta.nombre if self.tipo_tarjeta else "—",
            "precio": float(self.precio),
            "metodo": self.metodo,
            "vendido_por": (f"{self.vendedor.nombre} {self.vendedor.apellido}"
                            if self.vendedor else "—"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ConfigResidencial(db.Model):
    """
    Configuración de una residencial (día de pago, días de gracia).
    Controla parámetros que aplican a todas las cuentas de ESA residencial.

    Día 54 — bug real encontrado por el usuario, sin relación con los
    niveles de plan: esta tabla estaba diseñada como UNA SOLA FILA global
    (id=1), compartida por TODAS las residenciales del sistema. Cambiar
    el día de pago desde una residencial lo cambiaba para todas. Nunca se
    había notado porque hasta ahora nunca hubo dos residenciales usando
    cuotas al mismo tiempo. Se agrega residencial_id (única, una config
    por residencial) y get() pasa a exigir de cuál residencial se habla.
    """
    __tablename__ = "config_residencial"

    id               = db.Column(db.BigInteger, primary_key=True)
    residencial_id   = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"), unique=True, nullable=True)
    dia_pago         = db.Column(db.Integer, nullable=False, default=1)    # día del mes para el cobro
    dias_gracia      = db.Column(db.Integer, nullable=False, default=7)    # días adicionales antes de bloquear
    actualizado_en   = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    @classmethod
    def get(cls, residencial_id=None):
        """
        Una config por residencial. residencial_id=None se mantiene por
        compatibilidad con instalaciones viejas de un solo tenant (la fila
        legado id=1, sin residencial_id, migrada así a propósito -- ver
        migración) -- todo caller nuevo debe pasar residencial_id real.
        """
        cfg = cls.query.filter_by(residencial_id=residencial_id).first()
        if not cfg:
            cfg = cls(residencial_id=residencial_id, dia_pago=1, dias_gracia=7)
            db.session.add(cfg)
            db.session.commit()
        return cfg

    def to_dict(self):
        return {
            "dia_pago": self.dia_pago,
            "dias_gracia": self.dias_gracia,
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None,
        }


# ---------------------------------------------------------------------
# SOLICITUD DE BAJA: un admin de edificio pide dar de baja a un inquilino
# ---------------------------------------------------------------------
class SolicitudBaja(db.Model):
    __tablename__ = "solicitudes_baja"

    id             = db.Column(db.BigInteger, primary_key=True)
    uuid_publico   = _uuid_col()
    cuenta_id      = db.Column(db.BigInteger, db.ForeignKey("cuentas.id"), nullable=False)
    solicitada_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    motivo         = db.Column(db.Text, nullable=False)
    fecha_desocupacion = db.Column(db.Date, nullable=False)
    estado         = db.Column(db.String(20), nullable=False, default="pendiente")  # pendiente | aprobada | rechazada
    respuesta_admin = db.Column(db.Text)
    created_at     = db.Column(db.DateTime(timezone=True), default=_now)
    resuelto_en    = db.Column(db.DateTime(timezone=True))

    cuenta   = db.relationship("Cuenta", lazy="joined")
    usuario  = db.relationship("Usuario", lazy="joined")

    def to_dict(self):
        c = self.cuenta
        t = c.titular() if c else None
        titular_nombre = f"{t.usuario.nombre} {t.usuario.apellido}" if t and t.usuario else None
        return {
            "id": str(self.uuid_publico),
            "cuenta_id": str(c.uuid_publico) if c else None,
            "apartamento": c.apartamento if c else None,
            "edificio": c.unidad.identificador if c and c.unidad else None,
            "titular": titular_nombre,
            "solicitada_por": f"{self.usuario.nombre} {self.usuario.apellido}" if self.usuario else None,
            "motivo": self.motivo,
            "fecha_desocupacion": self.fecha_desocupacion.isoformat() if self.fecha_desocupacion else None,
            "estado": self.estado,
            "respuesta_admin": self.respuesta_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resuelto_en": self.resuelto_en.isoformat() if self.resuelto_en else None,
        }
