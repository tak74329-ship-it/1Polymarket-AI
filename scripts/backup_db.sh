#!/usr/bin/env bash
# Backup PostgreSQL database into backups/YYYYMMDD_HHMMSS.sql
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"

# Load DB config from .env if available
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DB:-polymarket}"
PG_USER="${POSTGRES_USER:-admin}"
PG_PASSWORD="${POSTGRES_PASSWORD:-admin123}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="$BACKUP_DIR/${PG_DB}_${TIMESTAMP}.sql"

export PGPASSWORD="$PG_PASSWORD"

echo "📦 Backing up '$PG_DB' to $OUTPUT_FILE ..."
pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    --format=plain \
    --no-owner \
    --no-acl \
    --file="$OUTPUT_FILE"

unset PGPASSWORD

# Compress
gzip -f "$OUTPUT_FILE"
COMPRESSED="${OUTPUT_FILE}.gz"

echo "✅ Backup complete: $COMPRESSED"
echo "   Size: $(du -h "$COMPRESSED" | cut -f1)"
