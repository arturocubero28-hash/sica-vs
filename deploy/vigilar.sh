#!/usr/bin/env bash
#
# Vigilante de SICA-VS (Día 73) — manda un correo si el worker o el
# backend se caen.
#
# POR QUÉ EXISTE
#
# El 5 de noviembre el worker quedó en un bucle de reinicios y nada lo
# delataba: el backend respondía, el health daba 200, el panel andaba.
# Pero el worker es el que genera las cuotas el 1ro de cada mes, revisa la
# mora, manda las notificaciones push y los correos de recuperar
# contraseña. Con él caído, el 1ro de diciembre no se habría generado
# ninguna cuota y nadie se habría enterado.
#
# POR QUÉ CORRE ACÁ, EN EL SERVIDOR, Y NO ADENTRO DEL SISTEMA
#
# Una alerta tiene que funcionar justo cuando lo demás falla. Si la
# mandara el worker, con el worker caído no saldría. Si la mandara el
# backend, con el backend caído tampoco. Este script corre con el cron
# del propio servidor, fuera de Docker, y manda el correo hablando
# directo con Resend: no necesita que nada del sistema esté en pie.
#
# QUÉ HACE, CADA 5 MINUTOS
#
#   1. Le pregunta al backend si el worker está vivo (/api/v1/health/worker).
#   2. Si falla DOS veces seguidas (10 minutos), manda el correo de alerta.
#      Una sola falla no alcanza: un despliegue reinicia los contenedores
#      y no queremos una alarma cada vez que se actualiza el sistema.
#   3. Mientras siga caído, recuerda cada 6 horas (no cada 5 minutos).
#   4. Cuando se recupera, manda un correo diciendo que volvió.
#
# INSTALAR (una vez):
#
#     1. En /opt/sicavs/.env agregar:   ALERTA_EMAIL=tu@correo.com
#     2. bash /opt/sicavs/deploy/vigilar.sh --probar   (te tiene que llegar un correo)
#     3. ( crontab -l 2>/dev/null | grep -v vigilar.sh; \
#          echo "*/5 * * * * /opt/sicavs/deploy/vigilar.sh" ) | crontab -
#
# Las rutas se pueden cambiar por entorno para probarlo fuera del servidor.

set -uo pipefail

URL="${VIGILAR_URL:-http://127.0.0.1:5000/api/v1/health/worker}"
ENV_FILE="${VIGILAR_ENV:-/opt/sicavs/.env}"
ESTADO="${VIGILAR_ESTADO:-/var/lib/sicavs-vigilar}"
COMPOSE_DIR="${VIGILAR_COMPOSE_DIR:-/opt/sicavs}"
RECORDAR_CADA=$((6 * 3600))
FALLAS_PARA_AVISAR=2

mkdir -p "$ESTADO"
log() { logger -t sicavs-vigilar "$*" 2>/dev/null || true; echo "$(date '+%F %T') $*"; }

# Lee una variable del .env sin ejecutarlo (el .env no es un script).
leer_env() {
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

RESEND_KEY="$(leer_env RESEND_API_KEY)"
DESTINO="$(leer_env ALERTA_EMAIL)"
REMITENTE="$(leer_env RESEND_FROM)"
REMITENTE="${REMITENTE:-Residencial Villas del Sol <notificaciones@patronatovillasdelsol.com>}"

enviar() {
  # $1 asunto, $2 cuerpo en texto plano
  if [ -z "$DESTINO" ]; then
    log "ALERTA sin destinatario (falta ALERTA_EMAIL en $ENV_FILE): $1"
    return 1
  fi
  if [ -z "$RESEND_KEY" ]; then
    log "ALERTA sin RESEND_API_KEY en $ENV_FILE: $1"
    return 1
  fi
  if [ "${VIGILAR_SECO:-}" = "si" ]; then          # modo prueba: no manda nada
    printf '── CORREO (simulado) ──\nPara: %s\nAsunto: %s\n\n%s\n' "$DESTINO" "$1" "$2"
    return 0
  fi
  # El JSON se arma con python para no romperlo con comillas o saltos de
  # línea del log que va en el cuerpo.
  local json
  json="$(python3 -c 'import json,sys; print(json.dumps({"from":sys.argv[1],"to":[sys.argv[2]],"subject":sys.argv[3],"text":sys.argv[4]}))' \
          "$REMITENTE" "$DESTINO" "$1" "$2")"
  local codigo
  codigo="$(curl -s -o /dev/null -w '%{http_code}' -m 20 \
            -H "Authorization: Bearer $RESEND_KEY" -H "Content-Type: application/json" \
            -d "$json" https://api.resend.com/emails)"
  if [ "$codigo" = "200" ]; then log "correo enviado a $DESTINO: $1"; return 0; fi
  log "NO se pudo mandar el correo de alerta (Resend respondió $codigo): $1"
  return 1
}

diagnostico() {
  echo "Estado de los contenedores:"
  (cd "$COMPOSE_DIR" 2>/dev/null && docker compose -f docker-compose.prod.yml ps \
     --format '  {{.Name}}  {{.Status}}' 2>/dev/null) || echo "  (no se pudo consultar Docker)"
  echo
  echo "Últimas líneas del worker:"
  (cd "$COMPOSE_DIR" 2>/dev/null && docker compose -f docker-compose.prod.yml logs worker \
     --tail 15 --no-color 2>/dev/null | sed 's/^/  /') || echo "  (no se pudieron leer los logs)"
}

# ── Modo prueba: manda un correo ya, para saber que las alertas llegan ──
if [ "${1:-}" = "--probar" ]; then
  if enviar "Prueba del vigilante de Villas del Sol" \
"Este es un correo de prueba del vigilante del servidor.

Si te llegó, las alertas funcionan: si el worker o el backend se caen,
te va a llegar un correo como este, con el diagnóstico.

$(diagnostico)"; then
    echo "Listo: revisá $DESTINO (y spam)."
  else
    echo "No se pudo mandar. Revisá ALERTA_EMAIL y RESEND_API_KEY en $ENV_FILE."
    exit 1
  fi
  exit 0
fi

# ── Chequeo normal ───────────────────────────────────────────────────────
respuesta="$(curl -s -m 10 -w '\n%{http_code}' "$URL" 2>/dev/null)"
codigo="$(echo "$respuesta" | tail -1)"
cuerpo="$(echo "$respuesta" | head -n -1)"

if [ "$codigo" = "200" ]; then
  # Vivo. Si veníamos de una alerta, avisar que volvió.
  if [ -f "$ESTADO/alertado" ]; then
    desde="$(cat "$ESTADO/alertado_desde" 2>/dev/null || echo "?")"
    enviar "✅ El sistema de Villas del Sol volvió a funcionar" \
"El worker vuelve a responder.

Estaba caído desde: $desde
Se recuperó:        $(date '+%F %T')

Revisá si en ese lapso se tenía que correr algo programado (las cuotas
del 1ro de mes a las 00:05, o la revisión de mora de la 1:00): si cayó
en ese horario, hay que correrlo a mano." \
      && rm -f "$ESTADO/alertado" "$ESTADO/ultimo_aviso" "$ESTADO/alertado_desde"
  fi
  rm -f "$ESTADO/fallas"
  exit 0
fi

# Algo falla. Qué.
if [ -z "$codigo" ] || [ "$codigo" = "000" ]; then
  que="el BACKEND no responde"
  efecto="El panel web y la app no funcionan."
elif echo "$cuerpo" | grep -q "redis_no_responde"; then
  que="REDIS no responde"
  efecto="El worker no puede trabajar y el panel puede estar fallando."
else
  que="el WORKER está caído"
  efecto="No se generan cuotas ni se revisa la mora, no salen notificaciones push ni correos de recuperar contraseña o regenerar enlace. El panel y la app siguen andando, así que nadie lo nota."
fi

fallas=$(( $(cat "$ESTADO/fallas" 2>/dev/null || echo 0) + 1 ))
echo "$fallas" > "$ESTADO/fallas"
log "falla $fallas: $que (HTTP $codigo)"
[ "$fallas" -lt "$FALLAS_PARA_AVISAR" ] && exit 0

ahora=$(date +%s)
ultimo=$(cat "$ESTADO/ultimo_aviso" 2>/dev/null || echo 0)
[ $((ahora - ultimo)) -lt "$RECORDAR_CADA" ] && exit 0

[ -f "$ESTADO/alertado_desde" ] || date '+%F %T' > "$ESTADO/alertado_desde"
recordatorio=""
[ -f "$ESTADO/alertado" ] && recordatorio="(Recordatorio: sigue caído desde $(cat "$ESTADO/alertado_desde").)
"

if enviar "🔴 Villas del Sol: $que" \
"${recordatorio}Desde hace al menos $((fallas * 5)) minutos, $que.

Qué afecta: $efecto

Respuesta del chequeo: HTTP ${codigo:-sin respuesta} ${cuerpo}

$(diagnostico)

Para revisarlo en el servidor:
  cd /opt/sicavs
  docker compose -f docker-compose.prod.yml ps
  docker compose -f docker-compose.prod.yml logs worker --tail 50

Este aviso se repite cada 6 horas mientras siga caído, y te llega otro
cuando se recupere."; then
  touch "$ESTADO/alertado"
  echo "$ahora" > "$ESTADO/ultimo_aviso"
fi
