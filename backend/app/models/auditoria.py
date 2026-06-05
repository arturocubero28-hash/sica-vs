"""
Log de auditoría forense — registra accesos al sistema para diagnóstico.
Cada entrada guarda: usuario, acción (endpoint), método HTTP, IP, timestamp
y el status code de la respuesta.
"""
import uuid
import datetime as dt
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


class LogAuditoria(db.Model):
    __tablename__ = "log_auditoria"

    id          = db.Column(db.BigInteger, primary_key=True)
    usuario_id  = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=True)
    email       = db.Column(db.String(120))           # por si el usuario no existe aún
    rol         = db.Column(db.String(30))
    metodo      = db.Column(db.String(10))            # GET, POST, etc.
    endpoint    = db.Column(db.String(200))           # /api/v1/auth/login
    status_code = db.Column(db.Integer)               # 200, 401, 500...
    ip          = db.Column(db.String(45))            # IPv4 o IPv6
    user_agent  = db.Column(db.String(300))
    created_at  = db.Column(db.DateTime(timezone=True), default=_now)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def descripcion(self):
        """Convierte el endpoint técnico en un texto legible para auditoría."""
        e = self.endpoint or ""
        m = self.metodo or ""
        mapa = {
            ("POST", "/api/v1/auth/login"):            "Inicio de sesión",
            ("GET",  "/api/v1/auth/me"):               "Verificó su sesión",
            ("POST", "/api/v1/caja/abrir"):            "Abrió caja",
            ("POST", "/api/v1/caja/cerrar"):           "Cerró caja",
            ("POST", "/api/v1/caja/pago"):             "Registró pago en ventanilla",
            ("POST", "/api/v1/caja/salida"):           "Solicitó salida de caja (depósito)",
            ("POST", "/api/v1/caja/ingreso"):          "Solicitó ingreso extraordinario",
            ("POST", "/api/v1/caja/saldo-inicial"):    "Modificó saldo inicial de caja",
            ("POST", "/api/v1/caja/descuadre"):        "Reportó descuadre de caja",
            ("POST", "/api/v1/cuotas/mias"):           "Subió comprobante de pago",
            ("POST", "/api/v1/visitas/"):              "Generó código QR de visita",
            ("POST", "/api/v1/visitas/qr/validar"):   "Validó código QR (guardia)",
            ("POST", "/api/v1/visitas/accesos/visita"):"Registró acceso con fotos",
            ("POST", "/api/v1/auth/recuperar"):        "Solicitó recuperación de contraseña",
            ("POST", "/api/v1/auth/reset"):            "Restableció contraseña",
        }
        # Buscar match exacto primero
        key = (m, e)
        if key in mapa:
            return mapa[key]
        # Buscar por prefijo
        for (met, path), desc in mapa.items():
            if m == met and e.startswith(path):
                return desc
        # Fallback legible
        accion = {"GET": "Consultó", "POST": "Ejecutó", "PUT": "Actualizó", "DELETE": "Eliminó"}.get(m, m)
        ruta = e.replace("/api/v1/", "").replace("/", " › ")
        return f"{accion} {ruta}"

    def to_dict(self):
        return {
            "id":           self.id,
            "email":        self.email or "—",
            "rol":          self.rol or "—",
            "metodo":       self.metodo,
            "endpoint":     self.endpoint,
            "descripcion":  self.descripcion(),
            "status_code":  self.status_code,
            "ip":           self.ip,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }
