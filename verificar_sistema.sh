#!/usr/bin/env bash
# Verifica que el sistema completo quedo arriba despues de un reinicio o
# corte de luz, sin tener que ir servicio por servicio.
#
#   ./verificar_sistema.sh
#
# Sale con 0 si todo esta bien y 1 si algo falla.

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IP="${1:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
fallos=0

ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
mal()  { printf '  \033[31mFALLA\033[0m %s\n' "$1"; fallos=$((fallos + 1)); }

echo "=== 1. Servicios ==="
for s in postgresql gunicorn nginx; do
  estado=$(systemctl is-active "$s" 2>&1)
  if [ "$estado" = "active" ]; then ok "$s activo"; else mal "$s -> $estado"; fi
done

echo
echo "=== 2. Arranque automatico ==="
for s in postgresql gunicorn nginx; do
  if systemctl is-enabled "$s" >/dev/null 2>&1; then
    ok "$s se inicia solo al prender"
  else
    mal "$s NO tiene arranque automatico (sudo systemctl enable $s)"
  fi
done

echo
echo "=== 3. Base de datos ==="
if command -v pg_isready >/dev/null 2>&1 && pg_isready -q 2>/dev/null; then
  ok "PostgreSQL acepta conexiones"
else
  mal "PostgreSQL no responde"
fi

echo
echo "=== 4. API (por la red, como la ve el telefono) ==="
if [ -n "$IP" ]; then
  codigo=$(curl -s -o /dev/null -w '%{http_code}' -m 8 "http://$IP/api/status/" 2>/dev/null)
  if [ "$codigo" = "200" ]; then
    ok "http://$IP/api/status/ responde 200"
  else
    mal "http://$IP/api/status/ -> ${codigo:-sin respuesta}"
  fi
else
  mal "no se pudo determinar la IP del servidor"
fi

echo
echo "=== 5. Frontend (archivos estaticos) ==="
if [ -f "$RAIZ/frontend/dist/index.html" ]; then
  ok "existe frontend/dist/index.html"
else
  mal "falta frontend/dist/ — hay que correr: cd frontend && npm run build"
fi

if [ -n "$IP" ]; then
  codigo=$(curl -s -o /dev/null -w '%{http_code}' -m 8 "http://$IP/" 2>/dev/null)
  if [ "$codigo" = "200" ]; then
    ok "http://$IP/ responde 200"
  else
    mal "http://$IP/ -> ${codigo:-sin respuesta}"
  fi
fi

echo
echo "=== 6. Permisos (Nginx corre como www-data) ==="
if [ -f "$RAIZ/frontend/dist/index.html" ]; then
  # -n = nunca pedir contrasena. Si no hay sudo sin interaccion, se cae al
  # chequeo de permisos en vez de dejar el script colgado esperando.
  if sudo -n -u www-data test -r "$RAIZ/frontend/dist/index.html" 2>/dev/null; then
    ok "www-data puede leer el frontend"
  else
    perms=$(stat -c '%a' "$RAIZ/frontend/dist/index.html" 2>/dev/null)
    # Los permisos que NO tienen bit de lectura para "otros" son el problema;
    # para el usuario que es dueno del archivo, 6xx/7xx son normales.
    otros="${perms: -1}"
    if [ "$otros" = "4" ] || [ "$otros" = "5" ] || [ "$otros" = "6" ] || [ "$otros" = "7" ]; then
      ok "frontend con permisos $perms (legible por otros)"
    else
      mal "www-data NO puede leer el frontend (permisos $perms)"
      echo "        solucion: sudo chmod -R a+rX $RAIZ/frontend/dist"
    fi
  fi
fi

echo
if [ "$fallos" -eq 0 ]; then
  printf '\033[32mTodo listo. La app esta en http://%s/\033[0m\n' "$IP"
  exit 0
else
  printf '\033[31m%d problema(s) encontrado(s). Revisa lo de arriba.\033[0m\n' "$fallos"
  exit 1
fi
