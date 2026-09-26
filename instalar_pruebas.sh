#!/usr/bin/env bash
# Instala el entorno de PRUEBAS completo, paso a paso y verificando cada uno.
# Si algo falla, dice exactamente que fallo y como seguir.
#
#   sudo ./instalar_pruebas.sh

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUERTO=8080

paso() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[32mOK\033[0m  %s\n' "$1"; }
mal()  { printf '    \033[31mFALLA\033[0m  %s\n' "$1"; }
nota() { printf '    --   %s\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Este script necesita root. Correrlo con:  sudo $0"
  exit 1
fi

paso "1. Copiando el unit de gunicorn de pruebas"
cp "$RAIZ/gunicorn-pruebas.service" /etc/systemd/system/
ok "gunicorn-pruebas.service instalado"

# El unit viejo (sevens-pruebas.service) se queda fuera a proposito: era un
# oneshot que solo existia para ordenar el arranque y terminaba en un ciclo
# que hacia que systemd respondiera 'Method call timed out'.
rm -f /etc/systemd/system/sevens-pruebas.service
systemctl daemon-reload
ok "systemd recarga la configuracion"

paso "2. Arrancando el backend de pruebas (puerto 8001)"
systemctl enable gunicorn-pruebas >/dev/null 2>&1
if systemctl restart gunicorn-pruebas; then
  sleep 6
  if systemctl is-active --quiet gunicorn-pruebas; then
    ok "gunicorn-pruebas activo"
  else
    mal "arranco pero se cae. Logs:  journalctl -u gunicorn-pruebas -n 30 --no-pager"
    exit 1
  fi
else
  mal "no pudo arrancar. Logs:  journalctl -u gunicorn-pruebas -n 30 --no-pager"
  exit 1
fi

paso "3. Verificando que responde y usa la base de pruebas"
sleep 2
resp=$(curl -s -m 8 http://127.0.0.1:8001/api/status/ 2>/dev/null)
if echo "$resp" | grep -q 'sevensdb_test'; then
  ok "el backend responde y apunta a sevensdb_test"
else
  mal "el backend no responde o no usa la base de pruebas"
  echo "        respuesta: ${resp:-sin respuesta}"
  exit 1
fi

paso "4. Instalando la configuracion de nginx (puerto $PUERTO)"
cp "$RAIZ/nginx.conf" /etc/nginx/sites-available/sevens_project
# sites-enabled es un symlink al available, asi que basta con recrearlo.
ln -sf /etc/nginx/sites-available/sevens_project /etc/nginx/sites-enabled/sevens_project

# nginx -t solo avisa "server directive is not allowed here" cuando hay una
# llave descolocada, y el numero de linea que senala no siempre es donde esta
# el problema. Este chequeo previo encuentra el server mal anidado ANTES de
# instalar nada, y dice en que linea.
if ! python3 - "$RAIZ/nginx.conf" <<'PYCHECK' 2>/tmp/sevens_ng_err
import re, sys

nivel = 0
problemas = []
for i, linea in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    s = linea.strip()
    if not s or s.startswith("#"):
        continue
    if re.match(r"^server\s*\{", s) and nivel != 0:
        problemas.append(f"linea {i}: 'server' anidado (nivel {nivel}, deberia ser 0)")
    if s.endswith("{"):
        nivel += 1
    elif s == "}":
        nivel -= 1
        if nivel < 0:
            problemas.append(f"linea {i}: llave de cierre sobrante")
if nivel != 0:
    problemas.append(f"faltan {nivel} llave(s) de cierre al final")

for p in problemas:
    print(p, file=sys.stderr)
sys.exit(1 if problemas else 0)
PYCHECK
then
  mal "el nginx.conf del proyecto tiene llaves descolocadas:"
  sed 's/^/        /' /tmp/sevens_ng_err
  exit 1
fi
ok "llaves correctas: los 2 server estan al mismo nivel"

if nginx -t 2>/dev/null; then
  ok "configuracion de nginx valida"
else
  mal "nginx rechazo la configuracion:"
  nginx -t 2>&1 | sed 's/^/        /'
  exit 1
fi
systemctl reload nginx
ok "nginx recargado"

paso "5. Abriendo el puerto $PUERTO en el firewall"
if command -v ufw >/dev/null 2>&1 && systemctl is-active --quiet ufw; then
  ufw allow "$PUERTO/tcp" >/dev/null 2>&1
  ok "puerto $PUERTO permitido"
else
  nota "ufw no activo, nada que abrir"
fi

paso "6. Comprobacion final desde la red"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$IP" ]; then
  for url in "http://$IP/api/status/" "http://$IP:$PUERTO/api/status/"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$url" 2>/dev/null)
    if [ "$code" = "200" ]; then
      ok "$url -> 200"
    else
      mal "$url -> ${code:-sin respuesta}"
    fi
  done
fi

echo
echo "Listo. Desde el telefono:"
echo "  Produccion:  http://$IP/"
echo "  Pruebas:     http://$IP:$PUERTO/   (pruebas / SevensPrueba2026)"
