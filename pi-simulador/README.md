# Simulador de Raspberry Pi — SICA-VS

Hace de Raspberry Pi virtual para probar el flujo completo de accesos sin el
hardware real. Es casi el mismo programa que correrá en la Pi de verdad; la
diferencia es que el relay se simula con un mensaje en pantalla en vez de mover
un pin GPIO.

## Cómo usarlo

1. Levantá el sistema normal: `docker compose up --build`
2. Entrá al **panel dev → pestaña Raspberry Pi**, creá una Pi (con su punto de
   acceso) y **copiá el token** que aparece.
3. Asegurate de tener trancas configuradas en ese punto (pestaña Trancas) y al
   menos un residente con tarjeta activa.
4. Arrancá el simulador con el token:

   ```bash
   PI_TOKEN=eltokenquecopiaste docker compose --profile sim up pi-simulador --build
   ```

5. Mirá la consola: vas a ver cómo sincroniza, "pasa tarjetas", abre la tranca
   (relay simulado) y reporta los eventos. Los accesos aparecen en el historial
   del sistema, igual que si fueran reales.

## Qué demuestra

- La copia local (valida sin consultar al servidor en cada paso)
- La dirección fija por tranca (entrada/salida)
- El reporte de eventos con idempotencia
- Que funciona aunque el servidor no esté disponible (acumula y reintenta)
