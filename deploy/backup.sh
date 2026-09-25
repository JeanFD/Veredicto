#!/usr/bin/env bash
set -euo pipefail
ORIGEM=/opt/veredito/data/veredito.db
DESTINO=/home/jean/backups
mkdir -p "$DESTINO"
sqlite3 "$ORIGEM" ".backup '$DESTINO/veredito-$(date +%Y%m%d-%H%M).db'"
find "$DESTINO" -name 'veredito-*.db' -mtime +7 -delete