"""
Modelo SesionActiva — registro de sesiones (dispositivos conectados).

Cada login crea una sesión con el jti del token, el dispositivo (User-Agent),
la IP y las marcas de tiempo. Permite al usuario ver dónde tiene sesión
abierta y cerrar dispositivos específicos (estilo WhatsApp/Google).

Cerrar una sesión = revocar su jti (blacklist) + eliminar el registro.
"""
import datetime as dt
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


class SesionActiva(db.Model):
    __tablename__ = "sesiones_activas"

    id            = db.Column(db.BigInteger, primary_key=True)
    usuario_id    = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    jti           = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # Info del dispositivo (derivada del User-Agent)
    dispositivo   = db.Column(db.String(120))   # ej: "Chrome en Windows"
    user_agent    = db.Column(db.String(300))
    ip            = db.Column(db.String(45))
    creada_en     = db.Column(db.DateTime(timezone=True), default=_now)
    ultimo_uso    = db.Column(db.DateTime(timezone=True), default=_now)
    expira_en     = db.Column(db.DateTime(timezone=True), nullable=False)

    def to_dict(self, jti_actual=None):
        return {
            "id": self.id,
            "dispositivo": self.dispositivo or "Dispositivo desconocido",
            "ip": self.ip,
            "creada_en": self.creada_en.isoformat() if self.creada_en else None,
            "ultimo_uso": self.ultimo_uso.isoformat() if self.ultimo_uso else None,
            "es_actual": (self.jti == jti_actual) if jti_actual else False,
        }


def describir_dispositivo(user_agent: str) -> str:
    """
    Convierte un User-Agent en una descripción legible tipo 'Chrome en Windows'.
    Heurística simple, suficiente para mostrar al usuario.
    """
    if not user_agent:
        return "Dispositivo desconocido"
    ua = user_agent.lower()
    # Navegador
    if "edg" in ua:
        nav = "Edge"
    elif "chrome" in ua and "chromium" not in ua:
        nav = "Chrome"
    elif "firefox" in ua:
        nav = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        nav = "Safari"
    elif "samsungbrowser" in ua:
        nav = "Samsung Internet"
    else:
        nav = "Navegador"
    # Sistema operativo
    if "android" in ua:
        so = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        so = "iPhone/iPad"
    elif "windows" in ua:
        so = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        so = "Mac"
    elif "linux" in ua:
        so = "Linux"
    else:
        so = "dispositivo"
    return f"{nav} en {so}"
