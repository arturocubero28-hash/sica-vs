"""
Utilidades de seguridad para manejo de archivos subidos.
Previene:
  - Path traversal (../../etc/passwd)
  - Subida de scripts ejecutables (.php, .py, .sh, .exe, etc.)
  - Nombres de archivo maliciosos
  - Doble extensión (imagen.jpg.php)
  - Validación por contenido real (magic bytes), no solo extensión
"""
import os
import uuid as uuid_lib
from flask import send_file, jsonify
from werkzeug.utils import secure_filename

# Extensiones de imagen permitidas (whitelist estricta)
EXT_IMAGEN = {"png", "jpg", "jpeg", "webp", "gif"}
EXT_DOCUMENTO = {"png", "jpg", "jpeg", "webp", "pdf"}  # comprobantes

# Firmas (magic bytes) de cada tipo real de archivo
MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",          # webp empieza con RIFF
    b"%PDF": "pdf",
}

# Mimetypes para servir
MIMETYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
}


def extension_segura(filename: str) -> str | None:
    """Devuelve la extensión en minúsculas si el nombre es válido, o None."""
    if not filename or "." not in filename:
        return None
    # Rechazar nombres con caracteres de path
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    partes = filename.rsplit(".", 1)
    ext = partes[1].lower().strip()
    return ext or None


def validar_contenido(stream, ext_declarada: str) -> bool:
    """Lee los primeros bytes y verifica que el contenido real coincida con la extensión."""
    head = stream.read(16)
    stream.seek(0)
    for firma, tipo in MAGIC.items():
        if head.startswith(firma):
            # jpg/jpeg son equivalentes
            if tipo == "jpg" and ext_declarada in ("jpg", "jpeg"):
                return True
            return tipo == ext_declarada
    return False


def guardar_imagen_segura(archivo, carpeta_destino, extensiones=EXT_IMAGEN):
    """
    Guarda un archivo subido de forma segura.
    Retorna (clave_archivo, None) si OK, o (None, mensaje_error) si falla.
    La clave puede ser una ruta local o una clave de Spaces según el entorno.
    """
    if not archivo or not archivo.filename:
        return None, "No se adjuntó ningún archivo. Seleccioná una foto o PDF del comprobante."

    ext = extension_segura(archivo.filename)
    if not ext or ext not in extensiones:
        permitidas = ", ".join(sorted(extensiones)).upper()
        return None, (f"Ese tipo de archivo no se permite. "
                      f"Subí una imagen o PDF ({permitidas}). "
                      f"Si es una captura de pantalla, guardala como JPG o PNG.")

    if not validar_contenido(archivo.stream, ext):
        return None, ("El archivo parece estar dañado o no es una imagen válida. "
                      "Probá tomar la foto de nuevo o elegir otro archivo.")

    archivo.stream.seek(0, os.SEEK_END)
    tam = archivo.stream.tell()
    archivo.stream.seek(0)
    MAX_BYTES = 5 * 1024 * 1024
    if tam > MAX_BYTES:
        mb = tam / (1024 * 1024)
        return None, (f"El archivo pesa {mb:.1f} MB y el máximo es 5 MB. "
                      f"Reducí la resolución de la foto o comprimila.")

    # Detectar si estamos en modo nube
    from app.services.storage import es_modo_nube, guardar_archivo
    if es_modo_nube():
        # En modo nube: la subcarpeta se deriva del path de carpeta_destino
        # para mantener la misma estructura (comprobantes/, fotos-acceso/, etc.)
        base = os.environ.get("UPLOAD_FOLDER", "/app/uploads")
        subcarpeta = os.path.relpath(carpeta_destino, base).replace("\\", "/")
        content_types = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "pdf": "application/pdf",
        }
        ct = content_types.get(ext, "application/octet-stream")
        try:
            clave = guardar_archivo(archivo.stream, subcarpeta, ct, ext)
            return clave, None
        except Exception as e:
            return None, f"Error al subir el archivo a la nube: {e}"
    else:
        # Modo local: guardar en disco como antes
        nombre_seguro = f"{uuid_lib.uuid4().hex}.{ext}"
        os.makedirs(carpeta_destino, exist_ok=True)
        ruta = os.path.join(carpeta_destino, nombre_seguro)
        archivo.save(ruta)
        return nombre_seguro, None


def servir_archivo_seguro(carpeta, nombre_archivo):
    """
    Sirve un archivo de forma segura, previniendo path traversal.
    En modo nube redirige al CDN de Spaces directamente.
    """
    from app.services.storage import es_modo_nube, servir_archivo
    if es_modo_nube():
        # En modo nube la clave es subcarpeta/nombre o solo nombre
        base = os.environ.get("UPLOAD_FOLDER", "/app/uploads")
        try:
            subcarpeta = os.path.relpath(carpeta, base).replace("\\", "/")
            clave = f"{subcarpeta}/{nombre_archivo}" if subcarpeta != "." else nombre_archivo
        except ValueError:
            clave = nombre_archivo
        return servir_archivo(clave)

    # Modo local: secure_filename + anti traversal
    nombre_limpio = secure_filename(nombre_archivo)
    if not nombre_limpio or nombre_limpio != nombre_archivo:
        return jsonify({"error": {"code": "nombre_invalido",
                                  "message": "Nombre de archivo no válido"}}), 400

    ruta = os.path.join(carpeta, nombre_limpio)
    ruta_real = os.path.realpath(ruta)
    carpeta_real = os.path.realpath(carpeta)
    if not ruta_real.startswith(carpeta_real + os.sep):
        return jsonify({"error": {"code": "acceso_denegado",
                                  "message": "Acceso denegado"}}), 403

    if not os.path.exists(ruta_real):
        return jsonify({"error": {"code": "no_encontrado",
                                  "message": "Archivo no encontrado"}}), 404

    ext = nombre_limpio.rsplit(".", 1)[-1].lower()
    mimetype = MIMETYPES.get(ext, "application/octet-stream")
    return send_file(ruta_real, mimetype=mimetype)
