"""
Criptografía del acceso BLE — cálculo y verificación del HMAC.

BLE-BE-18 (Auditoría Día 39). Ver docs/BLE_PROTOCOLO.md para el diseño completo.

PRINCIPIO CENTRAL:
    La clave secreta de una credencial vive en exactamente dos lugares:
    el servidor y el teléfono de su dueño. En ningún otro.

    Antes, /sincronizar enviaba clave_secreta en texto plano a cada
    Raspberry Pi. Eso anulaba el propósito del HMAC: una Pi comprometida
    habría entregado las credenciales de todos los residentes. Este módulo
    existe para que la verificación ocurra en el servidor, que es el único
    lugar (además del teléfono dueño) donde la clave tiene que estar.

    La Pi transporta la trama y aplica la decisión. No verifica firmas:
    no tiene con qué, y así debe ser.
"""
import hmac
import hashlib

# Versión del formato de trama. Va como primer byte del mensaje firmado,
# así un cambio de formato invalida automáticamente las firmas viejas y
# permite convivencia de versiones si algún día hace falta.
VERSION_TRAMA = 1

# Bytes del HMAC-SHA256 que viajan en la trama. El advertising BLE deja
# ~23 bytes útiles y un HMAC completo son 32, así que hay que truncar —
# es lo que hacen todos los sistemas BLE reales. 8 bytes = 64 bits: falsificar
# sin la clave requiere ~2^63 intentos, cada uno con una transmisión física
# frente al lector. Inviable.
BYTES_HMAC = 8

# Longitud del token en bytes (el hex tras el prefijo "BLE").
BYTES_TOKEN = 8


def _token_a_bytes(token):
    """
    Convierte "BLE7A3F9C21D8E4B506" en sus 8 bytes.

    El prefijo "BLE" es legibilidad para humanos (logs, panel admin); no
    aporta entropía, así que no se firma.
    """
    if not token:
        raise ValueError("token vacío")
    hexpart = token[3:] if token.upper().startswith("BLE") else token
    try:
        crudo = bytes.fromhex(hexpart)
    except ValueError as e:
        raise ValueError(f"token no es hexadecimal válido: {token!r}") from e
    if len(crudo) != BYTES_TOKEN:
        raise ValueError(
            f"token debe tener {BYTES_TOKEN} bytes ({BYTES_TOKEN*2} hex), "
            f"tiene {len(crudo)}")
    return crudo


def construir_mensaje(token, contador, version=VERSION_TRAMA):
    """
    Arma los bytes que se firman: versión ‖ token ‖ contador.

    El contador va en 4 bytes big-endian (hasta 4.294.967.295 usos, de sobra
    para la vida útil de una credencial).

    Incluir la versión y el contador dentro de lo firmado es lo que impide
    que alguien capture una trama y la reenvíe cambiando el contador: la
    firma dejaría de coincidir.
    """
    if contador < 0 or contador > 0xFFFFFFFF:
        raise ValueError(f"contador fuera de rango: {contador}")
    return (bytes([version])
            + _token_a_bytes(token)
            + contador.to_bytes(4, "big"))


def calcular_hmac(clave_secreta, token, contador, version=VERSION_TRAMA):
    """
    Calcula el HMAC truncado de una trama. Devuelve hex (16 caracteres).

    clave_secreta: los 64 caracteres hex que se generaron al activar.
    """
    if not clave_secreta:
        raise ValueError("clave_secreta vacía")
    try:
        clave = bytes.fromhex(clave_secreta)
    except ValueError as e:
        raise ValueError("clave_secreta no es hexadecimal válida") from e

    mensaje = construir_mensaje(token, contador, version)
    completo = hmac.new(clave, mensaje, hashlib.sha256).digest()
    return completo[:BYTES_HMAC].hex()


def verificar_hmac(clave_secreta, token, contador, hmac_recibido,
                   version=VERSION_TRAMA):
    """
    Verifica una trama. Devuelve True o False, nunca lanza por datos malos
    del cliente — una trama corrupta es simplemente inválida.

    Usa hmac.compare_digest para comparar en tiempo constante: comparar con
    '==' filtra información por el tiempo que tarda en fallar, y con
    suficientes intentos eso permite reconstruir la firma byte por byte.
    """
    if not hmac_recibido:
        return False
    try:
        esperado = calcular_hmac(clave_secreta, token, contador, version)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(esperado, hmac_recibido.lower().strip())


def precomputar_hmacs(clave_secreta, token, contador_desde, cantidad=50,
                      version=VERSION_TRAMA):
    """
    Genera los HMAC de los próximos N contadores.

    Para el caché offline (docs/BLE_PROTOCOLO.md §3.2): la Pi debe poder
    validar sin internet, pero darle la clave reintroduciría el problema
    que este módulo resuelve. En cambio recibe una lista de respuestas
    válidas precomputadas — compara, no calcula.

    Compromiso aceptado: una Pi comprometida en modo offline puede
    reproducir estos N accesos hasta que expire el caché. Mucho mejor que
    entregar la clave, que serviría para siempre y para cualquier contador.

    Todavía no se usa: queda listo para cuando se implemente el caché.
    """
    return [calcular_hmac(clave_secreta, token, c, version)
            for c in range(contador_desde, contador_desde + cantidad)]
