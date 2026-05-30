# SICA-VS — Sistema Integral de Control de Accesos
### Residencial Villas del Sol, San Pedro Sula

Plataforma para centralizar el control de accesos, generación de QR para visitas,
cuotas de mantenimiento y panel administrativo en tiempo real.

---

## 🚀 Cómo arrancar (lo único que necesitas hacer)

Requisito: tener **Docker Desktop** instalado.

```bash
git clone <url-del-repo>
cd sica-vs
cp .env.example .env
docker compose up
```

Eso es todo. Se levantan automáticamente:

| Servicio   | URL                          | Qué es                       |
|------------|------------------------------|------------------------------|
| Frontend   | http://localhost:5173        | La aplicación web (React)    |
| Backend    | http://localhost:5000/api/v1 | La API (Flask)               |
| PostgreSQL | localhost:5432               | Base de datos                |
| Redis      | localhost:6379               | Caché / tiempo real          |

La base de datos se crea sola con el esquema y datos de prueba la primera vez.

### Usuario de prueba
- **Admin:** `admin@villasdelsol.hn` / `admin123`
- **Guardia:** `guardia1@villasdelsol.hn` / `admin123`

Verifica que todo funciona:
```bash
curl http://localhost:5000/api/v1/health
# -> {"data":{"status":"ok","service":"sica-vs"}}
```

---

## 📁 Estructura del proyecto

```
sica-vs/
├── docker-compose.yml      # define todo el entorno
├── .env.example            # variables (copiar a .env)
├── backend/
│   ├── wsgi.py             # punto de entrada
│   └── app/
│       ├── __init__.py     # application factory (registra módulos)
│       ├── config.py       # configuración por variables de entorno
│       ├── extensions.py   # db, migrate, socketio
│       ├── models/         # 1 archivo por dominio (ej. usuario.py)
│       ├── api/            # 1 blueprint por módulo
│       ├── auth/           # login, JWT, decoradores de rol
│       ├── services/       # lógica de negocio
│       └── tasks/          # tareas Celery (mora, notificaciones)
│   └── migrations/
│       ├── schema.sql      # esquema completo de la BD
│       └── seed.sql        # datos de prueba
├── frontend/
│   └── src/
│       ├── App.tsx         # login + enrutado por rol
│       ├── api/client.ts   # cliente HTTP central (token, tipos)
│       ├── modules/        # 1 carpeta por módulo (cada dueño la suya)
│       └── shared/         # componentes/tipos compartidos
├── nginx/                  # config de producción
└── docs/                   # documentación
```

---

## 👥 Reparto de módulos

| Integrante | Módulo                                      | Carpetas principales                       |
|-----------|----------------------------------------------|--------------------------------------------|
| 1         | Base + autenticación + hardware (Raspberry)  | `auth/`, `models/usuario.py`, `tasks/`     |
| 2         | Unidades, residentes y tarjetas              | `models/cuenta.py`, `api/cuentas.py`       |
| 3         | Visitas, QR y panel de guardia               | `models/visita.py`, `api/visitas.py`       |
| 4         | Cuotas y pagos                               | `models/pago.py`, `api/pagos.py`, `tasks/` |
| 5         | Landing + panel administrativo               | `frontend/src/modules/admin`, `landing`    |

---

## ✅ Reglas del equipo

1. **Nadie trabaja en `main`.** Cada módulo va en su rama: `feature/cobros`, `feature/visitas`…
2. **Pull Request revisado** por al menos un compañero antes de integrar a `main`.
3. **Respetar los contratos de la API** (ver `docs/`). Si necesitas cambiar un endpoint, avisa primero.
4. **Tipos en TypeScript:** cada módulo define sus tipos en `frontend/src/api`.
5. **Definición de "terminado":** funciona de punta a punta (UI → API → BD), respeta los roles,
   y otro compañero pudo probarlo con `docker compose up`.

---

## 🧩 Cómo agregar un módulo nuevo (patrón a seguir)

1. **Modelo:** crea `backend/app/models/tu_modulo.py` (mira `usuario.py` como ejemplo).
2. **Regístralo** en `app/__init__.py` (sección "Importar modelos").
3. **Endpoints:** crea `backend/app/api/tu_modulo.py` con un Blueprint.
4. **Regístralo** en `app/__init__.py` (sección "Registrar blueprints").
5. **Protege rutas** con `@token_required` o `@roles_required("admin")`.
6. **Frontend:** crea `frontend/src/modules/tu_modulo/` y agrega funciones tipadas en `api/client.ts`.

---

## 🔐 Sobre la autenticación

- Login devuelve un **JWT** que el frontend guarda y envía en cada petición.
- Rutas protegidas usan los decoradores `token_required` / `roles_required`.
- La **biometría** (huella/Face ID) usa WebAuthn: la huella nunca llega al servidor,
  solo se guarda una llave pública. Se conecta más adelante sobre esta misma base.
