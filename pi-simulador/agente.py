"""
Simulador de Raspberry Pi para SICA-VS
=======================================

Hace de "Raspberry Pi virtual" para probar el flujo completo de accesos sin
el hardware real. Es prácticamente el mismo programa que correrá en la Pi de
verdad; la única diferencia es que aquí el relay se "activa" mostrando un
mensaje en pantalla, en lugar de mover un pin GPIO físico.

Qué hace:
  1. Sincroniza: descarga su copia local (tarjetas con permiso + trancas).
  2. Simula lecturas de tarjeta y valida CONTRA LA COPIA LOCAL (sin internet).
  3. Acciona la "tranca" (mensaje de relay) si el acceso es válido.
  4. Reporta los eventos al servidor (con id único, idempotente).
  5. Si el servidor no responde, acumula los eventos y los reintenta luego.

Config por variables de entorno:
  API_URL       URL base del backend (ej. http://backend:5000/api/v1)
  DEVICE_TOKEN  token de esta Pi (se obtiene del panel dev al crear la Pi)
  SYNC_SEGUNDOS cada cuántos segundos re-sincroniza (default 30)
"""
import os
import time
import uuid
import random
import datetime as dt

import requests

API_URL = os.environ.get("API_URL", "http://backend:5000/api/v1")
DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "")
SYNC_SEGUNDOS = int(os.environ.get("SYNC_SEGUNDOS", "30"))

HEADERS = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}


class PiSimulada:
    def __init__(self):
        self.tarjetas = {}      # card_uid -> info (copia local)
        self.accesos = []       # trancas de este punto
        self.punto = None
        self.pendientes = []    # eventos no reportados (cola offline)
        self.ultima_sync = None

    # ---- 1. Sincronización (bajar la copia local) ----
    def sincronizar(self):
        try:
            r = requests.get(f"{API_URL}/acceso/sincronizar", headers=HEADERS, timeout=8)
        except requests.RequestException as e:
            print(f"  ⚠️  Sin conexión al sincronizar ({e.__class__.__name__}). Sigo con la copia anterior.")
            return False
        if r.status_code == 401:
            print("  ❌ Token inválido o Pi revocada. Revisá el DEVICE_TOKEN.")
            return False
        if r.status_code != 200:
            print(f"  ⚠️  El servidor respondió {r.status_code} al sincronizar.")
            return False

        data = r.json().get("data", {})
        self.punto = data.get("punto_acceso")
        self.accesos = data.get("accesos", [])
        self.tarjetas = {t["card_uid"]: t for t in data.get("tarjetas", [])}
        self.ultima_sync = dt.datetime.utcnow()
        print(f"  ✅ Copia local actualizada: {len(self.tarjetas)} tarjeta(s) con permiso, "
              f"{len(self.accesos)} tranca(s). Punto: {self.punto or '—'}")
        return True

    # ---- 2 y 3. Validar localmente y accionar la tranca ----
    def pasar_tarjeta(self, card_uid, acceso):
        """Simula que alguien pasa una tarjeta por una tranca de este punto."""
        nombre_tranca = acceso["nombre"]
        direccion = acceso.get("direccion", "entrada")
        print(f"\n  💳 Tarjeta {card_uid} en «{nombre_tranca}» ({direccion})")

        # Validación contra la COPIA LOCAL (no se consulta al servidor)
        info = self.tarjetas.get(card_uid)
        if not info:
            print(f"     🚫 DENEGADO — la tarjeta no está en la copia local (sin permiso).")
            return

        # Compatibilidad de tipo: peatonal no abre trancas vehiculares
        if info["tipo_acceso"] == "peatonal" and acceso["tipo"] == "vehicular":
            print(f"     🚫 DENEGADO — tarjeta peatonal en tranca vehicular.")
            return

        # Acceso válido: accionar el relay (simulado)
        residente = info.get("residente") or "—"
        self.accionar_relay(acceso)
        print(f"     ✅ PERMITIDO — {residente}")

        # Registrar el evento para reportarlo
        self.pendientes.append({
            "id_externo": str(uuid.uuid4()),
            "card_uid": card_uid,
            "acceso_id": acceso["id"],
            "ocurrido_en": dt.datetime.utcnow().isoformat() + "Z",
        })

    def accionar_relay(self, acceso):
        """En la Pi real, aquí se activa el pin GPIO. Aquí se simula."""
        pin = acceso.get("relay_pin")
        pulso = acceso.get("pulso_ms", 800)
        if pin is None:
            print(f"     ⚙️  (esta tranca no tiene relay configurado todavía)")
            return
        print(f"     🔓 RELAY pin {pin} ACTIVO por {pulso} ms → la tranca se abre")
        time.sleep(pulso / 1000.0)
        print(f"     🔒 RELAY pin {pin} apagado")

    # ---- 4. Reportar eventos al servidor ----
    def reportar(self):
        if not self.pendientes:
            return
        try:
            r = requests.post(f"{API_URL}/acceso/reportar",
                              json={"eventos": self.pendientes}, headers=HEADERS, timeout=8)
        except requests.RequestException:
            print(f"  ⚠️  Sin conexión al reportar. Guardo {len(self.pendientes)} evento(s) para después.")
            return
        if r.status_code == 200:
            d = r.json().get("data", {})
            print(f"  📤 Reportados: {d.get('guardados',0)} nuevos, {d.get('duplicados',0)} duplicados.")
            self.pendientes = []   # ya viajaron; idempotencia protege de duplicar
        else:
            print(f"  ⚠️  El servidor respondió {r.status_code} al reportar. Reintento luego.")


def main():
    print("=" * 60)
    print("  SIMULADOR DE RASPBERRY PI · SICA-VS")
    print("=" * 60)
    if not DEVICE_TOKEN:
        print("\n  ❌ Falta DEVICE_TOKEN. Creá una Pi en el panel dev,")
        print("     copiá su token y poné DEVICE_TOKEN en el docker-compose.\n")
        return

    pi = PiSimulada()
    print(f"\n  Conectando a {API_URL} …")
    pi.sincronizar()

    ciclo = 0
    while True:
        ciclo += 1
        # Re-sincroniza periódicamente (como el RMS cada 30s)
        if ciclo > 1:
            print(f"\n  🔄 Re-sincronizando (cada {SYNC_SEGUNDOS}s)…")
            pi.sincronizar()

        # Simular algunas lecturas de tarjeta si hay trancas y tarjetas
        if pi.accesos and pi.tarjetas:
            for _ in range(random.randint(1, 3)):
                acceso = random.choice(pi.accesos)
                # 80% una tarjeta válida, 20% una desconocida (para ver el DENEGADO)
                if random.random() < 0.8:
                    card = random.choice(list(pi.tarjetas.keys()))
                else:
                    card = f"DESCONOCIDA-{random.randint(1000,9999)}"
                pi.pasar_tarjeta(card, acceso)
                time.sleep(1)
            pi.reportar()
        else:
            print("  (esperando: faltan trancas o tarjetas en la copia)")

        time.sleep(SYNC_SEGUNDOS)


if __name__ == "__main__":
    main()
