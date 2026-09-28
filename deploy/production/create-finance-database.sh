#!/bin/sh
set -eu

ENV_FILE=${1:-/opt/homelab/finance/finance.env}
test -f "$ENV_FILE"

set -a
# O arquivo é criado pelo administrador, pertence a root e tem modo 600.
. "$ENV_FILE"
set +a

: "${FINANCE_DB_PASSWORD:?FINANCE_DB_PASSWORD ausente}"
case "$FINANCE_DB_PASSWORD" in
  *[!0-9a-fA-F]*|'')
    echo "FINANCE_DB_PASSWORD deve ser uma senha hexadecimal gerada." >&2
    exit 1
    ;;
esac

docker exec -i -e FINANCE_ROLE_PASSWORD="$FINANCE_DB_PASSWORD" postgres sh <<'CONTAINER_SCRIPT'
set -eu
psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -v role_password="$FINANCE_ROLE_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE finance_app LOGIN PASSWORD %L', :'role_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'finance_app') \gexec
SELECT format('ALTER ROLE finance_app LOGIN PASSWORD %L', :'role_password') \gexec
SELECT 'CREATE DATABASE finance OWNER finance_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'finance') \gexec
REVOKE ALL ON DATABASE finance FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE finance TO finance_app;
SQL
CONTAINER_SCRIPT

echo "Banco finance e usuário finance_app preparados sem expor a senha."
