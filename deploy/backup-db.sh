#!/bin/bash
# =====================================================================
# SICA-VS — Backup automático de la base de datos (Día 60)
#
# Qué hace:
#   1. Genera un dump comprimido de Postgres (pg_dump -Fc) desde el
#      propio contenedor de la base, sin necesidad de exponer el puerto.
#   2. Lo sube a DigitalOcean Spaces (NO se guarda solo en el disco del
#      VPS -- mismo criterio que los archivos de la app: si el disco del
#      servidor falla, un backup guardado ahí mismo no protege de nada).
#   3. Borra los backups viejos de Spaces, quedándose solo con los
#      últimos RETENCION_DIAS.
#
# Requiere: AWS CLI instalado (apt install awscli), y las variables de
# entorno de Spaces ya presentes en /opt/sicavs/.env (las mismas que usa
# el backend -- no hace falta configurar credenciales aparte).
#
# Uso manual:      /opt/sicavs/deploy/backup-db.sh
# Uso automático:   ver deploy/GUIA_DEPLOY.md, sección de backups (cron)
# =====================================================================
set -euo pipefail

DIR_PROYECTO="/opt/sicavs"
ARCHIVO_ENV="$DIR_PROYECTO/.env"
COMPOSE="docker compose -f $DIR_PROYECTO/docker-compose.prod.yml"
CARPETA_BACKUPS_SPACES="backups-db"   # subcarpeta dentro del bucket
RETENCION_DIAS=14                     # cuántos backups conservar
TMPDIR="/tmp/sicavs-backups"
LOG="/var/log/sicavs-backup.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

if [ ! -f "$ARCHIVO_ENV" ]; then
  log "ERROR: no se encontró $ARCHIVO_ENV — no se puede leer POSTGRES_*/SPACES_*."
  exit 1
fi

# Carga SOLO las variables puntuales que este script necesita, leyéndolas
# como texto plano -- NO se hace "source" de todo el archivo.
#
# Por qué: un `source` normal ejecuta el .env como si fuera código bash
# real, línea por línea. Si CUALQUIER otra variable del archivo (una que
# ni siquiera usa este script) tiene un valor sin comillas con espacios
# -- por ejemplo RATE_LIMIT_DEFAULT=600 per hour, tal como viene en la
# plantilla -- bash interpreta "per" como un COMANDO aparte a ejecutar,
# no como parte del valor, y el script entero falla con un error que no
# tiene nada que ver con backups. Leyendo target solo las variables que
# hacen falta, ninguna variable ajena puede romper esto.
leer_var() {
  grep -E "^$1=" "$ARCHIVO_ENV" | tail -1 | cut -d '=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}
POSTGRES_USER=$(leer_var POSTGRES_USER)
POSTGRES_DB=$(leer_var POSTGRES_DB)
POSTGRES_PASSWORD=$(leer_var POSTGRES_PASSWORD)
SPACES_KEY=$(leer_var SPACES_KEY)
SPACES_SECRET=$(leer_var SPACES_SECRET)
SPACES_BUCKET=$(leer_var SPACES_BUCKET)
SPACES_REGION=$(leer_var SPACES_REGION)

FECHA=$(date +%Y%m%d-%H%M%S)
ARCHIVO="sicavs-${FECHA}.dump"
mkdir -p "$TMPDIR"

log "Iniciando backup: $ARCHIVO"

# 1. Dump comprimido desde el contenedor de la base (-Fc: formato
#    "custom" de Postgres — comprimido y restaurable de forma selectiva
#    con pg_restore, a diferencia de un .sql plano).
#
#    PGPASSWORD explícito: por defecto Postgres NO confía en conexiones
#    locales dentro del contenedor (pide contraseña igual) -- sin esto,
#    pg_dump se queda esperando un input que nunca llega, y en un cron
#    (sin nadie mirando la terminal) el script simplemente se cuelga
#    para siempre en vez de fallar con un error claro.
if ! $COMPOSE exec -T -e PGPASSWORD="${POSTGRES_PASSWORD}" db \
    pg_dump -U "${POSTGRES_USER:-sicavs}" -Fc "${POSTGRES_DB:-sicavs}" > "$TMPDIR/$ARCHIVO"; then
  log "ERROR: pg_dump falló. Backup NO generado."
  rm -f "$TMPDIR/$ARCHIVO"
  exit 1
fi

TAMANO=$(du -h "$TMPDIR/$ARCHIVO" | cut -f1)
log "Dump generado localmente: $TAMANO"

# 2. Subir a Spaces (mismo bucket que ya usan los archivos de la app,
#    en su propia subcarpeta para no mezclarse).
export AWS_ACCESS_KEY_ID="$SPACES_KEY"
export AWS_SECRET_ACCESS_KEY="$SPACES_SECRET"
ENDPOINT="https://${SPACES_REGION:-nyc3}.digitaloceanspaces.com"

if ! aws s3 cp "$TMPDIR/$ARCHIVO" "s3://${SPACES_BUCKET}/${CARPETA_BACKUPS_SPACES}/$ARCHIVO" \
    --endpoint-url "$ENDPOINT" --only-show-errors; then
  log "ERROR: no se pudo subir el backup a Spaces. Queda solo la copia local en $TMPDIR/$ARCHIVO (temporal)."
  exit 1
fi

log "Subido a Spaces: ${CARPETA_BACKUPS_SPACES}/$ARCHIVO ($TAMANO)"

# 3. Limpiar la copia local temporal — la única copia que importa vive
#    en Spaces, no tiene sentido ocupar disco del VPS con esto.
rm -f "$TMPDIR/$ARCHIVO"

# 4. Retención: conservar solo los backups de los últimos RETENCION_DIAS
#    días, borrando el resto de Spaces. Los nombres de archivo ya tienen
#    la fecha (sicavs-YYYYMMDD-HHMMSS.dump), así que se puede filtrar por
#    nombre sin necesidad de leer metadata de cada objeto.
FECHA_LIMITE=$(date -d "-${RETENCION_DIAS} days" +%Y%m%d)
BORRADOS=0
for obj in $(aws s3 ls "s3://${SPACES_BUCKET}/${CARPETA_BACKUPS_SPACES}/" --endpoint-url "$ENDPOINT" | awk '{print $4}'); do
  # obj tiene forma sicavs-YYYYMMDD-HHMMSS.dump — se extrae la fecha.
  FECHA_OBJ=$(echo "$obj" | grep -oP '(?<=sicavs-)\d{8}' || echo "99999999")
  if [ "$FECHA_OBJ" -lt "$FECHA_LIMITE" ]; then
    aws s3 rm "s3://${SPACES_BUCKET}/${CARPETA_BACKUPS_SPACES}/$obj" --endpoint-url "$ENDPOINT" --only-show-errors
    BORRADOS=$((BORRADOS + 1))
  fi
done
[ "$BORRADOS" -gt 0 ] && log "Retención: $BORRADOS backup(s) viejo(s) eliminado(s) (más de $RETENCION_DIAS días)."

log "Backup completo. OK."
