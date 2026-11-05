#!/usr/bin/env bash
#
# Actualizar SICA-VS en el servidor de producción.
#
# POR QUÉ EXISTE ESTE SCRIPT (Día 73)
#
# Desplegar a mano son cuatro pasos y en una sola noche se nos escaparon
# tres, cada uno con un síntoma distinto y ninguno con un mensaje de error:
#
#   1. Compilar el panel pero no copiarlo. Vite escribe en frontend/dist,
#      pero Nginx sirve /var/www/sicavs. Sin el cp, el panel sigue viejo.
#
#   2. Usar "restart backend". En desarrollo el código está montado
#      (./backend:/app, con hot-reload) y restart alcanza. En producción
#      NO está montado: va adentro de la imagen. restart reinicia el
#      proceso con el código viejo.
#
#   3. Usar "up -d" sin --build. Recrea el contenedor -- toma variables de
#      entorno nuevas, sí -- pero reusa la imagen, o sea el código viejo.
#      Este es el peor de los tres: parece que funcionó, dice "Started", y
#      el código nuevo no está.
#
# Los tres terminan igual: el sistema anda, no hay ningún error en los
# logs, y el cambio simplemente no aparece. Se pierde más tiempo buscando
# un bug inexistente que desplegando.
#
# USO:
#     cd /opt/sicavs && bash deploy/actualizar.sh
#
# No toca la configuración de Nginx: si cambió, avisa y te deja el comando,
# porque pisar ese archivo a ciegas puede romper los certificados.

set -euo pipefail

RAIZ="/opt/sicavs"
WEB="/var/www/sicavs"
COMPOSE="docker compose -f docker-compose.prod.yml"

cd "$RAIZ"

RAMA="$(git rev-parse --abbrev-ref HEAD)"
ANTES="$(git rev-parse HEAD)"

echo "──────────────────────────────────────────────────────────"
echo " Actualizando SICA-VS — rama $RAMA"
echo "──────────────────────────────────────────────────────────"

echo
echo "▶ Trayendo cambios…"
git pull origin "$RAMA"
DESPUES="$(git rev-parse HEAD)"

if [ "$ANTES" = "$DESPUES" ]; then
  echo
  echo "No había nada nuevo. Nada que desplegar."
  exit 0
fi

# Qué cambió, para no reconstruir lo que no hace falta: el build del
# frontend son ~20 segundos y el del backend puede ser un minuto largo.
CAMBIOS="$(git diff --name-only "$ANTES" "$DESPUES")"
toco() { echo "$CAMBIOS" | grep -q "^$1"; }

echo
echo "▶ Cambiaron $(echo "$CAMBIOS" | wc -l) archivo(s):"
echo "$CAMBIOS" | sed 's/^/    /'

# ── Backend ──────────────────────────────────────────────────────────────
if toco "backend/"; then
  echo
  echo "▶ Backend: reconstruyendo la imagen (el código va adentro, no montado)…"
  $COMPOSE up -d --build backend worker
else
  echo
  echo "▶ Backend: sin cambios, no se toca."
fi

# ── Frontend ─────────────────────────────────────────────────────────────
if toco "frontend/"; then
  echo
  echo "▶ Panel web: compilando…"
  ( cd frontend && npm run build )
  echo "▶ Panel web: copiando a $WEB …"
  cp -r frontend/dist/* "$WEB"/
else
  echo
  echo "▶ Panel web: sin cambios, no se toca."
fi

# ── Nginx: avisar, no tocar ──────────────────────────────────────────────
if toco "deploy/nginx-"; then
  echo
  echo "⚠  CAMBIÓ LA CONFIGURACIÓN DE NGINX y este script NO la aplica."
  echo "   Pisar ese archivo a ciegas puede dejarte sin certificados, así"
  echo "   que revisá la diferencia primero y aplicala a mano:"
  echo
  echo "     diff /etc/nginx/sites-available/sicavs deploy/nginx-sicavs.conf"
  echo "     cp deploy/nginx-sicavs.conf /etc/nginx/sites-available/sicavs"
  echo "     nginx -t && systemctl reload nginx"
fi

# ── Comprobación final ───────────────────────────────────────────────────
echo
echo "▶ Estado de los contenedores:"
$COMPOSE ps --format "    {{.Name}}\t{{.Status}}"

echo
echo "▶ Respuesta del backend:"
if curl -fsS -o /dev/null -w "    /api/v1/health → %{http_code}\n" \
     http://127.0.0.1:5000/api/v1/health 2>/dev/null; then
  :
else
  echo "    No respondió. Mirá los logs:"
  echo "    $COMPOSE logs backend --tail 40"
fi

echo
echo "──────────────────────────────────────────────────────────"
echo " Listo. $ANTES → $DESPUES"
echo "──────────────────────────────────────────────────────────"
