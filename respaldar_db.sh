#!/usr/bin/env bash
set -euo pipefail

DB="${1:-sevensdb}"
DIR=/home/sevens/respaldos
ARCH="$DIR/${DB}_$(date +%F_%H%M).dump"

mkdir -p "$DIR"
sudo -u postgres pg_dump -Fc "$DB" > "$ARCH"     # formato comprimido, se restaura con pg_restore
rclone copy "$ARCH" r2:seven-backup/db/       # sube a R2
find "$DIR" -name '*.dump' -mtime +7 -delete      # en el servidor solo guarda 7 días
echo "Respaldo listo: $(basename "$ARCH")"