# Auditoría de dependencias del frontend — Día 69

`npm audit` reportaba **14 vulnerabilidades (1 crítica, 7 altas, 6 moderadas)**.
Tras esta revisión quedan **6**, y ninguna de las 6 alcanza a un usuario del
sistema en producción.

Este documento existe para no tener que volver a razonarlo cada vez que
alguien corre `npm install` y ve el aviso en rojo.

---

## El criterio

Una vulnerabilidad en una dependencia **no es automáticamente una
vulnerabilidad del sistema**. Lo que importa es si el código de SICA-VS
llama a la función afectada, y con qué datos. Un fallo en el parseo de
archivos no te afecta si nunca parseás un archivo.

Por eso cada punto de abajo dice **qué API usamos**, no solo qué dice el
aviso. Y donde la conclusión es "no alcanza", está el comando con el que
se verificó, para que cualquiera lo pueda repetir.

---

## Resueltas

### react-router-dom (4 avisos: open redirect, XSS)

**Estaba declarada en `package.json` y no se importaba en ningún archivo.**

```bash
grep -rn "react-router\|BrowserRouter\|useNavigate\|<Link" src/
# sin resultados
```

La navegación del panel es estado de React (`seccion` en `App.tsx`), no
rutas. La dependencia era un resto de un andamiaje temprano.

**Acción: se eliminó.** No se actualizó — se borró. Cuatro avisos menos.

El bundle **no cambió ni un byte**, y eso es lo esperado: Vite solo empaqueta
lo que se importa, y esto no se importaba desde ningún lado. El chunk
principal quedó con el mismo hash (`index-CxdvomHn.js`, 1 086 645 bytes)
antes y después de borrarla.

Lo que sí se reduce es otra cosa, y es la que importa acá: tres paquetes
menos en `node_modules`, cuatro avisos menos en cada auditoría, y una
dependencia menos de la cual depender si mañana alguien la compromete. La
superficie de cadena de suministro no se mide en el bundle.

### browserslist, nanoid, postcss, source-map-js, baseline-browser-mapping

Herramientas de build (entran por Vite). No viajan en el bundle que se
sirve a los usuarios. Se actualizaron con `npm audit fix` sin romper nada.

---

## Las 6 que quedan, y por qué se aceptan

### xlsx — ALTA — sin arreglo disponible

Prototype pollution y ReDoS en SheetJS. `npm audit` dice `fix: false`
porque SheetJS dejó de publicar en npm: la versión corregida solo está en
su CDN. La del registro quedó congelada.

**No alcanza.** Las dos vulnerabilidades están en el **parseo** de
archivos. Nosotros solo generamos:

```bash
grep -rhoE "XLSX\.[a-zA-Z_.]+" src/ | sort | uniq -c
#   18 XLSX.utils.book_append_sheet
#   18 XLSX.utils.aoa_to_sheet
#    9 XLSX.writeFile
#    9 XLSX.utils.book_new
```

No hay un solo `XLSX.read` ni `XLSX.readFile`. El sistema nunca abre una
hoja de cálculo que venga de afuera.

> **Si algún día se agrega importación de Excel** (por ejemplo, para cargar
> el padrón desde un archivo), esta decisión deja de valer y hay que migrar
> al paquete del CDN de SheetJS **antes** de escribir esa función.

### jspdf — CRÍTICA — y jspdf-autotable, dompurify

La lista de avisos de jsPDF es larga y la parte grave es "Arbitrary
JavaScript Execution" vía AcroForm y `addJS`.

**Esa parte no alcanza.** No usamos ninguna de esas APIs:

```bash
grep -rn "AcroForm\|addJS\|doc.html(\|createOption\|FreeText" src/
# solo addImage, para el logo de la residencial
```

Usamos `addImage` y `autoTable`. `dompurify` entra como dependencia de
jsPDF para `doc.html()`, que tampoco usamos, así que ni se ejecuta.

**Lo que sí queda** es el riesgo de ReDoS: un nombre de residente o una
placa con un texto malicioso podría colgar la pestaña del administrador
que genera el reporte. Es una molestia local en el navegador de quien
genera el PDF — no toca el servidor, no expone datos, no afecta a otros
usuarios.

**Por qué no se arregló hoy:** `jspdf@4` y `jspdf-autotable@5` son saltos
de versión mayor que cambian la API, y `src/utils/pdfReporte.ts` genera
todos los recibos y reportes del sistema. Migrar y volver a verificar cada
PDF es un sprint propio, no un `npm audit fix` a las 2 de la tarde con
producción recién levantada.

### vite y esbuild — ALTA / MODERADA

Path traversal y "cualquier sitio web puede leer del servidor de
desarrollo". Ambas son del **servidor de desarrollo** (`npm run dev`).
Vite está en `devDependencies` y no forma parte del bundle de producción.

**No alcanza a producción.** Solo importa en la máquina de quien
desarrolla, mientras tiene `npm run dev` corriendo y navega a un sitio
hostil en la misma sesión.

---

## Pendiente, ordenado por lo que de verdad conviene

1. **Migrar jsPDF a 4.x** y autotable a 5.x. Después de la defensa, con
   tiempo para revisar cada reporte generado.
2. **Subir Vite a 8.x.** Mismo criterio: rompe, y no protege a ningún
   usuario.
3. **Revisar `xlsx` si alguna vez se agrega importación.** Anotado arriba.

---

## Cómo repetir esta auditoría

```bash
cd frontend
npm audit
```

Si el número sube, la pregunta no es "cuántas son" sino **"qué API nuestra
las toca"**. Este documento es el ejemplo de cómo contestarla.
