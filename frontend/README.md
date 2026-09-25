# Frontend React — Proyecto Sevens

Este directorio esta **vacio a proposito**: es el destino del frontend React que
vive en el otro servidor. Copia aqui el contenido de tu proyecto React.

## Como copiarlo desde el otro servidor

```bash
# En el servidor donde esta tu React:
tar czf frontend-sevens.tar.gz --exclude=node_modules --exclude=dist --exclude=.git .

# Traerlo a este servidor:
scp usuario@servidor-frontend:/ruta/frontend-sevens.tar.gz /tmp/
tar xzf /tmp/frontend-sevens.tar.gz -C /home/sevens/sevens_project/frontend
```

Excluye `node_modules`, `dist` y `.git`: aqui se reinstalan y se compilan.

## Build para produccion (Nginx)

```bash
cd /home/sevens/sevens_project/frontend
npm install
npm run build      # genera dist/
```

Nginx ya esta configurado para servir `frontend/dist/` y hacer proxy de
`/api/` hacia Gunicorn (ver `../nginx.conf`). No hay que cambiar nada mas.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Desarrollo con hot reload

```bash
npm run dev -- --host
```

En dev el frontend corre en `:5173` y no pasa por Nginx, asi que en
`frontend/.env` pon la URL absoluta del backend:

```env
VITE_API_URL=http://<IP-DE-ESTE-SERVIDOR>:8000/api
```

Y agrega ese origen a `CORS_ALLOWED_ORIGINS` en `backend/.env`.

## Contrato de API

El backend expone todo bajo `/api/`. Autenticacion por **sesion con cookies**
(`login()` de Django), no JWT. Endpoints que exige la suite de tests:

| Endpoint | Metodo | Descripcion |
|---|---|---|
| `/api/auth/login/` | POST | Login (acepta username o email, case-insensitive) |
| `/api/auth/logout/` | POST | Logout |
| `/api/auth/status/` | GET | Usuario de la sesion actual |
| `/api/pedidos/` | POST | Crear pedido |
| `/api/pedidos/<id>/estado/` | POST | Cambiar estado del pedido |
| `/api/pedidos/cobro/` | POST | Cobrar pedidos |
| `/api/pedidos/cocina/` | GET | Comandas activas de cocina |
| `/api/facturas/<id>/abonos/` | POST | Abonos de factura |
| `/api/admin/catalogo/` | GET | Catalogo de productos |
| `/api/admin/usuarios/` | GET | Usuarios y roles |
| `/api/admin/gastos/` | GET/POST | Gastos |
| `/api/admin/compras/borrador/agregar/` | POST | Lineas del borrador de compra |
| `/api/admin/reportes/estado-resultados/` | GET | Reporte de resultados |

> **Nota**: el backend tiene ~78 vistas implementadas, pero `sevens/urls.py`
> aun no existe, asi que hoy solo responde lo que este enrutado. Eso se esta
> corrigiendo — si tu React llama endpoints que no aparecen aqui, es porque
> falta enrutarlos.

## WebSockets (tiempo real de cocina)

`ws://<host>/ws/pedidos/` — requiere `credentials` en el cliente WebSocket.
Aun no esta habilitado en produccion (falta `CHANNEL_LAYERS` y servir ASGI).

## Roles

Los permisos se derivan del rol del usuario: Administrador, Analista, Mesero,
Cocinero, Cajera, Contador. Mas `is_staff`/`is_superuser` para el dueno.
