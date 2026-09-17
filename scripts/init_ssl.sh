#!/bin/sh
set -e

if [ -z "$DOMAIN_NAME" ] || [ -z "$CERTBOT_EMAIL" ]; then
    echo "ERROR: DOMAIN_NAME and CERTBOT_EMAIL must be set in your .env file!"
    exit 1
fi

echo "### Starting SSL certificate check for domain: $DOMAIN_NAME ($CERTBOT_EMAIL) ..."

CERT_DIR="/etc/letsencrypt/live/$DOMAIN_NAME"

if [ ! -d "$CERT_DIR" ]; then
    echo "### Certificate not found. Creating temporary dummy certificate for Nginx startup..."
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "$CERT_DIR/privkey.pem" \
        -out "$CERT_DIR/fullchain.pem" \
        -subj "/CN=localhost"
    DUMMY=1
else
    echo "### Existing certificate found. Starting normal flow..."
    DUMMY=0
fi

echo "### Starting Nginx..."
docker compose -f docker-compose.prod.yml up -d --build nginx

if [ "$DUMMY" = "1" ]; then
    echo "### Requesting real Let's Encrypt certificate..."
    # Удаляем временный сертификат
    rm -rf "$CERT_DIR"

    # Запускаем получение боевого сертификата через standalone / webroot
    docker compose -f docker-compose.prod.yml run --rm --entrypoint "\
        certbot certonly --webroot -w /var/www/certbot \
        --email $CERTBOT_EMAIL \
        -d $DOMAIN_NAME \
        -d www.$DOMAIN_NAME \
        --rsa-key-size 4096 \
        --agree-tos \
        --non-interactive \
        --force-renewal" certbot

    echo "### Reloading Nginx with real certificate..."
    docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
fi

echo "### SSL setup finished successfully!"
