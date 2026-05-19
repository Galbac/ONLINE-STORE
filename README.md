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

API будет доступен на `http://localhost:8000`.

Проверка:

```bash
curl http://localhost:8000/health
```

Остановка dev/prod:

```bash
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.prod.yml down
```

## Admin Products

Ручные изменения остатков через `PATCH /api/admin/products/{product_id}/stock` могут быть перезаписаны следующей синхронизацией с 1С.
