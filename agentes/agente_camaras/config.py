"""
Configuración del Agente de Cámaras — editar estos valores por cada Pi.

SERVIDOR_URL: la URL pública del backend SICA-VS (nube). Es la misma URL
              que usa la app móvil y el panel web.
DEVICE_TOKEN: el token de ESTE dispositivo específico. Se genera y se
              copia una sola vez desde el Panel del Desarrollador ->
              Raspberry Pi -> Crear dispositivo (tipo: cámara).
PUERTO_LOCAL: puerto donde el agente escucha en la Pi. El túnel (Cloudflare/
              ngrok) debe apuntar a este mismo puerto.
"""

SERVIDOR_URL = "https://TU-DOMINIO-O-TUNEL.example.com"
DEVICE_TOKEN = "PEGAR-AQUI-EL-TOKEN-DEL-DISPOSITIVO"

PUERTO_LOCAL = 8090
HEARTBEAT_SEGUNDOS = 30
