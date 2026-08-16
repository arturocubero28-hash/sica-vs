#!/bin/bash
# =====================================================================
# SICA-VS — Restaurar la base de datos desde un backup (Día 60)
#
# ADVERTENCIA: esto SOBREESCRIBE la base de datos actual por completo.
# No correr contra producción sin estar seguro -- ver la sección
# "Probar la restauración sin arriesgar producción" en
# deploy/GUIA_DEPLOY.md antes de usar esto en el servidor real.
#
# Uso:
#   ./deploy/restore-db.sh sicavs-20260816-030000.dump
#
# Para ver qué backups existen en Spaces:
#   source .env && export AWS_ACCESS_KEY_ID=$SPACES_KEY AWS_SECRET_ACCESS_KEY=$SPACES_SECRET
#   aws s3 ls s3://$SPACES_BUCKET/backups-db/ --endpoint-url https://$SPACES_REGION.digitaloceanspaces.com
# =====================================================================
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Uso: $0 <nombre-del-archivo.dump>"
  echo "Ejemplo: $0 sicavs-20260816-030000.dump"
  exit 1
fi

ARCHIVO="$1"
DIR_PROYECTO="/opt/sicavs"
ARCHIVO_ENV="$DIR_PROYECTO/.env"
COMPOSE="docker compose -f $DIR_PROYECTO/docker-compose.prod.yml"
CARPETA_BACKUPS_SPACES="backups-db"
TMPDIR="/tmp/sicavs-backups"

# Mismo criterio que backup-db.sh: se leen SOLO las variables puntuales
# que hacen falta, en vez de un "source" de todo el .env -- un source
# ejecuta el archivo como código bash real, y cualquier valor sin
# comillas con espacios en OTRA variable (ej. RATE_LIMIT_DEFAULT=600 per
# hour) rompe todo el script con un error que no tiene nada que ver.
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

mkdir -p "$TMPDIR"
export AWS_ACCESS_KEY_ID="$SPACES_KEY"
export AWS_SECRET_ACCESS_KEY="$SPACES_SECRET"
ENDPOINT="https://${SPACES_REGION:-nyc3}.digitaloceanspaces.com"

echo "Descargando $ARCHIVO desde Spaces..."
aws s3 cp "s3://${SPACES_BUCKET}/${CARPETA_BACKUPS_SPACES}/$ARCHIVO" "$TMPDIR/$ARCHIVO" \
  --endpoint-url "$ENDPOINT" --only-show-errors

echo ""
echo "⚠️  Vas a restaurar '$ARCHIVO' sobre la base '${POSTGRES_DB:-sicavs}'."
echo "⚠️  Esto BORRA los datos actuales de esa base y los reemplaza por los del backup."
read -r -p "Escribí 'restaurar' para confirmar: " CONFIRMACION
if [ "$CONFIRMACION" != "restaurar" ]; then
  echo "Cancelado. No se tocó nada."
  rm -f "$TMPDIR/$ARCHIVO"
  exit 0
fi

echo "Restaurando..."
# --clean: borra los objetos existentes antes de recrearlos (para que la
# restauración no choque con lo que ya hay). -1: todo en una transacción,
# si algo falla no deja la base a medio restaurar.
$COMPOSE exec -T -e PGPASSWORD="${POSTGRES_PASSWORD}" db \
  pg_restore -U "${POSTGRES_USER:-sicavs}" -d "${POSTGRES_DB:-sicavs}" --clean --if-exists -1 \
  < "$TMPDIR/$ARCHIVO"

rm -f "$TMPDIR/$ARCHIVO"
echo "Restauración completa."
