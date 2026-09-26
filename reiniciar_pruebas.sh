#!/usr/bin/env bash
# Reconstruye la base de datos de PRUEBAS desde cero: la borra, aplica las
# migraciones y carga el catalogo de demostracion.
#
#   ./reiniciar_pruebas.sh
#
# Pensado para cuando hay que empezar de limpio tras una prueba fallida.
# NUNCA toca la base de produccion: el nombre de la base de pruebas se
# comprueba antes de borrar nada.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RAIZ/backend"
PY="$BACKEND/venv/bin/python"

DB_TEST="${DB_TEST:-sevensdb_test}"
DB_PROD="${DB_PROD:-sevensdb}"

# --- Red de seguridad: no borrar la base equivocada ------------------------
if [ "$DB_TEST" = "$DB_PROD" ]; then
  echo "ABORTO: DB_TEST y DB_PROD apuntan a la misma base ($DB_PROD)." >&2
  echo "Si de verdad quieres borrar produccion, no uses este script." >&2
  exit 1
fi
if [ -z "$DB_TEST" ] || [ "$DB_TEST" = "postgres" ] || [ "$DB_TEST" = "template0" ] || [ "$DB_TEST" = "template1" ]; then
  echo "ABORTO: '$DB_TEST' no es un nombre de base valido para pruebas." >&2
  exit 1
fi

if [ -t 0 ]; then
  echo "Se va a BORRAR la base de pruebas '$DB_TEST' y a recrearla."
  echo "La base de produccion '$DB_PROD' NO se toca."
  read -r -p "Escribe SI para continuar: " resp
  [ "$resp" = "SI" ] || { echo "Cancelado."; exit 1; }
fi

PW="$(grep '^DB_PASSWORD=' "$BACKEND/.env" | cut -d= -f2-)"
HOST_="$(grep '^DB_HOST=' "$BACKEND/.env" | cut -d= -f2-)"
PUERTO="$(grep '^DB_PORT=' "$BACKEND/.env" | cut -d= -f2-)"
USER_="$(grep '^DB_USER=' "$BACKEND/.env" | cut -d= -f2-)"

psql_q() { PGPASSWORD="$PW" psql -h "$HOST_" -U "$USER_" -d postgres -tAc "$1" 2>/dev/null; }

echo "==> 1/4 Borrando '$DB_TEST'"
# Terminar conexiones abiertas antes de DROP DATABASE, que si no falla.
psql_q "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_TEST' AND pid <> pg_backend_pid();" >/dev/null
psql_q "DROP DATABASE IF EXISTS $DB_TEST;"
psql_q "CREATE DATABASE $DB_TEST WITH OWNER $USER_ ENCODING 'UTF8' TEMPLATE template0;"
echo "    creada"

echo "==> 2/4 Aplicando migraciones"
cd "$BACKEND"
DB_NAME="$DB_TEST" "$PY" manage.py migrate --noinput | tail -2

echo "==> 3/4 Cargando catalogo de demostracion"
DB_NAME="$DB_TEST" "$PY" manage.py seed_restaurant_data 2>&1 | tail -1
DB_NAME="$DB_TEST" "$PY" manage.py seed_carnes_pollos  2>&1 | tail -1
DB_NAME="$DB_TEST" "$PY" manage.py seed_beverages_data 2>&1 | tail -1

echo "==> 4/4 Mesas y usuario de pruebas"
DB_NAME="$DB_TEST" "$PY" - <<'PYCODE' 2>&1 | tail -3
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from sevens.models import VGMesa, VGUsuario, VGRol

for n in range(1, 13):
    VGMesa.objects.get_or_create(
        numero=n, defaults={"capacidad": 4, "ubicacion": "Salon", "estado": "libre"}
    )

rol, _ = VGRol.objects.get_or_create(nombre_role="Administrador")
u, _ = VGUsuario.objects.get_or_create(
    username="pruebas", defaults={"cedula": "00000001", "id_role": rol}
)
u.set_password("SevensPrueba2026")
u.is_staff = u.is_superuser = u.is_active = True
u.id_role = rol
u.first_name, u.last_name = "Usuario", "De Pruebas"
u.save()

print(f"    mesas: {VGMesa.objects.count()} | usuarios: {VGUsuario.objects.count()}")
print("    acceso: pruebas / SevensPrueba2026")
PYCODE

echo
echo "Listo. Base de pruebas reconstruida: $DB_TEST"
echo "Para trabajar contra ella:  ./entorno.sh prueba <comando>"
