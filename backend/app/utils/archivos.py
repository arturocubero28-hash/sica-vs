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
    Retorna (nombre_generado, None) si OK, o (None, mensaje_error) si falla.

    Seguridad aplicada:
      - Whitelist de extensiones
      - Validación de magic bytes (el contenido debe ser realmente una imagen)
      - Nombre 100% generado por el servidor (UUID), nunca el del usuario
      - El usuario nunca controla la ruta ni el nombre
    """
    if not archivo or not archivo.filename:
        return None, "No se adjuntó ningún archivo. Seleccioná una foto o PDF del comprobante."

    ext = extension_segura(archivo.filename)
    if not ext or ext not in extensiones:
        permitidas = ", ".join(sorted(extensiones)).upper()
        return None, (f"Ese tipo de archivo no se permite. "
                      f"Subí una imagen o PDF ({permitidas}). "
                      f"Si es una captura de pantalla, guardala como JPG o PNG.")

    # Validar que el contenido real coincida con la extensión
    if not validar_contenido(archivo.stream, ext):
        return None, ("El archivo parece estar dañado o no es una imagen válida. "
                      "Probá tomar la foto de nuevo o elegir otro archivo.")

    # Validar tamaño máximo (5 MB). Se mide moviendo el cursor al final.
    archivo.stream.seek(0, os.SEEK_END)
    tam = archivo.stream.tell()
    archivo.stream.seek(0)
    MAX_BYTES = 5 * 1024 * 1024
    if tam > MAX_BYTES:
        mb = tam / (1024 * 1024)
        return None, (f"El archivo pesa {mb:.1f} MB y el máximo es 5 MB. "
                      f"Reducí la resolución de la foto o comprimila.")

    # Nombre generado por el servidor — el usuario NO controla el nombre
    nombre_seguro = f"{uuid_lib.uuid4().hex}.{ext}"
    os.makedirs(carpeta_destino, exist_ok=True)
    ruta = os.path.join(carpeta_destino, nombre_seguro)
    archivo.save(ruta)
    return nombre_seguro, None


def servir_archivo_seguro(carpeta, nombre_archivo):
    """
    Sirve un archivo de forma segura, previniendo path traversal.
    Devuelve la respuesta Flask o un error JSON.
    """
    # secure_filename elimina cualquier intento de path traversal
    nombre_limpio = secure_filename(nombre_archivo)
    if not nombre_limpio or nombre_limpio != nombre_archivo:
        return jsonify({"error": {"code": "nombre_invalido",
                                  "message": "Nombre de archivo no válido"}}), 400

    ruta = os.path.join(carpeta, nombre_limpio)
    # Verificar que la ruta resuelta esté DENTRO de la carpeta (anti traversal)
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
