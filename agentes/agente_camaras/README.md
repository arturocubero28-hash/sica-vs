# Agente de Cámaras — SICA-VS

Programa que corre en la Raspberry Pi dedicada a cámaras, en la LAN de la
residencial. Se conecta al NVR por RTSP/ONVIF y expone el video hacia el
servidor central (nube) a través de un túnel saliente.

## Por qué existe

El backend central vive en la nube. El NVR de cámaras vive en la red local
de la residencial (ONVIF/RTSP no está pensado para atravesar internet
directamente). Este agente hace de puente: habla con el NVR en la LAN, y
entrega el video ya convertido a la nube.

Es un programa **separado** del agente de accesos (Raspberry Pi de trancas),
aunque comparten el mismo modelo de dispositivo/token en el backend — cada
uno es su propia Pi, su propio programa, para que un fallo en cámaras no
afecte accesos y viceversa.

## Instalación (Raspberry Pi)

```bash
# 1. Sistema operativo: Raspberry Pi OS Lite (64-bit) recomendado
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-opencv git

# 2. Copiar esta carpeta a la Pi (ej. vía git clone o scp)
mkdir -p /home/pi/agente_camaras
cp agente_camaras.py config.py requirements.txt /home/pi/agente_camaras/
cd /home/pi/agente_camaras

# 3. Instalar dependencias de Python
pip3 install -r requirements.txt --break-system-packages

# 4. Configurar (ver sección siguiente)
nano config.py

# 5. Probar manualmente primero
python3 agente_camaras.py
# Deberías ver: "Agente de cámaras SICA-VS iniciando..."
# Verificar en el navegador de la misma Pi: http://localhost:8090/salud

# 6. Una vez que funciona, instalarlo como servicio (arranca solo)
sudo cp agente_camaras.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agente_camaras
sudo systemctl start agente_camaras
sudo systemctl status agente_camaras
```

## Configuración (`config.py`)

Antes de arrancar, hay que crear el dispositivo en el sistema:

1. Entrar al Panel del Desarrollador (rol `desarrollador`) → pestaña
   **Raspberry Pi** → **Crear dispositivo**
2. Nombre: algo descriptivo, ej. "Pi Cámaras Villas del Sol"
3. Tipo: **cámara**
4. Al crear, se muestra el **token** — copiarlo (solo se muestra una vez)
5. Pegar ese token en `config.py` → `DEVICE_TOKEN`
6. En `SERVIDOR_URL`, poner la URL pública del backend (el mismo dominio
   que usa la app móvil / panel web)

Luego, hay que **asignar las cámaras** a este dispositivo desde el panel de
Cámaras (cada cámara tiene un campo `dispositivo_id` que indica qué agente
la expone). El agente descarga automáticamente qué cámaras le tocan al
arrancar y las refresca cada pocos minutos.

## Conexión hacia la nube (el túnel)

El agente escucha en el puerto `8090` de la Pi, pero **nunca abre ese
puerto a internet directamente**. Se necesita un túnel saliente que exponga
ese puerto con una URL fija, para que el backend en la nube pueda pedirle
el video.

Opciones (elegir una, se instala en la misma Pi):

- **Cloudflare Tunnel** (recomendado, gratis, sin abrir puertos del router):
  ```bash
  cloudflared tunnel --url http://localhost:8090
  ```
- **ngrok** (más simple para pruebas, gratis con limitaciones):
  ```bash
  ngrok http 8090
  ```

La URL que entrega el túnel es la que el backend usa para pedirle el video
a esta Pi específica (se configura como parte de los datos del dispositivo
o de cada cámara, según cómo se quiera enrutar — ver la sección "Próximos
pasos" más abajo).

## Endpoints que usa (del backend central)

| Endpoint | Método | Qué hace |
|---|---|---|
| `/api/v1/acceso/camaras/config` | GET | Descarga las cámaras asignadas a este dispositivo (con credenciales RTSP) |
| `/api/v1/acceso/camaras/heartbeat` | POST | Avisa que el agente sigue conectado |

Ambos se autentican con el header `X-Device-Token` (el mismo token del
dispositivo, igual que el agente de accesos).

## Endpoints que expone (para el backend/Centro de Monitoreo)

| Endpoint | Qué hace |
|---|---|
| `GET /salud` | Health check simple, para pruebas locales |
| `GET /stream/<uuid_camara>` | Proxy MJPEG de esa cámara específica |

## Próximos pasos (pendiente de definir con el hardware real)

- Cómo el backend central descubre la URL del túnel de cada agente (hoy es
  manual; a futuro el agente podría reportar su URL de túnel en el
  heartbeat, si se usa un túnel que la genere dinámicamente)
- Alertas si un agente lleva mucho tiempo sin heartbeat (dashboard del
  desarrollador ya tiene el campo `ultimo_heartbeat` para esto)
