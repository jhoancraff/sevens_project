# Proyecto Sevens

Sistema de gestion para restaurante: Django + PostgreSQL + React + Gunicorn + Nginx.

La app de Django (`backend/sevens/`) cubre menu con recetas, inventario y
costeo, mesas, pedidos, cocina en tiempo real, facturacion fiscal, compras,
devoluciones,conciliacion bancaria, cierre de caja y reportes de margen.

---

## 🗄️ 1. Base de Datos (PostgreSQL)

- **Motor:** PostgreSQL
- **Base de Datos:** `sevensdb`
- **Usuario:** `sevens`
- **Estado:** Activo vía systemd (`sudo systemctl status postgresql`)

Las tablas usan el prefijo `vg_` (`vg_usuarios`, `vg_pedidos`, ...) porque los
50 modelos declaran `db_table` explicito. El label de la app de Django es
`sevens` (antes `varagrill`).

```bash
psql -h localhost -U sevens -d sevensdb
```

---

## 🔒 2. Seguridad y Variables de Entorno (Git Seguro)

- Ninguna contraseña, llave secreta o URL sensible está en el repositorio Git.
- Todos los archivos `.env` están agregados al `.gitignore`.
- Se incluyen archivos `.env.example` como plantilla.


### Configuración Backend (`backend/.env`):
```env
DEBUG=True
SECRET_KEY=clave-secreta-local
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DB_NAME=sevensdb
DB_USER=sevens
DB_PASSWORD=tu_clave_aqui
DB_HOST=127.0.0.1
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost
```

### Configuración Frontend (`frontend/.env`):
```env
VITE_API_URL=/api
```

---

## 🦄 3. Backend (Django + Gunicorn)

- **Servicio Systemd:** `gunicorn.service` (Activo y corriendo en segundo plano)
- **Panel de administración:** `/admin/`
- **App de restaurante:** `backend/sevens/` — 50 modelos, 63 migraciones, 83 endpoints
- **Autenticación:** sesión con cookies de Django (no JWT). El login acepta
  username o email, sin distinguir mayúsculas.

### Endpoints principales

| Ruta | Contenido |
|---|---|
| `/api/auth/login/` | Iniciar sesión |
| `/api/auth/logout/` | Cerrar sesión |
| `/api/auth/status/` | Usuario de la sesión actual |
| `/api/pedidos/` | Crear pedido |
| `/api/pedidos/cocina/` | Comandas activas de cocina |
| `/api/pedidos/cobro/` | Cobrar pedidos |
| `/api/mesas/` | Mesas del restaurante |
| `/api/productos/` | Menú disponible |
| `/api/facturas/`, `/api/notas-entrega/` | Facturación |
| `/api/admin/...` | Administración, compras, gastos, reportes |

La lista completa está en `backend/sevens/urls.py` y en `frontend/README.md`.

### Pruebas

```bash
cd backend
./venv/bin/python manage.py test sevens
```

La suite cubre login por email/mayúsculas, catálogo, usuarios, cocina, cobro
con descuento de inventario e importación de ingredientes desde Excel.

### Dar de alta al personal

Cada persona necesita un usuario con su rol. Desde la terminal:

```bash
cd /home/sevens/sevens_project/backend

# Ver los roles disponibles
./venv/bin/python manage.py crear_usuario --listar-roles

# Crear un mesero
./venv/bin/python manage.py crear_usuario \
    --username jhoan --password 'ClaveSegura123' \
    --cedula 12345678 --rol mesero \
    --nombre Jhoan --apellido Perez

# Cambiar solo la contraseña de alguien que ya existe
./venv/bin/python manage.py crear_usuario --username jhoan --password 'NuevaClave456'
```

El rol se puede escribir en cualquier caso (`mesero`, `MESERO`) y la cédula es
obligatoria y única. También se puede hacer desde el panel de `/admin/`, en
*Usuarios → Agregar*.

### Comandos útiles del servicio Backend:
```bash
sudo systemctl status gunicorn   # Ver estado del servicio
sudo systemctl restart gunicorn  # Reiniciar tras cambios en código Python
sudo journalctl -u gunicorn -f   # Ver logs en tiempo real
```

### Entorno virtual manual:
```bash
cd /home/sevens/sevens_project/backend
source venv/bin/activate
python manage.py migrate
```

---

## 🌐 4. Servidor Web Nginx (Proxy Inverso Unificado)

Nginx (`nginx.conf`) unifica todo el ecosistema en el puerto `80`:
- `/` -> Sirve la aplicación React SPA (`frontend/dist/`).
- `/api/` -> Encamina automáticamente a Gunicorn (`http://127.0.0.1:8000/api/`).
- `/admin/` -> Encamina automáticamente al panel de Django (`http://127.0.0.1:8000/admin/`).
- `/static/` -> Sirve directamente los archivos estáticos de Django (`backend/staticfiles/`).

### Comandos Nginx:
```bash
sudo systemctl status nginx
sudo systemctl reload nginx
```

---

## ⚛️ 5. Frontend (React + Vite)

### Compilación y publicación en Nginx:
```bash
cd /home/sevens/sevens_project/frontend
npm run build
```
Los archivos en `dist/` se sirven inmediatamente a través de Nginx en `http://localhost/`.

### Servidor de desarrollo con Hot Reload:
```bash
cd /home/sevens/sevens_project/frontend
npm run dev -- --host
```

---

## 🌿 6. Control de Versiones (Git)

El repositorio Git está inicializado en `/home/sevens/sevens_project/`.
Para revisar el estado de los archivos:
```bash
git status
```
Los archivos `.env`, directorios `venv/` y `node_modules/` están estrictamente ignorados y protegidos contra filtraciones accidentales.
