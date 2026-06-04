#!/bin/bash
set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/qsp_backup_$TIMESTAMP.sql"

echo "💾 Starting backup..."

# Database backup
docker exec qsp-postgres pg_dump -U qsp_admin quantum_scalper_pro > "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"

# Keep only last 30 backups
ls -t $BACKUP_DIR/*.sql.gz | tail -n +31 | xargs -r rm

echo "✅ Backup complete: $BACKUP_FILE.gz"
