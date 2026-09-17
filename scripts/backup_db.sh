#!/bin/sh
set -e

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="grocery_store_${TIMESTAMP}.sql.gz"

echo "### Starting PostgreSQL backup to ${BACKUP_DIR}/${FILENAME}..."

docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U postgres grocery_store | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "### Backup created successfully: ${BACKUP_DIR}/${FILENAME}"

# Удаление бэкапов старше 14 дней для экономии дискового пространства
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
echo "### Cleaned up backups older than 14 days."
