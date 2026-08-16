# SICA-VS — Guía de despliegue a producción (VPS Hostinger)

Día 58. Servidor: VPS de Hostinger, Ubuntu. Dominio: `patronatovillasdelsol.com`.
Almacenamiento: DigitalOcean Spaces (no el disco del VPS).

Todo esto se corre por SSH, conectado al VPS:

```
ssh root@2.25.106.253
```

**Antes de nada**: esa contraseña que compartieron por chat, cambiala apenas
termines el deploy (`passwd`), o mejor, pasá a login por llave SSH y
deshabilitá el login por contraseña. No es parte de esta guía, pero
quedó anotado como pendiente de seguridad.

---

## 1. Preparar el servidor

```bash
apt update && apt upgrade -y

# Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# Nginx y Certbot (para el SSL)
apt install -y nginx certbot python3-certbot-nginx

# Confirmar versiones
docker --version
docker compose version
nginx -v
```

## 2. Clonar el repo

```bash
cd /opt
git clone -b feature/qr-imagen "https://arturocubero28-hash:TU_TOKEN@github.com/arturocubero28-hash/sica-vs.git" sicavs
cd /opt/sicavs
```

(Reemplazar `TU_TOKEN` por el token de GitHub real.)

## 3. Crear el bucket de DigitalOcean Spaces

Si todavía no existe:

1. Entrar a https://cloud.digitalocean.com/spaces → **Create Spaces Bucket**.
2. Región: `nyc3` (o la que prefieras — anotarla, va en `SPACES_REGION`).
3. Nombre del bucket: por ejemplo `sica-vs-archivos`.
4. Una vez creado, copiar la URL del endpoint del CDN que muestra el panel
   (algo como `https://sica-vs-archivos.nyc3.cdn.digitaloceanspaces.com`).
5. Generar las llaves de acceso: **API → Spaces Keys → Generate New Key**
   (⚠️ son distintas de las llaves de API de Droplets). Copiar el Key y el
   Secret — el Secret solo se muestra una vez.

## 4. Configurar las variables de entorno

```bash
cp .env.prod.example .env
nano .env
```

Completar, como mínimo:
- `POSTGRES_PASSWORD` — generar con `openssl rand -base64 24`
- `JWT_SECRET` — generar con `openssl rand -hex 32`
- `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_REGION`, `SPACES_CDN_URL`
  — los del paso 3
- `RESEND_API_KEY` — si ya se tiene; si no, dejar vacío por ahora (el envío
  de correos de activación queda deshabilitado hasta completarlo)

`CORS_ORIGINS`, `WEBAUTHN_RP_ID` y `WEBAUTHN_ORIGIN` ya vienen con el
dominio correcto en la plantilla — solo confirmar que digan
`patronatovillasdelsol.com`.

## 5. Primer arranque del backend (sin Nginx todavía)

```bash
cd /opt/sicavs
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Las 4 piezas (`sicavs_db`, `sicavs_redis`, `sicavs_backend`, `sicavs_worker`)
deben quedar `Up` / `healthy`. Verificar que el backend responde local:

```bash
curl http://127.0.0.1:5000/api/v1/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"no@existe.com","password":"x"}'
```

Una respuesta JSON (aunque sea de error de credenciales) confirma que el
backend está vivo. Si sale un error de conexión, revisar logs:

```bash
docker compose -f docker-compose.prod.yml logs backend --tail 50
```

## 6. Compilar y publicar el frontend

Esto se hace **fuera** de Docker — el build es estático, Nginx lo sirve
directo desde el disco.

```bash
cd /opt/sicavs/frontend

# Node, si no está instalado
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

npm install
VITE_API_URL=https://patronatovillasdelsol.com/api/v1 npm run build

mkdir -p /var/www/sicavs
cp -r dist/* /var/www/sicavs/
```

## 7. Nginx — arranque provisional (HTTP, sin SSL todavía)

```bash
mkdir -p /var/www/certbot
cp /opt/sicavs/deploy/nginx-provisional-http.conf /etc/nginx/sites-available/sicavs
ln -s /etc/nginx/sites-available/sicavs /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default   # el sitio de bienvenida por defecto
nginx -t
systemctl reload nginx
```

Probar en el navegador: `http://patronatovillasdelsol.com` — debería
cargar el sitio (sin candado todavía, es esperado en este paso).

## 8. Obtener el certificado SSL

```bash
certbot certonly --webroot -w /var/www/certbot \
  -d patronatovillasdelsol.com -d www.patronatovillasdelsol.com \
  --email TU_CORREO@ejemplo.com --agree-tos --no-eff-email
```

Si sale bien, los certificados quedan en
`/etc/letsencrypt/live/patronatovillasdelsol.com/`.

## 9. Nginx — pasar a la config definitiva (con HTTPS + CSP)

```bash
cp /opt/sicavs/deploy/nginx-sicavs.conf /etc/nginx/sites-available/sicavs
nginx -t
systemctl reload nginx
```

Probar: `https://patronatovillasdelsol.com` — ahora sí con candado.

## 10. Renovación automática del certificado

Certbot ya instala un temporizador systemd que renueva solo. Confirmar:

```bash
systemctl status certbot.timer
certbot renew --dry-run
```

## 11. Verificación final

- [ ] `https://patronatovillasdelsol.com` carga el sitio con candado
- [ ] Login funciona (probar con un usuario real)
- [ ] Subir un archivo (foto de acceso, comprobante) y confirmar que
      aparece en el bucket de Spaces, no en el disco del VPS:
      `docker compose -f docker-compose.prod.yml exec backend python -c "import os; print(os.environ.get('STORAGE_BACKEND'))"`
      debe imprimir `spaces`
- [ ] `docker compose -f docker-compose.prod.yml logs worker --tail 20`
      sin errores — confirma que Celery (cron de cuotas, notificaciones)
      está corriendo
- [ ] Cambiar la contraseña de root del VPS (o pasar a llave SSH)

## Actualizar código después del primer deploy

Cuando haya cambios nuevos en el repo:

```bash
cd /opt/sicavs
git pull origin feature/qr-imagen
docker compose -f docker-compose.prod.yml up -d --build backend worker
```

Si el cambio fue en el frontend:

```bash
cd /opt/sicavs/frontend
VITE_API_URL=https://patronatovillasdelsol.com/api/v1 npm run build
cp -r dist/* /var/www/sicavs/
```

## Backups automáticos de la base de datos (Día 60)

Genera un dump comprimido de Postgres todos los días y lo sube a DigitalOcean Spaces (no al disco del VPS — si el servidor falla, un backup guardado ahí mismo no protege de nada). Conserva los últimos 14 días, borrando los más viejos automáticamente.

### 1. Instalar AWS CLI (una sola vez)

El script sube los backups a Spaces usando esta herramienta (Spaces es compatible con S3, así que funciona igual que con Amazon).

```bash
apt install -y awscli
```

### 2. Probar el backup a mano, antes de automatizarlo

```bash
cd /opt/sicavs
./deploy/backup-db.sh
```

Si todo sale bien, el final del log dice `Backup completo. OK.`. Confirmá que el archivo apareció en Spaces:

```bash
# No usar "source .env" a mano -- si alguna otra variable del archivo
# tiene un valor sin comillas con espacios (ej. RATE_LIMIT_DEFAULT=600
# per hour), bash lo interpreta como un comando aparte y falla. Se leen
# solo las 3 variables puntuales que hacen falta acá.
SPACES_KEY=$(grep -E '^SPACES_KEY=' .env | cut -d '=' -f2-)
SPACES_SECRET=$(grep -E '^SPACES_SECRET=' .env | cut -d '=' -f2-)
SPACES_BUCKET=$(grep -E '^SPACES_BUCKET=' .env | cut -d '=' -f2-)
SPACES_REGION=$(grep -E '^SPACES_REGION=' .env | cut -d '=' -f2-)
export AWS_ACCESS_KEY_ID=$SPACES_KEY AWS_SECRET_ACCESS_KEY=$SPACES_SECRET
aws s3 ls s3://$SPACES_BUCKET/backups-db/ --endpoint-url https://$SPACES_REGION.digitaloceanspaces.com
```

### 3. Probar la restauración — sin arriesgar producción

Un backup que nunca se probó restaurar no es un backup de fiar. **No lo pruebes directo contra la base real** — primero contra una base descartable, para confirmar que el mecanismo funciona sin ningún riesgo:

```bash
# Mismas variables puntuales que antes, más las de Postgres
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d '=' -f2-)
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d '=' -f2-)

# Crear una base de prueba, separada de la real
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db \
  psql -U $POSTGRES_USER -c "CREATE DATABASE sicavs_test_restore;"

# Restaurar el backup MÁS RECIENTE ahí (reemplazá el nombre del archivo
# por el que viste en el paso 2)
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db \
  pg_restore -U $POSTGRES_USER -d sicavs_test_restore --no-owner < /tmp/sicavs-backups/ELNOMBREQUEVISTE.dump

# Confirmar que trajo datos reales (por ejemplo, contar usuarios)
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db \
  psql -U $POSTGRES_USER -d sicavs_test_restore -c "SELECT count(*) FROM usuarios;"

# Borrar la base de prueba una vez confirmado
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db \
  psql -U $POSTGRES_USER -c "DROP DATABASE sicavs_test_restore;"
```

Si el conteo de usuarios coincide con lo real, confirmado: el backup sirve. Guardá `deploy/restore-db.sh` como referencia para el día que haga falta restaurar de verdad (ese sí pide confirmación explícita antes de tocar la base real).

### 4. Automatizar con cron — que corra solo, todos los días

```bash
crontab -e
```

Agregar esta línea al final (corre todos los días a las 3:00 AM, hora de menor uso):

```
0 3 * * * /opt/sicavs/deploy/backup-db.sh >> /var/log/sicavs-backup.log 2>&1
```

Guardar y salir. Confirmar que quedó registrado:

```bash
crontab -l
```

### 5. Verificar de vez en cuando que los backups siguen corriendo

```bash
tail -20 /var/log/sicavs-backup.log
```

Si en algún momento deja de aparecer un backup nuevo cada día, algo se rompió (credenciales vencidas, disco lleno, etc.) — vale la pena chequear este log cada tanto, no asumir que "como lo configuré una vez, sigue andando solo para siempre".

