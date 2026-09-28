#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Uso: $0 /backup/finance/daily/finance-AAAA.dump" >&2
  exit 1
fi

BACKUP_FILE=$1
TEST_DATABASE=finance_restore_test
test -r "$BACKUP_FILE"
docker exec -i postgres pg_restore --list < "$BACKUP_FILE" >/dev/null

cleanup() {
  docker exec postgres sh -c \
    'dropdb -U "$POSTGRES_USER" --if-exists finance_restore_test' >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

cleanup
docker exec postgres sh -c \
  'createdb -U "$POSTGRES_USER" -O finance_app finance_restore_test'
docker exec -i postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d finance_restore_test --no-owner --no-acl' \
  < "$BACKUP_FILE"
docker exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d finance_restore_test -v ON_ERROR_STOP=1 -Atc \
  "SELECT CASE WHEN to_regclass('"'"'public.transactions'"'"') IS NOT NULL THEN '"'"'ok'"'"' ELSE '"'"'missing'"'"' END"' \
  | grep -qx ok

echo "Restauração validada no banco temporário finance_restore_test."
