#!/usr/bin/env bash
# Despliega los cambios que trajiste de git: descarga, compila el frontend,
# reinicia el backend y verifica que todo quedo bien.
#
#   ./desplegar.sh              # descarga y compila
#   ./desplegar.sh --sin-pull   # solo recompila, sin descargar de git
#
# Por que esto hace falta: frontend/dist/ esta en el .gitignore, asi que un
# git pull actualiza frontend/src/ pero NO el build que sirve nginx. Sin
# recompilar, el navegador sigue viendo la version anterior.

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$RAIZ/frontend"
BACKEND="$RAIZ/backend"
PY="$BACKEND/venv/bin/python"

paso() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[32mOK\033[0m    %s\n' "$1"; }
mal()  { printf '    \033[31mFALLA\033[0m  %s\n' "$1"; }
nota() { printf '    --    %s\n' "$1"; }

SIN_PULL=0
[ "${1:-}" = "--sin-pull" ] && SIN_PULL=1

paso "1. Cambios de git"
ANTES=$(git rev-parse --short HEAD 2>/dev/null)
if [ "$SIN_PULL" -eq 0 ]; then
  git pull --ff-only 2>&1 | sed 's/^/    /'
  ok "descargado"
else
  ok "omitido (--sin-pull)"
fi
AHORA=$(git rev-parse --short HEAD 2>/dev/null)
if [ "$ANTES" = "$AHORA" ]; then
  nota "sin commits nuevos (ya estabas al dia)"
else
  ok "commit $ANTES -> $AHORA"
  git --no-pager log --oneline "$ANTES..$AHORA" | head -10 | sed 's/^/       /'
fi

paso "2. Estado del repositorio"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  mal "hay cambios sin commitear:"
  git status --short | head -10 | sed 's/^/          /'
  echo "    Commitea o descartalos antes de desplegar."
  exit 1
fi
ok "arbol limpio"

paso "3. Migraciones pendientes"
cd "$BACKEND"
if out=$("$PY" manage.py makemigrations --check --dry-run 2>&1); then
  ok "no hay cambios de modelo pendientes"
else
  mal "el codigo nuevo cambio los modelos y necesita migracion:"
  echo "$out" | tail -5 | sed 's/^/          /'
  echo "    Crear con:  ./entorno.sh produccion manage.py makemigrations"
  exit 1
fi

paso "4. Compilando el frontend"
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  nota "node_modules no existe, instalando dependencias (tarda un poco)"
  npm ci --no-audit --no-fund 2>&1 | tail -3 | sed 's/^/    /'
fi
BUNDLE_ANTES=$(ls dist/assets/index-*.js 2>/dev/null | head -1)
if npm run build 2>&1 | tail -6 | sed 's/^/    /'; then
  BUNDLE_DESP=$(ls dist/assets/index-*.js 2>/dev/null | head -1)
  ok "build correcto"
  if [ "$BUNDLE_ANTES" != "$BUNDLE_DESP" ]; then
    nota "bundle nuevo: $(basename "${BUNDLE_DESP:-?}")"
  else
    nota "el bundle no cambio de nombre (mismo contenido)"
  fi
else
  mal "el build fallo (arriba el error)"
  exit 1
fi

# Nginx corre como www-data: si los permisos no quedan abiertos, el sitio
# devuelve 403 aunque el build este bien.
find dist -type d -exec chmod 755 {} \;
find dist -type f -exec chmod 644 {} \;
ok "permisos ajustados para nginx"

paso "5. Chequeo del backend"
cd "$BACKEND"
if "$PY" manage.py check 2>&1 | tail -2 | sed 's/^/    /'; then
  ok "backend sin errores"
else
  mal "el backend tiene errores"
  exit 1
fi

paso "6. Reiniciando servicios"
if [ "$(id -u)" -eq 0 ]; then
  systemctl restart gunicorn 2>/dev/null && ok "gunicorn reiniciado" || mal "no se pudo reiniciar gunicorn"
  if systemctl is-active --quiet gunicorn-pruebas; then
    systemctl restart gunicorn-pruebas 2>/dev/null && ok "gunicorn-pruebas reiniciado" || nota "no se pudo reiniciar el de pruebas"
  fi
  nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null && ok "nginx recargado" || nota "nginx no se recargo (config sin cambios)"
else
  mal "hace falta root para reiniciar los servicios"
  cat <<'CMDS'
        Ejecuta esto despues:

          sudo systemctl restart gunicorn
          sudo systemctl restart gunicorn-pruebas   # si usas el entorno de pruebas
          sudo systemctl reload nginx
CMDS
fi

paso "7. Verificacion por la red"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
sleep 3
for url in "http://$IP/" "http://$IP:8080/"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$url" 2>/dev/null)
  if [ "$code" = "200" ]; then ok "$url -> 200"; else nota "$url -> ${code:-sin respuesta}"; fi
done

echo
printf '  \033[1mEn el celular:\033[0m si no ves el cambio, borra la app de la\n'
printf '  pantalla de inicio y vuelve a abrirla. El service worker guarda el\n'
printf '  bundle viejo en cache aunque el servidor ya tenga el nuevo.\n'