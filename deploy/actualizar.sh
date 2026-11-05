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
#
#     bash deploy/actualizar.sh            lo normal
#     bash deploy/actualizar.sh --forzar   reconstruir todo igual
#
# COMPARA CONTRA LO ÚLTIMO DESPLEGADO, NO CONTRA LO ÚLTIMO BAJADO.
#
# La primera versión comparaba el HEAD de antes del pull contra el de
# después, y se rompía sola en el caso más común: hacer "git pull" a mano
# y después correr el script. Ahí no había nada que traer, el script decía
# "nada que desplegar" y se saltaba el build -- con el código nuevo ya en
# el disco y sin desplegar, que es exactamente el engaño que este script
# venía a evitar.
#
# Por eso se guarda el commit desplegado en .ultimo-despliegue y la
# comparación se hace contra ese. Correr el script dos veces seguidas no
# hace nada la segunda, que es lo que uno espera.

set -euo pipefail

# Las rutas se pueden sobreescribir por entorno para poder probar el
# script fuera del servidor, sin tocar nada real.
RAIZ="${SICAVS_RAIZ:-/opt/sicavs}"
WEB="${SICAVS_WEB:-/var/www/sicavs}"
SELLO="$RAIZ/.ultimo-despliegue"
COMPOSE="${SICAVS_COMPOSE:-docker compose -f docker-compose.prod.yml}"

FORZAR="no"
[ "${1:-}" = "--forzar" ] && FORZAR="si"

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

# Punto de partida: lo último que este script desplegó. Si no hay sello
# todavía (primera vez), no se puede saber qué falta, así que se
# reconstruye todo -- más lento, pero nunca deja algo sin desplegar.
REFERENCIA=""
if [ -f "$SELLO" ]; then
  REFERENCIA="$(cat "$SELLO")"
  git cat-file -e "$REFERENCIA^{commit}" 2>/dev/null || REFERENCIA=""
fi

if [ "$FORZAR" = "si" ]; then
  echo
  echo "▶ --forzar: se reconstruye todo sin mirar qué cambió."
  CAMBIOS=$'backend/\nfrontend/'
elif [ -z "$REFERENCIA" ]; then
  echo
  echo "▶ Primera corrida (no hay registro de despliegue previo):"
  echo "  se reconstruye todo para no dejar nada sin desplegar."
  CAMBIOS=$'backend/\nfrontend/'
elif [ "$REFERENCIA" = "$DESPUES" ]; then
  echo
  echo "Ya está desplegado $DESPUES. Nada que hacer."
  exit 0
else
  # Qué cambió, para no reconstruir lo que no hace falta: el build del
  # frontend son ~20 segundos y el del backend puede ser un minuto largo.
  CAMBIOS="$(git diff --name-only "$REFERENCIA" "$DESPUES")"
fi
toco() { echo "$CAMBIOS" | grep -q "^$1"; }

echo
echo "▶ A desplegar:"
echo "$CAMBIOS" | sed 's/^/    /'

# ── Backend ──────────────────────────────────────────────────────────────
REINICIO_WORKER=""
if toco "backend/"; then
  echo
  echo "▶ Backend: reconstruyendo la imagen (el código va adentro, no montado)…"
  REINICIO_WORKER="$(date +%s)"
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

# ── Día 73 — ¿el worker NUEVO quedó vivo? ────────────────────────────────
# El 5 de noviembre un despliegue dejó el worker en un bucle de reinicios y
# este script dijo "Listo": el backend respondía y el health daba 200. El
# worker es el que genera las cuotas y manda las notificaciones, así que
# ahora se verifica que esté latiendo (ver app/tasks/latido.py).
#
# Ojo con la trampa: el último latido del worker VIEJO queda fresco en
# Redis unos minutos, y un worker nuevo roto pasaría por vivo. Por eso se
# exige un latido POSTERIOR al reinicio: hace_segundos tiene que ser menor
# que el tiempo que pasó desde que se reinició.
if [ -n "$REINICIO_WORKER" ]; then
  echo
  echo "▶ Worker: esperando que el nuevo dé señales de vida…"
  VIVO=""
  for _ in $(seq 1 20); do
    sleep 3
    R="$(curl -s -m 5 "${SICAVS_WORKER_URL:-http://127.0.0.1:5000/api/v1/health/worker}" 2>/dev/null || true)"
    # Tolerante a espacios: "hace_segundos":1 o "hace_segundos": 1.
    HACE="$(echo "$R" | grep -oE '"hace_segundos"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+$')"
    TRANSCURRIDO=$(( $(date +%s) - REINICIO_WORKER ))
    if [ -n "$HACE" ] && [ "$HACE" -lt "$TRANSCURRIDO" ]; then VIVO="si"; break; fi
  done
  if [ "$VIVO" = "si" ]; then
    echo "    vivo — latió hace ${HACE}s"
  else
    echo
    echo "⚠  EL WORKER NO DIO SEÑALES DE VIDA EN 60 SEGUNDOS."
    echo "   Sin worker no se generan cuotas ni salen notificaciones ni correos."
    echo "   Mirá qué le pasa:"
    echo
    echo "     $COMPOSE ps worker"
    echo "     $COMPOSE logs worker --tail 40"
    echo
    echo "   (No se marca como desplegado: la próxima corrida lo vuelve a intentar.)"
    exit 1
  fi
fi

# El sello se escribe AL FINAL y solo si todo salió bien: con set -e,
# cualquier paso que falle corta antes de llegar acá, y la próxima corrida
# vuelve a intentar lo mismo en vez de darlo por desplegado.
echo "$DESPUES" > "$SELLO"

echo
echo "──────────────────────────────────────────────────────────"
echo " Listo. $ANTES → $DESPUES"
echo "──────────────────────────────────────────────────────────"
