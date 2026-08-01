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


def comprimir_imagen_webp(datos: bytes, calidad: int = 70, max_size: int = 1024) -> bytes | None:
    """
    Comprime una imagen a WebP — mismo criterio que usa la app móvil
    (lib/api/camara_helper.dart: calidad 70, redimensiona si excede
    max_size, sin EXIF). Se agrega del lado del servidor porque esa
    compresión de la app es SOLO del lado del cliente (un plugin de
    Flutter) — el panel web (tanto el comprobante de suscripción del
    admin como el de cuotas del residente desde la web) no tenía
    ninguna compresión, subía el archivo tal cual lo eligiera el
    usuario. Aplicarlo acá, del lado del servidor, cubre los dos
    caminos (app y web) con una sola implementación, sin depender de
    que cada frontend lo repita por su cuenta.

    Devuelve los bytes comprimidos, o None si algo sale mal — nunca
    debe bloquear una subida por un problema de compresión, en ese caso
    el llamador sigue con el archivo original sin tocar.
    """
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(datos))
        img = img.convert("RGB")  # fotos reales no necesitan canal alfa
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        salida = io.BytesIO()
        img.save(salida, format="WEBP", quality=calidad, method=6)
        return salida.getvalue()
    except Exception:
        return None


def guardar_imagen_segura(archivo, carpeta_destino, extensiones=EXT_IMAGEN):
    """
    Guarda un archivo subido de forma segura.
    Retorna (clave_archivo, error, tamano_bytes). Si falla: (None, mensaje, None).
    La clave puede ser una ruta local o una clave de Spaces según el entorno.

    tamano_bytes es el tamaño REAL después de comprimir (si se comprimió) —
    quien llama y necesita contar esto contra una cuota de almacenamiento
    debe usar ESTE valor, no calcular el tamaño del archivo original antes
    de llamar (eso contaría de más, el tamaño previo a comprimir).
    """
    if not archivo or not archivo.filename:
        return None, "No se adjuntó ningún archivo. Seleccioná una foto o PDF del comprobante.", None

    ext = extension_segura(archivo.filename)
    if not ext or ext not in extensiones:
        permitidas = ", ".join(sorted(extensiones)).upper()
        return None, (f"Ese tipo de archivo no se permite. "
                      f"Subí una imagen o PDF ({permitidas}). "
                      f"Si es una captura de pantalla, guardala como JPG o PNG."), None

    if not validar_contenido(archivo.stream, ext):
        return None, ("El archivo parece estar dañado o no es una imagen válida. "
                      "Probá tomar la foto de nuevo o elegir otro archivo."), None

    # Compresión del lado del servidor (ver comprimir_imagen_webp) — solo
    # para imágenes reales, un PDF de comprobante se deja tal cual. Si la
    # compresión falla por cualquier motivo, se sigue con el archivo
    # original sin tocar — nunca bloquea la subida.
    #
    # Corrección (Día 50, señalada por el usuario): la app móvil YA
    # comprime del lado del cliente antes de subir (WebP, 40-70KB
    # típico) -- ese trabajo se hizo ahí a propósito, para no
    # sobrecargar el servidor. El primer intento de esta función
    # recomprimía TODO sin distinción, repitiendo ese trabajo de la app
    # de nuevo del lado del servidor. Ahora, si lo que llega ya es chico
    # (≤ UMBRAL_YA_COMPRIMIDO), se deja tal cual -- el servidor solo
    # entra a comprimir cuando hace falta de verdad (subidas grandes sin
    # comprimir, típicamente del panel web).
    UMBRAL_YA_COMPRIMIDO = 200 * 1024  # 200 KB
    stream_final = archivo.stream
    ext_final = ext
    if ext in EXT_IMAGEN:  # no incluye "pdf"
        datos_originales = archivo.stream.read()
        archivo.stream.seek(0)
        if len(datos_originales) > UMBRAL_YA_COMPRIMIDO:
            comprimido = comprimir_imagen_webp(datos_originales)
            if comprimido is not None:
                import io
                stream_final = io.BytesIO(comprimido)
                ext_final = "webp"

    stream_final.seek(0, os.SEEK_END)
    tam = stream_final.tell()
    stream_final.seek(0)
    MAX_BYTES = 5 * 1024 * 1024
    if tam > MAX_BYTES:
        mb = tam / (1024 * 1024)
        return None, (f"El archivo pesa {mb:.1f} MB y el máximo es 5 MB. "
                      f"Reducí la resolución de la foto o comprimila."), None

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
        ct = content_types.get(ext_final, "application/octet-stream")
        try:
            clave = guardar_archivo(stream_final, subcarpeta, ct, ext_final)
            return clave, None, tam
        except Exception as e:
            return None, f"Error al subir el archivo a la nube: {e}", None
    else:
        # Modo local: guardar en disco. Se escribe stream_final (los bytes
        # ya comprimidos, si la compresión funcionó) en vez de
        # archivo.save() directo, que hubiera guardado el original sin
        # comprimir.
        nombre_seguro = f"{uuid_lib.uuid4().hex}.{ext_final}"
        os.makedirs(carpeta_destino, exist_ok=True)
        ruta = os.path.join(carpeta_destino, nombre_seguro)
        with open(ruta, "wb") as f:
            f.write(stream_final.read())
        return nombre_seguro, None, tam


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
