# Protocolo de acceso BLE — SICA-VS

> **Estado: diseñado y parcialmente implementado. Inactivo hasta comprar el lector.**
>
> Este documento define cómo funciona el acceso por Bluetooth. La parte que
> **no** depende del lector físico ya está construida y probada. La que sí
> depende queda marcada explícitamente como pendiente.
>
> Bandera de activación: `BLE_FEATURE_ENABLED` (por defecto `false`).

---

## 1. Por qué existe este documento

BLE-BE-18 (Auditoría Día 39) señaló que el backend aceptaba activaciones BLE
y generaba claves criptográficas reales aunque no existiera hardware ni
protocolo. Al investigarlo apareció un problema de diseño más profundo, que
es el que este documento corrige.

### El problema encontrado

El modelo `CredencialBLE` documentaba su clave secreta así:

> *"Clave secreta para el desafío-respuesta (HMAC). Nunca sale del servidor
> ni del teléfono en texto plano."*

Pero el endpoint `/api/v1/acceso/sincronizar` la enviaba en texto plano a
**cada Raspberry Pi**, en cada sincronización:

```python
ble_out.append({
    "token": c.token_hoy,
    "clave_secreta": c.clave_secreta,   # <-- el secreto de cada residente
    ...
})
```

El código contradecía su propia documentación. El efecto: las claves HMAC de
todos los residentes con BLE activo quedaban replicadas en el caché local de
todas las Pi del residencial. **Una Pi comprometida entregaría las
credenciales de todos** — exactamente lo que un esquema HMAC existe para
evitar.

Como todavía no hay lector ni nadie usa BLE, el riesgo real era nulo. Pero
el diseño habría quedado mal cimentado al desplegar.

---

## 2. Principio de diseño

> **La clave secreta vive en exactamente dos lugares: el servidor y el
> teléfono de su dueño. En ningún otro.**

De ahí se derivan las reglas:

| Componente | Qué conoce | Qué NO conoce |
|---|---|---|
| Teléfono del residente | su propia `clave_secreta` y su `token` | claves de otros residentes |
| Lector BLE | nada persistente | ninguna clave |
| Raspberry Pi | tokens válidos (identificadores públicos) | **ninguna `clave_secreta`** |
| Servidor | todas las claves | — |

La Pi transporta y decide, pero **no verifica firmas**: no tiene con qué.

---

## 3. Flujo de verificación

### 3.1 En línea (camino normal)

```
  Teléfono                Lector BLE           Raspberry Pi            Servidor
     │                        │                     │                     │
     │  advertising:          │                     │                     │
     │  token + contador      │                     │                     │
     │  + HMAC truncado       │                     │                     │
     ├───────────────────────>│                     │                     │
     │                        │  trama cruda        │                     │
     │                        ├────────────────────>│                     │
     │                        │                     │  POST /validar-ble  │
     │                        │                     ├────────────────────>│
     │                        │                     │                     │ busca token
     │                        │                     │                     │ recalcula HMAC
     │                        │                     │                     │ verifica contador
     │                        │                     │  permitido / no     │ registra evento
     │                        │                     │<────────────────────┤
     │                        │  abrir / rechazar   │                     │
     │                        │<────────────────────┤                     │
```

El servidor es el único que puede recalcular el HMAC, porque es el único
(además del teléfono dueño) que tiene la clave.

### 3.2 Sin conexión (offline-first)

La Pi debe seguir abriendo si se cae el internet. Pero **no puede verificar
el HMAC** sin la clave, y dársela reintroduciría el problema original.

La solución es un **caché de respuestas precomputadas firmado por el
servidor**. En cada sincronización, para cada credencial activa, el servidor
envía los HMAC válidos de los próximos N contadores — no la clave:

```json
{
  "token": "BLE7A3F9C21D8E4B506",
  "tipo_acceso": "peatonal",
  "residente": "María López",
  "contador_desde": 42,
  "hmacs": ["a4f2c9d1", "7b3e8a05", "c1d94f7a", "..."],
  "valido_hasta": "2026-07-24T06:00:00Z",
  "firma_servidor": "e91c...":
}
```

La Pi compara el HMAC recibido contra la lista. Coincide o no coincide —
nunca recalcula, nunca necesita la clave.

**Compromiso aceptado:** una Pi comprometida en modo offline puede reproducir
los N accesos precomputados hasta que expire el caché. Es mucho mejor que
entregar la clave, que serviría para siempre y para cualquier contador.
Valores iniciales sugeridos: `N = 50`, `valido_hasta = 24 h`.

Al recuperar conexión, la Pi reporta los accesos offline por `/reportar` y
el servidor avanza el contador real.

---

## 4. Formato de la trama

⚠️ **Esta sección depende del lector que se compre.** Los campos y su orden
son sólidos; los tamaños exactos pueden requerir ajuste.

### 4.1 La restricción

El paquete de anuncio BLE tiene **31 bytes**, de los cuales quedan unos
**23 útiles** tras las cabeceras. Un HMAC-SHA256 completo son 32 bytes: no
cabe. Hay que truncar, como hacen todos los sistemas reales.

### 4.2 Estructura propuesta

| Campo | Bytes | Contenido |
|---|---|---|
| Versión | 1 | `0x01` — permite cambiar el formato sin romper lectores viejos |
| Token | 8 | identificador de la credencial (los 8 bytes del hex tras el prefijo `BLE`) |
| Contador | 4 | entero sin signo, big-endian |
| HMAC truncado | 8 | primeros 8 bytes de `HMAC-SHA256(clave, versión‖token‖contador)` |
| **Total** | **21** | entra en los 23 disponibles |

### 4.3 Sobre el HMAC truncado a 8 bytes

64 bits de firma. Un atacante que quiera falsificar sin conocer la clave
necesita en promedio 2⁶³ intentos. Como cada intento requiere una transmisión
BLE física frente al lector, es inviable. El truncado es la práctica estándar
en credenciales BLE por la restricción de tamaño.

### 4.4 Lo que falta definir (requiere el lector)

- [ ] Formato exacto de advertising que acepta el lector (Service Data,
      Manufacturer Data, o UUID personalizado)
- [ ] Si el lector exige un UUID de servicio propietario
- [ ] Cómo entrega el lector la trama a la Pi (UART, Wiegand, HTTP, GPIO)
- [ ] Si el lector puede reenviar bytes crudos o impone su propio esquema
      (HID Seos, por ejemplo, es propietario y necesita licencia de SDK)
- [ ] Distancia efectiva y umbral de RSSI para evitar aperturas accidentales
      al pasar cerca

**Nota sobre HID Signo (~$200):** usa Seos, un ecosistema cerrado. Habría que
verificar si permite trama personalizada o si obliga a usar sus credenciales.
Un ESP32 con firmware propio sería más barato y totalmente controlable, a
costa de construir el lector.

---

## 5. Estado de implementación

| Parte | Estado | Depende del lector |
|---|---|---|
| Principio: la clave no sale del servidor | ✅ implementado | no |
| `/sincronizar` deja de enviar `clave_secreta` | ✅ implementado | no |
| Bandera `BLE_FEATURE_ENABLED` | ✅ implementado | no |
| Cálculo del HMAC (`hmac_ble`) | ✅ implementado + probado | no |
| Endpoint `/acceso/validar-ble` | ✅ implementado + probado | no |
| Verificación del rolling counter | ✅ implementado + probado | no |
| Caché offline precomputado | 📋 diseñado, sin implementar | parcialmente |
| Advertising BLE en la app Flutter | ❌ no implementado | **sí** |
| Firmware del lector | ❌ no implementado | **sí** |
| Formato final de la trama | ⚠️ propuesto | **sí** |

---

## 6. Cómo activar cuando llegue el lector

1. Confirmar el formato de trama contra la documentación del lector y ajustar
   la sección 4 si hace falta.
2. Implementar el advertising en Flutter, respetando el formato.
3. Implementar el caché offline de la sección 3.2.
4. Poner `BLE_FEATURE_ENABLED=true` en el entorno.
5. Cambiar `bleAccesoFisicoListo = true` en la app (BLE-08, Día 38).
6. Probar: acceso normal, contador repetido (debe rechazar), token expirado,
   credencial suspendida, modo offline, y un teléfono que no es el dueño.

---

## 7. Vectores de prueba

Para verificar que la implementación de la app coincide con la del servidor:

```
clave    = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
token    = "BLE7A3F9C21D8E4B506"
contador = 42
version  = 1

mensaje  = b"\x01" + bytes.fromhex("7A3F9C21D8E4B506") + (42).to_bytes(4, "big")
hmac     = HMAC-SHA256(bytes.fromhex(clave), mensaje)[:8]
```

**Resultado esperado:**

```
HMAC = 2ed219034109ae8a
```

Ese valor lo produce `backend/app/services/ble_cripto.py` y está verificado
por sus pruebas. **La app Flutter debe producir exactamente el mismo
resultado** — si difiere, el formato del mensaje no coincide y ninguna
credencial validaría.

Detalles fáciles de equivocar al implementar en Dart:

- El prefijo `BLE` del token **no** se firma: solo los 8 bytes hex.
- El contador va **big-endian** (`0x0000002A` para 42), no little-endian.
- La versión es el **primer** byte del mensaje.
- Se toman los **primeros** 8 bytes del HMAC-SHA256, no los últimos.
- La clave se interpreta como **bytes hex**, no como texto ASCII.
