#!/bin/sh
set -eu
mkdir -p /var/lib/postgresql/tls
cp /run/secrets/server.crt /var/lib/postgresql/tls/server.crt
cp /run/secrets/server.key /var/lib/postgresql/tls/server.key
chown -R postgres:postgres /var/lib/postgresql/tls
chmod 600 /var/lib/postgresql/tls/server.key
exec /usr/local/bin/docker-entrypoint.sh "$@"
