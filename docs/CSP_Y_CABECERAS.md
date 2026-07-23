# CSP y cabeceras de seguridad — SICA-VS

> **CSP-19 (Auditoría Día 39).** Por qué el CSP de desarrollo y el de
> producción son distintos, cuál protege de verdad, y qué verificar al
> desplegar.

---

## 1. El hallazgo y lo que apareció al revisarlo

La auditoría reportó que el CSP del backend permitía `unsafe-inline` y
`unsafe-eval` en `script-src`. Era cierto:

```python
"script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
```

Pero al revisar el contexto apareció algo que cambia el análisis: **ese CSP
casi no protegía nada.**

Un CSP es una instrucción al navegador sobre qué puede ejecutar **en una
página HTML**. El backend de SICA-VS tiene 180 rutas, de las cuales 179 son
`/api/` que devuelven JSON, y la única excepción es `/static/`. Aplicar un
CSP a una respuesta JSON no hace nada: no hay página, no hay scripts, no hay
nada que restringir.

**Quien sirve el HTML es otro:**

| Entorno | Sirve el HTML | CSP antes del Día 41 |
|---|---|---|
| Desarrollo | Vite (puerto 5173) | ninguno |
| Producción | Nginx | **ninguno — no estaba configurado** |
| API (ambos) | Flask | el reportado, sin efecto real |

El problema de fondo no era que el CSP de Flask fuera permisivo. Era que
**producción no iba a tener CSP en absoluto.**

---

## 2. Qué se hizo

**Flask** (`backend/app/__init__.py`): CSP reducido al mínimo posible.

```
default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
```

La API no ejecuta scripts ni carga recursos, así que negar todo no rompe
nada. Se endurece igual porque cuesta cero y evita que alguien copie un CSP
permisivo pensando que es el bueno.

**Nginx** (`deploy/nginx-sicavs.conf`): el CSP que sí importa, escrito y
comentado, listo para aplicar al desplegar. Junto con TLS, HSTS, caché y el
proxy hacia la API.

---

## 3. Por qué desarrollo y producción difieren

Esta es la parte que conviene entender antes de tocar nada, porque la
tentación natural al ver un error de CSP es aflojarlo.

### `unsafe-eval`

Convierte texto en código ejecutable (`eval()`, `new Function()`). Es la
directiva más peligrosa: si un atacante logra inyectar una cadena en algún
punto donde se evalúe, ejecuta lo que quiera.

- **Vite lo necesita** para el hot-reload, que evalúa módulos en caliente.
- **El build de producción no**: React sale compilado, no evalúa nada.

### `unsafe-inline` en `script-src`

Permite `<script>...</script>` incrustado en el HTML. Es la vía clásica de
XSS: si alguien inyecta un `<script>` en cualquier campo que se renderice,
el navegador lo ejecuta.

- **Vite lo necesita** para inyectar su cliente de recarga.
- **El build de producción no**: emite archivos `.js` separados.

### `unsafe-inline` en `style-src` ← la única concesión

React inyecta estilos en línea (`style={{...}}`) constantemente. Quitarlo
requeriría un nonce por cada render, lo que complica mucho el build.

Se acepta porque **el riesgo es de otro orden**: un estilo malicioso puede
alterar la apariencia — superponer un botón falso, ocultar una advertencia —
pero no puede ejecutar código. Es una degradación de la segunda barrera, no
un agujero.

Endurecerlo con nonces queda anotado como mejora futura.

---

## 4. El CSP de producción, directiva por directiva

```nginx
default-src 'self';                    # por defecto, solo el propio origen
script-src 'self';                     # sin unsafe-eval ni unsafe-inline
style-src 'self' 'unsafe-inline';      # concesión de React (ver §3)
img-src 'self' data: blob:;            # data: para el QR, blob: para previews
font-src 'self';
connect-src 'self';                    # sin ws: — Socket.IO se eliminó (SOCKET-17)
media-src 'self' blob:;
object-src 'none';                     # bloquea <object>, <embed>, <applet>
base-uri 'self';                       # no se puede reescribir la URL base
form-action 'self';                    # los formularios solo envían al propio sitio
frame-ancestors 'none';                # no embebible en iframes
upgrade-insecure-requests              # http:// → https:// automático
```

Dos notas:

- **`data:` en `img-src`** lo necesita el QR de la tarjeta virtual, que se
  genera en el cliente desde el Día 31. **`blob:`** lo necesita la vista
  previa de fotos antes de subirlas. Ambos son de origen local.
- **`connect-src` sin `ws:`/`wss:`** porque Socket.IO se eliminó en
  SOCKET-17. Si algún día se reintroduce tiempo real, agregar el origen
  concreto — nunca un comodín.

---

## 5. Al desplegar

### Antes de aplicar

```bash
sudo nginx -t          # valida la sintaxis; NO recargar si falla
```

### Después de aplicar, verificar

```bash
curl -I https://sicavs.villasdelsol.hn | grep -i "content-security\|strict-transport"
```

Y en el navegador, con F12 → Console, recorrer las pantallas principales
buscando errores que empiecen con *"Refused to..."*. Cada uno indica algo
que el CSP está bloqueando.

**Si aparece un bloqueo, no aflojar el CSP por reflejo.** Primero entender
qué recurso es y por qué no estaba previsto. Casi siempre la solución
correcta es cambiar el código, no la política.

### Lista de verificación funcional

- [ ] Iniciar sesión (web y app)
- [ ] Tarjeta virtual con QR — es la más propensa a fallar (`data:`)
- [ ] Subir un comprobante de pago (`blob:` en la vista previa)
- [ ] Registrar una entrada de visita con foto
- [ ] Descargar un recibo PDF
- [ ] Panel del desarrollador → Métricas de código
- [ ] Biometría / WebAuthn

---

## 6. Pendientes relacionados

### Fotos de evidencia — bloqueadas a propósito

La configuración de Nginx **bloquea `/uploads/`** con `deny all`.

No es un descuido. La auditoría del Día 39 señaló que las fotos de identidad
y placa no deben servirse como carpeta estática pública. Los nombres son
UUID impredecibles, pero *"difícil de adivinar" no es control de acceso*:
cualquiera con el enlace vería la cédula de un visitante, y un residente
podría ver evidencia de otra cuenta.

Lo correcto es un endpoint autenticado que verifique permisos, o URLs
firmadas de corta vida desde DigitalOcean Spaces — el módulo `storage.py`
ya lo soporta.

Hasta implementarlo, es preferible que la función no ande a que filtre
documentos de identidad.

### Mejoras futuras

- **Nonces para `style-src`**, para eliminar la última concesión.
- **`Report-To` / `report-uri`**, para que el navegador avise de violaciones
  del CSP en producción en vez de fallar en silencio.
- **HSTS con `preload`**, solo cuando el dominio esté consolidado. Es
  prácticamente irreversible: salir de la lista de precarga de los
  navegadores toma meses.
