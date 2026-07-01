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
    tipo = db.Column(db.String(10), nullable=False)        # 'casa' | 'edificio'
    identificador = db.Column(db.String(60), unique=True, nullable=False)  # "Casa 24", "Edificio 1"
    direccion_ref = db.Column(db.String(160))
    # Para edificios: el usuario dueño/responsable que avala a sus inquilinos
    propietario_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    activa = db.Column(db.Boolean, nullable=False, default=True)
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
    tarifa_id = db.Column(db.BigInteger, db.ForeignKey("tarifas.id"), nullable=False)
    dia_pago = db.Column(db.SmallInteger, nullable=False)   # 1..28
    fecha_alta = db.Column(db.Date, nullable=False, default=dt.date.today)
    estado = db.Column(db.String(20), nullable=False, default="al_dia")
    bloqueada = db.Column(db.Boolean, nullable=False, default=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)   # baja: deja de generar cuotas y accesos
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

    def to_dict(self, detalle=False):
        t = self.titular()
        unidad = None
        try:
            unidad = self.unidad.identificador if self.unidad else None
        except Exception:
            unidad = None
        d = {
            "id": str(self.uuid_publico),
            "apartamento": self.apartamento,
            "identificador": unidad,
            "nombre_completo": (f"{unidad} · Apto {self.apartamento}"
                                if unidad and self.apartamento else (unidad or "—")),
            "es_apartamento": bool(self.apartamento),
            "dia_pago": self.dia_pago,
            "estado": self.estado,
            "bloqueada": self.bloqueada,
            "activa": self.activa,
            "tarifa": self.tarifa.nombre if self.tarifa else None,
            "monto": float(self.tarifa.monto) if self.tarifa else None,
            "titular": t.to_dict() if t else None,
            "total_residentes": len([r for r in self.residentes if r.activo]),
            "total_tarjetas": len([x for x in self.tarjetas if x.estado == "activa"]),
        }
        if detalle:
            d["residentes"] = [r.to_dict() for r in self.residentes if r.activo]
            d["tarjetas"] = [x.to_dict() for x in self.tarjetas]
        return d


# ---------------------------------------------------------------------
# TARIFA (catálogo; ya existe en el schema, modelo mínimo para relación)
# ---------------------------------------------------------------------
class Tarifa(db.Model):
    __tablename__ = "tarifas"

    id = db.Column(db.BigInteger, primary_key=True)
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
    rol_cuenta = db.Column(db.String(10), nullable=False, default="miembro")  # titular | miembro
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
    tipo_acceso = db.Column(db.String(20), nullable=False, default="vehicular")  # vehicular | peatonal
    estado = db.Column(db.String(20), nullable=False, default="activa")
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
    subido_por           = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    metodo               = db.Column(db.String(20), nullable=False, default="transferencia")
    monto                = db.Column(db.Numeric(10, 2), nullable=False)
    comprobante_archivo  = db.Column(db.String(255))
    referencia           = db.Column(db.String(120))
    estado               = db.Column(db.String(20), nullable=False, default="en_revision", index=True)
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

    def to_dict(self):
        return {
            "id":                  str(self.uuid_publico),
            "cuota_id":            str(self.cuota.uuid_publico) if self.cuota else None,
            "monto":               float(self.monto),
            "metodo":              self.metodo,
            "referencia":          self.referencia,
            "comprobante_archivo": self.comprobante_archivo,
            "numero_recibo":       self.numero_recibo,
            "estado":              self.estado,
            "nota_admin":          self.nota_admin,
            "revisado_en":         self.revisado_en.isoformat() if self.revisado_en else None,
            "created_at":          self.created_at.isoformat(),
        }


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
    Configuración de recibos (una sola fila, id=1).
    FASE 1: datos del emisor + correlativo interno.
    FASE 2 (preparado): CAI, rango autorizado y fecha límite de la SAR.
    """
    __tablename__ = "config_recibo"

    id                 = db.Column(db.BigInteger, primary_key=True)
    # Datos del emisor (Fase 1)
    nombre_emisor      = db.Column(db.String(160), default="Residencial Villas del Sol")
    rtn_emisor         = db.Column(db.String(20))
    direccion_emisor   = db.Column(db.String(255), default="San Pedro Sula, Honduras")
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
    def get(cls):
        cfg = cls.query.get(1)
        if not cfg:
            cfg = cls(id=1)
            db.session.add(cfg)
            db.session.commit()
        return cfg

    def siguiente_correlativo(self):
        """Reserva y devuelve el siguiente número de recibo."""
        self.ultimo_correlativo = (self.ultimo_correlativo or 0) + 1
        return self.ultimo_correlativo

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
