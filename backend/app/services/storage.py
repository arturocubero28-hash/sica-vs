"""
Servicio de almacenamiento de archivos — SICA-VS
=================================================
Abstracción que funciona en DOS modos según las variables de entorno:

MODO LOCAL (desarrollo, sin configurar):
  - Los archivos se guardan en disco, en UPLOAD_FOLDER (/app/uploads)
  - Cero dependencias externas
  - Igual que antes, sin cambios para el desarrollador

MODO NUBE (producción en DigitalOcean):
  - Los archivos se guardan en DigitalOcean Spaces (compatible con S3)
  - Se configura con 4 variables de entorno (ver abajo)
  - Las URLs son públicas (CDN de DO Spaces) o pre-firmadas si es privado
  - El disco del servidor NO guarda fotos → puede ser un Droplet pequeño

Variables de entorno para activar el modo NUBE:
  STORAGE_BACKEND=spaces          (o 's3' — son el mismo protocolo)
  SPACES_KEY=<tu access key>
  SPACES_SECRET=<tu secret key>
  SPACES_BUCKET=sica-vs-archivos  (nombre del bucket que creaste en DO)
  SPACES_REGION=nyc3              (región de tu bucket, ej. nyc3, sfo3)
  SPACES_CDN_URL=https://sica-vs-archivos.nyc3.cdn.digitaloceanspaces.com
    (opcional: si habilitaste CDN en el bucket, usa esa URL para las imágenes)

Si STORAGE_BACKEND no está seteada, cae automáticamente al modo local.
Así el equipo de desarrollo no necesita configurar nada extra.
"""
import os
import io
import uuid as uuid_lib

_backend = None  # lazy init


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    modo = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    if modo in ("spaces", "s3"):
        _backend = _SpacesBackend()
    else:
        _backend = _LocalBackend()
    return _backend


class _LocalBackend:
    """Guarda archivos en disco (UPLOAD_FOLDER). Para desarrollo."""

    def guardar(self, stream, nombre_archivo: str, subcarpeta: str = "",
                content_type: str = "application/octet-stream") -> str:
        """Guarda el stream en disco. Devuelve la clave (subcarpeta/nombre)."""
        from flask import current_app
        base = current_app.config.get("UPLOAD_FOLDER", "/app/uploads")
        carpeta = os.path.join(base, subcarpeta) if subcarpeta else base
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, nombre_archivo)
        with open(ruta, "wb") as f:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                f.write(chunk)
        return f"{subcarpeta}/{nombre_archivo}" if subcarpeta else nombre_archivo

    def url_publica(self, clave: str) -> str | None:
        """En modo local no hay URL pública directa — el backend sirve el archivo."""
        return None

    def stream(self, clave: str):
        """Devuelve (bytes, content_type) del archivo o None si no existe."""
        from flask import current_app
        base = current_app.config.get("UPLOAD_FOLDER", "/app/uploads")
        ruta = os.path.join(base, clave)
        if not os.path.exists(ruta):
            return None, None
        ext = clave.rsplit(".", 1)[-1].lower()
        mimetypes = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "pdf": "application/pdf",
        }
        return open(ruta, "rb"), mimetypes.get(ext, "application/octet-stream")

    def eliminar(self, clave: str) -> bool:
        from flask import current_app
        base = current_app.config.get("UPLOAD_FOLDER", "/app/uploads")
        ruta = os.path.join(base, clave)
        try:
            os.remove(ruta)
            return True
        except FileNotFoundError:
            return False


class _SpacesBackend:
    """Guarda archivos en DigitalOcean Spaces (compatible con AWS S3)."""

    def __init__(self):
        import boto3
        from botocore.client import Config
        region = os.environ.get("SPACES_REGION", "nyc3")
        self._bucket = os.environ.get("SPACES_BUCKET", "sica-vs")
        self._cdn = os.environ.get("SPACES_CDN_URL", "").rstrip("/")
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://{region}.digitaloceanspaces.com",
            aws_access_key_id=os.environ["SPACES_KEY"],
            aws_secret_access_key=os.environ["SPACES_SECRET"],
            config=Config(signature_version="s3v4"),
        )

    def guardar(self, stream, nombre_archivo: str, subcarpeta: str = "",
                content_type: str = "application/octet-stream") -> str:
        clave = f"{subcarpeta}/{nombre_archivo}" if subcarpeta else nombre_archivo
        self._client.upload_fileobj(
            stream,
            self._bucket,
            clave,
            ExtraArgs={
                "ContentType": content_type,
                # FILES-05 (Auditoría Día 35): antes 'public-read'. Fotos de
                # identidad y comprobantes de pago son datos sensibles — un
                # UUID en la URL no es "seguro por oscuridad" si esa URL se
                # filtra en un log, una captura compartida, o un reenvío sin
                # querer. Ahora el bucket es privado y el acceso es siempre
                # a través de servir_archivo() con una URL firmada de corta
                # duración (ver url_firmada), nunca de forma pública directa.
                "ACL": "private",
            },
        )
        return clave

    def url_publica(self, clave: str) -> str | None:
        if self._cdn:
            return f"{self._cdn}/{clave}"
        region = os.environ.get("SPACES_REGION", "nyc3")
        return f"https://{self._bucket}.{region}.digitaloceanspaces.com/{clave}"

    def url_firmada(self, clave: str, expira_en: int = 3600) -> str:
        """URL pre-firmada que expira. Para archivos privados."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": clave},
            ExpiresIn=expira_en,
        )

    def stream(self, clave: str):
        """Descarga el archivo desde Spaces. Para servir vía el backend."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=clave)
            return resp["Body"], resp.get("ContentType", "application/octet-stream")
        except Exception:
            return None, None

    def eliminar(self, clave: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=clave)
            return True
        except Exception:
            return False


# ── API pública del módulo ────────────────────────────────────────────────────

def guardar_archivo(stream, subcarpeta: str, content_type: str = "application/octet-stream",
                    extension: str = "jpg") -> str:
    """
    Guarda un archivo subido. Genera el nombre como UUID para evitar
    colisiones y ataques de path traversal.
    Devuelve la CLAVE del archivo (para guardar en la DB).
    """
    nombre = f"{uuid_lib.uuid4().hex}.{extension}"
    return _get_backend().guardar(stream, nombre, subcarpeta, content_type)


def url_archivo(clave: str) -> str | None:
    """
    URL pública directa del archivo (sin pasar por el backend).

    FILES-05: en modo nube el bucket ahora es PRIVADO — esta función ya no
    devuelve una URL utilizable para fotos de identidad/comprobantes (el
    bucket rechazará el acceso). No está en uso actualmente en el código;
    se conserva por si en el futuro hace falta una URL pública real para
    contenido no sensible (ej. el logo público de la app). Para servir
    archivos sensibles, usar siempre servir_archivo(), que pasa por
    autenticación del endpoint y genera una URL firmada de corta duración.
    """
    return _get_backend().url_publica(clave)


def servir_archivo(clave: str):
    """
    Sirve un archivo desde donde esté (local o Spaces).
    Devuelve una respuesta Flask.

    FILES-05: en modo nube, el bucket es privado — se genera una URL
    pre-firmada de corta duración (10 min) en vez de un link público
    permanente, y se redirige a ella. Cada llamada a este endpoint pasa
    primero por la verificación de rol/pertenencia del endpoint que lo
    invoca (ver_foto, ver_comprobante, ver_imagen) — la URL firmada es
    una capa adicional, no la única protección.
    """
    from flask import send_file, jsonify
    backend = _get_backend()
    # Si está en Spaces, redirigir a una URL firmada de corta duración
    if isinstance(backend, _SpacesBackend):
        from flask import redirect
        url = backend.url_firmada(clave, expira_en=600)  # 10 minutos
        return redirect(url, code=302)
    # Modo local: servir desde disco
    stream, content_type = backend.stream(clave)
    if stream is None:
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Archivo no encontrado"}}), 404
    return send_file(stream, mimetype=content_type)


def eliminar_archivo(clave: str) -> bool:
    """Elimina un archivo. Devuelve True si se eliminó."""
    return _get_backend().eliminar(clave)


def es_modo_nube() -> bool:
    """True si el sistema está usando almacenamiento en la nube."""
    return os.environ.get("STORAGE_BACKEND", "local").lower() in ("spaces", "s3")
