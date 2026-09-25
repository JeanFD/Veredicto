#!/usr/bin/env bash
set -euo pipefail
ORIGEM=/opt/veredicto/data/veredicto.db
DESTINO=/home/jean/backups
mkdir -p "$DESTINO"
sqlite3 "$ORIGEM" ".backup '$DESTINO/veredicto-$(date +%Y%m%d-%H%M).db'"
find "$DESTINO" -name 'veredicto-*.db' -mtime +7 -delete