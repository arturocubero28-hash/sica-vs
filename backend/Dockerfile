FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema mínimas (incluye ffmpeg + libs para OpenCV/RTSP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    ffmpeg libsm6 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# En desarrollo, docker-compose sobreescribe el command con flask run --debug
#
# Día 66 — workers y timeout explícitos. Antes corría con la configuración
# por defecto de gunicorn: UN SOLO worker sincrónico, lo que significa que
# el backend atendía una petición a la vez. Con varios residentes usando la
# app al mismo tiempo, todos hacían cola detrás de la petición en curso --
# esa era la causa de la lentitud percibida, no falta de recursos (el
# servidor estaba al 0% de CPU y con 2.9GB de RAM libres).
#
# 4 workers: regla habitual (2 x núcleos + 1) ajustada al tamaño del
# droplet. Cada worker usa ~120MB, así que 4 son ~500MB de los 3.8GB.
# timeout 120: algunas operaciones (generar PDF de recibo, subir
# comprobante grande) pueden pasar los 30s del default.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "wsgi:app"]
