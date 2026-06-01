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
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
