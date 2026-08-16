# SICA-VS — Manual de recuperación ante desastres

**Para quién es este documento:** para vos (o cualquier persona que tome tu lugar) el día que algo salga muy mal — el servidor se dañó, la base de datos se corrompió, alguien borró algo por error, o cualquier situación donde necesites **restaurar los datos desde un backup**, ya mismo, con la cabeza fría y sin tener que andar buscando cómo funciona el sistema.

No asume que sepas nada de antemano. Cada comando viene explicado: qué hace y por qué.

---

## Antes de tocar nada: entendé qué tenés

Todos los días, a las 3:00 AM, un proceso automático (`cron`) genera una copia completa de la base de datos de SICA-VS y la guarda en un servicio llamado **DigitalOcean Spaces** — un lugar de almacenamiento separado del propio servidor. Esto es importante: **el backup no vive en el mismo servidor que la aplicación**. Si el servidor se rompe por completo, el backup sigue existiendo en otro lado, intacto.

Se guardan los backups de los **últimos 14 días**. Cada uno tiene un nombre con la fecha y hora exacta en que se generó, por ejemplo:

```
sicavs-20260816-030001.dump
```

Eso significa: generado el **2026-08-16** (16 de agosto de 2026) a las **03:00:01** de la mañana.

---

## Paso 0 — Conectate al servidor

Desde tu computadora, abrí una terminal (PowerShell si es Windows) y entrá al servidor:

```bash
ssh root@2.25.106.253
```

Si configuraste una llave con contraseña propia (passphrase), te la va a pedir en este paso.

Una vez adentro, andá a la carpeta del proyecto:

```bash
cd /opt/sicavs
```

Todos los comandos de este manual asumen que estás parado en esa carpeta.

---

## Paso 1 — Confirmá qué backups existen

Antes de restaurar nada, mirá qué backups tenés disponibles y de qué fecha son. Copiá y pegá este bloque completo (son varias líneas juntas, se pegan todas de una vez):

```bash
SPACES_KEY=$(grep -E '^SPACES_KEY=' .env | cut -d '=' -f2-)
SPACES_SECRET=$(grep -E '^SPACES_SECRET=' .env | cut -d '=' -f2-)
SPACES_BUCKET=$(grep -E '^SPACES_BUCKET=' .env | cut -d '=' -f2-)
SPACES_REGION=$(grep -E '^SPACES_REGION=' .env | cut -d '=' -f2-)
export AWS_ACCESS_KEY_ID=$SPACES_KEY AWS_SECRET_ACCESS_KEY=$SPACES_SECRET
aws s3 ls s3://$SPACES_BUCKET/backups-db/ --endpoint-url https://$SPACES_REGION.digitaloceanspaces.com
```

**Qué hace:** lee las credenciales de acceso a Spaces desde el archivo de configuración del servidor (`.env`), y te muestra la lista de todos los backups guardados, con su fecha, hora y tamaño. Algo así:

```
2026-08-15 03:00:03     172033 sicavs-20260815-030001.dump
2026-08-16 03:00:05     176211 sicavs-20260816-030001.dump
```

**Elegí el backup que querés usar.** Normalmente es el **más reciente** (el de más abajo en la lista) — pero si el problema fue, por ejemplo, que alguien borró datos por error ayer, tal vez te convenga un backup de **antes** de que eso pasara. Copiá el nombre exacto del archivo que elegiste (por ejemplo `sicavs-20260816-030001.dump`) — lo vas a necesitar en el próximo paso.

---

## Paso 2 — Descargá ese backup al servidor

El backup vive en Spaces, no en el servidor — hay que traerlo primero. Reemplazá `NOMBRE_DEL_ARCHIVO.dump` por el nombre que copiaste en el paso anterior:

```bash
mkdir -p /tmp/sicavs-backups
aws s3 cp s3://$SPACES_BUCKET/backups-db/NOMBRE_DEL_ARCHIVO.dump /tmp/sicavs-backups/ --endpoint-url https://$SPACES_REGION.digitaloceanspaces.com
```

**Qué hace:** crea una carpeta temporal en el servidor y descarga ahí el backup elegido. Vas a ver un mensaje como:

```
download: s3://sica-vs-archivos/backups-db/NOMBRE_DEL_ARCHIVO.dump to ../../tmp/sicavs-backups/NOMBRE_DEL_ARCHIVO.dump
```

Eso confirma que ya está en el servidor, listo para usarse.

---

## Paso 3 — Decidí: ¿restaurar sobre la base real, o probar primero en una de prueba?

Acá hay una decisión importante.

- Si estás **100% seguro** de que hay que restaurar (por ejemplo, la base real quedó destruida o corrupta y no hay otra opción) → andá directo al **Paso 4A**.
- Si tenés alguna duda, o simplemente querés confirmar que el backup elegido tiene lo que esperás **antes** de arriesgar la base real → andá al **Paso 4B** (restaurar primero en una base de prueba, mirar los datos, y recién después decidir).

**Recomendación: si no es una emergencia con el reloj corriendo, siempre elegí el Paso 4B primero.** Cuesta dos minutos extra y evita sustos.

---

## Paso 4A — Restaurar directo sobre la base REAL (⚠️ solo si estás seguro)

Este comando **borra los datos actuales** de la base real y los reemplaza por completo con los del backup. No hay forma de deshacerlo después — por eso el propio comando te va a pedir que confirmes escribiendo la palabra "restaurar" a mano.

```bash
./deploy/restore-db.sh NOMBRE_DEL_ARCHIVO.dump
```

Te va a mostrar una advertencia y esperar tu confirmación:

```
⚠️  Vas a restaurar 'NOMBRE_DEL_ARCHIVO.dump' sobre la base 'sicavs'.
⚠️  Esto BORRA los datos actuales de esa base y los reemplaza por los del backup.
Escribí 'restaurar' para confirmar:
```

Escribí exactamente `restaurar` (sin comillas) y apretá Enter. Si escribís cualquier otra cosa, se cancela sin tocar nada.

Cuando termine, vas a ver `Restauración completa.` — en ese momento la base real ya tiene los datos del backup elegido. **Reiniciá el backend** para que tome los datos frescos:

```bash
docker compose -f docker-compose.prod.yml restart backend worker
```

Listo. Andá al final de este documento, sección "Después de restaurar", para los últimos chequeos.

---

## Paso 4B — Restaurar primero en una base de PRUEBA (recomendado)

Esto crea una copia separada, sin tocar la base real, para que puedas revisarla tranquilo antes de decidir si la usás de verdad.

### 4B.1 — Traer las credenciales de la base de datos

```bash
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d '=' -f2-)
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d '=' -f2-)
```

### 4B.2 — Crear la base de prueba

```bash
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db psql -U $POSTGRES_USER -c "CREATE DATABASE sicavs_test_restore;"
```

Deberías ver `CREATE DATABASE`.

### 4B.3 — Restaurar el backup ahí adentro

```bash
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db pg_restore -U $POSTGRES_USER -d sicavs_test_restore --no-owner < /tmp/sicavs-backups/NOMBRE_DEL_ARCHIVO.dump
```

Es normal que este comando no muestre nada si sale bien. Si aparece algo en rojo con la palabra `ERROR`, copialo — puede ser una señal de que el backup está dañado (raro, pero posible).

### 4B.4 — Revisar que los datos son los esperados

Por ejemplo, para ver los usuarios que quedaron en esa base de prueba:

```bash
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db psql -U $POSTGRES_USER -d sicavs_test_restore -c "SELECT nombre, email, rol FROM usuarios;"
```

O para ver cuántas residenciales hay:

```bash
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db psql -U $POSTGRES_USER -d sicavs_test_restore -c "SELECT nombre FROM residenciales;"
```

Mirá si los datos coinciden con lo que esperabas de esa fecha.

### 4B.5 — Ya revisaste y confirmás que es el backup correcto: ¿ahora qué?

Tenés dos caminos:

**A) Restaurarlo también sobre la base real** — repetí el Paso 4A de arriba (el script `restore-db.sh`) con el mismo archivo.

**B) Descartar la prueba** (si decidiste que no era el backup que necesitabas, o si solo querías confirmar sin restaurar nada de verdad):

```bash
docker compose -f docker-compose.prod.yml exec -T -e PGPASSWORD=$POSTGRES_PASSWORD db psql -U $POSTGRES_USER -c "DROP DATABASE sicavs_test_restore;"
```

Esto borra la base de prueba. La base real nunca fue tocada en todo este proceso.

---

## Después de restaurar — últimos chequeos

Una vez que restauraste sobre la base real (Paso 4A) y reiniciaste el backend, confirmá que todo esté funcionando:

1. **Abrí el sitio** en el navegador: `https://patronatovillasdelsol.com` — debería cargar normal.
2. **Probá iniciar sesión** con un usuario que sepas que existía en el backup restaurado.
3. **Revisá los logs del backend**, por si hay algún error:
   ```bash
   docker compose -f docker-compose.prod.yml logs backend --tail 50
   ```

Si algo no se ve bien, revisá que el backend haya reiniciado correctamente:

```bash
docker compose -f docker-compose.prod.yml ps
```

Todos los servicios (`sicavs_db`, `sicavs_redis`, `sicavs_backend`, `sicavs_worker`) deberían decir `Up`.

---

## Preguntas frecuentes

**¿Qué pasa si borro la base de prueba sin querer, en vez de la real?**
No pasa nada grave — es una base descartable creada solo para pruebas. La base real (`sicavs`) nunca se toca a menos que corras específicamente `restore-db.sh` (Paso 4A) y confirmes escribiendo "restaurar".

**¿Qué pasa si el backup más reciente también está dañado?**
Por eso se guardan 14 días de backups, no solo el último. Volvé al Paso 1 y elegí uno más viejo.

**¿Puedo perder datos entre el backup y el momento del incidente?**
Sí — los backups son diarios (3 AM), así que en el peor caso podés perder hasta un día de actividad (lo que haya pasado entre el último backup y el momento del problema). Esto es normal y esperado en cualquier sistema de backups diarios; si en el futuro se necesita menos margen de pérdida, se puede aumentar la frecuencia (cada 6 horas, por ejemplo) editando el cron.

**¿Cómo sé si el sistema de backups sigue funcionando día a día?**
```bash
tail -20 /var/log/sicavs-backup.log
```
Deberías ver una línea nueva de `Backup completo. OK.` con fecha de cada día. Si hace más de un día que no aparece una entrada nueva, algo se rompió — revisá el log completo para ver el error.
