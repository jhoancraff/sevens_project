# Sevens frontend

Frontend React (Vite) del sistema de restaurante. Se comunica con el backend
Django por rutas relativas `/api/...`, que Nginx hace de proxy hacia Gunicorn.

## Rutas de este servidor

| Que | Donde |
|---|---|
| Frontend | `/home/sevens/sevens_project/frontend` |
| Build | `/home/sevens/sevens_project/frontend/dist` |
| Backend | `/home/sevens/sevens_project/backend` |
| Config Nginx | `/home/sevens/sevens_project/nginx.conf` |

> Este README antes describia `/home/mariadb/app/frontend` y
> `/var/www/sevensadmin/dist` (servidor anterior). Las rutas de arriba son
> las de aqui; el bloque de nginx de abajo ya esta actualizado.

## Compilar

```bash
cd /home/sevens/sevens_project/frontend
npm install
npm run build
```

El build escribe en `dist/` y Nginx lo sirve de inmediato. Si Nginx esta
activo, despues del build basta recargar:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Desarrollo con hot reload

```bash
npm run dev
```

Levanta en `0.0.0.0:3000`. El proxy de `vite.config.js` manda `/api`,
`/admin`, `/static` y `/ws` a `http://127.0.0.1:8000` (Gunicorn).

Para que el backend acepte el origen del dev server, agregalo a
`CORS_ALLOWED_ORIGINS` en `backend/.env`:

```
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

## Pruebas

```bash
npm test
```

## Nginx para servir el frontend

La configuracion de este servidor esta en `/home/sevens/sevens_project/nginx.conf`
y se instala copiandola a un sitio habilitado:

```bash
sudo cp /home/sevens/sevens_project/nginx.conf /etc/nginx/sites-available/sevens
sudo ln -sf /etc/nginx/sites-available/sevens /etc/nginx/sites-enabled/sevens
sudo nginx -t && sudo systemctl reload nginx
```

### Bloques que importan

- `client_max_body_size 20m` — sin esto, la subida del Excel de ingredientes
  a `/api/admin/catalogo/importar/` se corta (el default de Nginx es 1m).
- `location /assets/` — cache larga para los JS/CSS con hash del build.
- `location = /sw.js` — **sin** cache, para que la PWA detecte actualizaciones.
- `location /api/` y `/admin/` — proxy a Gunicorn en `127.0.0.1:8000`.

### Diagnostico

Si `/` responde pero `/api/` da `404`, Nginx esta cargando otro sitio:

```bash
sudo nginx -T | grep -n "server_name\|location /api/"
```

## PWA

`vite-plugin-pwa` genera `sw.js`, `workbox-*.js` y `manifest.webmanifest` en
`dist/`. El service worker usa `NetworkFirst` para navegaciones, asi que la app
sigue funcionando sin conexion y se actualiza sola.

## API

La lista completa de endpoints esta en `backend/sevens/urls.py` (83 rutas).
Todos los paths que este frontend llama existen en el backend: se verifico
resolviendo cada llamada contra el URLconf de Django.

