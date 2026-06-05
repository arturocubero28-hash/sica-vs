"""
Módulo de Caja — sesiones de caja con apertura, arqueo y cierre.

Flujo:
  1. El cajero ABRE una sesión con un monto inicial en efectivo (fondo de caja).
  2. Durante el día registra pagos en ventanilla (efectivo o tarjeta POS).
     Cada pago queda vinculado a la sesión (Pago.sesion_caja_id).
  3. Al CERRAR, el cajero cuenta el efectivo real y los vouchers POS.
     El sistema compara lo esperado vs lo contado y guarda la diferencia.
"""
import uuid
import datetime as dt
from app.extensions import db


def _uuid_col():
    return db.Column(db.UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)


def _now():
    return dt.datetime.now(dt.timezone.utc)


class SesionCaja(db.Model):
    __tablename__ = "sesiones_caja"

    id              = db.Column(db.BigInteger, primary_key=True)
    uuid_publico    = _uuid_col()
    cajero_id       = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)

    estado          = db.Column(db.String(15), nullable=False, default="abierta")  # abierta | cerrada
    monto_inicial   = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Valores al cierre (los cuenta el cajero)
    efectivo_contado = db.Column(db.Numeric(10, 2))
    pos_contado      = db.Column(db.Numeric(10, 2))
    nota_cierre      = db.Column(db.String(255))

    abierta_en      = db.Column(db.DateTime(timezone=True), default=_now)
    cerrada_en      = db.Column(db.DateTime(timezone=True))

    cajero = db.relationship("Usuario", foreign_keys=[cajero_id])
    pagos  = db.relationship("Pago", backref="sesion_caja", lazy="select")

    def resumen(self):
        """Calcula totales de la sesión a partir de los pagos vinculados."""
        efectivo = sum(float(p.monto) for p in self.pagos if p.metodo == "efectivo")
        pos      = sum(float(p.monto) for p in self.pagos if p.metodo == "tarjeta_pos")
        otros    = sum(float(p.monto) for p in self.pagos if p.metodo not in ("efectivo", "tarjeta_pos"))
        # Salidas: monto positivo = sale dinero, monto negativo = entra dinero (ingreso)
        salidas  = sum(float(s.monto) for s in self.salidas if s.estado == "autorizada" and float(s.monto) > 0)
        ingresos = sum(-float(s.monto) for s in self.salidas if s.estado == "autorizada" and float(s.monto) < 0)
        return {
            "efectivo": efectivo,
            "pos": pos,
            "otros": otros,
            "salidas": salidas,
            "ingresos": ingresos,
            "cantidad_pagos": len(self.pagos),
        }

    def to_dict(self, con_pagos=False):
        r = self.resumen()
        inicial = float(self.monto_inicial)
        # efectivo_esperado = fondo + cobros - salidas + ingresos
        efectivo_esperado = inicial + r["efectivo"] - r["salidas"] + r["ingresos"]

        d = {
            "id":             str(self.uuid_publico),
            "estado":         self.estado,
            "cajero":         f"{self.cajero.nombre} {self.cajero.apellido}" if self.cajero else "—",
            "monto_inicial":  inicial,
            "total_efectivo": r["efectivo"],
            "total_pos":      r["pos"],
            "total_otros":    r["otros"],
            "total_salidas":  r["salidas"],
            "total_ingresos": r["ingresos"],
            "cantidad_pagos": r["cantidad_pagos"],
            "efectivo_esperado": efectivo_esperado,
            "pos_esperado":   r["pos"],
            "abierta_en":     self.abierta_en.isoformat() if self.abierta_en else None,
            "cerrada_en":     self.cerrada_en.isoformat() if self.cerrada_en else None,
        }
        if self.estado == "cerrada":
            ef_contado = float(self.efectivo_contado or 0)
            pos_contado = float(self.pos_contado or 0)
            d["efectivo_contado"] = ef_contado
            d["pos_contado"] = pos_contado
            d["diferencia_efectivo"] = round(ef_contado - efectivo_esperado, 2)
            d["diferencia_pos"] = round(pos_contado - r["pos"], 2)
            d["nota_cierre"] = self.nota_cierre
        if con_pagos:
            d["pagos"] = [{
                "id": str(p.uuid_publico),
                "monto": float(p.monto),
                "metodo": p.metodo,
                "referencia": p.referencia,
                "hora": p.created_at.isoformat() if p.created_at else None,
            } for p in self.pagos]
        return d


class ConfigCaja(db.Model):
    """
    Configuración global de caja (una sola fila, id=1).
    Mantiene el saldo inicial del sistema (cuando se implementa en una
    residencial que ya venía operando con otro sistema) y permite ajustes
    manuales, siempre protegidos por la clave del desarrollador.
    """
    __tablename__ = "config_caja"

    id              = db.Column(db.BigInteger, primary_key=True)
    saldo_inicial   = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    actualizado_en  = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)
    actualizado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))

    @classmethod
    def get(cls):
        """Devuelve la fila única de configuración, creándola si no existe."""
        cfg = cls.query.get(1)
        if not cfg:
            cfg = cls(id=1, saldo_inicial=0)
            db.session.add(cfg)
            db.session.commit()
        return cfg

    def to_dict(self):
        return {
            "saldo_inicial": float(self.saldo_inicial),
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None,
        }


class AjusteCaja(db.Model):
    """
    Ajustes al saldo de caja: descuadres (sobrante/faltante) reportados por
    el cajero y aprobados por admin/desarrollador, y cambios de saldo inicial.
    Cada ajuste afecta el saldo de caja del sistema una vez aprobado.
    """
    __tablename__ = "ajustes_caja"

    id            = db.Column(db.BigInteger, primary_key=True)
    uuid_publico  = _uuid_col()
    tipo          = db.Column(db.String(20), nullable=False)   # sobrante | faltante | saldo_inicial
    monto         = db.Column(db.Numeric(12, 2), nullable=False)  # positivo suma, negativo resta
    motivo        = db.Column(db.String(255))
    estado        = db.Column(db.String(15), nullable=False, default="pendiente")  # pendiente | aprobado | rechazado

    sesion_caja_id = db.Column(db.BigInteger, db.ForeignKey("sesiones_caja.id"))
    reportado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    aprobado_por  = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))

    created_at    = db.Column(db.DateTime(timezone=True), default=_now)
    resuelto_en   = db.Column(db.DateTime(timezone=True))

    reportador = db.relationship("Usuario", foreign_keys=[reportado_por])
    aprobador  = db.relationship("Usuario", foreign_keys=[aprobado_por])

    def to_dict(self):
        return {
            "id":           str(self.uuid_publico),
            "tipo":         self.tipo,
            "monto":        float(self.monto),
            "motivo":       self.motivo,
            "estado":       self.estado,
            "reportado_por": f"{self.reportador.nombre} {self.reportador.apellido}" if self.reportador else "—",
            "aprobado_por": f"{self.aprobador.nombre} {self.aprobador.apellido}" if self.aprobador else None,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "resuelto_en":  self.resuelto_en.isoformat() if self.resuelto_en else None,
        }


class SalidaCaja(db.Model):
    """
    Salida de efectivo de caja: cuando el cajero manda dinero al banco
    u otro concepto autorizado. Reduce el efectivo_esperado de la sesión.

    Flujo:
      1. Cajero solicita salida (queda en estado 'pendiente').
      2. Admin la autoriza con su contraseña (estado → 'autorizada').
      3. Al autorizar, el monto se descuenta del efectivo esperado de la sesión.
      4. Si se rechaza, no afecta nada.
    """
    __tablename__ = "salidas_caja"

    id            = db.Column(db.BigInteger, primary_key=True)
    uuid_publico  = _uuid_col()
    sesion_id     = db.Column(db.BigInteger, db.ForeignKey("sesiones_caja.id"), nullable=False)
    monto         = db.Column(db.Numeric(12, 2), nullable=False)
    concepto      = db.Column(db.String(255), nullable=False)   # "Depósito banco Ficohsa", etc.
    estado        = db.Column(db.String(15), nullable=False, default="pendiente")
    # pendiente | autorizada | rechazada

    solicitado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    autorizado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"))
    created_at     = db.Column(db.DateTime(timezone=True), default=_now)
    resuelto_en    = db.Column(db.DateTime(timezone=True))

    sesion      = db.relationship("SesionCaja", backref="salidas")
    solicitador = db.relationship("Usuario", foreign_keys=[solicitado_por])
    autorizador = db.relationship("Usuario", foreign_keys=[autorizado_por])

    def to_dict(self):
        return {
            "id":             str(self.uuid_publico),
            "sesion_id":      str(self.sesion.uuid_publico) if self.sesion else None,
            "monto":          float(self.monto),
            "concepto":       self.concepto,
            "estado":         self.estado,
            "solicitado_por": f"{self.solicitador.nombre} {self.solicitador.apellido}" if self.solicitador else "—",
            "autorizado_por": f"{self.autorizador.nombre} {self.autorizador.apellido}" if self.autorizador else None,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "resuelto_en":    self.resuelto_en.isoformat() if self.resuelto_en else None,
        }
