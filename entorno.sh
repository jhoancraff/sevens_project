#!/usr/bin/env bash
# Conmuta entre el entorno de PRODUCCION y el de PRUEBAS.
#
#   ./entorno.sh produccion <comando manage.py>...
#   ./entorno.sh prueba     <comando manage.py>...
#
# Ejemplos:
#   ./entorno.sh produccion manage.py crear_usuario --username ana --rol cajera
#   ./entorno.sh prueba     manage.py seed_restaurant_data
#   ./entorno.sh prueba     manage.py shell
#
# Sin argumentos, muestra el estado de los dos entornos.
#
# Como funciona: Django carga backend/.env con load_dotenv(), que NO pisa
# las variables que ya vienen del entorno. Por eso con exportar DB_NAME
# alcanza para apuntar a otra base sin tocar ningún archivo.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RAIZ/backend"
PY="$BACKEND/venv/bin/python"

DB_PROD="${DB_PROD:-sevensdb}"
DB_TEST="${DB_TEST:-sevensdb_test}"

# --- modo informacion ------------------------------------------------------
if [ $# -eq 0 ]; then
  echo "Entornos disponibles:"
  echo "  produccion -> $DB_PROD   (los datos reales del restaurante)"
  echo "  prueba     -> $DB_TEST   (datos de prueba, se puede romper sin riesgo)"
  echo
  echo "Uso:  ./entorno.sh <produccion|prueba> <comando manage.py>..."
  echo "Ej.:  ./entorno.sh prueba manage.py shell"
  exit 0
fi

ENTORNO="$1"; shift

case "$ENTORNO" in
  produccion|prod) DB="$DB_PROD" ;;
  prueba|test)     DB="$DB_TEST" ;;
  *)
    echo "Entorno desconocido: '$ENTORNO'" >&2
    echo "Usa 'produccion' o 'prueba'." >&2
    exit 2
    ;;
esac

# Aviso cuando se toca produccion con un comando que modifica datos, para
# que nadie ejecute un seed o un reset sin darse cuenta.
#
# Importante: si NO hay terminal (un pipe, un script, un cron), NO se salta
# la confirmacion en silencio: se aborta. Ejecutar a ciegas contra la base
# real es justo el error que este script existe para evitar.
case " $* " in
  *" seed_"*|*" reset_"*|*" flush"*|*" createmigrations "*)
    if [ "$DB" = "$DB_PROD" ]; then
      echo "ABORTO: eso modifica la base de PRODUCCION ($DB_PROD)." >&2
      echo "       Sin terminal no se puede confirmar, asi que no se ejecuta." >&2
      echo "       Para datos de prueba usa:  ./entorno.sh prueba ..." >&2
      echo "       Si de verdad es produccion, correlo a mano," >&2
      echo "       con SEVENS_SIN_AVISO=1 para saltar esta proteccion." >&2
      exit 1
    fi
    ;;
esac

# Las migraciones se piden aparte: no borran datos, pero tampoco conviene
# correrlas a ciegas sobre la base real.
if [ "$DB" = "$DB_PROD" ] && [ "${SEVENS_SIN_AVISO:-}" != "1" ] && [ -t 0 ]; then
  case " $* " in
    *" migrate"*)
      echo "Vas a aplicar migraciones en PRODUCCION ($DB_PROD)." >&2
      read -r -p "Escribe SI para continuar: " resp
      [ "$resp" = "SI" ] || { echo "Cancelado."; exit 1; }
      ;;
  esac
fi

cd "$BACKEND"
export DB_NAME="$DB"

# Si no se paso manage.py, se asume que es un comando de Django.
if [ "$1" = "manage.py" ]; then
  shift
fi
exec "$PY" manage.py "$@"
