# Proyecto Sevens: Django + PostgreSQL + React + Gunicorn

Este proyecto está configurado con una arquitectura moderna desacoplada en Frontend y Backend, con base de datos PostgreSQL y despliegue WSGI mediante Gunicorn.

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
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### Configuración Frontend (`frontend/.env`):
```env
VITE_API_URL=http://localhost:8000/api
```

---

## 🦄 3. Backend (Django + Gunicorn)

### Activar entorno virtual:
```bash
cd /home/sevens/sevens_project/backend
source venv/bin/activate
```

### Ejecutar migraciones:
```bash
python manage.py migrate
```

### Iniciar servidor de desarrollo Django:
```bash
python manage.py runserver 0.0.0.0:8000
```

### Iniciar con Gunicorn (Producción / WSGI):
Puedes usar el script incluido:
```bash
./start_gunicorn.sh
```
O directamente con el archivo de configuración:
```bash
venv/bin/gunicorn -c gunicorn.conf.py core.wsgi:application
```

### Servicio Systemd (Opcional para segundo plano):
El archivo `gunicorn.service` está listo en la raíz del proyecto. Para instalarlo:
```bash
sudo cp /home/sevens/sevens_project/gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
```

---

## ⚛️ 4. Frontend (React + Vite)

### Iniciar servidor de desarrollo React:
```bash
cd /home/sevens/sevens_project/frontend
npm run dev -- --host
```

### Compilar para producción:
```bash
npm run build
```

---

## 🌿 5. Git

El repositorio Git está inicializado en `/home/sevens/sevens_project/`.
Para revisar el estado de los archivos ignorados:
```bash
git status
```
Comprobarás que `.env`, `venv/` y `node_modules/` nunca son rastreados por Git.
