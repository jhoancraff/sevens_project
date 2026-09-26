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

---

## 🧪 5. Entornos: producción y pruebas

Hay **dos bases de datos separadas** en el mismo PostgreSQL. Los datos de
pruebas se pueden romper, borrar o llenar de basura sin tocar los reales.

| Entorno | Base | Contenido |
|---|---|---|
| **produccion** | `sevensdb` | La que usa la app en `http://192.168.68.100/` |
| **prueba** | `sevensdb_test` | Solo para experimentar |

Las dos tienen las **mismas 63 migraciones**, así que el esquema siempre coincide.

### Cambiar de entorno

```bash
cd /home/sevens/sevens_project

./entorno.sh                      # muestra los dos entornos
./entorno.sh produccion <comando> # contra los datos reales
./entorno.sh prueba     <comando> # contra los de prueba
```

Ejemplos:

```bash
./entorno.sh prueba manage.py shell
./entorno.sh produccion manage.py crear_usuario --username ana --rol cajera
```

Funciona porque Django carga `backend/.env` con `load_dotenv()`, que **no** pisa
las variables que ya vienen del entorno: con exportar `DB_NAME` basta para
apuntar a otra base, sin tocar ningún archivo.

> Si intentas correr un `seed_*`, `reset_*` o `flush` contra **producción**,
> el script se detiene y avisa. Sin terminal (en un pipe o un script) aborta
> en vez de dejar pasar el cambio en silencio. Para pasarlo a propósito:
> `SEVENS_SIN_AVISO=1 ./entorno.sh produccion manage.py ...`

### Empezar de cero en pruebas

Después de una prueba fallida, para volver a datos limpios:

```bash
./reiniciar_pruebas.sh
```

Borra `sevensdb_test`, aplica las migraciones y carga el catálogo de
demostración (27 productos, 53 ingredientes, 16 preparaciones, 12 mesas).
Tiene dos redes de seguridad: pide confirmación si hay terminal, y se aborta
si `DB_TEST` coincide con la base de producción o tiene un nombre inválido.

### Entrar al entorno de pruebas desde el navegador

Por defecto la app en `:80` apunta a **producción**. Para probar la interfaz
sin tocar los datos reales, levanta una segunda instancia apuntando a la base
de pruebas:

```bash
cd /home/sevens/sevens_project/backend
DB_NAME=sevensdb_test ./venv/bin/gunicorn -c gunicorn.conf.py core.wsgi:application \
    --bind 127.0.0.1:8001 --workers 1
```

Y en otra terminal, sírvela con un servidor simple:

```bash
cd /home/sevens/sevens_project/frontend
npx vite preview --port 3000
```

Ahí entra con el usuario de pruebas:

```
pruebas / SevensPrueba2026
```

Cierra ambas ventanas (`Ctrl+C`) para volver a producción.

### Comandos útiles del servicio Backend:
```bash
sudo systemctl status gunicorn   # Ver estado del servicio
sudo systemctl restart gunicorn  # Reiniciar tras cambios en código Python
sudo journalctl -u gunicorn -f   # Ver logs en tiempo real
```

---

## 💡 4. Arranque automático

Los tres servicios están habilitados (`systemctl enable`), así que **levantan
solos al prender el servidor**: no hay que escribir ningún comando.

| Servicio | Qué hace | Unit |
|---|---|---|
| `postgresql` | Base de datos | del sistema |
| `gunicorn` | API Django | `gunicorn.service` |
| `nginx` | Sirve la SPA y hace proxy de `/api/` | del sistema |

El frontend **no necesita servicio propio**: React se compila a archivos
estáticos en `frontend/dist/` y es Nginx quien los sirve.

### Orden de arranque

`gunicorn.service` define las dependencias para que no haya errores al prender:

1. Espera a `network-online.target` — con `network.target` a secas, el servicio
   puede arrancar antes de que la red tenga IP (típico con DHCP).
2. `Requires=postgresql.service` — la base tiene que estar escuchando antes de
   que Django abra conexiones.
3. `Before=nginx.service` — Gunicorn primero, Nginx después, para que nadie
   reciba un 502 al entrar apenas se prende. Si Gunicorn fallara, Nginx igual
   levanta y sigue sirviendo el frontend.

### Verificar que todo quedó arriba

```bash
cd /home/sevens/sevens_project
./verificar_sistema.sh
```

Revisa servicios, arranque automático, base de datos, API, frontend y
permisos de lectura para Nginx. Imprime `OK` o `FALLA` en cada punto y
avisa qué hacer si algo falla.

### Después de un corte de luz

No hay que hacer nada: el sistema se levanta solo. Para confirmarlo, abre
`http://<IP-del-servidor>/` desde cualquier teléfono de la red, o corre el
script de arriba.

### Si toca instalarlo de nuevo

```bash
sudo cp gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now postgresql gunicorn nginx
sudo systemctl is-enabled gunicorn nginx postgresql   # deben decir: enabled
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
