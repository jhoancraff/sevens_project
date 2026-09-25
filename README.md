# Proyecto Sevens: Django + PostgreSQL + React + Gunicorn + Nginx

Este proyecto cuenta con una arquitectura fullstack completa y desacoplada con base de datos PostgreSQL, backend en Django expuesto mediante Gunicorn (gestionado por systemd), frontend en React (Vite) y servidor web Nginx como proxy inverso unificado.

---

## 🗄️ 1. Base de Datos (PostgreSQL)

- **Motor:** PostgreSQL 18
- **Base de Datos:** `sevensdb`
- **Usuario:** `sevens`
- **Host:** `localhost` (puerto `5432`)
- **Estado del servicio:** Activo vía systemd (`sudo systemctl status postgresql`)

Para conectarte directamente por consola:
```bash
psql -h localhost -U sevens -d sevensdb
```

---

## 🔒 2. Seguridad y Variables de Entorno (Git Seguro)

Siguiendo las mejores prácticas de seguridad:
- Ninguna contraseña, llave secreta o URL sensible está en el repositorio Git.
- Todos los archivos `.env` están agregados al `.gitignore`.
- Se incluyen archivos `.env.example` como plantilla para despliegues o nuevos desarrolladores.

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
- **Superusuario Django:** `sevens` (acceso al panel de administración en `/admin/`)
- **API REST Framework:** Endpoints disponibles en `/api/` (ej: `/api/items/` y `/api/status/`)

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
