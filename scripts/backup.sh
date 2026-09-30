#!/bin/bash
set -euo pipefail

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/qsp_backup_$TIMESTAMP.sql"

echo "💾 Starting backup..."

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Database backup
docker compose exec -T postgres pg_dump -U qsp_admin quantum_scalper_pro > "$BACKUP_FILE"
test -s "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"
gzip -t "$BACKUP_FILE.gz"

# Keep only last 30 backups
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'qsp_backup_*.sql.gz' -printf '%T@ %p\n' \
    | sort -rn | awk 'NR > 30 {sub(/^[^ ]+ /, ""); print}' | xargs -r -- rm --

echo "✅ Backup complete: $BACKUP_FILE.gz"
