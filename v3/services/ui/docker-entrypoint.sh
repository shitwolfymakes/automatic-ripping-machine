#!/usr/bin/env sh
# UI-side entrypoint. Merges the mounted internal CA into the container's
# trust store so nginx's proxy_ssl_verify accepts arm-backend's leaf, then
# hands off to nginx (which manages its own master/worker privilege drop).
# We deliberately don't run gosu here — nginx needs root to bind 443 first.
set -eu

if [ -f /etc/ssl/arm/arm-ca.crt ]; then
    cp /etc/ssl/arm/arm-ca.crt /usr/local/share/ca-certificates/arm-ca.crt
    update-ca-certificates >/dev/null 2>&1 || true
fi

exec "$@"
