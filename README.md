# Grocery Store

## Docker

Dev:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Prod:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

### Настройка домена и SSL (Nginx + Let's Encrypt / Certbot)

1. В файле `.env` укажите ваш домен и почту:
```env
DOMAIN_NAME=yourdomain.com
CERTBOT_EMAIL=admin@yourdomain.com
```

2. Для первичного получения SSL-сертификата выполните скрипт:
```bash
./scripts/init_ssl.sh
```
Скрипт создаст временный самоподписанный сертификат для первого старта Nginx, запросит боевой сертификат Let's Encrypt через ACME-challenge и перезагрузит Nginx с валидным SSL.

3. **Автообновление**: сервис `certbot` в `docker-compose.prod.yml` автоматически каждые 12 часов проверяет срок действия сертификатов и обновляет их без простоя.

### Автоматические бэкапы базы данных

В `docker-compose.prod.yml` встроен автономный сервис `db_backup`:
* Создает сжатый дамп (`.sql.gz`) каждые **6 часов** (настраивается через `BACKUP_INTERVAL_HOURS`).
* Сохраняет файлы в директорию `./backups/postgres` на сервере.
* Автоматически удаляет бэкапы старше **14 дней** (настраивается через `BACKUP_KEEP_DAYS`).

Ручное создание бэкапа в любой момент:
```bash
./scripts/backup_db.sh
```

API и сайт будут доступны по адресу: `https://yourdomain.com`.

Проверка:

```bash
curl https://yourdomain.com/health
```

Остановка dev/prod:

```bash
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.prod.yml down
```

## Admin Products

Ручные изменения остатков через `PATCH /api/admin/products/{product_id}/stock` могут быть перезаписаны следующей синхронизацией с 1С.
