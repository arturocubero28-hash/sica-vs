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
