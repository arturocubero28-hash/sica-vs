"""
Configuración central del backend SICA-VS.
Lee las variables de entorno definidas en docker-compose / .env
"""
import os


class Config:
    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://sicavs:sicavs_dev@db:5432/sicavs"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis
    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    # Seguridad / JWT
    JWT_SECRET = os.environ.get("JWT_SECRET", "dev_secret_cambiar")
    # Duración del token de sesión. 12h es un balance entre comodidad (no
    # reloguear seguido) y exposición si un token se filtra. Hay blacklist por
    # jti (logout) y registro de sesiones activas como mitigación. Para mayor
    # seguridad, bajar este valor o implementar refresh tokens a futuro.
    JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", "12"))

    # CORS
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

    # Resend (correo)
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

    # WebAuthn (biometría)
    WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
    WEBAUTHN_RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "SICA-VS Villas del Sol")
    WEBAUTHN_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:5173")

    # Subida de archivos (comprobantes, fotos de visitas)
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/app/uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

    # Entorno: 'development' (default) o 'production'
    ENV = os.environ.get("SICAVS_ENV", "development")

    # Límite de intentos de login. Estricto en producción (frena fuerza bruta);
    # relajado en desarrollo para no estorbar durante las pruebas.
    LOGIN_RATE_LIMIT = "5 per 15 minutes" if ENV == "production" else "100 per minute"

    # OBSOLETO (DEVICE-06, Auditoría Día 35): este token global compartido
    # ya no se usa en ningún endpoint. Cada Raspberry Pi tiene su propio
    # token individual, hasheado en la base (ver Dispositivo.token_hash,
    # panel de desarrollador → Dispositivos). Se conserva la variable acá
    # para no romper el arranque si docker-compose.yml todavía la define.
    DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "sicavs-device-dev")

    # ── Google Wallet (tarjeta virtual de acceso) ──────────────────────────────
    # GOOGLE_ISSUER_ID: el ID numérico del emisor en Google Pay & Wallet Console
    #   → pay.google.com/business/console → URL contiene el issuer ID
    # GOOGLE_SERVICE_ACCOUNT_EMAIL: email de la cuenta de servicio de Google Cloud
    # GOOGLE_SERVICE_ACCOUNT_KEY: contenido completo del JSON descargado de GCP
    #   (poner en una sola línea escapando las comillas, o usar un archivo montado)
    # LOGO_URL: URL pública del logo para que aparezca en el pase de la Wallet
    #   Ej: https://sicavs.villasdelsol.hn/logo-vs.png
    GOOGLE_ISSUER_ID            = os.environ.get("GOOGLE_ISSUER_ID", "")
    GOOGLE_SERVICE_ACCOUNT_EMAIL = os.environ.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
    GOOGLE_SERVICE_ACCOUNT_KEY   = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    LOGO_URL = os.environ.get("LOGO_URL", "")


# Defaults inseguros que NUNCA deben usarse en producción
_SECRETOS_INSEGUROS = {
    "dev_secret_cambiar",
    "cambiar_esto_en_produccion",
}


def validar_config_produccion():
    """
    Si el backend arranca en modo producción (SICAVS_ENV=production), se niega a
    iniciar si detecta secretos con valores de desarrollo. Esto evita el riesgo
    de desplegar con un JWT_SECRET conocido (cualquiera podría forjar tokens).
    Llamar desde create_app() al inicio.
    """
    if Config.ENV != "production":
        return  # en desarrollo no se valida

    problemas = []
    if Config.JWT_SECRET in _SECRETOS_INSEGUROS or len(Config.JWT_SECRET) < 32:
        problemas.append(
            "JWT_SECRET es inseguro o muy corto. Generá uno aleatorio largo, ej:\n"
            "    python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if "sicavs_dev" in Config.SQLALCHEMY_DATABASE_URI:
        problemas.append("La contraseña de PostgreSQL sigue siendo la de desarrollo (sicavs_dev).")
    # CORS con credenciales no debe usar comodín ni http en producción
    if "*" in Config.CORS_ORIGINS:
        problemas.append("CORS_ORIGINS no puede contener '*' en producción (se usan credenciales).")
    if any(o.strip().startswith("http://") for o in Config.CORS_ORIGINS):
        problemas.append("CORS_ORIGINS contiene orígenes http:// en producción; deben ser https://.")

    if problemas:
        msg = ("\n" + "=" * 60 +
               "\n  SICA-VS NO PUEDE ARRANCAR EN PRODUCCIÓN\n" + "=" * 60 +
               "\nSe detectaron secretos inseguros:\n\n  - " +
               "\n  - ".join(problemas) +
               "\n\nSeteá las variables de entorno correctas antes de desplegar.\n" +
               "=" * 60)
        raise RuntimeError(msg)
