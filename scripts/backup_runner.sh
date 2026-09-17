#!/bin/sh
set -e

BACKUP_DIR="/backups"
mkdir -p "$BACKUP_DIR"

INTERVAL="${BACKUP_INTERVAL_HOURS:-6}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

echo "### PostgreSQL Automated Backup Service started."
echo "### Backup frequency: every ${INTERVAL} hours. Retaining backups for: ${KEEP_DAYS} days."

# Бесконечный цикл выполнения бэкапов
while true; do
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    FILENAME="db_backup_${TIMESTAMP}.sql.gz"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating database backup..."
    
    # Создание сжатого дампа базы данных
    if pg_dump -h postgres -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "${BACKUP_DIR}/${FILENAME}.tmp"; then
        mv "${BACKUP_DIR}/${FILENAME}.tmp" "${BACKUP_DIR}/${FILENAME}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup successfully created: ${FILENAME} (Size: $(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1))"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Backup failed!"
        rm -f "${BACKUP_DIR}/${FILENAME}.tmp"
    fi

    # Ротация: удаление бэкапов старше указанного количества дней
    find "$BACKUP_DIR" -type f -name "db_backup_*.sql.gz" -mtime "+${KEEP_DAYS}" -delete 2>/dev/null || true

    # Ожидание следующего цикла
    sleep "${INTERVAL}h" &
    wait $!
done
